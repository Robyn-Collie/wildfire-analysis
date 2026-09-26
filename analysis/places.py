"""Place briefs and the prevention calendar: the FPA FOD record summarised for people who plan for one state.

Each state brief answers the questions a prevention planner, a land manager or a reporter asks first: when do
fires start here and from what, which of them become large, is burned area changing, how much of it is on
protected land, what burned homes, and how complete is the record. Every count-based number is computed inside
the state's usable reporting window from the coverage mask (analysis/coverage.py): outside it, record counts
change because reporting systems joined or left, not because fires did.

Usage (from the repo root):
    python -m analysis.places --out outputs/

Needs:
    data/fires.parquet
    outputs/coverage_state_year.csv                         (python -m analysis.conservation)
    data/external/padus/fires_padus.parquet                 (PAD-US join; optional, section skipped without it)
    data/external/ics209plus/.../ics209-plus-wf_incidents_1999to2020.csv   (optional)

Writes:
    outputs/claims_places.json                  one claim per state (places.state.XX) plus the calendar claims
    outputs/tables/places_summary.csv           one row per state
    outputs/tables/calendar/XX.csv              fires by month x general cause, per state, usable window
    outputs/tables/calendar_regions.csv         the same by region, usable state-years only
    outputs/tables/state_year.csv               fires, acres and large fires per state-year with the usable flag
"""
from __future__ import annotations

import argparse
import logging
import os
import time

import numpy as np
import pandas as pd
from scipy import stats

from .common import (CAUSE_MISSING, MONTH_ABBR, OWNER_MISSING, REGION_ORDER, REPO_ROOT, claim, gacc_of, load_fires,
                     normalize_owner, region_of, set_source, write_claims)
from .conservation import ICS_INCIDENTS, PADUS_OUT, load_ics

log = logging.getLogger('places')

STATE_NAMES = {
    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California', 'CO': 'Colorado',
    'CT': 'Connecticut', 'DE': 'Delaware', 'DC': 'District of Columbia', 'FL': 'Florida', 'GA': 'Georgia',
    'HI': 'Hawaii', 'ID': 'Idaho', 'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas',
    'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland', 'MA': 'Massachusetts', 'MI': 'Michigan',
    'MN': 'Minnesota', 'MS': 'Mississippi', 'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada',
    'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York', 'NC': 'North Carolina',
    'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma', 'OR': 'Oregon', 'PA': 'Pennsylvania',
    'PR': 'Puerto Rico', 'RI': 'Rhode Island', 'SC': 'South Carolina', 'SD': 'South Dakota', 'TN': 'Tennessee',
    'TX': 'Texas', 'UT': 'Utah', 'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia',
    'WI': 'Wisconsin', 'WY': 'Wyoming',
}
COLUMNS = ['FOD_ID', 'FIRE_YEAR', 'DISCOVERY_DATE', 'DISCOVERY_MONTH', 'STATE', 'FIRE_SIZE',
           'NWCG_CAUSE_CLASSIFICATION', 'NWCG_GENERAL_CAUSE', 'OWNER_DESCR', 'CONT_DATE',
           'ICS_209_PLUS_INCIDENT_JOIN_ID', 'FIRE_NAME']
LARGE = 300.0
MIN_TREND_YEARS = 15
YEARS = list(range(1992, 2021))
CAUSE_CLASSES = ['Human', 'Natural', CAUSE_MISSING]
GENERAL_ORDER = ['Debris and open burning', 'Arson/incendiarism', 'Equipment and vehicle use', 'Recreation and ceremony',
                 'Smoking', 'Misuse of fire by a minor', 'Railroad operations and maintenance',
                 'Power generation/transmission/distribution', 'Fireworks', 'Firearms and explosives use',
                 'Other causes', 'Natural', CAUSE_MISSING]
GAP_LABEL = {'1': 'GAP 1-2 (managed for biodiversity)', '2': 'GAP 1-2 (managed for biodiversity)',
             '3': 'GAP 3 (multiple use)', '4': 'GAP 4 (no known mandate)', 'none': 'Not in PAD-US',
             'unmatched': 'Not in PAD-US'}
GAP_ORDER = ['GAP 1-2 (managed for biodiversity)', 'GAP 3 (multiple use)', 'GAP 4 (no known mandate)', 'Not in PAD-US']
USABLE_NOTE = ('Counted inside the state\'s usable reporting window (analysis/coverage.py): the longest run of years '
               'with no reporting break.')


def trend(years: np.ndarray, values: np.ndarray) -> dict:
    tau, p = stats.kendalltau(years, values)
    slope, intercept, lo, hi = stats.theilslopes(values, years)
    return {'years': [int(years.min()), int(years.max())], 'n_years': int(len(years)), 'kendall_tau': float(tau),
            'kendall_p': float(p), 'theil_sen_slope': float(slope), 'slope_ci95': [float(lo), float(hi)],
            'first_half_mean': float(values[:len(values) // 2].mean()),
            'second_half_mean': float(values[len(values) - len(values) // 2:].mean())}


def trend_words(t: dict | None, unit: str) -> str:
    if t is None:
        return f'The usable window is shorter than {MIN_TREND_YEARS} years, too short for a trend test.'
    span = f'{t["years"][0]}-{t["years"][1]}'
    if t['kendall_p'] >= 0.05:
        return f'No detectable trend in {unit}, {span} (Kendall p = {t["kendall_p"]:.2f}).'
    way = 'upward' if t['kendall_tau'] > 0 else 'downward'
    return f'An {way} trend in {unit}, {span} (Kendall tau {t["kendall_tau"]:.2f}, p = {t["kendall_p"]:.3f}).'


def load(out_dir: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = load_fires(COLUMNS)
    df['REGION'] = region_of(df['STATE'])
    df['LARGE'] = df['FIRE_SIZE'] >= LARGE
    df['CAUSE'] = df['NWCG_CAUSE_CLASSIFICATION'].astype(str)
    df['GENERAL'] = df['NWCG_GENERAL_CAUSE'].astype(str)
    df['OWNER'] = normalize_owner(df['OWNER_DESCR'])
    df['MONTH'] = df['DISCOVERY_MONTH'].astype(int)
    cov = pd.read_csv(os.path.join(out_dir, 'coverage_state_year.csv'))
    ok = cov.set_index(['STATE', 'FIRE_YEAR'])['coverage_ok']
    key = pd.MultiIndex.from_arrays([df['STATE'].astype(str), df['FIRE_YEAR'].astype(int)])
    df['USABLE'] = ok.reindex(key).fillna(False).to_numpy(dtype=bool)
    return df, cov


def padus_table(df: pd.DataFrame) -> pd.DataFrame | None:
    if not os.path.exists(PADUS_OUT):
        log.warning(f'PAD-US join not found ({PADUS_OUT}); protected-land section skipped')
        return None
    p = pd.read_parquet(PADUS_OUT, columns=['FOD_ID', 'Unit_Nm', 'Mang_Type', 'Mang_Name', 'Des_Tp', 'GAP_Sts'])
    g = p['GAP_Sts'].astype(object)
    cat = pd.Series('unmatched', index=p.index, dtype=object)
    inpad = p['Unit_Nm'].notna() & (p['Unit_Nm'] != 'Non-PAD-US Area')
    cat[inpad] = g[inpad].astype(str)
    cat[p['Unit_Nm'] == 'Non-PAD-US Area'] = 'none'
    p['GAP'] = cat.map(GAP_LABEL).fillna('Not in PAD-US')
    p['IN_PAD'] = inpad
    return df[['FOD_ID', 'STATE', 'FIRE_SIZE']].merge(p, on='FOD_ID', how='left')


def ics_incidents(df: pd.DataFrame) -> pd.DataFrame | None:
    """One row per ICS-209-PLUS wildfire incident matched to the FPA FOD, with state and cause of its largest fire."""
    if not os.path.exists(ICS_INCIDENTS):
        log.warning('ICS-209-PLUS not found; losses section skipped')
        return None
    inc = load_ics()
    j = df[df['ICS_209_PLUS_INCIDENT_JOIN_ID'].notna()]
    j = j[j['ICS_209_PLUS_INCIDENT_JOIN_ID'].astype(str).isin(set(inc['INCIDENT_ID']))]
    rep = j.sort_values('FIRE_SIZE', ascending=False).drop_duplicates('ICS_209_PLUS_INCIDENT_JOIN_ID')
    rep = rep.set_index('ICS_209_PLUS_INCIDENT_JOIN_ID')[['STATE', 'FIRE_YEAR', 'CAUSE', 'GENERAL', 'FIRE_NAME']]
    out = rep.join(inc.set_index('INCIDENT_ID')[['INCIDENT_NAME', 'STR_DESTROYED_TOTAL', 'STR_DESTROYED_RES_TOTAL',
                                                  'FATALITIES', 'FINAL_ACRES', 'INCTYP_ABBREVIATION']], how='inner')
    return out


def brief(st: str, d: pd.DataFrame, cov: pd.DataFrame, pad: pd.DataFrame | None, ics: pd.DataFrame | None) -> dict:
    c = cov[cov['STATE'] == st].set_index('FIRE_YEAR')
    w0, w1 = int(c['window_start'].iloc[0]), int(c['window_end'].iloc[0])
    breaks = [int(y) for y in c.index[c['break']]]
    zero = [int(y) for y in c.index[c['zero']]]
    u = d[d['USABLE']]
    n_u_years = w1 - w0 + 1
    per_year = pd.DataFrame({
        'fires': d.groupby('FIRE_YEAR').size(),
        'acres': d.groupby('FIRE_YEAR')['FIRE_SIZE'].sum(),
        'large_fires': d[d['LARGE']].groupby('FIRE_YEAR').size(),
        'large_acres': d[d['LARGE']].groupby('FIRE_YEAR')['FIRE_SIZE'].sum(),
    }).reindex(YEARS).fillna(0)
    per_year['usable'] = [(w0 <= y <= w1) for y in YEARS]

    # Calendar: fires per year by month and cause class, usable window.
    cal = u.groupby(['MONTH', 'CAUSE']).size().unstack(fill_value=0).reindex(index=range(1, 13), columns=CAUSE_CLASSES,
                                                                              fill_value=0)
    cal_rate = cal / n_u_years
    by_month = cal.sum(axis=1)
    human_peak = int(cal['Human'].idxmax()) if cal['Human'].sum() else None
    natural_peak = int(cal['Natural'].idxmax()) if cal['Natural'].sum() else None
    gen = u['GENERAL'].value_counts()
    known_human = u[(u['CAUSE'] == 'Human') & (u['GENERAL'] != CAUSE_MISSING)]['GENERAL'].value_counts()
    top_human = [{'cause': k, 'fires': int(v), 'share_of_known_human': float(v / known_human.sum())}
                 for k, v in known_human.head(5).items()] if len(known_human) else []
    # For the top human cause, the months it peaks in.
    for t in top_human[:3]:
        m = u[u['GENERAL'] == t['cause']].groupby('MONTH').size().reindex(range(1, 13), fill_value=0)
        t['peak_months'] = [MONTH_ABBR[i - 1] for i in m.sort_values(ascending=False).index[:3]]

    # Which fires become large: share reaching 300 acres by month and cause class, usable window.
    lg = u.groupby(['CAUSE', 'MONTH'])['LARGE'].agg(['size', 'sum'])
    large_rate = {cause: {MONTH_ABBR[m - 1]: {'fires': int(lg.loc[(cause, m), 'size']),
                                              'large': int(lg.loc[(cause, m), 'sum']),
                                              'rate': float(lg.loc[(cause, m), 'sum'] / lg.loc[(cause, m), 'size'])}
                          for m in range(1, 13) if (cause, m) in lg.index}
                  for cause in CAUSE_CLASSES}
    large_u = u[u['LARGE']]
    large_by_cause = large_u['CAUSE'].value_counts().reindex(CAUSE_CLASSES, fill_value=0)
    large_acres_by_cause = large_u.groupby('CAUSE')['FIRE_SIZE'].sum().reindex(CAUSE_CLASSES, fill_value=0)

    # Trends, inside the usable window only.
    py = per_year[per_year['usable']]
    t_acres = trend(py.index.to_numpy(), py['acres'].to_numpy()) if len(py) >= MIN_TREND_YEARS else None
    t_large = trend(py.index.to_numpy(), py['large_fires'].to_numpy()) if len(py) >= MIN_TREND_YEARS else None
    t_fires = trend(py.index.to_numpy(), py['fires'].to_numpy()) if len(py) >= MIN_TREND_YEARS else None

    out = {
        'state': st, 'name': STATE_NAMES.get(st, st), 'region': d['REGION'].iloc[0],
        'gacc': gacc_of(pd.Series([st])).iloc[0],
        'fires': int(len(d)), 'acres': float(d['FIRE_SIZE'].sum()),
        'large_fires': int(d['LARGE'].sum()), 'large_share_of_acres': float(d.loc[d['LARGE'], 'FIRE_SIZE'].sum() / max(d['FIRE_SIZE'].sum(), 1e-9)),
        'window': [w0, w1], 'window_years': n_u_years, 'break_years': breaks, 'zero_years': zero,
        'fires_in_window': int(len(u)), 'fires_per_year_in_window': float(len(u) / n_u_years),
        'acres_per_year_in_window': float(u['FIRE_SIZE'].sum() / n_u_years),
        'per_year': {int(y): {'fires': int(r['fires']), 'acres': float(r['acres']), 'large_fires': int(r['large_fires']),
                              'large_acres': float(r['large_acres']), 'usable': bool(r['usable'])}
                     for y, r in per_year.iterrows()},
        'calendar_per_year': {MONTH_ABBR[m - 1]: {k: float(v) for k, v in cal_rate.loc[m].items()} for m in range(1, 13)},
        'busiest_month': MONTH_ABBR[int(by_month.idxmax()) - 1] if by_month.sum() else None,
        'busiest_month_share': float(by_month.max() / by_month.sum()) if by_month.sum() else None,
        'human_peak_month': MONTH_ABBR[human_peak - 1] if human_peak else None,
        'natural_peak_month': MONTH_ABBR[natural_peak - 1] if natural_peak else None,
        'cause_shares': {k: float(v / len(u)) for k, v in u['CAUSE'].value_counts().reindex(CAUSE_CLASSES, fill_value=0).items()} if len(u) else {},
        'general_cause_counts': {k: int(gen.get(k, 0)) for k in GENERAL_ORDER},
        'top_human_causes': top_human,
        'large_rate_by_month': large_rate,
        'large_rate_overall': float(u['LARGE'].mean()) if len(u) else None,
        'large_fires_by_cause': large_by_cause.astype(int).to_dict(),
        'large_acres_by_cause': large_acres_by_cause.astype(float).to_dict(),
        'trend_acres': t_acres, 'trend_acres_words': trend_words(t_acres, 'acres burned'),
        'trend_large_fires': t_large, 'trend_large_words': trend_words(t_large, 'fires of 300+ acres'),
        'trend_fires': t_fires,
        'completeness': {
            'cause_missing_share': float((d['CAUSE'] == CAUSE_MISSING).mean()),
            'general_cause_missing_share': float((d['GENERAL'] == CAUSE_MISSING).mean()),
            'owner_missing_share': float((d['OWNER'] == OWNER_MISSING).mean()),
            'containment_date_missing_share': float(d['CONT_DATE'].isna().mean()),
            'cause_missing_share_in_window': float((u['CAUSE'] == CAUSE_MISSING).mean()) if len(u) else None,
        },
    }
    if pad is not None:
        p = pad[pad['STATE'] == st]
        by_gap = p.groupby('GAP').agg(fires=('FOD_ID', 'size'), acres=('FIRE_SIZE', 'sum')).reindex(GAP_ORDER, fill_value=0)
        tot_f, tot_a = max(by_gap['fires'].sum(), 1), max(by_gap['acres'].sum(), 1e-9)
        units = (p[p['IN_PAD']].groupby(['Unit_Nm', 'Mang_Name', 'Des_Tp', 'Mang_Type'])
                 .agg(fires=('FOD_ID', 'size'), acres=('FIRE_SIZE', 'sum')).reset_index()
                 .sort_values('acres', ascending=False))
        trib = p[p['Mang_Type'] == 'TRIB']
        out['protected'] = {
            'by_gap': {g: {'fires': int(r['fires']), 'acres': float(r['acres']), 'fire_share': float(r['fires'] / tot_f),
                           'acre_share': float(r['acres'] / tot_a)} for g, r in by_gap.iterrows()},
            'top_units': [{'unit': r['Unit_Nm'], 'manager': r['Mang_Name'], 'designation': r['Des_Tp'],
                           'manager_type': r['Mang_Type'], 'fires': int(r['fires']), 'acres': float(r['acres'])}
                          for _, r in units.head(6).iterrows()],
            'tribal': {'fires': int(len(trib)), 'acres': float(trib['FIRE_SIZE'].sum())},
        }
    if ics is not None:
        s = ics[ics['STATE'] == st]
        wf = s[s['INCTYP_ABBREVIATION'].isin(['WF', 'CX'])]
        destroyed = wf['STR_DESTROYED_TOTAL'].fillna(0)
        by_cause = wf.assign(D=destroyed).groupby('CAUSE').agg(incidents=('D', 'size'), destroyed=('D', 'sum'))
        by_general = (wf.assign(D=destroyed)[wf['CAUSE'] == 'Human'].groupby('GENERAL')['D'].sum()
                      .sort_values(ascending=False))
        top = wf.assign(D=destroyed).sort_values('D', ascending=False)
        out['losses'] = {
            'incidents': int(len(wf)), 'structures_destroyed': float(destroyed.sum()),
            'residences_destroyed': float(wf['STR_DESTROYED_RES_TOTAL'].fillna(0).sum()),
            'incidents_with_destroyed': int((destroyed > 0).sum()),
            'fatalities_reported': float(wf['FATALITIES'].fillna(0).sum()),
            'by_cause': {k: {'incidents': int(r['incidents']), 'destroyed': float(r['destroyed'])}
                         for k, r in by_cause.iterrows()},
            'human_by_general_cause': {k: float(v) for k, v in by_general.head(5).items() if v > 0},
            'top_incidents': [{'name': r['INCIDENT_NAME'], 'year': int(r['FIRE_YEAR']), 'destroyed': float(r['D']),
                               'cause': r['CAUSE'], 'general_cause': r['GENERAL']}
                              for _, r in top.head(5).iterrows() if r['D'] > 0],
        }
    return out


def calendar(df: pd.DataFrame, tab_dir: str) -> None:
    """Prevention calendar claims: region x month x cause, holiday spikes, unknown-cause shares."""
    u = df[df['USABLE']]
    n = len(u)
    reg = (u.groupby(['REGION', 'MONTH', 'GENERAL']).size().rename('fires').reset_index())
    reg['month'] = reg['MONTH'].map(lambda m: MONTH_ABBR[m - 1])
    reg[['REGION', 'MONTH', 'month', 'GENERAL', 'fires']].to_csv(os.path.join(tab_dir, 'calendar_regions.csv'), index=False)

    region_month = {}
    for r in REGION_ORDER:
        x = u[u['REGION'] == r]
        if not len(x):
            continue
        m = x.groupby(['MONTH', 'CAUSE']).size().unstack(fill_value=0).reindex(index=range(1, 13), columns=CAUSE_CLASSES, fill_value=0)
        hl = x[x['LARGE'] & (x['CAUSE'] == 'Human')].groupby('MONTH').size().reindex(range(1, 13), fill_value=0)
        region_month[r] = {MONTH_ABBR[i - 1]: {'human': int(m.loc[i, 'Human']), 'natural': int(m.loc[i, 'Natural']),
                                               'missing': int(m.loc[i, CAUSE_MISSING]), 'human_large': int(hl.loc[i])}
                           for i in range(1, 13)}
    claim('calendar.region_month', region_month,
          'Fires by region, discovery month and cause class (human, natural, cause missing), and human-caused fires '
          'of 300+ acres, counted in usable state-years only. ' + USABLE_NOTE, n)

    known = u[u['GENERAL'] != CAUSE_MISSING]
    hm = known[known['CAUSE'] == 'Human'].groupby(['MONTH', 'GENERAL']).size().unstack(fill_value=0)
    top_by_month = {MONTH_ABBR[m - 1]: {'top': hm.loc[m].idxmax(), 'share': float(hm.loc[m].max() / hm.loc[m].sum())}
                    for m in hm.index}
    claim('calendar.top_human_cause_by_month', top_by_month,
          'For each discovery month, the most common known general cause among human-caused fires, and its share '
          'of human-caused fires with a known general cause (usable state-years).', int(len(known)))

    # Holiday spike: fires discovered on 4-5 July against the same-year average of 24 Jun-1 Jul and 8-15 Jul.
    date = pd.to_datetime(u['DISCOVERY_DATE'])
    md = date.dt.strftime('%m-%d')
    daily = u.groupby([u['FIRE_YEAR'], md]).size()
    base_days = [f'06-{d:02d}' for d in range(24, 31)] + ['07-01'] + [f'07-{d:02d}' for d in range(8, 16)]
    rows = []
    for y in YEARS:
        s = daily.get(y)
        if s is None:
            continue
        base = s.reindex(base_days, fill_value=0).mean()
        rows.append({'year': y, 'jul4': int(s.get('07-04', 0)), 'jul5': int(s.get('07-05', 0)), 'baseline': float(base)})
    j = pd.DataFrame(rows)
    fw = u[md.isin(['07-04', '07-05'])]
    fw_share = float((fw['GENERAL'] == 'Fireworks').mean())
    ny = u[md.isin(['12-31', '01-01'])]
    base_ny = u[md.isin([f'12-{d:02d}' for d in range(20, 28)] + [f'01-{d:02d}' for d in range(5, 13)])]
    claim('calendar.july4', {
        'jul4_mean': float(j['jul4'].mean()), 'jul5_mean': float(j['jul5'].mean()),
        'baseline_mean': float(j['baseline'].mean()), 'jul4_ratio': float(j['jul4'].mean() / j['baseline'].mean()),
        'jul5_ratio': float(j['jul5'].mean() / j['baseline'].mean()),
        'years_jul4_highest_of_year': int(sum(1 for y in YEARS if y in daily.index.get_level_values(0)
                                              and daily.loc[y].idxmax() == '07-04')),
        'fireworks_share_jul4_5': fw_share,
        'cause_missing_share_jul4_5': float((fw['GENERAL'] == CAUSE_MISSING).mean()),
        'fires_jul4_5_total': int(len(fw)),
        'new_year_ratio': float((len(ny) / 2) / (len(base_ny) / 16)),
    }, 'Fires discovered on 4 and 5 July per year (mean over 1992-2020, usable state-years) against the mean of the '
       'same year\'s 24 Jun-1 Jul and 8-15 Jul days; the number of years in which 4 July was the busiest day of the '
       'year; and the share of 4-5 July fires whose general cause is Fireworks. new_year_ratio: 31 Dec and 1 Jan '
       'against 20-27 Dec and 5-12 Jan.', len(fw))
    by_state = []
    for st, x in u.groupby('STATE'):
        d = pd.to_datetime(x['DISCOVERY_DATE']).dt.strftime('%m-%d')
        yrs = x['FIRE_YEAR'].nunique()
        j4 = int((d == '07-04').sum())
        b = int(d.isin(base_days).sum()) / len(base_days)
        if j4 >= 30:
            by_state.append({'state': st, 'jul4_fires': j4, 'ratio': float(j4 / b) if b else None,
                             'fireworks_share': float((x.loc[d == '07-04', 'GENERAL'] == 'Fireworks').mean())})
    by_state.sort(key=lambda r: -(r['ratio'] or 0))
    claim('calendar.july4_by_state', by_state,
          'States with at least 30 fires discovered on 4 July (usable years): 4 July fires, ratio to the mean '
          'baseline day (24 Jun-1 Jul, 8-15 Jul), share with general cause Fireworks.', len(u))

    debris = u[u['GENERAL'] == 'Debris and open burning']
    dm = debris.groupby(['REGION', 'MONTH']).size().unstack(fill_value=0).reindex(columns=range(1, 13), fill_value=0)
    claim('calendar.debris_peak', {r: {'peak_months': [MONTH_ABBR[m - 1] for m in dm.loc[r].sort_values(ascending=False).index[:3]],
                                       'mar_apr_share': float(dm.loc[r, [3, 4]].sum() / dm.loc[r].sum())}
                                   for r in dm.index if dm.loc[r].sum() >= 1000},
          'Debris and open burning fires: the three busiest discovery months per region and the share in March and '
          'April (usable state-years, regions with 1,000+ such fires).', len(debris))

    miss = df.groupby('STATE').agg(fires=('FOD_ID', 'size'),
                                   missing=('CAUSE', lambda s: float((s == CAUSE_MISSING).mean())))
    miss = miss[miss['fires'] >= 1000].sort_values('missing', ascending=False)
    claim('calendar.cause_missing_by_state', miss['missing'].to_dict(),
          'Share of fires whose cause classification is missing or undetermined, per state (states with 1,000+ fires, '
          'all years). Where this is high, any cause calendar describes only the fires whose cause was recorded.',
          int(miss['fires'].sum()))
    claim('calendar.human_share', {
        'all_fires': float((u['CAUSE'] == 'Human').mean()),
        'known_cause': float((known['CAUSE'] == 'Human').mean()),
        'large_known_cause': float((known.loc[known['LARGE'], 'CAUSE'] == 'Human').mean()),
        'large_acres_known_cause': float(known.loc[known['LARGE'] & (known['CAUSE'] == 'Human'), 'FIRE_SIZE'].sum()
                                         / known.loc[known['LARGE'], 'FIRE_SIZE'].sum()),
    }, 'Share of fires caused by people (usable state-years): of all fires, of fires with a known cause, of fires '
       'of 300+ acres with a known cause, and of those fires\' acres.', n)


def run(out_dir: str) -> None:
    t0 = time.time()
    df, cov = load(out_dir)
    log.info(f'loaded {len(df):,} fires, {df["USABLE"].mean():.1%} in usable state-years ({time.time() - t0:.0f}s)')
    tab_dir = os.path.join(out_dir, 'tables')
    os.makedirs(os.path.join(tab_dir, 'calendar'), exist_ok=True)
    pad = padus_table(df)
    ics = ics_incidents(df)
    rows = []
    for st, d in df.groupby('STATE'):
        b = brief(st, d, cov, pad, ics)
        claim(f'places.state.{st}', b, f'Brief for {b["name"]}: FPA FOD 1992-2020. ' + USABLE_NOTE +
              ' Large = 300+ acres. Protected-land shares use the PAD-US 4.1 point join; losses use ICS-209-PLUS '
              'incidents (1999-2020) whose largest joined FPA FOD fire started in the state.', b['fires'])
        u = d[d['USABLE']]
        u.groupby(['MONTH', 'GENERAL']).size().unstack(fill_value=0).reindex(
            index=range(1, 13), columns=GENERAL_ORDER, fill_value=0).rename(index=lambda m: MONTH_ABBR[m - 1]).to_csv(
            os.path.join(tab_dir, 'calendar', f'{st}.csv'), index_label='month')
        rows.append({
            'state': st, 'name': b['name'], 'region': b['region'], 'fires': b['fires'], 'acres': round(b['acres'], 1),
            'window_start': b['window'][0], 'window_end': b['window'][1], 'fires_per_year_in_window': round(b['fires_per_year_in_window'], 1),
            'busiest_month': b['busiest_month'], 'human_share_in_window': round(b['cause_shares'].get('Human', 0), 4),
            'cause_missing_share': round(b['completeness']['cause_missing_share'], 4),
            'large_rate': round(b['large_rate_overall'] or 0, 5),
            'acres_trend_p': None if b['trend_acres'] is None else round(b['trend_acres']['kendall_p'], 4),
            'acres_trend_tau': None if b['trend_acres'] is None else round(b['trend_acres']['kendall_tau'], 3),
            'structures_destroyed_1999_2020': b.get('losses', {}).get('structures_destroyed'),
            'gap12_acre_share': b.get('protected', {}).get('by_gap', {}).get(GAP_ORDER[0], {}).get('acre_share'),
        })
    summary = pd.DataFrame(rows).sort_values('acres', ascending=False)
    summary.to_csv(os.path.join(tab_dir, 'places_summary.csv'), index=False)
    ups = int((summary['acres_trend_p'].notna()).sum())
    sig_up = summary[(summary['acres_trend_p'] < 0.05) & (summary['acres_trend_tau'] > 0)]['state'].tolist()
    sig_dn = summary[(summary['acres_trend_p'] < 0.05) & (summary['acres_trend_tau'] < 0)]['state'].tolist()
    claim('places.acres_trend_summary', {'states_tested': ups, 'upward_p05': sig_up, 'downward_p05': sig_dn,
                                         'expected_false_positives_at_p05': 0.05 * ups},
          f'States whose annual acres burned show a Kendall trend at p < 0.05 inside a usable window of at least '
          f'{MIN_TREND_YEARS} years. With this many tests about 5% would pass by chance.', len(df))
    claim('places.window_lengths', summary.set_index('state')[['window_start', 'window_end']].apply(
        lambda r: int(r['window_end'] - r['window_start'] + 1), axis=1).to_dict(),
          'Length in years of each state\'s usable reporting window.', len(df))
    sy = cov[['STATE', 'REGION', 'FIRE_YEAR', 'fires', 'acres', 'coverage_ok']].copy()
    lg = df[df['LARGE']].groupby(['STATE', 'FIRE_YEAR']).size().rename('large_fires')
    sy = sy.merge(lg.reset_index(), on=['STATE', 'FIRE_YEAR'], how='left').fillna({'large_fires': 0})
    sy.to_csv(os.path.join(tab_dir, 'state_year.csv'), index=False)
    calendar(df, tab_dir)
    log.info(f'places done in {time.time() - t0:.0f}s')


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default='outputs')
    args = ap.parse_args(argv)
    set_source('analysis.places')
    run(args.out)
    path = os.path.join(args.out, 'claims_places.json')
    print(f'claims: {write_claims(path)} -> {path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
