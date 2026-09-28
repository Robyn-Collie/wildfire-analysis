"""Group FPA FOD records into incidents, and list the largest incidents once each.

The FPA FOD has one row per reported fire. A complex (several fires managed as one incident) appears as
several rows: the August Complex of 2020 is the DOE fire (589,368 acres) and the HOPKINS fire (328,363
acres), among others. A "largest fires" list built from rows therefore shows the same incident more than
once. The first public site did (docs/review/V1_SITE_AUDIT.md, row "100 largest fires").

Usage (from the repo root):
    python -m analysis.incidents --out outputs/

Writes:
    outputs/tables/largest_incidents.csv   the 250 largest incidents, one row each, with their component fires
    outputs/claims_incidents.json          claims

Rule. Two records belong to the same incident when they share any of these keys:
    ICS_209_PLUS_COMPLEX_JOIN_ID              the same ICS-209 complex
    ICS_209_PLUS_INCIDENT_JOIN_ID             the same ICS-209 incident
    FIRE_YEAR + STATE + COMPLEX_NAME          the same named complex in the same state and year
Membership is transitive (connected components of the record-key graph). A record with none of the keys is
an incident on its own. MTBS_ID is deliberately not a grouping key: one MTBS perimeter can span fires managed
as different complexes (in the 2008 northern California lightning siege, chaining through MTBS_ID merged four
complexes and 107 records into one "incident").

The FPA FOD may still hold a few fires reported twice by two systems. A rule to find them (same MTBS
perimeter, different source system, similar size) was tried and dropped: it flagged the I-40 and Borger (HWY 152)
fires of the 2006 East Amarillo Complex, which are two separate fires of 427,696 and 479,549 acres. No record is
removed.

Incident acres are the sum of the component records' FIRE_SIZE. Components of a complex mostly burn separate ground,
so the sum is the complex's area as reported to the FPA FOD, not an MTBS mapped area. When components merged
during the fire and each record reports the merged area, the sum overstates; the table shows the largest
record beside the sum so a reader can see how much depends on the grouping.
"""
from __future__ import annotations

import argparse
import logging
import os
import time

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from .common import claim, load_fires, region_of, set_source, write_claims

log = logging.getLogger('incidents')

COLUMNS = ['FOD_ID', 'SOURCE_SYSTEM', 'FIRE_YEAR', 'STATE', 'FIRE_NAME', 'FIRE_SIZE', 'MTBS_ID', 'MTBS_FIRE_NAME', 'COMPLEX_NAME',
           'ICS_209_PLUS_INCIDENT_JOIN_ID', 'ICS_209_PLUS_COMPLEX_JOIN_ID', 'DISCOVERY_DATE',
           'NWCG_CAUSE_CLASSIFICATION', 'NWCG_GENERAL_CAUSE', 'LATITUDE', 'LONGITUDE']
KEYS = ['ICS_209_PLUS_COMPLEX_JOIN_ID', 'ICS_209_PLUS_INCIDENT_JOIN_ID', 'COMPLEX_KEY']
TOP_N = 250
RULE = ('Records share an incident when they share ICS_209_PLUS_COMPLEX_JOIN_ID, ICS_209_PLUS_INCIDENT_JOIN_ID, '
        'or FIRE_YEAR+STATE+COMPLEX_NAME (transitively). Incident acres = sum of component FIRE_SIZE; '
        'no record is dropped.')


def clean_name(s: pd.Series) -> pd.Series:
    """Upper case, non-breaking spaces and runs of whitespace collapsed ("SOLSTICE\\xa0COMPLEX")."""
    return s.astype('string').str.replace('\u00a0', ' ', regex=False).str.replace(r'\s+', ' ', regex=True).str.strip().str.upper()


def group(df: pd.DataFrame) -> pd.Series:
    """Incident id for every row: the smallest FOD_ID in its connected component."""
    df = df.copy()
    name = clean_name(df['COMPLEX_NAME'])
    df['COMPLEX_KEY'] = (df['FIRE_YEAR'].astype(str) + '|' + df['STATE'].astype(str) + '|' + name).where(name.notna() & (name != ''))
    pos = np.arange(len(df))
    rows, cols = [], []
    offset = len(df)
    for k in KEYS:
        v = df[k].astype('string')
        ok = v.notna() & (v.str.strip() != '')
        codes, _ = pd.factorize(v[ok])
        rows.append(pos[ok.to_numpy()])
        cols.append(codes + offset)
        offset += int(codes.max()) + 1 if len(codes) else 0
    r = np.concatenate(rows)
    c = np.concatenate(cols)
    g = coo_matrix((np.ones(len(r), dtype=np.int8), (r, c)), shape=(offset, offset))
    _, label = connected_components(g, directed=False)
    label = label[:len(df)]
    fod = df['FOD_ID'].to_numpy()
    first = pd.Series(fod).groupby(label).transform('min').to_numpy()
    return pd.Series(first, index=df.index, name='INCIDENT')


def incident_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Acres, component count and lead record (largest component) for every incident: vectorised."""
    g = df.groupby('INCIDENT', sort=False)
    out = pd.DataFrame({'acres': g['FIRE_SIZE'].sum(), 'components': g.size()})
    lead = df.sort_values('FIRE_SIZE', ascending=False).drop_duplicates('INCIDENT').set_index('INCIDENT')
    out['state'] = lead['STATE']
    out['year'] = lead['FIRE_YEAR']
    out['cause'] = lead['NWCG_CAUSE_CLASSIFICATION']
    return out.sort_values('acres', ascending=False)


def incident_table(df: pd.DataFrame) -> pd.DataFrame:
    """Full description of the incidents present in ``df`` (call on the rows of the top incidents only)."""
    df = df.sort_values('FIRE_SIZE', ascending=False)
    g = df.groupby('INCIDENT', sort=False)
    lead = g.head(1).set_index('INCIDENT')
    out = pd.DataFrame({
        'acres': g['FIRE_SIZE'].sum(),
        'components': g.size(),
        'largest_component_acres': g['FIRE_SIZE'].max(),
        'first_discovery': g['DISCOVERY_DATE'].min(),
        'states': g['STATE'].agg(lambda s: '/'.join(sorted(set(s)))),
        'years': g['FIRE_YEAR'].agg(lambda s: '/'.join(str(y) for y in sorted(set(s)))),
        'component_names': g['FIRE_NAME'].agg(lambda s: '; '.join(str(x) for x in s.head(8)) + ('; ...' if len(s) > 8 else '')),
    })
    out['name'] = clean_name(lead['COMPLEX_NAME'].fillna(lead['MTBS_FIRE_NAME']).fillna(lead['FIRE_NAME']))
    out['lead_fire'] = clean_name(lead['FIRE_NAME'])
    out['state'] = lead['STATE']
    out['year'] = lead['FIRE_YEAR']
    out['cause'] = lead['NWCG_CAUSE_CLASSIFICATION']
    out['general_cause'] = lead['NWCG_GENERAL_CAUSE']
    out['mtbs_id'] = lead['MTBS_ID']
    out['ics209_id'] = lead['ICS_209_PLUS_COMPLEX_JOIN_ID'].fillna(lead['ICS_209_PLUS_INCIDENT_JOIN_ID'])
    out['latitude'] = lead['LATITUDE']
    out['longitude'] = lead['LONGITUDE']
    out.index.name = 'incident_fod_id'
    return out.sort_values('acres', ascending=False)


def run(out_dir: str) -> None:
    t0 = time.time()
    df = load_fires(COLUMNS)
    n = len(df)
    df['INCIDENT'] = group(df)
    rows_all = df
    inc = incident_totals(df)
    multi = inc[inc['components'] > 1]
    log.info(f'{n:,} records -> {len(inc):,} incidents ({len(multi):,} with >1 record) in {time.time() - t0:.1f}s')

    claim('incidents.rule', RULE, 'How FPA FOD records are grouped into incidents for the largest-fires table.', None)
    claim('incidents.grouping', {
        'records': n, 'incidents': len(inc), 'multi_record_incidents': len(multi),
        'records_in_multi_record_incidents': int(multi['components'].sum()),
        'max_components': int(inc['components'].max()),
    }, 'Records, incidents after grouping, and incidents made of more than one record (FPA FOD 1992-2020).', n)

    # The row-based list the first site used, and how many of its rows are the same incident.
    for top in (100,):
        rows = rows_all.nlargest(top, 'FIRE_SIZE')
        k = rows['INCIDENT'].nunique()
        dup = rows[rows['INCIDENT'].duplicated(keep=False)].sort_values(['INCIDENT', 'FIRE_SIZE'], ascending=[True, False])
        dup = dup.assign(COMPLEX_NAME=clean_name(dup['COMPLEX_NAME']).astype(object),
                         FIRE_NAME=clean_name(dup['FIRE_NAME']).astype(object))
        pairs = (dup.groupby('INCIDENT').agg(name=('COMPLEX_NAME', 'first'), year=('FIRE_YEAR', 'first'),
                                            state=('STATE', 'first'), records=('FIRE_NAME', list),
                                            ranks=('FIRE_SIZE', lambda s: [int((rows['FIRE_SIZE'] > x).sum()) + 1 for x in s])))
        claim(f'incidents.row_top{top}_duplicates', {
            'rows': top, 'distinct_incidents': int(k), 'rows_sharing_an_incident': int(len(dup)),
            'incidents_with_several_rows': [
                {'name': r['name'] if isinstance(r['name'], str) else r['records'][0], 'year': int(r['year']),
                 'state': r['state'], 'records': r['records'], 'row_ranks': r['ranks']}
                for _, r in pairs.iterrows()],
        }, f'Among the {top} largest FPA FOD records by FIRE_SIZE, how many distinct incidents they are, and which '
           'incidents appear as more than one row (the first public site listed rows).', top)

    top = incident_table(df[df['INCIDENT'].isin(inc.index[:TOP_N])]).head(TOP_N)
    claim('incidents.largest', [
        {'rank': i + 1, 'name': r['name'], 'lead_fire': r['lead_fire'], 'state': r['states'], 'year': r['years'],
         'acres': round(float(r['acres']), 1), 'components': int(r['components']),
         'largest_component_acres': round(float(r['largest_component_acres']), 1), 'cause': r['cause']}
        for i, (_, r) in enumerate(top.head(25).iterrows())],
        'The 25 largest incidents in FPA FOD 1992-2020, one row per incident. ' + RULE, n)
    top100 = inc.head(100)
    claim('incidents.largest100_summary', {
        'acres_min': float(top100['acres'].min()), 'acres_max': float(top100['acres'].max()),
        'multi_record': int((top100['components'] > 1).sum()),
        'by_state': top100['state'].value_counts().head(10).to_dict(),
        'alaska_share': float((top100['state'] == 'AK').mean()),
        'by_decade': top100['year'].map(lambda y: f'{int(y) // 10 * 10}s').value_counts().sort_index().to_dict(),
        'since_2010': int((top100['year'] >= 2010).sum()),
        'by_cause': top100['cause'].value_counts().to_dict(),
        'by_region': region_of(top100['state']).value_counts().to_dict(),
    }, 'The 100 largest incidents (grouped): acreage range, how many are complexes of several records, and where, '
       'when and by what cause they started (cause and state of the largest component).', n)
    big = inc[inc['acres'] >= 100_000]
    per_year = big.groupby('year').size().reindex(range(1992, 2021), fill_value=0)
    claim('incidents.100k_per_year', per_year.to_dict(),
          'Incidents of 100,000 acres or more per year (grouped, discovery year of the largest component). '
          'Very large fires are reported by federal systems throughout, so this count is less exposed to the '
          'reporting breaks that affect small-fire counts, but it is still a count from a compiled record.', len(big))

    tab_dir = os.path.join(out_dir, 'tables')
    os.makedirs(tab_dir, exist_ok=True)
    cols = ['name', 'lead_fire', 'states', 'years', 'first_discovery', 'acres', 'components', 'largest_component_acres',
            'cause', 'general_cause', 'mtbs_id', 'ics209_id', 'latitude', 'longitude', 'component_names']
    t = top[cols].copy()
    t.insert(0, 'rank', np.arange(1, len(t) + 1))
    t['first_discovery'] = pd.to_datetime(t['first_discovery']).dt.date.astype(str)
    t.to_csv(os.path.join(tab_dir, 'largest_incidents.csv'), float_format='%.1f')


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default='outputs')
    args = ap.parse_args(argv)
    set_source('analysis.incidents')
    run(args.out)
    path = os.path.join(args.out, 'claims_incidents.json')
    print(f'claims: {write_claims(path)} -> {path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
