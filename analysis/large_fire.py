"""Large-fire model: P(final size >= 300 acres) at discovery, CONUS, 2010-2020.

CLI (from the repo root):
    python -m analysis.large_fire --stage {build,develop,final,all} --out outputs/

Stages
    build    load the sample, join data/attributes_2010_2020.parquet, build the feature frame,
             write the sample definition, feature list and null table to outputs/model/.
    develop  expanding-window temporal folds on 2010-2018 (train through 2014/15/16/17, test the
             next year): baselines, the G0..G6 ablation, the HGB tuning grid, GroupKFold(3) by
             1-degree cell, the calibration decision. Writes outputs/model/develop_*.json|csv and
             outputs/model/chosen_config.json. Never touches 2019-2020.
    final    retrain the chosen configuration on 2010-2018, evaluate ONCE on 2019-2020 (per year,
             per region, per state, bootstrap intervals, grouped permutation importance), save
             models (joblib), figures and outputs/claims_model.json.

Protocol (docs/EXPERIMENTS.md, "Locked holdout"): holdout = FIRE_YEAR in {2019, 2020}; development
= 2010-2018 only; every table carries the base rate, the cell x month climatology, a logistic
regression on the same features and a geography-plus-season-only learner.

Labels: LARGE = FIRE_SIZE >= 300 acres (primary); MTBS = MTBS_ID present (secondary; MTBS maps
fires >= 1,000 acres in the West and >= 500 acres in the East, so it is an outcome independent
of the reported size).

Encoding of categoricals: pandas category dtype passed to HistGradientBoosting with
categorical_features='from_dtype' (native categorical splits). Columns with more than
MAX_CATEGORIES levels keep the most frequent levels and lump the rest into '__other__'.
Missing values stay missing (HGB routes them). Logistic regression gets the same columns via
median imputation with missing indicators, standard scaling and one-hot encoding
(levels with fewer than 50 rows merged).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from typing import Any

os.environ.setdefault('OMP_NUM_THREADS', '2')

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.compose import ColumnTransformer  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402
from sklearn.isotonic import IsotonicRegression  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import average_precision_score, roc_auc_score  # noqa: E402
from sklearn.model_selection import GroupKFold  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import OneHotEncoder, StandardScaler  # noqa: E402

from .common import (REGION_DEFINITION, REPO_ROOT, claim, load_fires, region_of,  # noqa: E402
                     set_source, write_claims)

log = logging.getLogger('large_fire')
N_JOBS = 1
SEED = 42
HOLDOUT_YEARS = (2019, 2020)
DEV_YEARS = tuple(range(2010, 2019))
TEMPORAL_FOLDS = [(2014, 2015), (2015, 2016), (2016, 2017), (2017, 2018)]  # (train through, test year)
NON_CONUS = ('AK', 'HI', 'PR')
LARGE_ACRES = 300.0
MAX_CATEGORIES = 200
ATTRIBUTES_PATH = os.path.join(REPO_ROOT, 'data', 'attributes_2010_2020.parquet')
# Two binning schemes exist in the files: six bins for most variables and twelve bins for vpd_Percentile.
PERCENTILE_MIDPOINT = {'<10%': 5.0, '10-30%': 20.0, '30-50%': 40.0, '50-70%': 60.0, '70-90%': 80.0, '>90%': 95.0,
                       '<2%': 1.0, '2-5%': 3.5, '5-10%': 7.5, '10-20%': 15.0, '20-30%': 25.0, '70-80%': 75.0,
                       '80-90%': 85.0, '90-95%': 92.5, '95-98%': 96.5, '>98%': 99.0}

# ------------------------------------------------------------------ feature groups
GEO = ['LATITUDE', 'LONGITUDE']
SEASON = ['SIN_DOY', 'COS_DOY']
CAUSE = ['CAUSE3']
REPORTING = ['OWNER6', 'AGENCY']
WEATHER = ['pr', 'tmmn', 'tmmx', 'rmin', 'rmax', 'sph', 'vs', 'th', 'srad', 'etr', 'fm100', 'fm1000', 'bi', 'vpd', 'erc']
NORMALS = ['pr_Normal', 'tmmn_Normal', 'tmmx_Normal', 'rmin_Normal', 'rmax_Normal', 'sph_Normal', 'srad_Normal',
           'fm100_Normal', 'fm1000_Normal', 'bi_Normal', 'vpd_Normal', 'erc_Normal']
# tmmn_Percentile and tmmx_Percentile are '>90%' for every CONUS row in the 2010-2020 files (a defect in the
# source), so they are excluded from the features.
PERCENTILES = ['sph_Percentile', 'vs_Percentile', 'fm100_Percentile', 'bi_Percentile', 'vpd_Percentile', 'erc_Percentile']
ANNUAL = ['Annual_etr', 'Annual_precipitation', 'Annual_tempreture', 'Aridity_index']
TERRAIN = ['Elevation', 'Slope', 'Aspect', 'TPI', 'TRI', 'Elevation_1km', 'Slope_1km', 'Aspect_1km', 'TPI_1km', 'TRI_1km']
FUELS = ['EVT_1km', 'EVT_1km_share', 'EVC_1km', 'EVH_1km', 'FRG_1km', 'Land_Cover_1km', 'rpms_1km',
         'MOD_NDVI_12m_mean', 'MOD_NDVI_12m_max', 'NDVI-1day']  # EVT/FRG/Land_Cover = dominant 1 km class;
# EVC/EVH dominant class codes are ordinal (cover %, height) and are used as numbers; *_share = share of the dominant class
ECOREGION = ['Ecoregion_US_L3CODE', 'Ecoregion_NA_L1CODE', 'NAME']
PROTECTION = ['GAP_Sts', 'GAP_Prity', 'Mang_Type', 'Des_Tp']
SOCIAL = ['RPL_THEMES', 'Population', 'Popo_1km', 'GHM']
SUPPRESSION = ['No_FireStation_1.0km', 'No_FireStation_5.0km', 'No_FireStation_10.0km', 'No_FireStation_20.0km',
               'road_county_dis', 'road_interstate_dis', 'road_common_name_dis', 'road_other_dis', 'road_state_dis',
               'road_US_dis', 'SDI', 'Evacuation', 'NPL']
GACC = ['GACCAbbrev', 'GACC_PL', 'GACC_New fire', 'GACC_Uncont LF', 'GACC_Type 1 IMTs', 'GACC_Type 2 IMTs']
DRAWDOWN = ['FIRES_7D_UNIT', 'FIRES_7D_CELL']

CATEGORICAL = ['CAUSE3', 'OWNER6', 'AGENCY', 'EVT_1km', 'FRG_1km', 'Land_Cover_1km', 'Ecoregion_US_L3CODE',
               'Ecoregion_NA_L1CODE', 'NAME', 'Mang_Type', 'Des_Tp', 'GACCAbbrev']

ABLATION_GROUPS: list[tuple[str, str, list[str]]] = [
    ('G0', 'geography + season', GEO + SEASON),
    ('G1', '+ cause, owner, agency', CAUSE + REPORTING),
    ('G2', '+ same-day weather (gridMET)', WEATHER),
    ('G3', '+ climate normals, percentiles, aridity', NORMALS + PERCENTILES + ANNUAL),
    ('G4', '+ fuels, terrain, vegetation, ecoregion', TERRAIN + FUELS + ECOREGION),
    ('G5', '+ protection status + social', PROTECTION + SOCIAL),
    ('G6', '+ suppression context + GACC preparedness + drawdown', SUPPRESSION + GACC + DRAWDOWN),
]
IMPORTANCE_GROUPS: dict[str, list[str]] = {
    'geography': GEO,
    'season': SEASON,
    'cause': CAUSE,
    'owner/agency': REPORTING,
    'same-day weather': WEATHER,
    'climate normals/percentiles': NORMALS + PERCENTILES + ANNUAL,
    'fuels/terrain/ecoregion': TERRAIN + FUELS + ECOREGION,
    'protection/social': PROTECTION + SOCIAL,
    'suppression context': SUPPRESSION + GACC + DRAWDOWN,
}


def feature_set(upto: str) -> list[str]:
    cols: list[str] = []
    for gid, _, group in ABLATION_GROUPS:
        cols += group
        if gid == upto:
            break
    return cols


FULL_FEATURES = feature_set('G6')

TUNING_GRID = [dict(learning_rate=lr, max_leaf_nodes=ml, min_samples_leaf=msl, l2_regularization=l2)
               for lr in (0.05, 0.1) for ml in (31, 63) for msl in (50, 200) for l2 in (0.0, 1.0)]
DEFAULT_HGB = dict(learning_rate=0.1, max_leaf_nodes=31, min_samples_leaf=50, l2_regularization=0.0)

OWNER_MAP = {
    'USFS': 'Federal', 'BLM': 'Federal', 'NPS': 'Federal', 'FWS': 'Federal', 'BOR': 'Federal', 'BIA': 'Federal',
    'OTHER FEDERAL': 'Federal', 'UNDEFINED FEDERAL': 'Federal',
    'STATE': 'State', 'PRIVATE': 'Private', 'TRIBAL': 'Tribal', 'MISSING/NOT SPECIFIED': 'Missing',
    'STATE OR PRIVATE': 'Other', 'COUNTY': 'Other', 'MUNICIPAL/LOCAL': 'Other', 'FOREIGN': 'Other',
}
OWNER_DEFINITION = ('OWNER_DESCR upper-cased then mapped: Federal = USFS BLM NPS FWS BOR BIA OTHER FEDERAL UNDEFINED '
                    'FEDERAL; State = STATE; Private = PRIVATE; Tribal = TRIBAL; Missing = MISSING/NOT SPECIFIED; '
                    'Other = STATE OR PRIVATE, COUNTY, MUNICIPAL/LOCAL, FOREIGN.')
CAUSE_MAP = {'Human': 'Human', 'Natural': 'Natural', 'Missing data/not specified/undetermined': 'Missing'}
REGION_LABEL = {'West': 'West', 'South': 'South', 'Northeast': 'Northeast', 'Other': 'Plains-Midwest'}


# ------------------------------------------------------------------ data build

def _doy_angle(dates: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Leap-aware angle: (dayofyear - 1) / days_in_year, so 31 Dec of a leap year is not 1 Jan."""
    doy = dates.dt.dayofyear.to_numpy() - 1
    diy = np.where(dates.dt.is_leap_year.to_numpy(), 366, 365)
    ang = 2 * np.pi * doy / diy
    return np.sin(ang), np.cos(ang)


def _prior_7day_counts(key: pd.Series, day: np.ndarray) -> np.ndarray:
    """Number of rows with the same key and a day in [day-7, day-1] (strictly before discovery)."""
    codes = pd.factorize(key.astype(str))[0].astype(np.int64)
    comp = codes * 100_000 + day.astype(np.int64)
    srt = np.sort(comp)
    lo = np.searchsorted(srt, comp - 7, side='left')
    hi = np.searchsorted(srt, comp - 1, side='right')
    return (hi - lo).astype(np.int32)


def build_sample(quick: bool = False) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load 2010-2020 CONUS fires, join the attributes, build features. Returns (frame, sample_info)."""
    t0 = time.time()
    cols = ['FOD_ID', 'FIRE_YEAR', 'DISCOVERY_DATE', 'LATITUDE', 'LONGITUDE', 'STATE', 'FIRE_SIZE', 'MTBS_ID',
            'NWCG_CAUSE_CLASSIFICATION', 'OWNER_DESCR', 'NWCG_REPORTING_AGENCY', 'NWCG_REPORTING_UNIT_ID']
    fires = load_fires(cols)
    fires = fires[fires.FIRE_YEAR >= 2009].reset_index(drop=True)  # 2009 only feeds the drawdown window
    day = (fires.DISCOVERY_DATE - pd.Timestamp('2000-01-01')).dt.days.to_numpy()
    fires['FIRES_7D_UNIT'] = _prior_7day_counts(fires.NWCG_REPORTING_UNIT_ID, day)
    cell = np.floor(fires.LATITUDE).astype(int).astype(str) + '_' + np.floor(fires.LONGITUDE).astype(int).astype(str)
    fires['CELL'] = cell
    fires['FIRES_7D_CELL'] = _prior_7day_counts(cell, day)
    fires = fires[fires.FIRE_YEAR >= 2010]
    n_2010 = len(fires)
    non_conus = fires.STATE.astype(str).isin(NON_CONUS)
    dropped = fires[non_conus].groupby(fires[non_conus].STATE.astype(str)).size().to_dict()
    ak_class_g_share = float(fires.loc[(fires.FIRE_SIZE >= 5000) & (fires.STATE.astype(str) == 'AK'), 'FIRE_SIZE'].sum()
                             / fires.loc[fires.FIRE_SIZE >= 5000, 'FIRE_SIZE'].sum())
    df = fires[~non_conus].copy()

    attrs = pd.read_parquet(ATTRIBUTES_PATH)
    attrs = attrs.drop(columns=['FIRE_YEAR'])
    n_before = len(df)
    df = df.merge(attrs, on='FOD_ID', how='left', validate='one_to_one')
    assert len(df) == n_before
    join_rate = float(df['erc_Normal'].notna().mean())

    sin, cos = _doy_angle(df.DISCOVERY_DATE)
    df['SIN_DOY'], df['COS_DOY'] = sin.astype(np.float32), cos.astype(np.float32)
    df['CAUSE3'] = df.NWCG_CAUSE_CLASSIFICATION.astype(str).map(CAUSE_MAP).fillna('Missing')
    df['OWNER6'] = df.OWNER_DESCR.astype(str).str.upper().map(OWNER_MAP).fillna('Other')
    df['AGENCY'] = df.NWCG_REPORTING_AGENCY.astype(str).str.upper()
    for c in PERCENTILES:
        df[c] = df[c].map(PERCENTILE_MIDPOINT).astype(np.float32)
    df['MONTH'] = df.DISCOVERY_DATE.dt.month.astype(np.int8)
    df['LARGE'] = (df.FIRE_SIZE >= LARGE_ACRES).astype(np.int8)
    df['MTBS'] = df.MTBS_ID.notna().astype(np.int8)
    df['REGION'] = region_of(df.STATE).map(REGION_LABEL)
    df['STATE'] = df.STATE.astype(str)

    category_info = {}
    for c in CATEGORICAL:
        s = df[c]
        if pd.api.types.is_float_dtype(s):
            s = s.round().astype('Int64').astype(str).where(s.notna(), None)
        else:
            s = s.astype(object).where(s.notna(), None)
        vc = s.value_counts()
        n_levels = int(len(vc))
        if n_levels > MAX_CATEGORIES:
            keep = set(vc.index[:MAX_CATEGORIES - 1])
            s = s.where(s.isin(keep) | s.isna(), '__other__')
        df[c] = pd.Categorical(s)
        category_info[c] = {'levels_in_data': n_levels, 'levels_used': int(len(df[c].cat.categories)),
                            'null_rate': float(df[c].isna().mean())}
    numeric = [c for c in FULL_FEATURES if c not in CATEGORICAL]
    for c in numeric:
        df[c] = pd.to_numeric(df[c], errors='coerce').astype(np.float32)
    keep_cols = ['FOD_ID', 'FIRE_YEAR', 'MONTH', 'STATE', 'REGION', 'CELL', 'FIRE_SIZE', 'LARGE', 'MTBS'] + FULL_FEATURES
    df = df[keep_cols].reset_index(drop=True)
    if quick:
        df = df.sample(frac=0.15, random_state=SEED).reset_index(drop=True)

    info = {
        'definition': ('All FPA FOD v6 fires with FIRE_YEAR 2010-2020 and STATE not in AK, HI, PR (the FPA FOD-Attributes '
                       'dataset is CONUS-only). No CONT_DATE selection. Label LARGE = FIRE_SIZE >= 300 acres; '
                       'label MTBS = MTBS_ID present.'),
        'n_fires_2010_2020_all_states': int(n_2010),
        'n_dropped_non_conus': int(non_conus.sum()),
        'dropped_by_state': {k: int(v) for k, v in dropped.items()},
        'alaska_share_of_class_g_acres_2010_2020': ak_class_g_share,
        'n_sample': int(len(df)),
        'attribute_join_rate_erc_normal': join_rate,
        'n_large': int(df.LARGE.sum()), 'rate_large': float(df.LARGE.mean()),
        'n_mtbs': int(df.MTBS.sum()), 'rate_mtbs': float(df.MTBS.mean()),
        'by_year': {int(y): {'n': int(len(g)), 'large': int(g.LARGE.sum()), 'mtbs': int(g.MTBS.sum())}
                    for y, g in df.groupby('FIRE_YEAR')},
        'holdout_years': list(HOLDOUT_YEARS), 'development_years': list(DEV_YEARS),
        'owner_definition': OWNER_DEFINITION,
        'cause_definition': 'NWCG_CAUSE_CLASSIFICATION mapped to Human / Natural / Missing.',
        'region_definition': REGION_DEFINITION + ' Plains-Midwest = the "Other" region (AK, HI, PR are not in the sample).',
        'drawdown_definition': ('FIRES_7D_UNIT = fires discovered in the same NWCG_REPORTING_UNIT_ID on the 7 calendar days '
                                'before discovery (strictly before, so nothing from the discovery day itself); FIRES_7D_CELL '
                                'the same for the 1-degree lat/lon cell. Both computed from FPA FOD rows 2009-2020.'),
        'categorical_encoding': category_info,
        'percentile_midpoints': PERCENTILE_MIDPOINT,
        'quick_subsample': quick,
        'build_seconds': round(time.time() - t0, 1),
    }
    log.info(f'sample built: {len(df):,} rows, {len(FULL_FEATURES)} features, {info["build_seconds"]}s')
    return df, info


# ------------------------------------------------------------------ baselines

def climatology(train: pd.DataFrame, test: pd.DataFrame, target: str, k: float = 20.0) -> np.ndarray:
    """P(target) by 1-degree cell x month from training rows, smoothed with k pseudo-counts toward the
    cell rate, which is itself smoothed toward the global rate; backs off cell x month -> cell -> global."""
    prior = float(train[target].mean())
    c = train.groupby('CELL', observed=True)[target].agg(['sum', 'count'])
    c['p'] = (c['sum'] + k * prior) / (c['count'] + k)
    g = train.groupby(['CELL', 'MONTH'], observed=True)[target].agg(['sum', 'count']).reset_index()
    g['cell_p'] = g.CELL.map(c['p'])
    g['p'] = (g['sum'] + k * g['cell_p']) / (g['count'] + k)
    g = g.set_index(['CELL', 'MONTH'])['p']
    cp = pd.Series(c['p'].reindex(test.CELL).to_numpy(), index=test.index).fillna(prior)
    key = pd.MultiIndex.from_arrays([test.CELL, test.MONTH])
    p = pd.Series(g.reindex(key).to_numpy(), index=test.index).fillna(cp)
    return p.to_numpy(dtype=float)


def make_hgb(params: dict[str, Any] | None = None, max_iter: int = 500) -> HistGradientBoostingClassifier:
    p = dict(DEFAULT_HGB if params is None else params)
    return HistGradientBoostingClassifier(max_iter=max_iter, early_stopping=True, validation_fraction=0.1,
                                          n_iter_no_change=25, categorical_features='from_dtype',
                                          random_state=SEED, **p)


def make_logreg(features: list[str]) -> Pipeline:
    num = [c for c in features if c not in CATEGORICAL]
    cat = [c for c in features if c in CATEGORICAL]
    steps = []
    if num:
        steps.append(('num', Pipeline([('imp', SimpleImputer(strategy='median', add_indicator=True)),
                                       ('sc', StandardScaler())]), num))
    if cat:
        steps.append(('cat', OneHotEncoder(handle_unknown='infrequent_if_exist', min_frequency=50, sparse_output=True), cat))
    return Pipeline([('ct', ColumnTransformer(steps, sparse_threshold=1.0)),
                     ('lr', LogisticRegression(max_iter=300, tol=1e-3, C=1.0))])


def fit_predict_hgb(train: pd.DataFrame, test: pd.DataFrame, features: list[str], target: str,
                    params: dict[str, Any] | None = None) -> tuple[np.ndarray, HistGradientBoostingClassifier, float]:
    t0 = time.time()
    m = make_hgb(params).fit(train[features], train[target])
    return m.predict_proba(test[features])[:, 1], m, time.time() - t0


# ------------------------------------------------------------------ metrics

def _sorted_groups(p: np.ndarray):
    order = np.argsort(-p, kind='stable')
    ps = p[order]
    starts = np.flatnonzero(np.r_[True, ps[1:] != ps[:-1]])
    return order, starts


def weighted_ap_auc(y: np.ndarray, p: np.ndarray, w: np.ndarray | None = None, pre=None) -> tuple[float, float]:
    """Average precision (sklearn's step definition) and ROC-AUC with ties, with optional integer weights."""
    order, starts = pre if pre is not None else _sorted_groups(p)
    ys = y[order].astype(float)
    ws = np.ones(len(y)) if w is None else w[order].astype(float)
    wy = ws * ys
    g_wy = np.add.reduceat(wy, starts)
    g_w = np.add.reduceat(ws, starts)
    tp = np.cumsum(g_wy)
    tot = np.cumsum(g_w)
    TP = tp[-1]
    if TP == 0:
        return float('nan'), float('nan')
    prec = tp / np.maximum(tot, 1e-12)  # zero-weight leading groups under bootstrap resampling
    rec = tp / TP
    ap = float(np.sum(np.diff(np.r_[0.0, rec]) * prec))
    g_wn = g_w - g_wy
    neg_before = np.cumsum(g_wn) - g_wn  # negatives ranked strictly above this group (higher score)
    # AUC = P(score_pos > score_neg) + 0.5 P(tie): positives beat negatives ranked below them
    N = tot[-1] - TP
    neg_below = N - neg_before - g_wn
    auc = float(np.sum(g_wy * (neg_below + 0.5 * g_wn)) / (TP * N))
    return ap, auc


def reliability_table(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> list[dict[str, Any]]:
    order = np.argsort(p, kind='stable')
    bins = np.array_split(order, n_bins)
    rows = []
    for i, idx in enumerate(bins):
        rows.append({'bin': i + 1, 'n': int(len(idx)), 'n_positive': int(y[idx].sum()),
                     'mean_predicted': float(p[idx].mean()), 'observed_rate': float(y[idx].mean()),
                     'min_predicted': float(p[idx].min()), 'max_predicted': float(p[idx].max())})
    return rows


def score(y: np.ndarray, p: np.ndarray, base_rate: float, p_clim: np.ndarray | None = None,
          with_reliability: bool = True) -> dict[str, Any]:
    y = np.asarray(y, dtype=np.int8)
    p = np.asarray(p, dtype=float)
    ap, auc = weighted_ap_auc(y, p)
    brier = float(np.mean((p - y) ** 2))
    brier_base = float(np.mean((base_rate - y) ** 2))
    out = {'n': int(len(y)), 'n_positive': int(y.sum()), 'base_rate_test': float(y.mean()),
           'base_rate_train': float(base_rate),
           'pr_auc': ap, 'roc_auc': auc, 'brier': brier, 'brier_skill_vs_base_rate': 1 - brier / brier_base}
    if p_clim is not None:
        brier_clim = float(np.mean((p_clim - y) ** 2))
        out['brier_skill_vs_climatology'] = 1 - brier / brier_clim
    thr = np.quantile(p, 0.9)
    top = p >= thr
    if abs(top.mean() - 0.1) > 0.005:  # ties at the threshold: take exactly the top 10% by rank instead
        # (before 2026-09-25 this triggered only above 20%, so the isotonic scores' "top decile" in E-015
        # flagged 12.0% of fires; model.capture_at_top gives the exact value)
        top = np.zeros(len(p), bool)
        top[np.argsort(-p, kind='stable')[: int(round(0.1 * len(p)))]] = True
    out['top_decile_share_of_rows'] = float(top.mean())
    out['top_decile_recall'] = float(y[top].sum() / max(y.sum(), 1))
    out['top_decile_lift'] = float(y[top].mean() / max(y.mean(), 1e-12))
    out['top_decile_precision'] = float(y[top].mean())
    # precision at 50% recall: best precision among thresholds reaching recall >= 0.5
    order, starts = _sorted_groups(p)
    ys = y[order].astype(float)
    tp = np.cumsum(np.add.reduceat(ys, starts))
    tot = np.cumsum(np.add.reduceat(np.ones(len(y)), starts))
    rec = tp / max(tp[-1], 1)
    prec = tp / tot
    ok = rec >= 0.5
    out['precision_at_50pct_recall'] = float(prec[ok].max()) if ok.any() else float('nan')
    if with_reliability:
        out['reliability'] = reliability_table(y, p)
        rel = out['reliability']
        # relative error is only meaningful where the observed rate is estimated from enough positives
        usable = [r for r in rel if r['n_positive'] >= 20]
        out['max_relative_calibration_error'] = float(max(abs(r['mean_predicted'] - r['observed_rate'])
                                                        / r['observed_rate'] for r in usable)) if usable else float('nan')
        out['max_absolute_calibration_error'] = float(max(abs(r['mean_predicted'] - r['observed_rate']) for r in rel))
        out['n_bins_with_20_positives'] = len(usable)
    return out


def pr_curve_points(y: np.ndarray, p: np.ndarray, n_points: int = 200) -> list[dict[str, float]]:
    order, starts = _sorted_groups(p)
    ys = y[order].astype(float)
    tp = np.cumsum(np.add.reduceat(ys, starts))
    tot = np.cumsum(np.add.reduceat(np.ones(len(y)), starts))
    rec, prec = tp / max(tp[-1], 1), tp / tot
    thr = p[order][starts]  # score of each tie group; flagging at >= thr flags tot[i] fires
    idx = np.unique(np.linspace(0, len(rec) - 1, n_points).astype(int))
    return [{'recall': float(rec[i]), 'precision': float(prec[i]), 'threshold': float(thr[i]),
             'n_flagged': int(tot[i])} for i in idx]


def bootstrap(y: np.ndarray, preds: dict[str, np.ndarray], base_rate: float, n_boot: int = 1000,
              seed: int = SEED) -> dict[str, dict[str, Any]]:
    """95% percentile intervals (n_boot resamples of rows) for PR-AUC, ROC-AUC, Brier skill and top-decile recall."""
    rng = np.random.default_rng(seed)
    n = len(y)
    pre = {k: _sorted_groups(p) for k, p in preds.items()}
    thr = {k: np.quantile(p, 0.9) for k, p in preds.items()}
    top = {k: (p >= thr[k]) for k, p in preds.items()}
    for k, p in preds.items():
        if abs(top[k].mean() - 0.1) > 0.005:
            t = np.zeros(n, bool)
            t[np.argsort(-p, kind='stable')[: int(round(0.1 * n))]] = True
            top[k] = t
    res = {k: {'pr_auc': [], 'roc_auc': [], 'brier_skill_vs_base_rate': [], 'top_decile_recall': []} for k in preds}
    yf = y.astype(float)
    for _ in range(n_boot):
        w = rng.multinomial(n, np.full(n, 1.0 / n)).astype(float)
        W = w.sum()
        npos = float((w * yf).sum())
        bb = float((w * (base_rate - yf) ** 2).sum() / W)
        for k, p in preds.items():
            ap, auc = weighted_ap_auc(y, p, w, pre[k])
            br = float((w * (p - yf) ** 2).sum() / W)
            res[k]['pr_auc'].append(ap)
            res[k]['roc_auc'].append(auc)
            res[k]['brier_skill_vs_base_rate'].append(1 - br / bb)
            res[k]['top_decile_recall'].append(float((w * yf)[top[k]].sum() / max(npos, 1)))
    out = {}
    for k in preds:
        out[k] = {}
        for m, vals in res[k].items():
            v = np.asarray(vals)
            out[k][m] = {'low': float(np.nanpercentile(v, 2.5)), 'high': float(np.nanpercentile(v, 97.5)),
                         'n_boot': n_boot}
    return out


def grouped_permutation_importance(model, X: pd.DataFrame, y: np.ndarray, groups: dict[str, list[str]],
                                   n_repeats: int = 10, seed: int = SEED) -> list[dict[str, Any]]:
    rng = np.random.default_rng(seed)
    feats = list(X.columns)
    base_p = model.predict_proba(X)[:, 1]
    base_ap, base_auc = weighted_ap_auc(y, base_p)
    rows = []
    for gname, gcols in groups.items():
        cols = [c for c in gcols if c in feats]
        if not cols:
            continue
        drops_ap, drops_auc = [], []
        for _ in range(n_repeats):
            Xp = X.copy()
            perm = rng.permutation(len(X))
            for c in cols:
                Xp[c] = X[c].to_numpy()[perm]
            p = model.predict_proba(Xp)[:, 1]
            ap, auc = weighted_ap_auc(y, p)
            drops_ap.append(base_ap - ap)
            drops_auc.append(base_auc - auc)
        rows.append({'group': gname, 'n_features': len(cols), 'features': cols,
                     'pr_auc_drop_mean': float(np.mean(drops_ap)), 'pr_auc_drop_low': float(np.min(drops_ap)),
                     'pr_auc_drop_high': float(np.max(drops_ap)), 'pr_auc_drop_std': float(np.std(drops_ap)),
                     'roc_auc_drop_mean': float(np.mean(drops_auc)), 'roc_auc_drop_low': float(np.min(drops_auc)),
                     'roc_auc_drop_high': float(np.max(drops_auc)), 'n_repeats': n_repeats,
                     'base_pr_auc': float(base_ap), 'base_roc_auc': float(base_auc)})
    rows.sort(key=lambda r: -r['pr_auc_drop_mean'])
    return rows


# ------------------------------------------------------------------ io helpers

def _dump(obj: Any, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(obj, f, indent=1, default=lambda o: o.item() if hasattr(o, 'item') else str(o))


def _model_dir(out: str) -> str:
    d = os.path.join(out, 'model')
    os.makedirs(d, exist_ok=True)
    return d


def _short(m: dict[str, Any]) -> dict[str, Any]:
    keys = ['n', 'n_positive', 'base_rate_test', 'pr_auc', 'roc_auc', 'brier', 'brier_skill_vs_base_rate',
            'brier_skill_vs_climatology', 'top_decile_recall', 'top_decile_lift', 'precision_at_50pct_recall',
            'max_relative_calibration_error']
    return {k: m[k] for k in keys if k in m}


# ------------------------------------------------------------------ stage: build

def stage_build(df: pd.DataFrame, info: dict[str, Any], out: str) -> None:
    md = _model_dir(out)
    _dump(info, os.path.join(md, 'sample.json'))
    feats = []
    for gid, label, group in ABLATION_GROUPS:
        for c in group:
            feats.append({'feature': c, 'ablation_group': gid, 'ablation_label': label,
                          'type': 'categorical' if c in CATEGORICAL else 'numeric',
                          'null_rate': float(df[c].isna().mean()),
                          'importance_group': next(k for k, v in IMPORTANCE_GROUPS.items() if c in v)})
    pd.DataFrame(feats).to_csv(os.path.join(md, 'features.csv'), index=False)
    log.info(f'build: wrote sample.json and features.csv ({len(feats)} features)')


# ------------------------------------------------------------------ stage: develop

def _fold_frames(df: pd.DataFrame, train_through: int, test_year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    return df[(df.FIRE_YEAR >= 2010) & (df.FIRE_YEAR <= train_through)], df[df.FIRE_YEAR == test_year]


def stage_develop(df: pd.DataFrame, out: str, quick: bool = False) -> dict[str, Any]:
    md = _model_dir(out)
    dev = df[df.FIRE_YEAR.isin(DEV_YEARS)]
    assert not dev.FIRE_YEAR.isin(HOLDOUT_YEARS).any()
    grid = TUNING_GRID[:2] if quick else TUNING_GRID
    results: dict[str, Any] = {'folds': [], 'ablation': [], 'grid': [], 'spatial': [], 'mtbs': []}

    # ---- baselines and ablation on each temporal fold, LARGE
    for train_through, test_year in TEMPORAL_FOLDS:
        tr, te = _fold_frames(dev, train_through, test_year)
        y, base = te.LARGE.to_numpy(), float(tr.LARGE.mean())
        p_clim = climatology(tr, te, 'LARGE')
        fold = {'train_through': train_through, 'test_year': test_year, 'n_train': int(len(tr)), 'n_test': int(len(te)),
                'models': {}}
        fold['models']['base_rate'] = _short(score(y, np.full(len(te), base), base, p_clim))
        fold['models']['climatology_cell_month'] = _short(score(y, p_clim, base, p_clim))
        t0 = time.time()
        lr = make_logreg(FULL_FEATURES).fit(tr[FULL_FEATURES], tr.LARGE)
        fold['models']['logistic_regression'] = _short(score(y, lr.predict_proba(te[FULL_FEATURES])[:, 1], base, p_clim))
        fold['models']['logistic_regression']['fit_seconds'] = round(time.time() - t0, 1)
        log.info(f'fold {test_year}: baselines done (logreg {time.time() - t0:.0f}s)')
        for gid, label, _ in ABLATION_GROUPS:
            feats = feature_set(gid)
            p, m, secs = fit_predict_hgb(tr, te, feats, 'LARGE')
            s = _short(score(y, p, base, p_clim))
            s.update({'fit_seconds': round(secs, 1), 'n_iter': int(m.n_iter_)})
            row = {'group': gid, 'label': label, 'n_features': len(feats), 'test_year': test_year, **s}
            results['ablation'].append(row)
            if gid == 'G0':
                fold['models']['hgb_geography_season_only'] = s
            if gid == 'G6':
                fold['models']['hgb_full'] = s
            log.info(f'fold {test_year} {gid}: PR-AUC {s["pr_auc"]:.4f} ROC {s["roc_auc"]:.4f} '
                     f'BSS {s["brier_skill_vs_base_rate"]:.4f} ({secs:.0f}s, {m.n_iter_} iter)')
        results['folds'].append(fold)
    abl = pd.DataFrame(results['ablation'])
    abl.to_csv(os.path.join(md, 'develop_ablation.csv'), index=False)
    abl_mean = abl.groupby(['group', 'label'], sort=True)[['pr_auc', 'roc_auc', 'brier_skill_vs_base_rate',
                                                            'brier_skill_vs_climatology', 'top_decile_recall']].mean()
    log.info('ablation fold means:\n' + abl_mean.round(4).to_string())

    # ---- tuning grid on the full feature set
    for i, params in enumerate(grid):
        per_year = {}
        for train_through, test_year in TEMPORAL_FOLDS:
            tr, te = _fold_frames(dev, train_through, test_year)
            p, m, secs = fit_predict_hgb(tr, te, FULL_FEATURES, 'LARGE', params)
            s = score(te.LARGE.to_numpy(), p, float(tr.LARGE.mean()), with_reliability=False)
            per_year[test_year] = {'pr_auc': s['pr_auc'], 'roc_auc': s['roc_auc'],
                                   'brier_skill_vs_base_rate': s['brier_skill_vs_base_rate'], 'n_iter': int(m.n_iter_),
                                   'fit_seconds': round(secs, 1)}
        row = {'config_id': i, **params,
               'mean_pr_auc': float(np.mean([v['pr_auc'] for v in per_year.values()])),
               'min_pr_auc': float(np.min([v['pr_auc'] for v in per_year.values()])),
               'mean_roc_auc': float(np.mean([v['roc_auc'] for v in per_year.values()])),
               'mean_brier_skill': float(np.mean([v['brier_skill_vs_base_rate'] for v in per_year.values()])),
               'per_year': per_year}
        results['grid'].append(row)
        log.info(f'grid {i}: {params} mean PR-AUC {row["mean_pr_auc"]:.4f} (min {row["min_pr_auc"]:.4f})')
    grid_df = pd.DataFrame([{k: v for k, v in r.items() if k != 'per_year'} for r in results['grid']])
    grid_df.to_csv(os.path.join(md, 'develop_grid.csv'), index=False)
    best = max(results['grid'], key=lambda r: r['mean_pr_auc'])
    chosen = {k: best[k] for k in DEFAULT_HGB}
    log.info(f'chosen config {best["config_id"]}: {chosen} mean PR-AUC {best["mean_pr_auc"]:.4f}')

    # ---- calibration decision on the 2018 fold with the chosen config
    tr, te = _fold_frames(dev, 2017, 2018)
    p_raw, m2018, _ = fit_predict_hgb(tr, te, FULL_FEATURES, 'LARGE', chosen)
    y2018, base2018 = te.LARGE.to_numpy(), float(tr.LARGE.mean())
    clim2018 = climatology(tr, te, 'LARGE')
    raw = score(y2018, p_raw, base2018, clim2018)
    iso = IsotonicRegression(out_of_bounds='clip', y_min=0.0, y_max=1.0).fit(p_raw, y2018)
    needs_cal = raw['max_relative_calibration_error'] > 0.20
    # in-sample view of the calibrator on the same fold (optimistic by construction; reported as such)
    cal_in = score(y2018, iso.predict(p_raw), base2018, clim2018)
    # honest view: calibrator fitted on the 2017 fold (model through 2016), applied to the 2018 fold
    tr17, te17 = _fold_frames(dev, 2016, 2017)
    p17, _, _ = fit_predict_hgb(tr17, te17, FULL_FEATURES, 'LARGE', chosen)
    iso17 = IsotonicRegression(out_of_bounds='clip', y_min=0.0, y_max=1.0).fit(p17, te17.LARGE.to_numpy())
    cal_out = score(y2018, iso17.predict(p_raw), base2018, clim2018)
    results['calibration'] = {
        'rule': ('fit isotonic on the 2018 fold if any of the 10 quantile bins with at least 20 observed large fires '
                 'is off by more than 20% relative (bins with fewer positives cannot support a relative test)'),
        'raw_2018': raw, 'max_relative_error_raw': raw['max_relative_calibration_error'],
        'isotonic_applied': bool(needs_cal),
        'isotonic_in_sample_2018': _short(cal_in),
        'isotonic_fitted_on_2017_applied_to_2018': _short(cal_out) | {'reliability': cal_out['reliability']},
    }
    log.info(f'calibration: raw max relative bin error {raw["max_relative_calibration_error"]:.3f} -> '
             f'{"apply isotonic" if needs_cal else "no calibration"}')

    # ---- spatial GroupKFold(3) by 1-degree cell on the development years (secondary check)
    sp = dev.sample(frac=0.5, random_state=SEED) if quick else dev
    gkf = GroupKFold(n_splits=3)
    for k, (itr, ite) in enumerate(gkf.split(sp, groups=sp.CELL)):
        tr, te = sp.iloc[itr], sp.iloc[ite]
        y, base = te.LARGE.to_numpy(), float(tr.LARGE.mean())
        p_clim = climatology(tr, te, 'LARGE')
        row = {'fold': k, 'n_train': int(len(tr)), 'n_test': int(len(te)), 'n_cells_test': int(te.CELL.nunique())}
        row['climatology_cell_month'] = _short(score(y, p_clim, base, p_clim, with_reliability=False))
        p, _, _ = fit_predict_hgb(tr, te, feature_set('G0'), 'LARGE', chosen)
        row['hgb_geography_season_only'] = _short(score(y, p, base, p_clim, with_reliability=False))
        p, _, _ = fit_predict_hgb(tr, te, FULL_FEATURES, 'LARGE', chosen)
        row['hgb_full'] = _short(score(y, p, base, p_clim, with_reliability=False))
        results['spatial'].append(row)
        log.info(f'spatial fold {k}: clim {row["climatology_cell_month"]["pr_auc"]:.4f} geo '
                 f'{row["hgb_geography_season_only"]["pr_auc"]:.4f} full {row["hgb_full"]["pr_auc"]:.4f}')

    # ---- secondary label MTBS on the temporal folds (chosen config, no separate tuning)
    for train_through, test_year in TEMPORAL_FOLDS:
        tr, te = _fold_frames(dev, train_through, test_year)
        y, base = te.MTBS.to_numpy(), float(tr.MTBS.mean())
        p_clim = climatology(tr, te, 'MTBS')
        row = {'test_year': test_year, 'n_test': int(len(te)), 'n_positive': int(y.sum())}
        row['base_rate'] = _short(score(y, np.full(len(te), base), base, p_clim, with_reliability=False))
        row['climatology_cell_month'] = _short(score(y, p_clim, base, p_clim, with_reliability=False))
        p, _, _ = fit_predict_hgb(tr, te, feature_set('G0'), 'MTBS', chosen)
        row['hgb_geography_season_only'] = _short(score(y, p, base, p_clim, with_reliability=False))
        p, _, _ = fit_predict_hgb(tr, te, FULL_FEATURES, 'MTBS', chosen)
        row['hgb_full'] = _short(score(y, p, base, p_clim, with_reliability=False))
        results['mtbs'].append(row)
        log.info(f'MTBS fold {test_year}: clim {row["climatology_cell_month"]["pr_auc"]:.4f} '
                 f'full {row["hgb_full"]["pr_auc"]:.4f}')

    chosen_out = {'hgb_params': chosen, 'config_id': best['config_id'], 'mean_pr_auc_temporal': best['mean_pr_auc'],
                  'isotonic': bool(needs_cal), 'features': FULL_FEATURES, 'quick': quick,
                  'grid_size': len(grid), 'decided_at': pd.Timestamp.now('UTC').isoformat()}
    _dump(chosen_out, os.path.join(md, 'chosen_config.json'))
    _dump(results, os.path.join(md, 'develop_results.json'))
    pd.DataFrame([{'test_year': f['test_year'], 'model': k, **v} for f in results['folds'] for k, v in f['models'].items()]
                 ).to_csv(os.path.join(md, 'develop_folds.csv'), index=False)
    return results


# ------------------------------------------------------------------ stage: final

def stage_final(df: pd.DataFrame, info: dict[str, Any], out: str, quick: bool = False) -> dict[str, Any]:
    md = _model_dir(out)
    with open(os.path.join(md, 'chosen_config.json')) as f:
        chosen = json.load(f)
    params = chosen['hgb_params']
    n_boot = 200 if quick else 1000
    tr = df[df.FIRE_YEAR.isin(DEV_YEARS)]
    te = df[df.FIRE_YEAR.isin(HOLDOUT_YEARS)]
    log.info(f'FINAL: train {len(tr):,} (2010-2018), holdout {len(te):,} (2019-2020). This is the one look.')
    y, base = te.LARGE.to_numpy(), float(tr.LARGE.mean())
    preds: dict[str, np.ndarray] = {}
    preds['base_rate'] = np.full(len(te), base)
    preds['climatology_cell_month'] = climatology(tr, te, 'LARGE')
    t0 = time.time()
    lr = make_logreg(FULL_FEATURES).fit(tr[FULL_FEATURES], tr.LARGE)
    preds['logistic_regression'] = lr.predict_proba(te[FULL_FEATURES])[:, 1]
    log.info(f'logreg fitted in {time.time() - t0:.0f}s')
    p_geo, m_geo, _ = fit_predict_hgb(tr, te, feature_set('G0'), 'LARGE', params)
    preds['hgb_geography_season_only'] = p_geo
    p_raw, model, secs = fit_predict_hgb(tr, te, FULL_FEATURES, 'LARGE', params)
    log.info(f'final HGB fitted in {secs:.0f}s, {model.n_iter_} iterations')
    preds['hgb_full_raw'] = p_raw
    # calibrator: isotonic fitted on the 2018 development fold (model trained through 2017)
    tr17, te18 = _fold_frames(tr, 2017, 2018)
    p18, _, _ = fit_predict_hgb(tr17, te18, FULL_FEATURES, 'LARGE', params)
    iso = IsotonicRegression(out_of_bounds='clip', y_min=0.0, y_max=1.0).fit(p18, te18.LARGE.to_numpy())
    preds['hgb_full_isotonic'] = iso.predict(p_raw)
    final_key = 'hgb_full_isotonic' if chosen['isotonic'] else 'hgb_full_raw'
    preds['hgb_full'] = preds[final_key]

    p_clim = preds['climatology_cell_month']
    res: dict[str, Any] = {'chosen': chosen, 'final_prediction': final_key, 'n_train': int(len(tr)), 'n_test': int(len(te)),
                           'overall': {}, 'per_year': {}, 'per_region': {}, 'per_state': {}, 'mtbs': {}}
    for k, p in preds.items():
        res['overall'][k] = score(y, p, base, p_clim)
    log.info('holdout overall:\n' + pd.DataFrame({k: _short(v) for k, v in res['overall'].items()}).T.round(4).to_string())
    boot_keys = ['base_rate', 'climatology_cell_month', 'logistic_regression', 'hgb_geography_season_only',
                 'hgb_full_raw', 'hgb_full_isotonic']
    t0 = time.time()
    res['bootstrap'] = bootstrap(y, {k: preds[k] for k in boot_keys}, base, n_boot=n_boot)
    log.info(f'bootstrap ({n_boot}) done in {time.time() - t0:.0f}s')
    res['pr_curves'] = {k: pr_curve_points(y, preds[k]) for k in ['climatology_cell_month', 'logistic_regression',
                                                                 'hgb_geography_season_only', 'hgb_full']}
    for yr in HOLDOUT_YEARS:
        m = (te.FIRE_YEAR == yr).to_numpy()
        res['per_year'][yr] = {k: _short(score(y[m], p[m], base, p_clim[m])) for k, p in preds.items()}
        res['per_year'][yr]['bootstrap'] = bootstrap(y[m], {k: preds[k][m] for k in ['climatology_cell_month', 'hgb_full']},
                                                     base, n_boot=n_boot)
    for reg in ['West', 'South', 'Plains-Midwest', 'Northeast']:
        m = (te.REGION == reg).to_numpy()
        res['per_region'][reg] = {k: _short(score(y[m], p[m], base, p_clim[m], with_reliability=False))
                                  for k, p in preds.items()}
        res['per_region'][reg]['n_train'] = int((tr.REGION == reg).sum())
    top_states = df.STATE.value_counts().index[:10].tolist()
    for st in top_states:
        m = (te.STATE == st).to_numpy()
        res['per_state'][st] = {k: _short(score(y[m], p[m], base, p_clim[m], with_reliability=False))
                                for k, p in preds.items() if k in ('climatology_cell_month', 'hgb_geography_season_only',
                                                                   'hgb_full')}
        res['per_state'][st]['n_train'] = int((tr.STATE == st).sum())
        res['per_state'][st]['train_rate_large'] = float(tr.LARGE[tr.STATE == st].mean())
    # importance
    t0 = time.time()
    Xte = te[FULL_FEATURES]
    res['importance'] = grouped_permutation_importance(model, Xte, y, IMPORTANCE_GROUPS, n_repeats=3 if quick else 10)
    log.info(f'importance done in {time.time() - t0:.0f}s:\n' + pd.DataFrame(res['importance'])[
        ['group', 'pr_auc_drop_mean', 'pr_auc_drop_low', 'pr_auc_drop_high']].round(4).to_string())
    # secondary label
    ym, basem = te.MTBS.to_numpy(), float(tr.MTBS.mean())
    climm = climatology(tr, te, 'MTBS')
    mt = {'base_rate': _short(score(ym, np.full(len(te), basem), basem, climm)),
          'climatology_cell_month': _short(score(ym, climm, basem, climm))}
    pm_geo, _, _ = fit_predict_hgb(tr, te, feature_set('G0'), 'MTBS', params)
    mt['hgb_geography_season_only'] = _short(score(ym, pm_geo, basem, climm))
    pm, model_mtbs, _ = fit_predict_hgb(tr, te, FULL_FEATURES, 'MTBS', params)
    mt['hgb_full'] = _short(score(ym, pm, basem, climm))
    mt['bootstrap'] = bootstrap(ym, {'climatology_cell_month': climm, 'hgb_full': pm}, basem, n_boot=n_boot)
    mt['per_year'] = {yr: {'climatology_cell_month': _short(score(ym[m], climm[m], basem, climm[m], False)),
                           'hgb_full': _short(score(ym[m], pm[m], basem, climm[m], False))}
                      for yr in HOLDOUT_YEARS for m in [(te.FIRE_YEAR == yr).to_numpy()]}
    mt['reliability_hgb_full'] = reliability_table(ym, pm)
    res['mtbs'] = mt
    # coverage / area of applicability
    cov = df.groupby('STATE').agg(n_train=('FIRE_YEAR', lambda s: int((s <= 2018).sum())),
                                  n_holdout=('FIRE_YEAR', lambda s: int((s >= 2019).sum())),
                                  rate_large=('LARGE', 'mean'),
                                  cause_missing=('CAUSE3', lambda s: float((s == 'Missing').mean())),
                                  owner_missing=('OWNER6', lambda s: float((s == 'Missing').mean())),
                                  erc_missing=('erc', lambda s: float(s.isna().mean())))
    cov['n_train_large'] = df[df.FIRE_YEAR <= 2018].groupby('STATE').LARGE.sum()
    res['coverage_by_state'] = cov.reset_index().to_dict('records')
    # practitioner lookup (backlog S-4.4): share reaching 300 acres by region x month x cause, training years only
    lk = tr.groupby(['REGION', 'MONTH', 'CAUSE3'], observed=True).LARGE.agg(['size', 'mean']).reset_index()
    res['base_rate_lookup'] = [{'region': r.REGION, 'month': int(r.MONTH), 'cause': r.CAUSE3, 'n': int(r['size']),
                                'rate': (float(r['mean']) if r['size'] >= 100 else None)} for _, r in lk.iterrows()]
    # save models and tables
    joblib.dump(model, os.path.join(md, 'large_fire_hgb.joblib'))
    joblib.dump(iso, os.path.join(md, 'large_fire_isotonic.joblib'))
    joblib.dump(m_geo, os.path.join(md, 'large_fire_hgb_geography_season_only.joblib'))
    joblib.dump(lr, os.path.join(md, 'large_fire_logreg.joblib'))
    joblib.dump(model_mtbs, os.path.join(md, 'mtbs_hgb.joblib'))
    _dump(res, os.path.join(md, 'final_holdout.json'))
    pd.DataFrame({k: _short(v) for k, v in res['overall'].items()}).T.to_csv(os.path.join(md, 'final_overall.csv'))
    pd.DataFrame(res['overall']['hgb_full']['reliability']).to_csv(os.path.join(md, 'final_reliability_hgb_full.csv'),
                                                                   index=False)
    pd.DataFrame(res['importance']).drop(columns='features').to_csv(os.path.join(md, 'final_importance.csv'), index=False)
    cov.to_csv(os.path.join(md, 'final_coverage_by_state.csv'))
    pd.DataFrame([{'region': r, 'model': k, **v} for r, d in res['per_region'].items() for k, v in d.items()
                  if isinstance(v, dict)]).to_csv(os.path.join(md, 'final_per_region.csv'), index=False)
    pd.DataFrame([{'state': s, 'model': k, **v} for s, d in res['per_state'].items() for k, v in d.items()
                  if isinstance(v, dict)]).to_csv(os.path.join(md, 'final_per_state.csv'), index=False)
    return res


# ------------------------------------------------------------------ figures

def make_figures(res: dict[str, Any], dev: dict[str, Any], out: str) -> list[str]:
    from . import figures as F
    import matplotlib.pyplot as plt
    fig_dir = os.path.join(out, 'figures')
    paths = []
    n_test = res['n_test']
    names = {'climatology_cell_month': 'Cell x month climatology', 'logistic_regression': 'Logistic regression',
             'hgb_geography_season_only': 'HGB, geography + season only', 'hgb_full': 'HGB, all features'}
    colors = {'climatology_cell_month': F.SERIES[3], 'logistic_regression': F.SERIES[2],
              'hgb_geography_season_only': F.SERIES[1], 'hgb_full': F.SERIES[0]}

    # 1. reliability diagram
    fig, ax = plt.subplots(figsize=(F.FIG_W, 4.8))
    lim = 0
    for k in ['climatology_cell_month', 'hgb_geography_season_only', 'hgb_full']:
        rel = res['overall'][k]['reliability']
        x = [r['mean_predicted'] for r in rel]
        yv = [r['observed_rate'] for r in rel]
        lim = max(lim, max(x), max(yv))
        ax.plot(x, yv, color=colors[k], lw=2, marker='o', ms=6, mec=F.SURFACE, mew=1.5, label=names[k])
    rel = res['overall']['hgb_full']['reliability']
    for r in rel[-3:]:
        ax.annotate(f"n = {r['n']:,}, {r['n_positive']:,} large", (r['mean_predicted'], r['observed_rate']),
                    xytext=(8, -4), textcoords='offset points', fontsize=8, color=F.INK2)
    ax.plot([0, lim * 1.05], [0, lim * 1.05], color=F.NEUTRAL, lw=1, label='Perfect calibration')
    ax.set_xlabel('Mean predicted P(fire reaches 300 acres), per decile of scores')
    ax.set_ylabel('Observed share of fires that reached 300 acres')
    ax.set_title('Reliability on the 2019-2020 holdout: 10 quantile bins', loc='left')
    ax.legend(loc='upper left')
    F._clean(ax)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    F._footer(fig, f'{n_test:,} holdout fires, {res["overall"]["hgb_full"]["n_positive"]:,} large',
              'Each point is one tenth of the holdout fires ranked by score. Base rate '
              f'{res["overall"]["hgb_full"]["base_rate_test"]:.3f}.')
    paths.append(F._save(fig, fig_dir, 'model_reliability.png'))

    # 2. PR curves
    fig, ax = plt.subplots(figsize=(F.FIG_W, 4.8))
    for k in ['climatology_cell_month', 'logistic_regression', 'hgb_geography_season_only', 'hgb_full']:
        pts = res['pr_curves'][k]
        ax.plot([p['recall'] for p in pts], [p['precision'] for p in pts], color=colors[k], lw=2,
                label=f"{names[k]} (PR-AUC {res['overall'][k]['pr_auc']:.3f})")
    br = res['overall']['base_rate']['base_rate_test']
    ax.axhline(br, color=F.NEUTRAL, lw=1)
    ax.annotate(f'Base rate {br:.3f}', (0.98, br), xytext=(0, 4), textcoords='offset points', ha='right', fontsize=8,
                color=F.INK2)
    ax.set_xlabel('Recall (share of large fires flagged)')
    ax.set_ylabel('Precision (share of flagged fires that were large)')
    ax.set_ylim(0, min(1, max(0.2, max(p['precision'] for p in res['pr_curves']['hgb_full'][1:]) * 1.1)))
    ax.set_xlim(0, 1)
    ax.set_title('Precision-recall on the 2019-2020 holdout', loc='left')
    ax.legend(loc='upper right')
    F._clean(ax)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    F._footer(fig, f'{n_test:,} holdout fires', 'All baselines fitted on 2010-2018 only.')
    paths.append(F._save(fig, fig_dir, 'model_pr_curves.png'))

    # 3. ablation bars (fold-mean PR-AUC with per-fold range)
    abl = pd.DataFrame(dev['ablation'])
    g = abl.groupby('group').agg(label=('label', 'first'), mean=('pr_auc', 'mean'), lo=('pr_auc', 'min'),
                                 hi=('pr_auc', 'max')).reset_index()
    clim_mean = np.mean([f['models']['climatology_cell_month']['pr_auc'] for f in dev['folds']])
    fig, ax = plt.subplots(figsize=(F.FIG_W, 4.4))
    ypos = np.arange(len(g))[::-1]
    ax.barh(ypos, g['mean'], height=0.55, color=F.SERIES[0])
    ax.errorbar(g['mean'], ypos, xerr=[g['mean'] - g['lo'], g['hi'] - g['mean']], fmt='none', ecolor=F.INK2,
                elinewidth=1, capsize=3)
    ax.axvline(clim_mean, color=F.SERIES[3], lw=1.5)
    ax.annotate(f'cell x month lookup {clim_mean:.3f}', (clim_mean, -0.75), xytext=(4, 0), textcoords='offset points',
                fontsize=8, color=F.INK2, va='center')
    ax.set_ylim(-1.1, len(g) - 0.4)
    for yy, v in zip(ypos, g['mean']):
        ax.annotate(f'{v:.3f}', (v, yy), xytext=(-4, 0), textcoords='offset points', ha='right', va='center',
                    fontsize=8, color=F.SURFACE)
    ax.set_yticks(ypos)
    ax.set_yticklabels([f"{r.group}: {r.label}" for r in g.itertuples()], fontsize=8)
    ax.set_xlabel('PR-AUC (bar: mean of four folds; whisker: range)')
    fig.suptitle('What each feature group adds (2015-2018 folds)', x=0.01, ha='left', fontweight='bold')
    F._clean(ax, y_grid=False)
    ax.xaxis.grid(True)
    ax.set_axisbelow(True)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    F._footer(fig, ', '.join(f"{f['n_test']:,} ({f['test_year']})" for f in dev['folds']) + ' test fires',
              'Each group adds to the previous one. Development years only; the holdout is untouched.')
    paths.append(F._save(fig, fig_dir, 'model_ablation.png'))

    # 4. grouped permutation importance with intervals
    imp = pd.DataFrame(res['importance'])
    fig, ax = plt.subplots(figsize=(F.FIG_W, 4.4))
    ypos = np.arange(len(imp))[::-1]
    ax.barh(ypos, imp['pr_auc_drop_mean'], height=0.55, color=F.SERIES[0])
    ax.errorbar(imp['pr_auc_drop_mean'], ypos, xerr=[imp['pr_auc_drop_mean'] - imp['pr_auc_drop_low'],
                                                     imp['pr_auc_drop_high'] - imp['pr_auc_drop_mean']],
                fmt='none', ecolor=F.INK2, elinewidth=1, capsize=3)
    ax.set_yticks(ypos)
    ax.set_yticklabels([f"{r.group} ({r.n_features})" for r in imp.itertuples()], fontsize=9)
    ax.set_xlabel(f"Drop in holdout PR-AUC when shuffled (base {imp['base_pr_auc'].iloc[0]:.3f}, uncalibrated)")
    fig.suptitle('Which inputs carry the ranking (2019-2020 holdout)', x=0.01, ha='left', fontweight='bold')
    F._clean(ax, y_grid=False)
    ax.xaxis.grid(True)
    ax.set_axisbelow(True)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    F._footer(fig, f'{n_test:,} holdout fires', f"Whiskers: min to max over {imp['n_repeats'].iloc[0]} permutations. "
              'Groups overlap, so drops do not sum. Calibration is monotone, so the ranking is unchanged.')
    paths.append(F._save(fig, fig_dir, 'model_importance.png'))

    # 5. per-year PR-AUC (development folds + holdout years)
    rows = []
    for f in dev['folds']:
        for k in ['climatology_cell_month', 'hgb_geography_season_only', 'hgb_full']:
            rows.append({'year': f['test_year'], 'model': k, 'pr_auc': f['models'][k]['pr_auc'], 'phase': 'development'})
    for yr, d in res['per_year'].items():
        for k in ['climatology_cell_month', 'hgb_geography_season_only', 'hgb_full']:
            rows.append({'year': int(yr), 'model': k, 'pr_auc': d[k]['pr_auc'], 'phase': 'holdout'})
    py = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(F.FIG_W, 4.2))
    for k in ['climatology_cell_month', 'hgb_geography_season_only', 'hgb_full']:
        s = py[py.model == k].sort_values('year')
        ax.plot(s.year, s.pr_auc, color=colors[k], lw=2, marker='o', ms=6, mec=F.SURFACE, mew=1.5, label=names[k])
    ax.axvspan(2018.5, 2020.5, color=F.GRID, alpha=0.5, lw=0)
    ax.annotate('Locked holdout', (2019.5, ax.get_ylim()[1]), xytext=(0, -12), textcoords='offset points', ha='center',
                fontsize=8, color=F.INK2)
    ax.set_xticks(sorted(py.year.unique()))
    ax.set_ylabel('PR-AUC on that year')
    ax.set_xlabel('Test year (trained on 2010 through the previous year; holdout years use 2010-2018)')
    ax.set_title('Skill by year: development folds and the holdout', loc='left')
    ax.set_ylim(0, max(py.pr_auc) * 1.25)
    ax.legend(loc='upper left', ncol=1)
    F._clean(ax)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    F._footer(fig, ', '.join(f"{f['n_test']:,}" for f in dev['folds']) + f' fires per fold; {n_test:,} in the holdout')
    paths.append(F._save(fig, fig_dir, 'model_per_year.png'))
    return paths


# ------------------------------------------------------------------ claims

def register_claims(res: dict[str, Any], dev: dict[str, Any], info: dict[str, Any], out: str) -> int:
    set_source('analysis.large_fire')
    n_te, n_tr = res['n_test'], res['n_train']
    claim('model.sample', {k: v for k, v in info.items() if k != 'categorical_encoding'}, info['definition'],
          info['n_sample'])
    claim('model.protocol', {'holdout_years': list(HOLDOUT_YEARS), 'development_years': list(DEV_YEARS),
                             'temporal_folds': [{'train_through': a, 'test_year': b} for a, b in TEMPORAL_FOLDS],
                             'spent_looks_at_holdout': ['E-008 (exploratory, defaults, no selection)',
                                                        'E-015 (this final evaluation)']},
          'Locked holdout protocol from docs/EXPERIMENTS.md', n_te)
    claim('model.chosen_config', res['chosen'], 'HGB configuration chosen by mean temporal-fold PR-AUC', n_tr)
    claim('model.holdout_overall', {k: _short(v) for k, v in res['overall'].items()},
          'Metrics on all 2019-2020 CONUS fires, every model fitted on 2010-2018', n_te,
          note='hgb_full = ' + res['final_prediction'] + '. Correction: top_decile_recall for hgb_full and '
               'hgb_full_isotonic counts the top 12.0% of fires, not 10%, because the isotonic scores are tied at '
               'the cut; the exact share at 10% is in model.capture_at_top (0.741). The other models flag exactly 10%.')
    claim('model.holdout_bootstrap', res['bootstrap'], '95% percentile bootstrap intervals, 1,000 row resamples', n_te)
    claim('model.holdout_reliability', {k: res['overall'][k]['reliability'] for k in
                                        ['climatology_cell_month', 'hgb_geography_season_only', 'hgb_full_raw', 'hgb_full']},
          '10 quantile bins of predicted probability with n, positives, mean predicted and observed rate', n_te)
    claim('model.holdout_pr_curves', res['pr_curves'], 'Precision-recall curve points, about 200 per model', n_te)
    claim('model.holdout_per_year', res['per_year'], 'Holdout metrics for 2019 and 2020 separately', n_te)
    claim('model.holdout_per_region', res['per_region'], 'Holdout metrics by region; ' + info['region_definition'], n_te)
    claim('model.holdout_per_state', res['per_state'], 'Holdout metrics for the ten states with the most fires 2010-2020',
          n_te)
    claim('model.ablation', dev['ablation'], 'Temporal-fold PR-AUC and Brier skill for cumulative feature groups G0..G6',
          None)
    claim('model.develop_folds', [{'test_year': f['test_year'], 'n_test': f['n_test'], **{k: v for k, v in f['models'].items()}}
                                  for f in dev['folds']], 'Baselines per temporal fold', None)
    claim('model.tuning_grid', [{k: v for k, v in r.items() if k != 'per_year'} for r in dev['grid']],
          'Every HGB configuration tried, mean and min PR-AUC over the temporal folds', None)
    claim('model.calibration', {k: v for k, v in dev['calibration'].items() if k != 'raw_2018'} |
          {'raw_2018': _short(dev['calibration']['raw_2018']), 'raw_2018_reliability': dev['calibration']['raw_2018']['reliability']},
          'Calibration decision on the 2018 fold', None)
    claim('model.spatial_cv', dev['spatial'], 'GroupKFold(3) by 1-degree cell on 2010-2018 (secondary check)', None)
    claim('model.importance', res['importance'], 'Grouped permutation importance on the holdout, PR-AUC drop', n_te)
    claim('model.mtbs', res['mtbs'], 'Secondary label: MTBS_ID present (>= 1,000 acres West, >= 500 East)', n_te)
    claim('model.mtbs_develop', dev['mtbs'], 'Secondary label on the temporal folds', None)
    claim('model.coverage_by_state', res['coverage_by_state'],
          'Training and holdout counts, large-fire rate and missingness by state (area of applicability)', info['n_sample'])
    claim('model.coverage_note', (
        f"CONUS model: {info['n_dropped_non_conus']:,} fires in AK, HI and PR were dropped because the attribute dataset "
        f"is CONUS-only; Alaska alone holds {info['alaska_share_of_class_g_acres_2010_2020']:.0%} of Class G acres in "
        '2010-2020, so nothing here applies to Alaska. Texas records are dominated by a 2011-2012 coverage jump and '
        'local reporters; states with mostly missing cause carry a "Missing" cause level that is a reporter indicator.'),
        'Area-of-applicability statement', info['n_sample'])

    # ---- the claims the site's Prediction page reads (contract in docs/SITE.md)
    fk = res['final_prediction']
    labels = [('hgb_full', f'Gradient boosting, all features ({"isotonic-calibrated" if fk.endswith("isotonic") else "uncalibrated"})', False, fk),
              ('hgb_geography_season_only', 'Gradient boosting, location and season only', True, 'hgb_geography_season_only'),
              ('logistic_regression', 'Logistic regression, all features', True, 'logistic_regression'),
              ('climatology_cell_month', 'Lookup: training rate by 1-degree cell and month', True, 'climatology_cell_month'),
              ('base_rate', 'Base rate (predict the 2010-2018 rate for every fire)', True, 'base_rate')]
    # top-decile capture is reported exactly in model.capture_at_top (see the note on model.holdout_overall)
    names = ['pr_auc', 'roc_auc', 'brier_skill_vs_base_rate']
    rows = []
    for key, label, is_base, boot_key in labels:
        pt, bs = res['overall'][key], res['bootstrap'].get(boot_key, {})
        rows.append({'model': label, 'baseline': is_base,
                     'metrics': {m: [pt[m], bs.get(m, {}).get('low'), bs.get(m, {}).get('high')] for m in names}})
    claim('model.card', {'name': 'Large-fire probability model', 'version': '1.0',
                         'target': 'probability that a newly discovered fire reaches 300 acres (FIRE_SIZE >= 300)',
                         'horizon': 'at discovery; features are those known on the discovery day',
                         'features': FULL_FEATURES, 'train_years': '2010-2018', 'test_years': '2019-2020 (locked holdout)',
                         'run_date': pd.Timestamp.now('UTC').strftime('%Y-%m-%d'), 'experiment_id': 'E-015'},
          'Model identity for the Prediction page; details in docs/MODEL_CARD.md', n_te)
    claim('model.metrics', {'metric_names': names, 'rows': rows},
          'Holdout metrics (all CONUS fires discovered 2019-2020; every model fitted on 2010-2018) with 95% intervals',
          n_te, note='95% percentile bootstrap intervals, 1,000 resamples of the holdout fires, seed 42; the base-rate '
                     'row has ROC-AUC 0.5 and Brier skill 0 by construction')
    claim('model.reliability', {'bins': [{'pred_lo': b['min_predicted'], 'pred_hi': b['max_predicted'],
                                          'mean_pred': b['mean_predicted'], 'obs_rate': b['observed_rate'], 'n': b['n']}
                                         for b in res['overall'][fk]['reliability']]},
          'Ten equal-count bins of the final model\'s predicted probability on the holdout', n_te)
    claim('model.pr_curve', {'base_rate': float(res['overall'][fk]['base_rate_test']),
                             'points': res['pr_curves']['hgb_full']},
          'Precision and recall of the final model on the holdout at about 200 thresholds', n_te)
    claim('model.coverage', {'text': cv_text(info)}, 'Area of applicability, shown on the Prediction page',
          info['n_sample'])
    claim('model.base_rates', {'rows': res['base_rate_lookup']},
          'Share of 2010-2018 CONUS fires that reached 300 acres, by region, discovery month and cause classification',
          n_tr, note='rate is null where the group has fewer than 100 fires')
    register_ranking_claims(res)
    return write_claims(os.path.join(out, 'claims_model.json'))


def capture_at_top(curve: list[dict[str, Any]], n: int, shares=(0.01, 0.05, 0.10, 0.20)) -> dict[str, float]:
    """Share of positives among the top k% of scores, interpolated linearly in the number flagged. Within a
    tied score group this is the expected capture under random tie-breaking, so it is exact whenever every
    tie group is a curve point (true for the isotonic scores, which have about 100 distinct values)."""
    xs = np.array([0] + [p['n_flagged'] for p in curve], dtype=float)
    ys = np.array([0.0] + [p['recall'] for p in curve], dtype=float)
    return {f'top_{int(round(s * 100))}pct': float(np.interp(s * n, xs, ys)) for s in shares}


def register_ranking_claims(res: dict[str, Any]) -> None:
    """Claims for presenting the model as a ranking (Robyn's decision): capture at the top of the scores, with
    the calibration failure stated beside it."""
    n = res['n_test']
    labels = {'hgb_full': 'Gradient boosting, all features', 'logistic_regression': 'Logistic regression, all features',
              'hgb_geography_season_only': 'Gradient boosting, location and season only',
              'climatology_cell_month': 'Lookup: training rate by 1-degree cell and month'}
    rows = [{'model': labels[k], 'baseline': k != 'hgb_full', **capture_at_top(res['pr_curves'][k], n)} for k in labels]
    rows.append({'model': 'No ranking (flag fires at random)', 'baseline': True,
                 'top_1pct': 0.01, 'top_5pct': 0.05, 'top_10pct': 0.10, 'top_20pct': 0.20})
    claim('model.capture_at_top', {'rows': rows},
          'Share of the 2019-2020 fires that reached 300 acres found among the top 1/5/10/20% of each model\'s scores',
          n, note='Interpolated in the number of fires flagged along each model\'s holdout precision-recall curve; '
                  'for tied scores this is the expected share under random tie-breaking')
    rel = res['overall'][res['final_prediction']]['reliability']
    top, py = rel[-1], res['per_year']
    claim('model.calibration_failure', {
        'top_decile_mean_score': top['mean_predicted'], 'top_decile_observed_rate': top['observed_rate'],
        'top_decile_n': top['n'],
        'brier_skill_vs_base_rate_overall': res['overall'][res['final_prediction']]['brier_skill_vs_base_rate'],
        'brier_skill_vs_base_rate_by_year': {str(y): py[y]['hgb_full']['brier_skill_vs_base_rate'] for y in py},
        'base_rate_by_year': {str(y): py[y]['hgb_full']['base_rate_test'] for y in py}},
        'Why the scores are not published as probabilities: the top-decile mean score against the observed rate, '
        'and Brier skill against predicting the 2010-2018 base rate, overall and per holdout year', n,
        note='A negative Brier skill means the scores, read as probabilities, do worse than one constant rate')


def cv_text(info: dict[str, Any]) -> str:
    return (f"Trained on {info['by_year'] and sum(v['n'] for k, v in info['by_year'].items() if int(k) <= 2018):,} "
            f"CONUS fires discovered 2010-2018 and tested on the {sum(v['n'] for k, v in info['by_year'].items() if int(k) >= 2019):,} "
            f"discovered 2019-2020. Alaska, Hawaii and Puerto Rico are excluded ({info['n_dropped_non_conus']:,} fires) "
            f"because the weather and fuels attributes cover CONUS only; Alaska holds "
            f"{info['alaska_share_of_class_g_acres_2010_2020']:.0%} of 2010-2020 Class G acres, so nothing here applies "
            "to it. Where a state's records come mostly from local reporters with no recorded cause (Texas, Kansas), "
            "the cause input is a reporter indicator rather than a cause.")


# ------------------------------------------------------------------ main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--stage', choices=['build', 'develop', 'final', 'all', 'claims'], default='all',
                    help='claims: re-register claims and figures from the saved results (no refit, no new look)')
    ap.add_argument('--out', default=os.path.join(REPO_ROOT, 'outputs'))
    ap.add_argument('--quick', action='store_true', help='15% subsample, 2 grid configs, 200 bootstraps (smoke test)')
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')
    t0 = time.time()
    md = _model_dir(args.out)
    if args.stage == 'claims':
        with open(os.path.join(md, 'sample.json')) as f:
            info = json.load(f)
        with open(os.path.join(md, 'develop_results.json')) as f:
            dev = json.load(f)
        with open(os.path.join(md, 'final_holdout.json')) as f:
            res = json.load(f)
        res['per_year'] = {int(k): v for k, v in res['per_year'].items()}
        figs = make_figures(res, dev, args.out)
        n = register_claims(res, dev, info, args.out)
        log.info(f'claims stage: {n} claims and {len(figs)} figures from saved results')
        return 0
    df, info = build_sample(quick=args.quick)
    if args.stage in ('build', 'all'):
        stage_build(df, info, args.out)
    dev = None
    if args.stage in ('develop', 'all'):
        dev = stage_develop(df, args.out, quick=args.quick)
    if args.stage in ('final', 'all'):
        if dev is None:
            with open(os.path.join(md, 'develop_results.json')) as f:
                dev = json.load(f)
        res = stage_final(df, info, args.out, quick=args.quick)
        figs = make_figures(res, dev, args.out)
        n = register_claims(res, dev, info, args.out)
        log.info(f'wrote {n} claims and {len(figs)} figures')
    log.info(f'done in {(time.time() - t0) / 60:.1f} min')
    return 0


if __name__ == '__main__':
    sys.exit(main())
