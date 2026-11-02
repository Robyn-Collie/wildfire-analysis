"""Power-line ignitions: what the record says about fires coded to power generation, transmission or distribution.

The FPA FOD general cause "Power generation/transmission/distribution" is the record's only utility cause. This
module describes it nationally: how many fires and acres, where and when, whether it becomes large out of
proportion to its count, what the incidents destroyed, and which incidents were largest. It does not and cannot
say why a line started a fire (vegetation contact, equipment failure, conductor clash): the record has one code
for all of them.

Usage (from the repo root):
    python -m analysis.power_lines --out outputs/

Needs:
    data/fires.parquet
    outputs/coverage_state_year.csv                         (python -m analysis.conservation)
    data/external/ics209plus/.../ics209-plus-wf_incidents_1999to2020.csv   (optional; losses skipped without it)
    data/external/wfigs/wfigs_2021_2025.parquet             (optional; 2021-2025 extension skipped without it)

Writes:
    outputs/claims_power.json
    outputs/tables/power_lines_largest_incidents.csv
"""
from __future__ import annotations

import argparse
import logging
import os
import time

import numpy as np
import pandas as pd

from .common import CAUSE_MISSING, MONTH_ABBR, REGION_ORDER, claim, load_fires, region_of, set_source, write_claims
from .conservation import ICS_INCIDENTS, _outcome_table, load_ics
from .incidents import RULE as INCIDENT_RULE
from .incidents import clean_name, group

log = logging.getLogger('power_lines')

POWER = 'Power generation/transmission/distribution'
LARGE = 300.0
YEARS = list(range(1992, 2021))
COLUMNS = ['FOD_ID', 'FIRE_YEAR', 'DISCOVERY_DATE', 'DISCOVERY_MONTH', 'STATE', 'FIRE_SIZE', 'FIRE_NAME',
           'COMPLEX_NAME', 'MTBS_FIRE_NAME', 'MTBS_ID', 'NWCG_CAUSE_CLASSIFICATION', 'NWCG_GENERAL_CAUSE',
           'ICS_209_PLUS_INCIDENT_JOIN_ID', 'ICS_209_PLUS_COMPLEX_JOIN_ID', 'FIPS_NAME']
BRIEF_STATES = ['CA']  # states with a utility-audience brief (site: brief-XX.html)
DEFINITION = (f'Power-line fires = FPA FOD 6th edition records with NWCG_GENERAL_CAUSE = "{POWER}", 1992-2020. '
              'The code is assigned at ignition by the reporting agency. It does not separate generation, '
              'transmission and distribution, or vegetation contact from equipment failure.')
LIMITS = ('Undercount of unknown size: about a quarter of records have no general cause, and some of those are '
          'power-line fires. The cause code says nothing about the mechanism (vegetation contact, equipment '
          'failure, conductor clash, animal contact). The record has no weather, so wind is not examined. '
          'Nothing here attributes a fire to any named utility.')
TOP_N = 25


def load(out_dir: str) -> pd.DataFrame:
    df = load_fires(COLUMNS)
    df['REGION'] = region_of(df['STATE'])
    df['GENERAL'] = df['NWCG_GENERAL_CAUSE'].astype(str)
    df['CAUSE'] = df['NWCG_CAUSE_CLASSIFICATION'].astype(str)
    df['POWER'] = df['GENERAL'] == POWER
    df['LARGE'] = df['FIRE_SIZE'] >= LARGE
    df['MONTH'] = df['DISCOVERY_MONTH'].astype(int)
    cov_path = os.path.join(out_dir, 'coverage_state_year.csv')
    if os.path.exists(cov_path):
        cov = pd.read_csv(cov_path)
        ok = cov.set_index(['STATE', 'FIRE_YEAR'])['coverage_ok']
        key = pd.MultiIndex.from_arrays([df['STATE'].astype(str), df['FIRE_YEAR'].astype(int)])
        df['USABLE'] = ok.reindex(key).fillna(False).to_numpy(dtype=bool)
    else:
        log.warning(f'{cov_path} not found; usable-window counts skipped')
        df['USABLE'] = np.nan
    return df


def overview(df: pd.DataFrame) -> None:
    n = len(df)
    p = df[df['POWER']]
    human = df[df['CAUSE'] == 'Human']
    known_general = df[df['GENERAL'] != CAUSE_MISSING]
    claim('power.definition', DEFINITION, 'How this page selects power-line fires.', n)
    claim('power.limits', LIMITS, 'What the record cannot say about power-line fires.', None)
    claim('power.overview', {
        'fires': len(p), 'acres': float(p['FIRE_SIZE'].sum()),
        'share_of_all_fires': len(p) / n, 'share_of_all_acres': float(p['FIRE_SIZE'].sum() / df['FIRE_SIZE'].sum()),
        'share_of_human_fires': len(p) / len(human),
        'share_of_human_acres': float(p['FIRE_SIZE'].sum() / human['FIRE_SIZE'].sum()),
        'share_of_known_general_cause_fires': len(p) / len(known_general),
        'mean_acres': float(p['FIRE_SIZE'].mean()), 'median_acres': float(p['FIRE_SIZE'].median()),
        'general_cause_missing_share': float((df['GENERAL'] == CAUSE_MISSING).mean()),
    }, DEFINITION + ' Shares are of all FPA FOD records 1992-2020, of Human-classified records, and of records '
       'with a general cause.', n)


def by_year_region_month(df: pd.DataFrame) -> None:
    p = df[df['POWER']]
    yr = pd.DataFrame({'fires': p.groupby('FIRE_YEAR').size(), 'acres': p.groupby('FIRE_YEAR')['FIRE_SIZE'].sum(),
                       'large_fires': p[p['LARGE']].groupby('FIRE_YEAR').size()}).reindex(YEARS).fillna(0)
    yr['share_of_year_fires'] = yr['fires'] / df.groupby('FIRE_YEAR').size().reindex(YEARS)
    claim('power.by_year', yr, 'Power-line fires, acres and fires of 300+ acres by FIRE_YEAR, every record. Year-to-year '
          'counts include reporting changes (see the coverage notes on the Trend page); large-fire counts are less '
          'exposed to them.', len(p))
    if df['USABLE'].dtype == bool:
        u = df[df['USABLE']]
        claim('power.share_usable_by_year', (u[u['POWER']].groupby('FIRE_YEAR').size()
                                             / u.groupby('FIRE_YEAR').size()).reindex(YEARS).fillna(0),
              'Power-line share of fires in usable state-years only (analysis/coverage.py), by FIRE_YEAR.',
              int(u['POWER'].sum()))
    rg = pd.DataFrame({
        'fires': p.groupby('REGION').size(), 'acres': p.groupby('REGION')['FIRE_SIZE'].sum(),
        'large_fires': p[p['LARGE']].groupby('REGION').size(),
        'share_of_region_fires': p.groupby('REGION').size() / df.groupby('REGION').size(),
        'share_of_region_acres': p.groupby('REGION')['FIRE_SIZE'].sum() / df.groupby('REGION')['FIRE_SIZE'].sum(),
    }).reindex(REGION_ORDER).fillna(0)
    claim('power.by_region', rg, 'Power-line fires, acres and 300+ acre fires by project region, with the power-line '
          'share of each region\'s fires and acres, 1992-2020.', len(p))
    mo = pd.DataFrame({'fires': p.groupby('MONTH').size(), 'acres': p.groupby('MONTH')['FIRE_SIZE'].sum(),
                       'large_fires': p[p['LARGE']].groupby('MONTH').size()}).reindex(range(1, 13)).fillna(0)
    mo.index = MONTH_ABBR
    claim('power.by_month', mo, 'Power-line fires, acres and 300+ acre fires by discovery month, 1992-2020.', len(p))
    rm = p.groupby(['REGION', 'MONTH']).size().unstack(fill_value=0).reindex(
        index=REGION_ORDER, columns=range(1, 13), fill_value=0)
    rm.columns = MONTH_ABBR
    claim('power.region_by_month', rm, 'Power-line fires by region and discovery month, 1992-2020. Months and '
          'regions only: the record has no weather, so wind is not examined.', len(p))


def large_rates(df: pd.DataFrame) -> None:
    """Large-fire rate and acre share by human general cause: is power a large-fire cause out of proportion?"""
    h = df[(df['CAUSE'] == 'Human') & (df['GENERAL'] != CAUSE_MISSING)]
    g = h.groupby('GENERAL')
    t = pd.DataFrame({'fires': g.size(), 'large_fires': g['LARGE'].sum(), 'acres': g['FIRE_SIZE'].sum()})
    t['large_rate'] = t['large_fires'] / t['fires']
    t['share_of_fires'] = t['fires'] / t['fires'].sum()
    t['share_of_large_fires'] = t['large_fires'] / t['large_fires'].sum()
    t['share_of_acres'] = t['acres'] / t['acres'].sum()
    t['large_share_over_fire_share'] = t['share_of_large_fires'] / t['share_of_fires']
    t = t.sort_values('large_rate', ascending=False)
    claim('power.large_rate_by_human_cause', t,
          f'Human-caused records with a general cause, 1992-2020: fires, fires of {LARGE:.0f}+ acres, the rate, and '
          'each cause\'s share of fires, of large fires and of acres. A ratio of share of large fires to share of '
          'fires above 1 means the cause produces more than its share of large fires.', len(h))
    hp = h[h['GENERAL'] == POWER]
    rest = h[h['GENERAL'] != POWER]
    claim('power.large_rate_vs_other_human', {
        'power_large_rate': float(hp['LARGE'].mean()), 'other_human_large_rate': float(rest['LARGE'].mean()),
        'ratio': float(hp['LARGE'].mean() / rest['LARGE'].mean()),
        'power_rank_among_human_causes': int(list(t.index).index(POWER) + 1), 'human_causes': int(len(t)),
    }, f'Share of power-line fires reaching {LARGE:.0f} acres against the same share for every other human general '
       'cause pooled, 1992-2020, and power\'s rank by that rate.', len(h))
    if df['USABLE'].dtype == bool:
        w = h[h['USABLE'] & (h['FIRE_YEAR'] >= 2010)]
        wp = w[w['GENERAL'] == POWER]
        wr = w[w['GENERAL'] != POWER]
        claim('power.large_rate_vs_other_human_2010_2020_usable', {
            'power_fires': len(wp), 'power_large_rate': float(wp['LARGE'].mean()),
            'other_human_large_rate': float(wr['LARGE'].mean()),
            'ratio': float(wp['LARGE'].mean() / wr['LARGE'].mean()),
        }, 'Same comparison restricted to 2010-2020 and usable state-years, as a check that the result is not '
           'an artifact of early reporting.', len(w))


def largest_incidents(df: pd.DataFrame, tab_dir: str) -> None:
    g = df.groupby('INCIDENT', sort=False)
    lead = df.sort_values('FIRE_SIZE', ascending=False).drop_duplicates('INCIDENT').set_index('INCIDENT')
    inc = pd.DataFrame({'acres': g['FIRE_SIZE'].sum(), 'components': g.size(),
                        'power_records': g['POWER'].sum()})
    inc['general_cause'] = lead['GENERAL']
    pinc = inc[inc['general_cause'] == POWER].sort_values('acres', ascending=False)
    top = pinc.head(TOP_N)
    l = lead.loc[top.index]
    out = top.assign(
        name=clean_name(l['COMPLEX_NAME'].fillna(l['MTBS_FIRE_NAME']).fillna(l['FIRE_NAME'])).astype(object),
        state=l['STATE'], year=l['FIRE_YEAR'], region=region_of(l['STATE']), mtbs_id=l['MTBS_ID'])
    claim('power.largest_incidents', [
        {'rank': i + 1, 'name': r['name'] if isinstance(r['name'], str) else '(unnamed)', 'state': r['state'],
         'year': int(r['year']), 'acres': round(float(r['acres']), 1), 'components': int(r['components'])}
        for i, (_, r) in enumerate(out.iterrows())],
        f'The {TOP_N} largest incidents whose largest record is coded {POWER}. ' + INCIDENT_RULE, len(pinc))
    claim('power.incident_summary', {
        'incidents': len(pinc), 'incidents_100k_plus': int((pinc['acres'] >= 100_000).sum()),
        'incidents_10k_plus': int((pinc['acres'] >= 10_000).sum()),
        'top_incident_share_of_power_acres': float(top['acres'].sum() / pinc['acres'].sum()),
        'by_region_10k_plus': region_of(lead.loc[pinc.index[pinc['acres'] >= 10_000], 'STATE']).value_counts().to_dict(),
    }, f'Incidents led by a power-line record, and how concentrated their acres are in the top {TOP_N}.', len(pinc))
    os.makedirs(tab_dir, exist_ok=True)
    out.to_csv(os.path.join(tab_dir, 'power_lines_largest_incidents.csv'), float_format='%.1f')


def state_brief(df: pd.DataFrame, st: str) -> None:
    """Power-line numbers for one state's utility-audience brief: when, where (county), how often large, largest."""
    d = df[df['STATE'] == st]
    h = d[(d['CAUSE'] == 'Human') & (d['GENERAL'] != CAUSE_MISSING)]
    p = d[d['POWER']]
    g = h.groupby('GENERAL')
    rates = pd.DataFrame({'fires': g.size(), 'large_fires': g['LARGE'].sum(), 'acres': g['FIRE_SIZE'].sum()})
    rates['large_rate'] = rates['large_fires'] / rates['fires']
    rates = rates.sort_values('large_rate', ascending=False)
    mo = pd.DataFrame({'fires': p.groupby('MONTH').size(), 'large_fires': p[p['LARGE']].groupby('MONTH').size(),
                       'acres': p.groupby('MONTH')['FIRE_SIZE'].sum()}).reindex(range(1, 13)).fillna(0)
    mo['large_rate'] = (mo['large_fires'] / mo['fires'].where(mo['fires'] > 0)).fillna(0)
    mo.index = MONTH_ABBR
    county = p['FIPS_NAME'].astype('string').str.strip()
    known = county.notna() & (county != '')
    cty = pd.DataFrame({'fires': p[known].groupby(county[known]).size(),
                        'large_fires': p[known & p['LARGE']].groupby(county[known & p['LARGE']]).size(),
                        'acres': p[known].groupby(county[known])['FIRE_SIZE'].sum()}).fillna(0)
    cty = cty.sort_values(['large_fires', 'acres'], ascending=False).head(10)
    g2 = d.groupby('INCIDENT', sort=False)
    lead = d.sort_values('FIRE_SIZE', ascending=False).drop_duplicates('INCIDENT').set_index('INCIDENT')
    inc = pd.DataFrame({'acres': g2['FIRE_SIZE'].sum(), 'components': g2.size()})
    inc = inc[lead.loc[inc.index, 'GENERAL'] == POWER].sort_values('acres', ascending=False).head(10)
    l = lead.loc[inc.index]
    names = clean_name(l['COMPLEX_NAME'].fillna(l['MTBS_FIRE_NAME']).fillna(l['FIRE_NAME'])).astype(object)
    other = h[h['GENERAL'] != POWER]
    claim(f'power.state.{st}', {
        'fires': len(p), 'acres': float(p['FIRE_SIZE'].sum()), 'large_fires': int(p['LARGE'].sum()),
        'large_rate': float(p['LARGE'].mean()) if len(p) else None,
        'other_human_large_rate': float(other['LARGE'].mean()) if len(other) else None,
        'share_of_known_human_fires': len(p) / len(h) if len(h) else None,
        'share_of_known_human_large_fires': float(p['LARGE'].sum() / h['LARGE'].sum()) if h['LARGE'].sum() else None,
        'share_of_known_human_acres': float(p['FIRE_SIZE'].sum() / h['FIRE_SIZE'].sum()) if len(h) else None,
        'general_cause_missing_share': float((d['GENERAL'] == CAUSE_MISSING).mean()),
        'county_missing_share': float(1 - known.mean()) if len(p) else None,
        'by_month': mo, 'large_rate_by_human_cause': rates, 'top_counties': cty,
        'largest_incidents': [{'name': n if isinstance(n, str) else '(unnamed)', 'year': int(y), 'acres': round(float(a), 1),
                               'components': int(c)}
                              for n, y, a, c in zip(names, l['FIRE_YEAR'], inc['acres'], inc['components'])],
    }, f'Power-line fires in {st}, FPA FOD 1992-2020: counts, the share reaching {LARGE:.0f} acres against every other '
       'human general cause in the state, by discovery month, the ten counties (FIPS_NAME as recorded) with the most '
       'power-line fires of 300+ acres, and the ten largest incidents led by a power-line record (incidents rule). '
       'Human fires with no general cause are left out of the comparisons.', len(d))


def losses(df: pd.DataFrame) -> None:
    if not os.path.exists(ICS_INCIDENTS):
        log.warning('ICS-209-PLUS not found; losses section skipped')
        return
    inc = load_ics()
    j = df[df['ICS_209_PLUS_INCIDENT_JOIN_ID'].notna()]
    j = j[j['ICS_209_PLUS_INCIDENT_JOIN_ID'].astype(str).isin(set(inc['INCIDENT_ID']))]
    rep = j.sort_values('FIRE_SIZE', ascending=False).drop_duplicates('ICS_209_PLUS_INCIDENT_JOIN_ID')
    s = rep.set_index('ICS_209_PLUS_INCIDENT_JOIN_ID')[['FIRE_SIZE', 'FIRE_YEAR', 'CAUSE', 'GENERAL', 'REGION']].join(
        inc.drop(columns='CAUSE').set_index('INCIDENT_ID'), how='inner')  # CAUSE here is FPA FOD's, not ICS-209's
    # Same sample as the Protected lands and losses page (ics.sample_definition): 2010-2020, 300+ acres.
    s = s[(s['FIRE_YEAR'] >= 2010) & (s['FIRE_SIZE'] >= LARGE)]
    s = s[(s['CAUSE'] == 'Human') & (s['GENERAL'] != CAUSE_MISSING)].copy()  # same pool as large_rates
    s['GROUP'] = np.where(s['GENERAL'] == POWER, 'Power lines', 'Other human causes')
    sample = ('ICS-209-PLUS incidents joined to FPA FOD via ICS_209_PLUS_INCIDENT_JOIN_ID, one row per incident, '
              'attributes from the largest joined fire, FIRE_YEAR 2010-2020, FIRE_SIZE >= 300 acres, Human cause '
              'with a recorded general cause (the losses-page sample, restricted to the human general causes)')
    claim('power.losses_vs_other_human', _outcome_table(s, 'GROUP', ['Power lines', 'Other human causes']),
          'Losses for power-line incidents against every other human cause. ' + sample, len(s))
    claim('power.losses_by_region', _outcome_table(s[s['GROUP'] == 'Power lines'], 'REGION', REGION_ORDER),
          'Losses for power-line incidents by region. ' + sample, int((s['GROUP'] == 'Power lines').sum()))


def wfigs_extension() -> None:
    from .wfigs import PARQUET_PATH as WFIGS
    if not os.path.exists(WFIGS):
        log.warning('WFIGS 2021-2025 parquet not found; extension skipped')
        return
    w = pd.read_parquet(WFIGS, columns=['year', 'fire_cause_general', 'size_acres'])
    vals = w['fire_cause_general'].astype(str)
    hit = vals.str.contains('power', case=False, na=False)
    labels = sorted(vals[hit].unique().tolist())
    by = w[hit].groupby('year').agg(fires=('year', 'size'), acres=('size_acres', 'sum'))
    claim('power.wfigs_2021_2025', {
        'matching_labels': labels, 'fires': int(hit.sum()), 'acres': float(w.loc[hit, 'size_acres'].sum()),
        'by_year': by, 'share_of_rows': float(hit.mean()),
        'general_cause_missing_share': float(w['fire_cause_general'].isna().mean()),
    }, 'WFIGS 2021-2025 rows whose FireCauseGeneral contains "power". WFIGS is a different system and '
       'FireCauseGeneral is empty for most rows (general_cause_missing_share), so these counts are not a '
       'continuation of the FPA FOD series.',
          len(w))


def run(out_dir: str) -> None:
    t0 = time.time()
    df = load(out_dir)
    log.info(f'loaded {len(df):,} fires, {int(df["POWER"].sum()):,} power-line ({time.time() - t0:.0f}s)')
    overview(df)
    by_year_region_month(df)
    large_rates(df)
    df['INCIDENT'] = group(df)
    largest_incidents(df, os.path.join(out_dir, 'tables'))
    for st in BRIEF_STATES:
        state_brief(df, st)
    losses(df)
    wfigs_extension()
    log.info(f'power lines done in {time.time() - t0:.0f}s')


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default='outputs')
    args = ap.parse_args(argv)
    set_source('analysis.power_lines')
    run(args.out)
    path = os.path.join(args.out, 'claims_power.json')
    print(f'claims: {write_claims(path)} -> {path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
