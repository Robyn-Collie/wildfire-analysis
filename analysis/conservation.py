"""Conservation lens: coverage mask, ICS-209-PLUS outcomes and PAD-US protected-area joins.

Usage (from the repo root):
    python -m analysis.conservation --out outputs/            # all three sections
    python -m analysis.conservation --out outputs/ --rebuild-padus   # redo the spatial join even if cached

Inputs:
    data/fires.parquet                                        (FPA FOD 6th ed. cache, see analysis/common.py)
    data/external/ics209plus/ics209plus-wildfire/ics209-plus-wf_incidents_1999to2020.csv
    data/external/padus_conus/PADUS4_1VectorAnalysis_CONUS.gdb, padus_ak/..._AK.gdb, padus_hi/..._HI.gdb
    (all external files come from scripts/download_external.py; see docs/DATA_JOINS.md)

Writes:
    outputs/claims_conservation.json      every number below, same schema as outputs/claims.json
    outputs/coverage.json, outputs/coverage_state_year.csv   (from analysis/coverage.py)
    outputs/ics209_fires_joined.csv       incident-level join table used for the outcome tables
    data/external/padus/fires_padus.parquet   per-fire PAD-US attributes (FOD_ID, GAP_Sts, Mang_Type, Mang_Name,
                                              Unit_Nm, Des_Tp, n_overlaps, plus FeatClass and Pub_Access)
    outputs/figures/coverage_state_year.png, padus_gap_by_block.png, padus_top_units.png,
    outputs/figures/padus_owner_agreement.png, ics_structures_by_year_cause.png

A section is skipped with a printed message when its external data is absent.
"""
from __future__ import annotations

import argparse
import logging
import os
import time

import numpy as np
import pandas as pd

from . import coverage as coverage_mod
from . import figures_conservation as figc
from .common import (CAUSE_MISSING, MONTH_ABBR, OWNER_MISSING, REGION_ORDER, REPO_ROOT, claim, load_fires,
                     normalize_owner, region_of, set_source, write_claims)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger('conservation')

ICS_INCIDENTS = os.path.join(REPO_ROOT, 'data', 'external', 'ics209plus', 'ics209plus-wildfire',
                             'ics209-plus-wf_incidents_1999to2020.csv')
PADUS_LAYERS = {
    'CONUS': os.path.join(REPO_ROOT, 'data', 'external', 'padus_conus', 'PADUS4_1VectorAnalysis_CONUS.gdb'),
    'AK': os.path.join(REPO_ROOT, 'data', 'external', 'padus_ak', 'PADUS4_1VectorAnalysis_AK.gdb'),
    'HI': os.path.join(REPO_ROOT, 'data', 'external', 'padus_hi', 'PADUS4_1VectorAnalysis_HI.gdb'),
}
PADUS_OUT = os.path.join(REPO_ROOT, 'data', 'external', 'padus', 'fires_padus.parquet')
PADUS_COLS = ['Unit_Nm', 'Mang_Type', 'Mang_Name', 'Des_Tp', 'GAP_Sts', 'FeatClass', 'Pub_Access']
CHUNK = 250_000

# Owner classes (docs/review/panel-conservation.md section c), applied to upper-cased OWNER_DESCR.
OWNER_CLASS = {
    'USFS': 'Federal', 'BLM': 'Federal', 'NPS': 'Federal', 'FWS': 'Federal', 'BOR': 'Federal',
    'OTHER FEDERAL': 'Federal', 'UNDEFINED FEDERAL': 'Federal',
    'BIA': 'Tribal/BIA', 'TRIBAL': 'Tribal/BIA',
    'STATE': 'State', 'PRIVATE': 'Private', 'STATE OR PRIVATE': 'State or private',
    'COUNTY': 'County/local', 'MUNICIPAL/LOCAL': 'County/local',
    OWNER_MISSING: 'Missing',
}
OWNER_CLASS_ORDER = ['Federal', 'Tribal/BIA', 'State', 'Private', 'State or private', 'County/local', 'Missing']
OWNER_CLASS_DEFINITION = ('Federal = USFS BLM NPS FWS BOR OTHER FEDERAL UNDEFINED FEDERAL; Tribal/BIA = BIA TRIBAL; '
                          'State = STATE; Private = PRIVATE; State or private = STATE OR PRIVATE; County/local = '
                          'COUNTY MUNICIPAL/LOCAL; Missing = MISSING/NOT SPECIFIED (OWNER_DESCR upper-cased)')
# PAD-US Mang_Type codes (PAD-US 4.1 data dictionary): FED federal, TRIB tribal, STAT state, LOC local,
# DIST regional agency special district, NGO non-governmental, PVT private, JNT joint, UNK unknown.
MANG_TYPE_LABEL = {'FED': 'FED', 'TRIB': 'TRIB', 'STAT': 'STAT', 'LOC': 'LOC', 'DIST': 'DIST', 'NGO': 'NGO',
                   'PVT': 'PVT', 'JNT': 'JNT', 'UNK': 'UNK'}
MANG_ORDER = ['FED', 'TRIB', 'STAT', 'LOC', 'DIST', 'NGO', 'PVT', 'JNT', 'UNK', 'Not in PAD-US']
# Which PAD-US manager types count as agreeing with each FPA FOD owner class.
AGREE = {'Federal': {'FED'}, 'Tribal/BIA': {'TRIB'}, 'State': {'STAT'}, 'County/local': {'LOC', 'DIST'},
         'Private': {'PVT', 'NGO', 'Not in PAD-US'}, 'State or private': {'STAT', 'PVT', 'NGO', 'Not in PAD-US'}}
# OWNER_DESCR agency codes and the PAD-US Mang_Name code that means the same manager
# (PAD-US codes tribal land TRIB, not BIA, and the Bureau of Reclamation USBR).
AGENCY_CODES = {'USFS': 'USFS', 'BLM': 'BLM', 'NPS': 'NPS', 'FWS': 'FWS', 'BOR': 'USBR', 'BIA': 'TRIB'}

BLOCKS = [(1992, 1996), (1997, 2001), (2002, 2006), (2007, 2011), (2012, 2016), (2017, 2020)]
LARGE_ACRES = 300.0
WINDOW = (2010, 2020)

FIRE_COLUMNS = ['FOD_ID', 'FIRE_YEAR', 'DISCOVERY_MONTH', 'FIRE_SIZE', 'FIRE_SIZE_CLASS', 'NWCG_CAUSE_CLASSIFICATION',
                'NWCG_GENERAL_CAUSE', 'OWNER_DESCR', 'STATE', 'LATITUDE', 'LONGITUDE', 'FIRE_NAME',
                'ICS_209_PLUS_INCIDENT_JOIN_ID', 'NWCG_REPORTING_AGENCY', 'SOURCE_SYSTEM_TYPE', 'SOURCE_SYSTEM']


def _block_label(year: pd.Series) -> pd.Series:
    out = pd.Series('', index=year.index, dtype=object)
    for a, b in BLOCKS:
        out[(year >= a) & (year <= b)] = f'{a}-{b}'
    return out


# =========================================================================== ICS-209-PLUS

ICS_NUMERIC = ['FINAL_ACRES', 'STR_DESTROYED_TOTAL', 'STR_DESTROYED_RES_TOTAL', 'STR_DAMAGED_TOTAL',
               'STR_THREATENED_MAX', 'WF_PEAK_PERSONNEL', 'TOTAL_PERSONNEL_SUM', 'PROJECTED_FINAL_IM_COST',
               'PEAK_EVACUATIONS', 'FATALITIES', 'INJURIES_TOTAL', 'INC_MGMT_NUM_SITREPS', 'START_YEAR',
               'FOD_FIRE_NUM', 'LRGST_FOD_ID']
ICS_KEEP = ['INCIDENT_ID', 'INCIDENT_NAME', 'INCTYP_ABBREVIATION', 'CAUSE', 'COMPLEX', 'POO_STATE',
            'EVACUATION_REPORTED'] + ICS_NUMERIC
ICS_CAUSE = {'H': 'Human', 'L': 'Lightning', 'U': 'Unknown', 'O': 'Other'}


def load_ics() -> pd.DataFrame:
    inc = pd.read_csv(ICS_INCIDENTS, usecols=ICS_KEEP, dtype=str, low_memory=False)
    for c in ICS_NUMERIC:
        inc[c] = pd.to_numeric(inc[c], errors='coerce')
    inc['EVACUATION_REPORTED'] = inc['EVACUATION_REPORTED'].map({'True': True, 'False': False, 'TRUE': True,
                                                                  'FALSE': False, '1.0': True, '0.0': False,
                                                                  '1': True, '0': False})
    return inc


def _outcome_table(inc: pd.DataFrame, by: str, order: list[str] | None = None) -> pd.DataFrame:
    g = inc.groupby(by, observed=True)
    out = pd.DataFrame({
        'incidents': g.size(),
        'fod_acres': g['FIRE_SIZE'].sum(),
        'ics_final_acres': g['FINAL_ACRES'].sum(),
        'structures_destroyed': g['STR_DESTROYED_TOTAL'].sum(),
        'residences_destroyed': g['STR_DESTROYED_RES_TOTAL'].sum(),
        'share_incidents_with_structures_destroyed': g['STR_DESTROYED_TOTAL'].apply(lambda s: float((s > 0).mean())),
        'structures_threatened_max_sum': g['STR_THREATENED_MAX'].sum(),
        'n_with_threatened': g['STR_THREATENED_MAX'].count(),
        'peak_personnel_sum': g['WF_PEAK_PERSONNEL'].sum(),
        'peak_personnel_median': g['WF_PEAK_PERSONNEL'].median(),
        'n_with_personnel': g['WF_PEAK_PERSONNEL'].count(),
        'projected_cost_usd_sum': g['PROJECTED_FINAL_IM_COST'].sum(),
        'n_with_cost': g['PROJECTED_FINAL_IM_COST'].count(),
        'evacuation_reported_incidents': g['EVACUATION_REPORTED'].apply(lambda s: int((s == True).sum())),  # noqa: E712
        'n_with_evacuation_flag': g['EVACUATION_REPORTED'].count(),
        'peak_evacuations_sum': g['PEAK_EVACUATIONS'].sum(),
        'n_with_peak_evacuations': g['PEAK_EVACUATIONS'].count(),
        'fatalities': g['FATALITIES'].sum(),
    })
    out['structures_destroyed_per_1000_acres'] = out['structures_destroyed'] / out['fod_acres'] * 1000
    if order is not None:
        out = out.reindex([o for o in order if o in out.index])
    return out


def ics_section(df: pd.DataFrame, out_dir: str, fig_dir: str) -> None:
    if not os.path.exists(ICS_INCIDENTS):
        print(f'ICS-209-PLUS section skipped: {ICS_INCIDENTS} not found. '
              'Run: python scripts/download_external.py --only ics209plus')
        return
    t0 = time.time()
    inc = load_ics()
    n_inc = len(inc)
    claim('ics.n_incidents', n_inc, 'rows in ics209-plus-wf_incidents_1999to2020.csv (one per incident)', n_inc)
    claim('ics.incident_type_counts', inc['INCTYP_ABBREVIATION'].value_counts(),
          'INCTYP_ABBREVIATION counts (WF wildfire, WFU wildland fire use, RX prescribed, CX complex)', n_inc)

    has = df['ICS_209_PLUS_INCIDENT_JOIN_ID'].notna() & (df['ICS_209_PLUS_INCIDENT_JOIN_ID'].astype(str) != '')
    ids = set(inc['INCIDENT_ID'])
    matched = has & df['ICS_209_PLUS_INCIDENT_JOIN_ID'].astype(str).isin(ids)
    n = len(df)
    claim('ics.fod_rows_with_join_id', int(has.sum()), 'FPA FOD rows with a non-empty ICS_209_PLUS_INCIDENT_JOIN_ID', n)
    claim('ics.fod_rows_matched', int(matched.sum()),
          'FPA FOD rows whose ICS_209_PLUS_INCIDENT_JOIN_ID equals an INCIDENT_ID in the ICS-209-PLUS incident table', n)
    claim('ics.distinct_incidents_matched', int(df.loc[matched, 'ICS_209_PLUS_INCIDENT_JOIN_ID'].nunique()),
          'distinct incident ids among matched rows (several FPA FOD fires can share one incident, e.g. complexes)', n)
    by_year = pd.DataFrame({'fires': df.groupby('FIRE_YEAR').size(),
                            'with_join_id': has.groupby(df['FIRE_YEAR']).sum(),
                            'matched': matched.groupby(df['FIRE_YEAR']).sum()})
    by_year['share_matched'] = by_year['matched'] / by_year['fires']
    large = df['FIRE_SIZE'] >= LARGE_ACRES
    by_year['fires_ge_300'] = df[large].groupby('FIRE_YEAR').size()
    by_year['share_matched_ge_300'] = matched[large].groupby(df.loc[large, 'FIRE_YEAR']).mean()
    claim('ics.match_rate_by_year', by_year, 'FPA FOD rows, rows with a join id, matched rows and match shares by '
          'FIRE_YEAR; the _ge_300 columns restrict to FIRE_SIZE >= 300 acres', n)
    w = (df['FIRE_YEAR'] >= WINDOW[0]) & (df['FIRE_YEAR'] <= WINDOW[1])
    by_cls = pd.DataFrame({'fires': df[w].groupby('FIRE_SIZE_CLASS', observed=True).size(),
                           'matched': matched[w].groupby(df.loc[w, 'FIRE_SIZE_CLASS'], observed=True).sum()})
    by_cls['share_matched'] = by_cls['matched'] / by_cls['fires']
    claim('ics.match_rate_by_size_class_2010_2020', by_cls, 'same by FIRE_SIZE_CLASS, FIRE_YEAR 2010-2020', int(w.sum()))

    # Incident-level join: one row per incident, FPA FOD attributes from the largest joined fire.
    fj = df.loc[matched, ['FOD_ID', 'ICS_209_PLUS_INCIDENT_JOIN_ID', 'FIRE_YEAR', 'FIRE_SIZE', 'FIRE_SIZE_CLASS',
                          'NWCG_CAUSE_CLASSIFICATION', 'NWCG_GENERAL_CAUSE', 'OWNER_DESCR', 'STATE', 'FIRE_NAME',
                          'REGION', 'OWNER_CLASS']].copy()
    fj = fj.sort_values('FIRE_SIZE', ascending=False)
    grp = fj.groupby('ICS_209_PLUS_INCIDENT_JOIN_ID')
    rep = grp.head(1).set_index('ICS_209_PLUS_INCIDENT_JOIN_ID')
    rep['n_fod_fires'] = grp.size()
    rep['fod_acres_all_fires'] = grp['FIRE_SIZE'].sum()
    joined = rep.join(inc.set_index('INCIDENT_ID'), how='inner')
    joined['ICS_CAUSE'] = joined['CAUSE'].map(ICS_CAUSE).fillna('Not recorded')
    joined.index.name = 'INCIDENT_ID'
    # Cause agreement between the two sources.
    ct = pd.crosstab(joined['NWCG_CAUSE_CLASSIFICATION'], joined['ICS_CAUSE'])
    claim('ics.cause_agreement_all_matched', ct,
          'matched incidents by FPA FOD NWCG_CAUSE_CLASSIFICATION (largest joined fire) and ICS-209-PLUS CAUSE '
          '(H Human, L Lightning, U Unknown, O Other)', len(joined))
    known = joined[joined['NWCG_CAUSE_CLASSIFICATION'].isin(['Human', 'Natural']) & joined['ICS_CAUSE'].isin(['Human', 'Lightning'])]
    agree = ((known['NWCG_CAUSE_CLASSIFICATION'] == 'Human') == (known['ICS_CAUSE'] == 'Human')).mean()
    claim('ics.cause_agreement_share', float(agree),
          'share of incidents where both sources record a cause and agree (Human vs Natural/Lightning)', len(known),
          unit='share')
    # LRGST_FOD_ID check.
    chk = joined['LRGST_FOD_ID'].notna()
    claim('ics.largest_fod_id_agreement', float((joined.loc[chk, 'LRGST_FOD_ID'] == joined.loc[chk, 'FOD_ID']).mean()),
          'share of matched incidents where the largest joined FPA FOD fire (by FIRE_SIZE) is the one ICS-209-PLUS '
          'lists in LRGST_FOD_ID', int(chk.sum()), unit='share')
    acres_ratio = (joined['FINAL_ACRES'] / joined['fod_acres_all_fires'].replace(0, np.nan)).replace([np.inf], np.nan)
    claim('ics.final_acres_vs_fod_acres', {'median_ratio': float(acres_ratio.median()),
                                          'share_within_25pct': float((acres_ratio.between(0.75, 1.25)).mean()),
                                          'share_ics_larger_than_2x': float((acres_ratio > 2).mean())},
          'ICS-209-PLUS FINAL_ACRES divided by the sum of FIRE_SIZE over the joined FPA FOD fires', len(joined),
          unit='ratio')

    # Sample for the outcome tables: 2010-2020, largest joined fire >= 300 acres.
    s = joined[(joined['FIRE_YEAR'] >= WINDOW[0]) & (joined['FIRE_YEAR'] <= WINDOW[1]) & (joined['FIRE_SIZE'] >= LARGE_ACRES)].copy()
    ns = len(s)
    sample_def = ('ICS-209-PLUS incidents joined to FPA FOD via ICS_209_PLUS_INCIDENT_JOIN_ID, one row per incident, '
                  'FPA FOD attributes from the largest joined fire, FIRE_YEAR 2010-2020, FIRE_SIZE >= 300 acres')
    claim('ics.sample_definition', sample_def, 'the sample used by every ics.outcomes_* claim', ns)
    claim('ics.sample_n', ns, sample_def, ns)
    claim('ics.field_fill_rates_sample', {c: float(s[c].notna().mean()) for c in
                                          ['STR_DESTROYED_TOTAL', 'STR_THREATENED_MAX', 'WF_PEAK_PERSONNEL',
                                           'PROJECTED_FINAL_IM_COST', 'EVACUATION_REPORTED', 'PEAK_EVACUATIONS',
                                           'FATALITIES']},
          'share of sample incidents with a non-null value for each ICS-209-PLUS field', ns, unit='share',
          note='STR_DESTROYED_TOTAL and FATALITIES include zeros by construction (data dictionary: "zero values '
               'included"), so a missing report and a true zero cannot be told apart. STR_THREATENED_MAX, '
               'WF_PEAK_PERSONNEL, PROJECTED_FINAL_IM_COST and PEAK_EVACUATIONS are null when never reported.')
    tot = _outcome_table(s.assign(_all='all'), '_all')
    claim('ics.outcomes_total', tot.loc['all'], 'outcome totals over the sample', ns,
          note='structures_threatened_max_sum sums the per-incident maximum, so it is not a count of distinct structures. '
               'Fractional structure counts occur because ICS-209-PLUS splits complex-level totals evenly across member '
               'incidents.')
    pre, post = s[s['FIRE_YEAR'] <= 2013], s[s['FIRE_YEAR'] >= 2014]
    claim('ics.evacuations_by_form_era',
          {'2010_2013_flag': {'incidents': len(pre), 'with_flag': int(pre['EVACUATION_REPORTED'].notna().sum()),
                              'evacuation_reported': int((pre['EVACUATION_REPORTED'] == True).sum()),  # noqa: E712
                              'share_reported': float((pre['EVACUATION_REPORTED'] == True).sum() / max(pre['EVACUATION_REPORTED'].notna().sum(), 1))},  # noqa: E712
           '2014_2020_peak_count': {'incidents': len(post), 'with_peak_evacuations': int(post['PEAK_EVACUATIONS'].notna().sum()),
                                    'with_peak_gt_0': int((post['PEAK_EVACUATIONS'] > 0).sum()),
                                    'peak_evacuations_sum': float(post['PEAK_EVACUATIONS'].sum()),
                                    'share_incidents_with_evacuations': float((post['PEAK_EVACUATIONS'] > 0).mean())}},
          'evacuation reporting split at the 2014 ICS-209 form change: 2010-2013 has a yes/no EVACUATION_REPORTED flag '
          'for every incident, 2014-2020 has PEAK_EVACUATIONS (a count, null when none reported) and the flag is derived '
          'from it', ns,
          note='The two eras are not comparable; the data dictionary says EVACUATION_REPORTED is "2002+ only, 2014+ set '
               'to true if PEAK_EVACUATIONS > 0".')
    claim('ics.outcomes_by_cause', _outcome_table(s, 'NWCG_CAUSE_CLASSIFICATION', ['Human', 'Natural', CAUSE_MISSING]),
          'outcomes by FPA FOD NWCG_CAUSE_CLASSIFICATION of the largest joined fire', ns)
    claim('ics.outcomes_by_general_cause', _outcome_table(s, 'NWCG_GENERAL_CAUSE').sort_values('structures_destroyed', ascending=False),
          'outcomes by NWCG_GENERAL_CAUSE of the largest joined fire', ns)
    claim('ics.outcomes_by_owner_class', _outcome_table(s, 'OWNER_CLASS', OWNER_CLASS_ORDER),
          'outcomes by owner class of the largest joined fire (' + OWNER_CLASS_DEFINITION + ')', ns)
    claim('ics.outcomes_by_region', _outcome_table(s, 'REGION', REGION_ORDER),
          'outcomes by project region of the largest joined fire', ns)
    claim('ics.outcomes_by_year', _outcome_table(s, 'FIRE_YEAR'), 'outcomes by FIRE_YEAR', ns)
    cause_region = s.groupby(['REGION', 'NWCG_CAUSE_CLASSIFICATION'], observed=True)['STR_DESTROYED_TOTAL'].sum().unstack().reindex(REGION_ORDER)
    claim('ics.structures_destroyed_by_region_cause', cause_region, 'structures destroyed by region and cause classification', ns)
    # Distribution.
    sd = s['STR_DESTROYED_TOTAL']
    claim('ics.structures_destroyed_distribution',
          {'share_zero': float((sd == 0).mean()), 'share_ge_1': float((sd >= 1).mean()), 'share_ge_10': float((sd >= 10).mean()),
           'share_ge_100': float((sd >= 100).mean()), 'share_ge_1000': float((sd >= 1000).mean()),
           'percentiles': {str(p): float(sd.quantile(p)) for p in [0.5, 0.75, 0.9, 0.95, 0.99, 0.999]},
           'max': float(sd.max()), 'total': float(sd.sum()),
           'share_of_total_in_top_10_incidents': float(sd.nlargest(10).sum() / sd.sum()),
           'share_of_total_in_top_25_incidents': float(sd.nlargest(25).sum() / sd.sum())},
          'distribution of STR_DESTROYED_TOTAL over the sample', ns)
    top = s.sort_values('STR_DESTROYED_TOTAL', ascending=False).head(25)[
        ['INCIDENT_NAME', 'STATE', 'FIRE_YEAR', 'FIRE_SIZE', 'FINAL_ACRES', 'STR_DESTROYED_TOTAL', 'STR_DESTROYED_RES_TOTAL',
         'STR_THREATENED_MAX', 'WF_PEAK_PERSONNEL', 'PROJECTED_FINAL_IM_COST', 'FATALITIES', 'NWCG_CAUSE_CLASSIFICATION',
         'NWCG_GENERAL_CAUSE', 'ICS_CAUSE', 'OWNER_DESCR', 'OWNER_CLASS', 'n_fod_fires']].reset_index()
    claim('ics.top25_structures_destroyed', top, 'the 25 sample incidents with the most structures destroyed', ns)
    top_share = {}
    for col in ['NWCG_CAUSE_CLASSIFICATION', 'OWNER_CLASS', 'STATE']:
        top_share[col] = top[col].value_counts().to_dict()
    claim('ics.top25_composition', top_share, 'cause, owner class and state counts among the top 25', 25)
    # Figure.
    yc = s.groupby(['FIRE_YEAR', 'NWCG_CAUSE_CLASSIFICATION'], observed=True)['STR_DESTROYED_TOTAL'].sum().unstack().fillna(0)
    figc.structures_by_year_cause(yc, ns, fig_dir)
    joined.reset_index().to_csv(os.path.join(out_dir, 'ics209_fires_joined.csv'), index=False)
    log.info(f'ICS-209-PLUS section done in {time.time() - t0:.1f}s ({ns:,} sample incidents)')


# =========================================================================== PAD-US

def _join_extent(points: pd.DataFrame, gdb: str, crs_cache: dict) -> pd.DataFrame:
    """Point-in-polygon join of ``points`` (FOD_ID, LATITUDE, LONGITUDE) into one PAD-US extent, in chunks."""
    import geopandas as gpd
    import pyogrio
    t0 = time.time()
    pa = pyogrio.read_dataframe(gdb, columns=PADUS_COLS + ['GAP_Sts_Prity'], use_arrow=True)
    for c in PADUS_COLS:
        pa[c] = pa[c].astype('category')
    log.info(f'  read {len(pa):,} polygons from {os.path.basename(gdb)} in {time.time() - t0:.0f}s')
    out = []
    for start in range(0, len(points), CHUNK):
        chunk = points.iloc[start:start + CHUNK]
        pts = gpd.GeoDataFrame(chunk[['FOD_ID']].reset_index(drop=True),
                               geometry=gpd.points_from_xy(chunk['LONGITUDE'], chunk['LATITUDE']), crs='EPSG:4326')
        pts = pts.to_crs(pa.crs)
        j = gpd.sjoin(pts, pa, how='inner', predicate='within')
        j = pd.DataFrame(j.drop(columns=['geometry', 'index_right']))
        # overlapping polygons: keep the lowest GAP status (most protected), record the multiplicity
        j['GAP_Sts_num'] = pd.to_numeric(j['GAP_Sts'], errors='coerce').fillna(9)
        mult = j.groupby('FOD_ID').size().rename('n_overlaps')
        j = j.sort_values(['FOD_ID', 'GAP_Sts_num']).drop_duplicates('FOD_ID', keep='first')
        j = j.merge(mult, left_on='FOD_ID', right_index=True)
        out.append(j.drop(columns=['GAP_Sts_num', 'GAP_Sts_Prity']))
        log.info(f'  {min(start + CHUNK, len(points)):,}/{len(points):,} points, {time.time() - t0:.0f}s')
    del pa
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=['FOD_ID'] + PADUS_COLS + ['n_overlaps'])


def build_padus_join(df: pd.DataFrame) -> pd.DataFrame:
    """Join every ignition point to PAD-US 4.1 (CONUS, AK, HI extents) and cache to PADUS_OUT."""
    pts_all = df[['FOD_ID', 'STATE', 'LATITUDE', 'LONGITUDE']]
    parts = []
    for extent, gdb in PADUS_LAYERS.items():
        if extent == 'CONUS':
            sel = ~pts_all['STATE'].isin(['AK', 'HI', 'PR'])
        else:
            sel = pts_all['STATE'] == extent
        pts = pts_all[sel]
        log.info(f'PAD-US {extent}: {len(pts):,} points')
        part = _join_extent(pts, gdb, {})
        part['extent'] = extent
        parts.append(part)
    res = pd.concat(parts, ignore_index=True)
    res = pts_all[['FOD_ID']].merge(res, on='FOD_ID', how='left')
    res['n_overlaps'] = res['n_overlaps'].fillna(0).astype('int16')
    for c in PADUS_COLS + ['extent']:
        res[c] = res[c].astype(str).where(res[c].notna(), None)
    os.makedirs(os.path.dirname(PADUS_OUT), exist_ok=True)
    res.to_parquet(PADUS_OUT, index=False)
    return res


def _gap_category(res: pd.DataFrame) -> pd.Series:
    """'1'..'4' for PAD-US polygons, 'none' for the Non-PAD-US fill polygons, 'unmatched' for points in no polygon."""
    g = res['GAP_Sts'].astype(object)
    out = pd.Series('unmatched', index=res.index, dtype=object)
    inpad = res['Unit_Nm'].notna() & (res['Unit_Nm'] != 'Non-PAD-US Area')
    out[inpad] = g[inpad].astype(str)
    out[res['Unit_Nm'] == 'Non-PAD-US Area'] = 'none'
    return out


def padus_section(df: pd.DataFrame, out_dir: str, fig_dir: str, rebuild: bool) -> None:
    missing = [p for p in PADUS_LAYERS.values() if not os.path.exists(p)]
    if missing and not os.path.exists(PADUS_OUT):
        print('PAD-US section skipped: missing ' + ', '.join(missing) + '. '
              'Run: python scripts/download_external.py --only padus_conus (and padus_ak, padus_hi)')
        return
    t0 = time.time()
    if rebuild or not os.path.exists(PADUS_OUT):
        if missing:
            print('PAD-US section skipped: cannot rebuild, missing ' + ', '.join(missing))
            return
        res = build_padus_join(df)
        log.info(f'PAD-US join built in {time.time() - t0:.0f}s')
    else:
        res = pd.read_parquet(PADUS_OUT)
        log.info(f'PAD-US join read from cache {PADUS_OUT}')
    n = len(res)
    res['gap'] = _gap_category(res)
    d = df.merge(res[['FOD_ID', 'gap', 'GAP_Sts', 'Mang_Type', 'Mang_Name', 'Unit_Nm', 'Des_Tp', 'n_overlaps', 'extent']],
                 on='FOD_ID', how='left')
    gap_order = ['1', '2', '3', '4', 'none', 'unmatched']
    claim('padus.source', 'PAD-US 4.1 Vector Analysis file (PADUS4_1VectorAnalysis_CONUS/AK/HI.gdb, inside the Raster '
          'Analysis zips on ScienceBase item 6759b67ed34edfeb8710a3db): the Combined Fee/Designation/Easement feature '
          'class with Military Lands and Tribal Areas from the Proclamation feature class, overlapping designations '
          'resolved by GAP status priority (GAP 1 over 2 over 3 over 4), clipped to Census state boundaries, with '
          'Non-PAD-US Area fill polygons. Puerto Rico and the territories are not covered.', 'data source', None)
    claim('padus.join_definition', 'ignition point (LATITUDE, LONGITUDE, EPSG:4326) projected to the layer CRS '
          '(USA Contiguous Albers Equal Area Conic USGS version, EPSG:5070 for CONUS; the AK and HI layers use their own '
          'Albers) and joined with geopandas.sjoin predicate within; where a point fell in more than one polygon the '
          'lowest GAP status was kept and the multiplicity recorded in n_overlaps. gap = GAP_Sts for PAD-US polygons, '
          '"none" for Non-PAD-US Area fill polygons, "unmatched" for points in no polygon (offshore, PR, bad coordinates).',
          'join method', n)
    claim('padus.n_points', n, 'ignition points submitted to the join', n)
    claim('padus.match_summary', {'matched_any_polygon': int(res['Unit_Nm'].notna().sum()),
                                  'in_padus_unit': int((res['gap'].isin(['1', '2', '3', '4'])).sum()),
                                  'non_padus_area': int((res['gap'] == 'none').sum()),
                                  'unmatched': int((res['gap'] == 'unmatched').sum()),
                                  'unmatched_by_state': d.loc[d['gap'] == 'unmatched', 'STATE'].value_counts().head(10).to_dict(),
                                  'n_overlaps_distribution': res['n_overlaps'].value_counts().sort_index().to_dict()},
          'how the points landed', n,
          note='n_overlaps is 1 for every matched point because the Vector Analysis file is already a flat partition; '
               'USGS resolved the overlaps by GAP priority before publication.')

    def _shares(sub: pd.DataFrame) -> pd.DataFrame:
        t = sub.groupby('gap', observed=True)['FIRE_SIZE'].agg(fires='size', acres='sum').reindex(gap_order, fill_value=0)
        t['share_fires'] = t['fires'] / t['fires'].sum()
        t['share_acres'] = t['acres'] / t['acres'].sum()
        known = sub[sub['NWCG_CAUSE_CLASSIFICATION'] != CAUSE_MISSING]
        t['human_share_known_cause'] = (known['NWCG_CAUSE_CLASSIFICATION'] == 'Human').groupby(known['gap'], observed=True).mean()
        t['n_known_cause'] = known.groupby('gap', observed=True).size()
        t['fires_ge_300'] = sub[sub['FIRE_SIZE'] >= LARGE_ACRES].groupby('gap', observed=True).size()
        t['share_of_fires_ge_300'] = t['fires_ge_300'] / t['fires_ge_300'].sum()
        t['share_ge_300_within_gap'] = t['fires_ge_300'] / t['fires']
        t['acres_ge_300'] = sub[sub['FIRE_SIZE'] >= LARGE_ACRES].groupby('gap', observed=True)['FIRE_SIZE'].sum()
        return t

    w = (d['FIRE_YEAR'] >= WINDOW[0]) & (d['FIRE_YEAR'] <= WINDOW[1])
    gdef = ('gap = GAP status at the ignition point (1 most protected ... 4, none = not in PAD-US, unmatched = outside '
            'the layer); fires = count, acres = sum FIRE_SIZE; human_share_known_cause = Human / (Human + Natural); '
            'fires_ge_300 = FIRE_SIZE >= 300 acres')
    claim('padus.by_gap_all_years', _shares(d), gdef + '; all records 1992-2020', n)
    claim('padus.by_gap_2010_2020', _shares(d[w]), gdef + '; FIRE_YEAR 2010-2020', int(w.sum()))
    claim('padus.by_gap_2010_2020_human_only', _shares(d[w & (d['NWCG_CAUSE_CLASSIFICATION'] == 'Human')]),
          gdef + '; FIRE_YEAR 2010-2020, Human cause only', int((w & (d['NWCG_CAUSE_CLASSIFICATION'] == 'Human')).sum()))
    # general cause on protected land (GAP 1-2) vs elsewhere, 2010-2020, known cause
    prot = d[w & d['gap'].isin(['1', '2'])]
    claim('padus.general_cause_share_gap12_2010_2020',
          prot['NWCG_GENERAL_CAUSE'].value_counts(normalize=True),
          'share of ignitions by NWCG_GENERAL_CAUSE on GAP 1-2 land, 2010-2020', len(prot), unit='share')
    claim('padus.general_cause_share_large_gap12_2010_2020',
          prot[prot['FIRE_SIZE'] >= LARGE_ACRES]['NWCG_GENERAL_CAUSE'].value_counts(normalize=True),
          'same, fires >= 300 acres', int((prot['FIRE_SIZE'] >= LARGE_ACRES).sum()), unit='share')
    # 5-year blocks
    d['block'] = _block_label(d['FIRE_YEAR'])
    bf = pd.crosstab(d['block'], d['gap']).reindex(columns=gap_order, fill_value=0)
    ba = pd.crosstab(d['block'], d['gap'], values=d['FIRE_SIZE'], aggfunc='sum').reindex(columns=gap_order).fillna(0.0)
    claim('padus.fires_by_block_gap', bf, 'ignitions by 5-year block (last block 2017-2020) and gap', n)
    claim('padus.acres_by_block_gap', ba, 'acres by 5-year block and gap', n, unit='acres')
    claim('padus.share_fires_by_block_gap', bf.div(bf.sum(axis=1), axis=0), 'row shares of the previous', n, unit='share')
    claim('padus.share_acres_by_block_gap', ba.div(ba.sum(axis=1), axis=0), 'row shares of the acres table', n, unit='share')
    figc.gap_by_block(bf.drop(columns=['unmatched']), ba.drop(columns=['unmatched']), int(res['Unit_Nm'].notna().sum()), fig_dir)

    # Top units by human-caused ignitions 2010-2020.
    hu = d[w & (d['NWCG_CAUSE_CLASSIFICATION'] == 'Human') & d['gap'].isin(['1', '2', '3', '4'])]
    ug = hu.groupby('Unit_Nm', observed=True)
    units = pd.DataFrame({'human_ignitions': ug.size(), 'human_acres': ug['FIRE_SIZE'].sum(),
                          'human_fires_ge_300': ug['FIRE_SIZE'].apply(lambda s: int((s >= LARGE_ACRES).sum())),
                          'Mang_Name': ug['Mang_Name'].agg(lambda s: s.mode().iloc[0]),
                          'Mang_Type': ug['Mang_Type'].agg(lambda s: s.mode().iloc[0]),
                          'GAP_Sts': ug['gap'].agg(lambda s: s.mode().iloc[0]),
                          'Des_Tp': ug['Des_Tp'].agg(lambda s: s.mode().iloc[0]),
                          'states': ug['STATE'].agg(lambda s: ' '.join(sorted(k for k, v in s.astype(str).value_counts(normalize=True).items() if v >= 0.02)[:4])),
                          'peak_month': ug['DISCOVERY_MONTH'].agg(lambda s: MONTH_ABBR[int(s.value_counts().idxmax()) - 1]),
                          'peak_month_share': ug['DISCOVERY_MONTH'].agg(lambda s: float(s.value_counts(normalize=True).max())),
                          'top_general_cause': ug['NWCG_GENERAL_CAUSE'].agg(lambda s: str(s.value_counts().idxmax()))})
    all_ign = d[w & d['gap'].isin(['1', '2', '3', '4'])].groupby('Unit_Nm', observed=True).size()
    units['all_ignitions'] = all_ign.reindex(units.index)
    units['human_share_all'] = units['human_ignitions'] / units['all_ignitions']
    top25 = units.sort_values('human_ignitions', ascending=False).head(25)
    claim('padus.top25_units_human_ignitions_2010_2020', top25,
          'PAD-US units (Unit_Nm) with the most Human-cause ignitions 2010-2020; Mang_Name, Mang_Type, GAP_Sts and Des_Tp '
          'are the modal values across the unit\'s ignitions; peak_month = DISCOVERY_MONTH with the most human ignitions; '
          'states = STATE values holding at least 2% of the unit\'s human ignitions',
          len(hu), note='A unit name can repeat across states (e.g. "State Trust Land"); rows are by name only. '
                        'Oklahoma Tribal Statistical Areas (Des_Tp TRIBL) are Census-defined tribal jurisdictions that '
                        'include private land, not conservation units.')
    non_tribal = units[units['Des_Tp'] != 'TRIBL'].sort_values('human_ignitions', ascending=False).head(25)
    claim('padus.top25_nontribal_units_human_ignitions_2010_2020', non_tribal,
          'same table excluding units whose modal Des_Tp is TRIBL (tribal reservations and statistical areas)', len(hu))
    claim('padus.human_ignitions_share_in_tribal_units_2010_2020',
          float((hu['Des_Tp'].astype(str) == 'TRIBL').mean()),
          'share of human ignitions inside PAD-US units 2010-2020 that fall in Des_Tp TRIBL units', len(hu), unit='share')
    claim('padus.n_units_with_human_ignitions_2010_2020', int(len(units)), 'distinct Unit_Nm with at least one human ignition 2010-2020', len(hu))
    claim('padus.top25_units_share_of_human_ignitions', float(top25['human_ignitions'].sum() / len(hu)),
          'share of all human ignitions inside PAD-US units 2010-2020 that fall in the top 25 units', len(hu), unit='share')
    figc.top_units(top25, len(hu), fig_dir)
    # Top units on GAP 1-2 land specifically.
    top12 = units[units['GAP_Sts'].isin(['1', '2'])].sort_values('human_ignitions', ascending=False).head(25)
    claim('padus.top25_gap12_units_human_ignitions_2010_2020', top12, 'same table restricted to units whose modal GAP status is 1 or 2', len(hu))
    # Manager-name view (agency level).
    mg = hu.groupby('Mang_Name', observed=True).size().sort_values(ascending=False).head(15)
    claim('padus.human_ignitions_by_manager_2010_2020', mg, 'Human ignitions 2010-2020 inside PAD-US units by Mang_Name', len(hu))

    # Agreement between OWNER_DESCR and PAD-US Mang_Type.
    d['mang_class'] = d['Mang_Type'].astype(object).where(d['gap'] != 'none', 'Not in PAD-US')
    has_owner = (d['OWNER_CLASS'] != 'Missing') & d['Unit_Nm'].notna()
    ho = d[has_owner]
    ct = pd.crosstab(ho['OWNER_CLASS'], ho['mang_class']).reindex(index=[o for o in OWNER_CLASS_ORDER if o != 'Missing'],
                                                                 columns=[m for m in MANG_ORDER if m in ho['mang_class'].unique()],
                                                                 fill_value=0)
    share = ct.div(ct.sum(axis=1), axis=0)
    claim('padus.owner_vs_mang_type_counts', ct, 'ignitions with a recorded OWNER_DESCR by owner class (rows, '
          + OWNER_CLASS_DEFINITION + ') and PAD-US Mang_Type at the point (columns; Not in PAD-US = Non-PAD-US Area)',
          len(ho))
    claim('padus.owner_vs_mang_type_row_shares', share, 'row shares of the previous table', len(ho), unit='share')
    agree_row = {o: float(sum(ct.loc[o, m] for m in AGREE[o] if m in ct.columns) / ct.loc[o].sum()) for o in ct.index if ct.loc[o].sum() > 0}
    overall = sum(ct.loc[o, m] for o in ct.index for m in AGREE[o] if m in ct.columns) / ct.values.sum()
    claim('padus.owner_agreement_by_class', agree_row,
          'share of each owner class whose PAD-US manager type is consistent: ' + '; '.join(f'{k} = {sorted(v)}' for k, v in AGREE.items()),
          len(ho), unit='share')
    claim('padus.owner_agreement_overall', float(overall), 'the same, all classes pooled', len(ho), unit='share')
    # Agency level: OWNER_DESCR code vs Mang_Name code.
    ag = d[d['OWNER'].isin(list(AGENCY_CODES)) & d['Unit_Nm'].notna()]
    agct = pd.crosstab(ag['OWNER'], ag['Mang_Name'].astype(object).where(ag['gap'] != 'none', 'Not in PAD-US'))
    keep_cols = [c for c in agct.columns if agct[c].sum() >= 500]
    agct2 = agct[keep_cols].copy()
    agct2['other'] = agct.drop(columns=keep_cols).sum(axis=1)
    claim('padus.agency_vs_mang_name_counts', agct2.reindex(list(AGENCY_CODES)),
          'ignitions whose OWNER_DESCR is a federal agency or BIA, by PAD-US Mang_Name at the point (columns with < 500 pooled into other)',
          len(ag))
    claim('padus.agency_exact_agreement',
          {a: float((ag.loc[ag['OWNER'] == a, 'Mang_Name'].astype(str) == code).mean()) for a, code in AGENCY_CODES.items()},
          'share of ignitions with OWNER_DESCR == agency whose PAD-US Mang_Name is the matching code '
          '(USFS, BLM, NPS, FWS as is; BOR = USBR; BIA = TRIB)', len(ag), unit='share')
    figc.agreement_matrix(share, ct, len(ho), fig_dir)

    # What PAD-US assigns where OWNER_DESCR is missing.
    mo = d[(d['OWNER_CLASS'] == 'Missing') & d['Unit_Nm'].notna()]
    mo_w = mo[(mo['FIRE_YEAR'] >= WINDOW[0]) & (mo['FIRE_YEAR'] <= WINDOW[1])]
    for tag, sub in [('all_years', mo), ('2010_2020', mo_w)]:
        t = sub.groupby('mang_class', observed=True)['FIRE_SIZE'].agg(fires='size', acres='sum').sort_values('fires', ascending=False)
        t['share_fires'] = t['fires'] / t['fires'].sum()
        t['share_acres'] = t['acres'] / t['acres'].sum()
        claim(f'padus.missing_owner_assignment_{tag}', t,
              'records with OWNER_DESCR = MISSING/NOT SPECIFIED, by PAD-US Mang_Type at the point (Not in PAD-US = '
              'Non-PAD-US Area, which is predominantly private land)', len(sub))
    t = mo['gap'].value_counts().reindex(gap_order, fill_value=0)
    claim('padus.missing_owner_by_gap_all_years', t, 'records with missing OWNER_DESCR by gap', len(mo))
    claim('padus.missing_owner_top_managers_all_years',
          mo[mo['gap'] != 'none']['Mang_Name'].value_counts().head(15),
          'PAD-US Mang_Name for missing-owner records that fall inside a PAD-US unit', int((mo['gap'] != 'none').sum()))
    # Reporting-agency view of the missing-owner block, so the reader sees who leaves owner blank
    claim('padus.missing_owner_by_reporting_agency_and_mang_type',
          pd.crosstab(mo['NWCG_REPORTING_AGENCY'].astype(str), mo['mang_class']),
          'missing-owner records by NWCG_REPORTING_AGENCY and PAD-US Mang_Type', len(mo))
    log.info(f'PAD-US section done in {time.time() - t0:.0f}s')


# =========================================================================== main

def run(out_dir: str, rebuild_padus: bool = False, skip: tuple[str, ...] = ()) -> int:
    set_source('analysis.conservation')
    os.makedirs(out_dir, exist_ok=True)
    fig_dir = os.path.join(out_dir, 'figures')
    t0 = time.time()
    df = load_fires(FIRE_COLUMNS)
    df['REGION'] = region_of(df['STATE'])
    df['OWNER'] = normalize_owner(df['OWNER_DESCR'])
    df['OWNER_CLASS'] = df['OWNER'].map(OWNER_CLASS).fillna('Missing')
    log.info(f'loaded {len(df):,} rows in {time.time() - t0:.1f}s')
    claim('conservation.owner_class_definition', OWNER_CLASS_DEFINITION, 'owner classes used in this module', None)
    claim('conservation.large_fire_definition', f'FIRE_SIZE >= {LARGE_ACRES:g} acres (classes E, F, G)', 'large fire', None)
    if 'coverage' not in skip:
        coverage_mod.run(out_dir, df=df[['FIRE_YEAR', 'STATE', 'FIRE_SIZE', 'NWCG_REPORTING_AGENCY', 'SOURCE_SYSTEM_TYPE', 'SOURCE_SYSTEM']])
    if 'ics' not in skip:
        ics_section(df, out_dir, fig_dir)
    if 'padus' not in skip:
        padus_section(df, out_dir, fig_dir, rebuild_padus)
    path = os.path.join(out_dir, 'claims_conservation.json')
    n_claims = write_claims(path)
    log.info(f'wrote {n_claims} claims to {path} in {time.time() - t0:.0f}s total')
    return n_claims


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default='outputs')
    ap.add_argument('--rebuild-padus', action='store_true', help='redo the spatial join even if fires_padus.parquet exists')
    ap.add_argument('--skip', nargs='*', default=[], choices=['coverage', 'ics', 'padus'], help='sections to skip')
    args = ap.parse_args(argv)
    n = run(args.out, args.rebuild_padus, tuple(args.skip))
    print(f'claims: {n}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
