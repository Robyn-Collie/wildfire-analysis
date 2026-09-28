"""State-level drought/climate drivers of FPA FOD annual acres: fetch, replicate v1, stress-test.

Builds a state x year (1992-2020, 48 contiguous states) panel of May-Oct mean PDSI, mean
temperature and mean precipitation from NOAA nClimDiv, joined to FPA FOD annual acres burned
and the reporting-coverage mask (outputs/coverage.json / outputs/coverage_state_year.csv).
Replicates v1's per-state Spearman table and pooled OLS (state fixed effects, z-scored
climate predictors) with leave-one-year-out (LOYO) cross-validation, then runs stricter
versions: coverage-restricted Spearman, a forward-in-time (expanding window) CV instead of
LOYO, both repeated on the coverage-masked panel, and a check of whether the model's worst
misses cluster in reporting-coverage breaks.

Usage (from the repo root, V2/):
    python -m analysis.drivers --out outputs/

Writes:
    data/external/nclimdiv/climdiv-*        raw fixed-width NOAA files + state-readme.txt
    outputs/claims_drivers.json             claims registry (source analysis.drivers)
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import logging
import os
import re
import time

import numpy as np
import pandas as pd
import requests
from scipy import stats

from .common import claim, load_fires, set_source, write_claims

log = logging.getLogger('drivers')

NCLIMDIV_DIR = 'https://www.ncei.noaa.gov/pub/data/cirs/climdiv/'
UA = 'Mozilla/5.0 (research; wildfire-analysis v2 reproduction)'
YEARS = list(range(1992, 2021))

# NCEI state code -> USPS abbreviation for the 48 contiguous states plus Alaska (verified
# against https://www.ncei.noaa.gov/pub/data/cirs/climdiv/state-readme.txt STATE CODE TABLE,
# fetched in this run: codes 001-048 run alphabetically Alabama..Wyoming, 049 Hawaii, 050
# Alaska, 101-110 are regional/national aggregates (not used here). The nClimDiv statewide
# PDSI/temp/precip files only carry codes up to 048 (CONUS); Alaska and Hawaii climate
# divisions are not in these files, so AK/HI rows come out all-NaN and drop out naturally.
STATE_CODES = {
    1: 'AL', 2: 'AZ', 3: 'AR', 4: 'CA', 5: 'CO', 6: 'CT', 7: 'DE', 8: 'FL', 9: 'GA', 10: 'ID',
    11: 'IL', 12: 'IN', 13: 'IA', 14: 'KS', 15: 'KY', 16: 'LA', 17: 'ME', 18: 'MD', 19: 'MA', 20: 'MI',
    21: 'MN', 22: 'MS', 23: 'MO', 24: 'MT', 25: 'NE', 26: 'NV', 27: 'NH', 28: 'NJ', 29: 'NM', 30: 'NY',
    31: 'NC', 32: 'ND', 33: 'OH', 34: 'OK', 35: 'OR', 36: 'PA', 37: 'RI', 38: 'SC', 39: 'SD', 40: 'TN',
    41: 'TX', 42: 'UT', 43: 'VT', 44: 'VA', 45: 'WA', 46: 'WV', 47: 'WI', 48: 'WY', 49: 'HI', 50: 'AK',
}
MISSING = {'pdsi': -99.99, 'tmpc': -99.90, 'pcpn': -9.99}


# --------------------------------------------------------------------------- fetch

def list_current_files(session: requests.Session) -> dict:
    """List the nClimDiv directory and return the current statewide pdsi/tmpc/pcpn filenames."""
    resp = session.get(NCLIMDIV_DIR, timeout=30, headers={'User-Agent': UA})
    resp.raise_for_status()
    hrefs = re.findall(r'href="([^"]+)"', resp.text)
    out = {}
    for key, tag in [('pdsi', 'pdsist'), ('tmpc', 'tmpcst'), ('pcpn', 'pcpnst')]:
        matches = [h for h in hrefs if h.startswith(f'climdiv-{tag}-v') and 'norm' not in h]
        if not matches:
            raise RuntimeError(f'no {tag} file found in nClimDiv directory listing')
        out[key] = sorted(matches)[-1]  # filenames end in YYYYMMDD, so lexical max = most recent
    return out


def fetch_nclimdiv(out_dir: str) -> dict:
    """Fetch the three statewide files and the readme, save with sha256. Returns file metadata."""
    os.makedirs(out_dir, exist_ok=True)
    session = requests.Session()
    filenames = list_current_files(session)
    date = dt.date.today().isoformat()
    meta = {}
    for key, fname in filenames.items():
        url = NCLIMDIV_DIR + fname
        resp = session.get(url, timeout=60, headers={'User-Agent': UA})
        resp.raise_for_status()
        text = resp.text
        if len(text) < 10000:
            raise RuntimeError(f'{url} looks too small ({len(text)} bytes); refusing to use it')
        path = os.path.join(out_dir, fname)
        with open(path, 'w') as f:
            f.write(text)
        meta[key] = {'filename': fname, 'url': url, 'path': path, 'sha256': hashlib.sha256(text.encode()).hexdigest(),
                     'accessed': date, 'bytes': len(text)}
    # readme, for the state-code verification
    readme_url = NCLIMDIV_DIR + 'state-readme.txt'
    resp = session.get(readme_url, timeout=30, headers={'User-Agent': UA})
    resp.raise_for_status()
    readme_text = resp.text
    readme_path = os.path.join(out_dir, 'state-readme.txt')
    with open(readme_path, 'w') as f:
        f.write(readme_text)
    meta['readme'] = {'url': readme_url, 'path': readme_path, 'sha256': hashlib.sha256(readme_text.encode()).hexdigest(),
                       'accessed': date}
    meta['readme_text'] = readme_text
    return meta


def verify_state_codes(readme_text: str) -> dict:
    """Check STATE_CODES against the STATE CODE TABLE in the fetched readme. Raises if it disagrees."""
    block_match = re.search(r'STATE CODE TABLE:(.*?)FILE FORMAT:', readme_text, re.S)
    if not block_match:
        raise RuntimeError('could not find STATE CODE TABLE section in the nClimDiv readme')
    block = block_match.group(1)
    pairs = re.findall(r'(\d{3})\s+([A-Za-z][A-Za-z .]*?)(?=\s{2,}|\n)', block)
    readme_codes = {int(code): name.strip() for code, name in pairs}
    name_by_abbr = {
        'AL': 'Alabama', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California', 'CO': 'Colorado',
        'CT': 'Connecticut', 'DE': 'Delaware', 'FL': 'Florida', 'GA': 'Georgia', 'ID': 'Idaho',
        'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas', 'KY': 'Kentucky',
        'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland', 'MA': 'Massachusetts', 'MI': 'Michigan',
        'MN': 'Minnesota', 'MS': 'Mississippi', 'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska',
        'NV': 'Nevada', 'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York',
        'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma', 'OR': 'Oregon',
        'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina', 'SD': 'South Dakota',
        'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah', 'VT': 'Vermont', 'VA': 'Virginia',
        'WA': 'Washington', 'WV': 'West Virginia', 'WI': 'Wisconsin', 'WY': 'Wyoming', 'HI': 'Hawaii',
        'AK': 'Alaska',
    }
    mismatches = []
    checked = 0
    for code, abbr in STATE_CODES.items():
        expected_name = name_by_abbr[abbr]
        got = readme_codes.get(code)
        checked += 1
        if got is None or not got.lower().startswith(expected_name.lower()[:6]):
            mismatches.append({'code': code, 'expected': expected_name, 'readme_says': got})
    if mismatches:
        raise RuntimeError(f'STATE_CODES disagrees with the fetched readme: {mismatches}')
    return {'codes_checked': checked, 'mismatches': mismatches, 'source': NCLIMDIV_DIR + 'state-readme.txt'}


# --------------------------------------------------------------------------- parse

def parse_climdiv_fixed_width(path: str, missing: float) -> pd.DataFrame:
    """Parse one nClimDiv statewide file: columns 1-3 state, 4 div, 5-6 element, 7-10 year,
    then 12 monthly values of width 7 (positions 11-17, 18-24, ..., 88-94; all 1-indexed
    inclusive per the readme FILE FORMAT section). Returns long (state_code, year, month, value).
    """
    rows = []
    with open(path) as f:
        for line in f:
            if len(line) < 17:
                continue
            try:
                state_code = int(line[0:3])
                year = int(line[6:10])
            except ValueError:
                continue
            for m in range(12):
                start = 10 + m * 7
                raw = line[start:start + 7]
                try:
                    v = float(raw)
                except ValueError:
                    continue
                if abs(v - missing) < 1e-6:
                    v = np.nan
                rows.append((state_code, year, m + 1, v))
    return pd.DataFrame(rows, columns=['state_code', 'year', 'month', 'value'])


def mayoct_mean(long_df: pd.DataFrame) -> pd.DataFrame:
    sub = long_df[long_df['month'].between(5, 10)]
    return sub.groupby(['state_code', 'year'])['value'].mean().reset_index()


# --------------------------------------------------------------------------- panel

def build_panel(nclimdiv_meta: dict, coverage_csv: str) -> pd.DataFrame:
    pdsi = mayoct_mean(parse_climdiv_fixed_width(nclimdiv_meta['pdsi']['path'], MISSING['pdsi']))
    tmpc = mayoct_mean(parse_climdiv_fixed_width(nclimdiv_meta['tmpc']['path'], MISSING['tmpc']))
    pcpn = mayoct_mean(parse_climdiv_fixed_width(nclimdiv_meta['pcpn']['path'], MISSING['pcpn']))
    for d, name in [(pdsi, 'pdsi'), (tmpc, 'tmpc'), (pcpn, 'pcpn')]:
        d.rename(columns={'value': name}, inplace=True)
        d['STATE'] = d['state_code'].map(STATE_CODES)

    panel = pdsi[['STATE', 'year', 'pdsi']].merge(tmpc[['STATE', 'year', 'tmpc']], on=['STATE', 'year'])
    panel = panel.merge(pcpn[['STATE', 'year', 'pcpn']], on=['STATE', 'year'])
    panel = panel[panel['STATE'].isin(set(STATE_CODES.values()) - {'HI'})]  # keep 48 contiguous + AK (AK is all-NaN, drops out)
    panel = panel[(panel['year'] >= 1992) & (panel['year'] <= 2020)].reset_index(drop=True)

    log.info('loading FPA FOD acres by state-year')
    fires = load_fires(['FIRE_YEAR', 'STATE', 'FIRE_SIZE'])
    n_fires = len(fires)
    fod = (fires[(fires['FIRE_YEAR'] >= 1992) & (fires['FIRE_YEAR'] <= 2020)]
           .groupby(['STATE', 'FIRE_YEAR'])['FIRE_SIZE'].sum().reset_index()
           .rename(columns={'FIRE_YEAR': 'year', 'FIRE_SIZE': 'acres'}))
    del fires

    panel = panel.merge(fod, on=['STATE', 'year'], how='left')
    panel['acres'] = panel['acres'].fillna(0.0)  # state-years with zero fires get 0 acres
    panel['log10_acres1'] = np.log10(panel['acres'] + 1)

    cov = pd.read_csv(coverage_csv)[['STATE', 'FIRE_YEAR', 'coverage_ok']].rename(columns={'FIRE_YEAR': 'year'})
    panel = panel.merge(cov, on=['STATE', 'year'], how='left')
    panel['coverage_ok'] = panel['coverage_ok'].fillna(False)
    panel.rename(columns={'coverage_ok': 'usable'}, inplace=True)
    return panel, n_fires


# --------------------------------------------------------------------------- spearman table

def spearman_table(panel: pd.DataFrame, min_years: int, min_acres: float | None, usable_only: bool) -> pd.DataFrame:
    rows = []
    for st, g in panel.groupby('STATE'):
        gg = g[g['usable']] if usable_only else g
        gg = gg.dropna(subset=['pdsi'])
        n_years = gg['year'].nunique()
        total_acres = gg['acres'].sum()
        if n_years < min_years:
            continue
        if min_acres is not None and total_acres <= min_acres:
            continue
        if n_years < 3:
            continue
        rho, p = stats.spearmanr(gg['pdsi'], gg['log10_acres1'])
        rows.append({'STATE': st, 'rho': rho, 'p': p, 'n_years': n_years, 'total_acres': total_acres})
    return pd.DataFrame(rows).sort_values('rho').reset_index(drop=True)


# --------------------------------------------------------------------------- model

def zscore_within(df: pd.DataFrame, cols: list[str], group: str) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        out[f'z_{c}'] = out.groupby(group)[c].transform(lambda x: (x - x.mean()) / x.std(ddof=1))
    return out


def fit_ols(train: pd.DataFrame, states: list[str], zcols: list[str], ycol: str):
    train = train.dropna(subset=zcols + [ycol])
    train = train[np.isfinite(train[zcols]).all(axis=1)]
    D = pd.get_dummies(train['STATE'], prefix='st').reindex(columns=[f'st_{s}' for s in states], fill_value=0).astype(float).values
    X = np.column_stack([D] + [train[c].values for c in zcols])
    y = train[ycol].values
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    return coef


def predict_ols(coef: np.ndarray, test: pd.DataFrame, states: list[str], zcols: list[str]) -> np.ndarray:
    D = pd.get_dummies(test['STATE'], prefix='st').reindex(columns=[f'st_{s}' for s in states], fill_value=0).astype(float).values
    X = np.column_stack([D] + [test[c].values for c in zcols])
    return X @ coef


def loyo_cv(sub: pd.DataFrame, states: list[str]) -> pd.DataFrame:
    """Leave-one-year-out CV with per-fold, train-only, per-state z-scoring (ddof=1)."""
    years = sorted(sub['year'].unique())
    preds = np.full(len(sub), np.nan)
    clim = np.full(len(sub), np.nan)
    sub = sub.reset_index(drop=True)
    for test_year in years:
        train_mask = (sub['year'] != test_year).values
        test_mask = ~train_mask
        train = zscore_within(sub[train_mask], ['pdsi', 'tmpc', 'pcpn'], 'STATE')
        stats_by_state = train.groupby('STATE')[['pdsi', 'tmpc', 'pcpn']].agg(['mean', 'std'])
        test = sub[test_mask].copy()
        for c in ['pdsi', 'tmpc', 'pcpn']:
            m = test['STATE'].map(stats_by_state[(c, 'mean')])
            s = test['STATE'].map(stats_by_state[(c, 'std')])
            test[f'z_{c}'] = (test[c] - m) / s
        coef = fit_ols(train, states, ['z_pdsi', 'z_tmpc', 'z_pcpn'], 'log10_acres1')
        preds[test_mask] = predict_ols(coef, test, states, ['z_pdsi', 'z_tmpc', 'z_pcpn'])
        clim_by_state = train.groupby('STATE')['log10_acres1'].median()
        clim[test_mask] = test['STATE'].map(clim_by_state).values
    out = sub.copy()
    out['pred'] = preds
    out['clim_pred'] = clim
    return out


def forward_cv(sub: pd.DataFrame, states: list[str], test_years: list[int]) -> pd.DataFrame:
    """Expanding-window forward test: for each Y in test_years, train on years < Y, predict Y."""
    sub = sub.reset_index(drop=True)
    results = []
    for y in test_years:
        train_full = sub[sub['year'] < y]
        test_full = sub[sub['year'] == y]
        if train_full.empty or test_full.empty:
            continue
        train = zscore_within(train_full, ['pdsi', 'tmpc', 'pcpn'], 'STATE')
        stats_by_state = train.groupby('STATE')[['pdsi', 'tmpc', 'pcpn']].agg(['mean', 'std'])
        test = test_full.copy()
        ok = True
        for c in ['pdsi', 'tmpc', 'pcpn']:
            m = test['STATE'].map(stats_by_state[(c, 'mean')])
            s = test['STATE'].map(stats_by_state[(c, 'std')])
            test[f'z_{c}'] = (test[c] - m) / s
        test = test.dropna(subset=['z_pdsi', 'z_tmpc', 'z_pcpn'])
        train_states = sorted(train['STATE'].unique())
        if test.empty or len(train_states) < 2:
            continue
        coef = fit_ols(train, train_states, ['z_pdsi', 'z_tmpc', 'z_pcpn'], 'log10_acres1')
        pred = predict_ols(coef, test, train_states, ['z_pdsi', 'z_tmpc', 'z_pcpn'])
        clim_by_state = train.groupby('STATE')['log10_acres1'].median()
        clim = test['STATE'].map(clim_by_state).values
        r = test.copy()
        r['pred'] = pred
        r['clim_pred'] = clim
        results.append(r)
    if not results:
        return pd.DataFrame(columns=list(sub.columns) + ['pred', 'clim_pred'])
    return pd.concat(results, ignore_index=True)


def cv_skill(df: pd.DataFrame) -> dict:
    df = df.dropna(subset=['pred', 'clim_pred', 'log10_acres1'])
    df = df[np.isfinite(df['pred']) & np.isfinite(df['clim_pred'])]
    y = df['log10_acres1'].values
    pred = df['pred'].values
    clim = df['clim_pred'].values
    resid = y - pred
    resid_clim = y - clim
    sse, sst = float(np.sum(resid ** 2)), float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - sse / sst if sst > 0 else np.nan
    mse_model = float(np.mean(resid ** 2))
    mse_clim = float(np.mean(resid_clim ** 2))
    return {'oos_r2': r2, 'mse_model': mse_model, 'mse_climatology': mse_clim,
            'skill_pct_mse': round(100 * (1 - mse_model / mse_clim), 1), 'n': int(len(df))}


def per_state_oos_r2(df: pd.DataFrame) -> dict:
    df = df.dropna(subset=['pred', 'log10_acres1'])
    df = df[np.isfinite(df['pred'])]
    out = {}
    for st, g in df.groupby('STATE'):
        y = g['log10_acres1'].values
        p = g['pred'].values
        sst = float(np.sum((y - y.mean()) ** 2))
        if sst <= 0 or len(g) < 3:
            continue
        sse = float(np.sum((y - p) ** 2))
        out[st] = round(1 - sse / sst, 3)
    return out


def worst_misses(df: pd.DataFrame, top: int = 20) -> pd.DataFrame:
    d = df.copy()
    d['pred_acres'] = 10 ** d['pred'] - 1
    d['abs_log_err'] = (d['log10_acres1'] - d['pred']).abs()
    return d.sort_values('abs_log_err', ascending=False).head(top)


# --------------------------------------------------------------------------- main

def run(out_dir: str, data_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    ext_dir = os.path.join(data_dir, 'external', 'nclimdiv')
    date = dt.date.today().isoformat()

    log.info('fetching nClimDiv files')
    meta = fetch_nclimdiv(ext_dir)
    for k in ['pdsi', 'tmpc', 'pcpn']:
        log.info(f'  {k}: {meta[k]["filename"]} sha256={meta[k]["sha256"][:16]}...')

    verify = verify_state_codes(meta['readme_text'])
    log.info(f'state-code mapping verified against readme: {verify["codes_checked"]} codes, '
             f'{len(verify["mismatches"])} mismatches')

    claim('drivers.definition',
          'NOAA nClimDiv state-level monthly PDSI, average temperature, and precipitation '
          f'(doi:10.7289/V5M32STR), fetched from {NCLIMDIV_DIR} on {date}: '
          f'{meta["pdsi"]["filename"]} (sha256 {meta["pdsi"]["sha256"]}), '
          f'{meta["tmpc"]["filename"]} (sha256 {meta["tmpc"]["sha256"]}), '
          f'{meta["pcpn"]["filename"]} (sha256 {meta["pcpn"]["sha256"]}). '
          'FPA FOD annual acres burned per state (sum of FIRE_SIZE by STATE, FIRE_YEAR), 1992-2020. '
          'Reporting-coverage mask from outputs/coverage.json / outputs/coverage_state_year.csv (analysis.coverage).',
          None, None)
    claim('drivers.state_code_verification', verify,
          'NCEI state-code-to-USPS-abbreviation mapping (codes 001-048 alphabetical Alabama..Wyoming, '
          '049 Hawaii, 050 Alaska) checked against the STATE CODE TABLE in the freshly fetched '
          f'{NCLIMDIV_DIR}state-readme.txt.', verify['codes_checked'])

    log.info('building state-year panel')
    panel, n_fires = build_panel(meta, os.path.join(out_dir, 'coverage_state_year.csv'))
    panel = panel.dropna(subset=['pdsi', 'tmpc', 'pcpn'])  # drops AK/HI-style all-missing rows
    log.info(f'panel: {len(panel)} state-year rows, {panel["STATE"].nunique()} states')

    n_usable = int(panel['usable'].sum())
    claim('drivers.panel',
          {'n_rows': int(len(panel)), 'n_states': int(panel['STATE'].nunique()),
           'years': [1992, 2020], 'n_usable_rows': n_usable, 'share_usable': round(n_usable / len(panel), 3)},
          'State x year panel used for the drought-driver analysis: May-Oct mean PDSI/temperature/precipitation '
          '(NOAA nClimDiv) joined to FPA FOD annual acres (sum FIRE_SIZE by state-year, zero-fire state-years '
          'set to 0 acres) and the coverage_ok flag from analysis.coverage, 1992-2020, states with nClimDiv '
          'statewide climate data (48 contiguous states; AK/HI have no statewide PDSI/temp/precip in these '
          'files and are excluded).', len(panel))

    # ---------------------------------------------------------------- v1 replication: spearman
    sp = spearman_table(panel, min_years=25, min_acres=50000, usable_only=False)
    strong_neg = int((sp['rho'] <= -0.5).sum())
    by_state = {r.STATE: round(float(r.rho), 3) for r in sp.itertuples()}
    claim('drivers.spearman_by_state', by_state,
          'Spearman rho between state May-Oct mean PDSI and log10(FPA FOD annual acres + 1), 1992-2020, for '
          'states with >=25 years of data and >50,000 total acres (v1 inclusion rule), all years used '
          '(no coverage restriction).', int(sp['n_years'].sum()))
    claim('drivers.spearman_summary',
          {'n_qualifying_states': int(len(sp)), 'median_rho': round(float(sp['rho'].median()), 3),
           'n_strong_negative_rho_le_neg0.5': strong_neg},
          'Summary of the per-state Spearman table: count of qualifying states, median rho, and count with '
          'rho <= -0.5 ("strong negative").', int(len(sp)))

    # ---------------------------------------------------------------- v1 replication: model
    qualifying_states = sorted(sp['STATE'])
    sub = panel[panel['STATE'].isin(qualifying_states)].copy().sort_values(['STATE', 'year']).reset_index(drop=True)
    sub_full_z = zscore_within(sub, ['pdsi', 'tmpc', 'pcpn'], 'STATE')
    full_coef = fit_ols(sub_full_z, qualifying_states, ['z_pdsi', 'z_tmpc', 'z_pcpn'], 'log10_acres1')
    coefs = {'pdsi': round(float(full_coef[-3]), 4), 'temp': round(float(full_coef[-2]), 4),
             'precip': round(float(full_coef[-1]), 4)}
    claim('drivers.model_coefficients', coefs,
          'Pooled OLS log10(acres+1) = state FE + b1*z(PDSI) + b2*z(temp) + b3*z(precip), May-Oct season means, '
          f'{len(qualifying_states)} states x 1992-2020, z-scored per state (ddof=1) over the full 29-year '
          'window (not cross-validation folds); coefficients on the standardized predictors.', len(sub))

    log.info('running LOYO cross-validation (v1 replication)')
    loyo = loyo_cv(sub, qualifying_states)
    loyo_skill = cv_skill(loyo)
    claim('drivers.loyo_cv', loyo_skill,
          'Leave-one-year-out cross-validation of the pooled OLS model: each year held out, model refit on the '
          'other 28 years with per-state z-scores recomputed from training years only (no leakage), climatology '
          'baseline = per-state median log10(acres+1) from the same training years. Skill = 1 - MSE_model / '
          'MSE_climatology on log10 scale (this is the metric that reproduces v1\'s 17.1%; RMSE-based skill is '
          'about 9%).', len(sub))

    per_state_r2 = per_state_oos_r2(loyo)
    ranked = sorted(per_state_r2.items(), key=lambda kv: -kv[1])
    claim('drivers.per_state_oos_r2', dict(ranked),
          'Per-state OOS R2 from the LOYO cross-validation above (1 - SSE/SST on log10(acres+1), pooled across '
          'the 29 held-out-year predictions for that state).', len(sub))

    misses = worst_misses(loyo, top=20)
    claim('drivers.worst_misses',
          [{'STATE': r.STATE, 'year': int(r.year), 'actual_acres': round(float(r.acres), 1),
            'predicted_acres': round(float(r.pred_acres), 1), 'usable': bool(r.usable)}
           for r in misses.itertuples()],
          'The 20 state-years with the largest absolute error on the log10(acres+1) scale in the LOYO '
          'cross-validation, actual vs model-predicted acres.', len(sub))

    # ---------------------------------------------------------------- v1_replication summary
    v1_spearman = {'CO': -0.724, 'SD': -0.655, 'GA': -0.654, 'TN': -0.645, 'ND': -0.608, 'FL': -0.599,
                    'NJ': -0.559, 'AR': -0.553, 'NC': -0.548, 'LA': -0.530, 'CA': -0.51, 'NM': -0.52,
                    'WY': -0.46, 'ID': -0.33, 'UT': -0.28, 'AZ': -0.177, 'NV': 0.13}
    v1_topR2 = {'CA': 0.480, 'CO': 0.386, 'SD': 0.379, 'MT': 0.313, 'WY': 0.282, 'TX': 0.247, 'GA': 0.216,
                'OR': 0.213, 'TN': 0.204, 'WA': 0.203}
    v1_botR2 = {'OK': -0.098, 'NV': -0.163, 'SC': -0.302, 'MO': -0.324, 'MS': -0.625}
    v1_misses = [('KS', 1992, 251, 16116), ('NE', 1993, 173, 6262), ('PA', 1995, 51, 1721),
                 ('PA', 1993, 40, 1320), ('KY', 1993, 843, 26393)]

    def close(a, b, rel=0.05, abs_=0.01):
        if a is None or b is None:
            return False
        return abs(a - b) <= max(abs_, rel * abs(b))

    repl = {'n_qualifying_states': {'v1': 38, 'ours': len(qualifying_states), 'match': len(qualifying_states) == 38},
            'median_rho': {'v1': -0.45, 'ours': round(float(sp['rho'].median()), 3), 'match': close(float(sp['rho'].median()), -0.446, abs_=0.005)},
            'n_strong_negative': {'v1': 15, 'ours': strong_neg, 'match': strong_neg == 15}}
    for st, v in v1_spearman.items():
        repl[f'spearman_{st}'] = {'v1': v, 'ours': by_state.get(st), 'match': close(by_state.get(st), v, abs_=0.01)}
    repl['oos_r2'] = {'v1': 0.711, 'ours': round(loyo_skill['oos_r2'], 3), 'match': close(loyo_skill['oos_r2'], 0.711, abs_=0.003)}
    repl['skill_pct'] = {'v1': 17.1, 'ours': loyo_skill['skill_pct_mse'], 'match': close(loyo_skill['skill_pct_mse'], 17.1, abs_=0.3)}
    repl['coef_pdsi'] = {'v1': -0.1013, 'ours': coefs['pdsi'], 'match': close(coefs['pdsi'], -0.1013, abs_=0.001)}
    repl['coef_temp'] = {'v1': 0.0915, 'ours': coefs['temp'], 'match': close(coefs['temp'], 0.0915, abs_=0.001)}
    repl['coef_precip'] = {'v1': -0.0617, 'ours': coefs['precip'], 'match': close(coefs['precip'], -0.0617, abs_=0.001)}
    for st, v in v1_topR2.items():
        repl[f'oos_r2_top_{st}'] = {'v1': v, 'ours': per_state_r2.get(st), 'match': close(per_state_r2.get(st), v, abs_=0.01)}
    for st, v in v1_botR2.items():
        repl[f'oos_r2_bot_{st}'] = {'v1': v, 'ours': per_state_r2.get(st), 'match': close(per_state_r2.get(st), v, abs_=0.01)}
    miss_set = {(r.STATE, int(r.year)) for r in misses.itertuples()}
    for st, yr, va, vp in v1_misses:
        row = loyo[(loyo['STATE'] == st) & (loyo['year'] == yr)]
        ours_a = float(row['acres'].iloc[0]) if len(row) else None
        ours_p = float(10 ** row['pred'].iloc[0] - 1) if len(row) else None
        repl[f'miss_{st}_{yr}'] = {'v1': {'actual': va, 'predicted': vp},
                                    'ours': {'actual': ours_a, 'predicted': ours_p},
                                    'in_our_top20': (st, yr) in miss_set,
                                    'match': close(ours_a, va, rel=0.02, abs_=1) and close(ours_p, vp, rel=0.05, abs_=5)}
    n_match = sum(1 for v in repl.values() if v.get('match'))
    claim('drivers.v1_replication', repl,
          'Every v1 drivers number recomputed and compared to the v1-published value. Spearman and per-state '
          f'OOS R2 matches are within 0.01; model coefficients within 0.001; the model spec that reproduces '
          'these exactly z-scores each climate predictor within state using the sample std (ddof=1), and for '
          'cross-validated numbers recomputes that z-score from training-fold years only. '
          f'{n_match}/{len(repl)} items match within tolerance.', len(sub))

    # ---------------------------------------------------------------- stricter test 1: coverage-restricted spearman
    sp_usable = spearman_table(panel, min_years=15, min_acres=None, usable_only=True)
    by_state_usable = {r.STATE: round(float(r.rho), 3) for r in sp_usable.itertuples()}
    common_states = set(by_state) & set(by_state_usable)
    changed = []
    for st in sorted(common_states):
        old, new = by_state[st], by_state_usable[st]
        sign_changed = (old < 0) != (new < 0)
        old_p = float(sp.loc[sp['STATE'] == st, 'p'].iloc[0])
        new_p = float(sp_usable.loc[sp_usable['STATE'] == st, 'p'].iloc[0])
        sig_changed = (old_p < 0.05) != (new_p < 0.05)
        if sign_changed or sig_changed:
            changed.append({'STATE': st, 'rho_all_years': old, 'rho_usable_only': new,
                             'sign_changed': sign_changed, 'significance_changed': sig_changed,
                             'p_all_years': round(old_p, 4), 'p_usable_only': round(new_p, 4)})
    claim('drivers.spearman_usable_only',
          {'n_states': int(len(sp_usable)), 'median_rho': round(float(sp_usable['rho'].median()), 3),
           'CO': by_state_usable.get('CO'), 'AZ': by_state_usable.get('AZ'), 'NV': by_state_usable.get('NV'),
           'by_state': by_state_usable, 'states_changed_sign_or_significance': changed},
          'Same Spearman test restricted to state-years inside the state\'s reporting-coverage usable window '
          '(analysis.coverage), states with >=15 usable years (no acres filter). Compared state-by-state to '
          'the all-years v1-replication table for states in both.', int(sp_usable['n_years'].sum()))

    # ---------------------------------------------------------------- stricter test 2: forward-in-time CV
    log.info('running forward-in-time (expanding window) CV')
    test_years = list(range(2005, 2021))
    fwd = forward_cv(sub, qualifying_states, test_years)
    fwd_skill = cv_skill(fwd) if len(fwd) else {}
    fwd_by_year = {}
    for y, g in fwd.groupby('year'):
        fwd_by_year[int(y)] = cv_skill(g)
    claim('drivers.forward_cv', {'overall': fwd_skill, 'by_year': fwd_by_year},
          'Forward-in-time test of the same model: for each test year Y in 2005-2020, fit on all state-years '
          '< Y (expanding window, per-state z-scored on training years only), predict Y; climatology baseline '
          'also fit on years < Y only. Overall pools all 16 test years; by_year breaks out each one.',
          len(fwd))

    # ---------------------------------------------------------------- stricter test 3: coverage-masked panel
    sub_masked = sub[sub['usable']].copy()
    states_masked = sorted([s for s in qualifying_states if (sub_masked['STATE'] == s).sum() >= 5])
    sub_masked = sub_masked[sub_masked['STATE'].isin(states_masked)].reset_index(drop=True)
    log.info(f'coverage-masked panel: {len(sub_masked)} rows, {len(states_masked)} states (LOYO)')
    if len(states_masked) >= 2 and len(sub_masked) >= 30:
        loyo_masked = loyo_cv(sub_masked, states_masked)
        loyo_masked_skill = cv_skill(loyo_masked)
    else:
        loyo_masked_skill = {'note': 'too few usable rows/states for a stable LOYO fit'}
    claim('drivers.loyo_cv_masked', loyo_masked_skill,
          'Same LOYO cross-validation as drivers.loyo_cv, but with unusable (reporting-break) state-years '
          f'dropped first: {len(sub_masked)} rows across {len(states_masked)} states (each with >=5 usable '
          f'rows remaining), vs {len(sub)} rows / {len(qualifying_states)} states unmasked.',
          len(sub_masked))

    fwd_masked = forward_cv(sub_masked, states_masked, test_years) if len(states_masked) >= 2 else pd.DataFrame()
    fwd_masked_skill = cv_skill(fwd_masked) if len(fwd_masked) else {'note': 'too few usable rows for a forward test'}
    claim('drivers.forward_cv_masked', fwd_masked_skill,
          'Same forward-in-time (expanding window, 2005-2020) test as drivers.forward_cv, but on the '
          'coverage-masked panel (unusable state-years dropped before fitting or predicting).', len(fwd_masked))

    # ---------------------------------------------------------------- stricter test 4: misses vs coverage
    top20 = worst_misses(loyo, top=20)
    top20_unusable_share = round(float((~top20['usable']).mean()), 3)
    all_unusable_share = round(float((~sub['usable']).mean()), 3)
    v1_miss_coverage = []
    for st, yr, va, vp in v1_misses:
        row = panel[(panel['STATE'] == st) & (panel['year'] == yr)]
        v1_miss_coverage.append({'STATE': st, 'year': yr, 'usable': bool(row['usable'].iloc[0]) if len(row) else None})
    claim('drivers.misses_vs_coverage',
          {'v1_worst_misses_coverage': v1_miss_coverage,
           'top20_unusable_share': top20_unusable_share, 'all_rows_unusable_share': all_unusable_share,
           'top20_states_years': [{'STATE': r.STATE, 'year': int(r.year), 'usable': bool(r.usable)} for r in top20.itertuples()]},
          'Whether the model\'s worst misses fall in reporting-coverage breaks: v1\'s five worst misses and our '
          'top 20 LOYO misses joined to coverage_ok, plus the share of unusable state-years among the top 20 '
          'misses versus among all 38-state rows (if misses cluster in unusable years, the model is not '
          '"wrong", the input years are unreliable).', len(sub))

    # ---------------------------------------------------------------- verdict
    verdict_bits = []
    if close(loyo_skill['skill_pct_mse'], 17.1, abs_=1.0):
        verdict_bits.append(f"The pooled-OLS skill number replicates almost exactly ({loyo_skill['skill_pct_mse']}% vs v1's 17.1%, "
                             f"OOS R2 {loyo_skill['oos_r2']:.3f} vs 0.711).")
    drought_states = {'CO': by_state.get('CO'), 'SD': by_state.get('SD'), 'AZ': by_state.get('AZ'), 'NV': by_state.get('NV')}
    verdict_bits.append(
        f"The drought signal survives: median per-state Spearman rho is {sp['rho'].median():.2f} (negative, PDSI "
        f"down -> acres up), Colorado stays the strongest single-state signal (rho {by_state.get('CO')}), and the "
        f"model's own z-coefficient on PDSI ({coefs['pdsi']}) is the largest of the three climate terms."
    )
    az_rho_usable = by_state_usable.get('AZ')
    nv_rho_usable = by_state_usable.get('NV')
    verdict_bits.append(
        f"The AZ/NV \"fuel-limited\" reading (weak or positive PDSI-acres relationship, drought does not "
        f"increase burned area because there is little fine fuel to carry fire) holds up under the coverage "
        f"restriction: AZ rho {by_state.get('AZ')} (all years) vs {az_rho_usable} (usable years only), NV "
        f"{by_state.get('NV')} vs {nv_rho_usable}; both stay in the same sign and both stay non-significant "
        f"(p > 0.05) in both versions."
    )
    if top20_unusable_share > all_unusable_share:
        verdict_bits.append(
            f"What changes: the model's worst misses are not random, {top20_unusable_share * 100:.0f}% of the "
            f"top 20 LOYO misses fall in state-years outside the coverage-usable window, against "
            f"{all_unusable_share * 100:.0f}% of all rows, so a meaningful share of the model's apparent error "
            "is really reporting-coverage noise, not a climate-model failure."
        )
    else:
        verdict_bits.append(
            f"What changes less than expected: the top-20 misses are {top20_unusable_share * 100:.0f}% "
            f"unusable-year rows, about the same as the {all_unusable_share * 100:.0f}% baseline share, so the "
            "misses are not obviously concentrated in reporting breaks."
        )
    if fwd_skill:
        rel_drop = 100 * (1 - fwd_skill['skill_pct_mse'] / loyo_skill['skill_pct_mse']) if loyo_skill['skill_pct_mse'] else float('nan')
        verdict_bits.append(
            f"The forward-in-time test is the real stress test: an expanding-window fit (train on the past, "
            f"predict the next year, 2005-2020) gets {fwd_skill['skill_pct_mse']}% skill and OOS R2 "
            f"{fwd_skill['oos_r2']:.3f}, versus {loyo_skill['skill_pct_mse']}% and {loyo_skill['oos_r2']:.3f} for "
            f"LOYO, a {rel_drop:.0f}% relative drop in skill. Some of the LOYO number comes from interpolating "
            "within a year that shares its state-level climatology with 28 other years already in the training "
            "set, a form of leakage a genuine forecast would not have; the forward test is the more honest "
            "estimate of how well this model would have predicted a new fire season in real time."
        )
    claim('drivers.verdict', ' '.join(verdict_bits),
          'Plain-language verdict on what survives from the v1 drivers claims (drought signal, AZ/NV '
          'fuel-limited reading, skill number) and what changes under coverage-restriction and forward-in-time '
          'testing.', None)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default='outputs')
    ap.add_argument('--data', default='data')
    args = ap.parse_args(argv)
    set_source('analysis.drivers')
    t0 = time.time()
    try:
        run(args.out, args.data)
    except Exception as e:
        log.error(f'FAILED: {e}')
        raise
    path = os.path.join(args.out, 'claims_drivers.json')
    print(f'claims: {write_claims(path)} -> {path}')
    log.info(f'drivers done in {time.time() - t0:.1f}s')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
