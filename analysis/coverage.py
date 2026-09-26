"""Coverage mask for the FPA FOD: which state-years can be used for count-based trends.

The FPA FOD is a compilation of federal, state and local reporting systems, not a census
(see docs/review/panel-fire.md F1). Reporter entry and exit shows up as step changes in the
state-year record counts. This module records the state x year series, flags the breaks,
derives a "usable window" per state and registers the headline numbers as claims.

Usage (from the repo root):
    python -m analysis.coverage --out outputs/

Writes:
    outputs/coverage.json                per state: series, flags, usable window; plus the agency-by-year table
    outputs/coverage_state_year.csv      one row per state-year with counts, acres, flags and coverage_ok
    outputs/figures/coverage_state_year.png
    outputs/claims_coverage.json         claims (when run standalone; analysis.conservation folds them into its own file)

Rule (coverage_ok):
    A break is flagged on year y of a state when the record count changes by more than a factor of
    BREAK_FACTOR (3) against the most recent earlier year with a non-zero count, provided the larger
    of the two counts is at least MIN_COUNT (30) so that tiny series do not trip the test. Zero-count
    years are flagged separately and are never usable. A break year starts a new reporting regime, so
    runs are cut *before* each break year and at every zero year. The usable window is the longest run
    of consecutive non-zero years with no break inside it (ties go to the most recent run).
    coverage_ok(state, year) is True when the year lies inside that window.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time

import numpy as np
import pandas as pd

from .common import claim, load_fires, region_of, set_source, write_claims, REGION_ORDER

log = logging.getLogger('coverage')

YEARS = list(range(1992, 2021))
BREAK_FACTOR = 3.0
MIN_COUNT = 30
COLUMNS = ['FIRE_YEAR', 'STATE', 'FIRE_SIZE', 'NWCG_REPORTING_AGENCY', 'SOURCE_SYSTEM_TYPE', 'SOURCE_SYSTEM']
RULE = (f'break on year y if count(y) / count(prior non-zero year) > {BREAK_FACTOR:g} or < 1/{BREAK_FACTOR:g} and '
        f'max(count(y), count(prior)) >= {MIN_COUNT}; zero-count years flagged and never usable; usable window = '
        'longest run of consecutive non-zero years containing no break year after its first year (ties to the '
        'most recent run); coverage_ok(state, year) = year inside the usable window')


# --------------------------------------------------------------------------- core

def flag_series(counts: pd.Series) -> pd.DataFrame:
    """Flag one state's year-indexed count series. Returns a frame indexed like ``counts``."""
    counts = counts.reindex(YEARS, fill_value=0).astype(int)
    out = pd.DataFrame({'fires': counts})
    out['zero'] = counts == 0
    ratio = pd.Series(np.nan, index=counts.index)
    prev = None
    for y in YEARS:
        c = counts[y]
        if c > 0 and prev is not None:
            ratio[y] = c / prev
        if c > 0:
            prev = c
    out['ratio_to_prior_nonzero'] = ratio
    big = np.maximum(counts, counts.where(counts > 0).ffill().shift(1).fillna(0)) >= MIN_COUNT
    out['break_up'] = (ratio > BREAK_FACTOR) & big
    out['break_down'] = (ratio < 1 / BREAK_FACTOR) & big
    out['break'] = out['break_up'] | out['break_down']
    nz = counts[counts > 0]
    out['first_year'] = int(nz.index.min()) if len(nz) else None
    out['last_year'] = int(nz.index.max()) if len(nz) else None
    # runs: cut before each break year and at zero years
    run_id = np.zeros(len(YEARS), dtype=int)
    rid = 0
    for i, y in enumerate(YEARS):
        if out.loc[y, 'zero']:
            run_id[i] = -1
            rid += 1
            continue
        if out.loc[y, 'break'] or (i > 0 and run_id[i - 1] == -1) or i == 0:
            rid += 1
        run_id[i] = rid
    out['run_id'] = run_id
    lengths = out[out['run_id'] >= 0].groupby('run_id').size()
    if len(lengths):
        best_len = lengths.max()
        best = lengths[lengths == best_len].index.max()  # ties: most recent
        yrs = out.index[out['run_id'] == best]
        out['coverage_ok'] = out['run_id'] == best
        out['window_start'] = int(yrs.min())
        out['window_end'] = int(yrs.max())
    else:
        out['coverage_ok'] = False
        out['window_start'] = None
        out['window_end'] = None
    return out


def coverage_ok(state: str, year: int, table: pd.DataFrame) -> bool:
    """Look up the rule on the state-year table produced by ``build``."""
    row = table[(table['STATE'] == state) & (table['FIRE_YEAR'] == year)]
    return bool(row['coverage_ok'].iloc[0]) if len(row) else False


def build(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (state_year table, agency x year counts, source-system-type x year counts)."""
    sy = df.groupby(['STATE', 'FIRE_YEAR'], observed=True)['FIRE_SIZE'].agg(fires='size', acres='sum')
    states = sorted(df['STATE'].astype(str).unique())
    parts = []
    for st in states:
        s = sy.xs(st, level='STATE') if st in sy.index.get_level_values(0) else pd.DataFrame()
        f = flag_series(s['fires'] if len(s) else pd.Series(dtype=int))
        f['acres'] = s['acres'].reindex(YEARS, fill_value=0.0) if len(s) else 0.0
        f['STATE'] = st
        f['FIRE_YEAR'] = f.index
        parts.append(f.reset_index(drop=True))
    table = pd.concat(parts, ignore_index=True)
    table['REGION'] = region_of(table['STATE'])
    table = table[['STATE', 'REGION', 'FIRE_YEAR', 'fires', 'acres', 'zero', 'ratio_to_prior_nonzero', 'break_up',
                   'break_down', 'break', 'first_year', 'last_year', 'run_id', 'window_start', 'window_end',
                   'coverage_ok']]
    agency = pd.crosstab(df['FIRE_YEAR'], df['NWCG_REPORTING_AGENCY'].astype(str)).reindex(YEARS, fill_value=0)
    sst = pd.crosstab(df['FIRE_YEAR'], df['SOURCE_SYSTEM_TYPE'].astype(str)).reindex(YEARS, fill_value=0) \
        if 'SOURCE_SYSTEM_TYPE' in df.columns else pd.DataFrame(index=YEARS)
    return table, agency, sst


# --------------------------------------------------------------------------- claims

def register(table: pd.DataFrame, agency: pd.DataFrame, sst: pd.DataFrame, n: int) -> dict:
    per_state = {}
    for st, g in table.groupby('STATE'):
        g = g.set_index('FIRE_YEAR')
        per_state[st] = {
            'region': str(g['REGION'].iloc[0]),
            'n_records': int(g['fires'].sum()),
            'fires': {int(y): int(v) for y, v in g['fires'].items()},
            'acres': {int(y): float(v) for y, v in g['acres'].items()},
            'first_year': None if pd.isna(g['first_year'].iloc[0]) else int(g['first_year'].iloc[0]),
            'last_year': None if pd.isna(g['last_year'].iloc[0]) else int(g['last_year'].iloc[0]),
            'zero_years': [int(y) for y in g.index[g['zero']]],
            'break_years': {int(y): round(float(g.loc[y, 'ratio_to_prior_nonzero']), 2) for y in g.index[g['break']]},
            'usable_window': [None if pd.isna(g['window_start'].iloc[0]) else int(g['window_start'].iloc[0]),
                              None if pd.isna(g['window_end'].iloc[0]) else int(g['window_end'].iloc[0])],
            'records_in_window': int(g.loc[g['coverage_ok'], 'fires'].sum()),
            'share_in_window': float(g.loc[g['coverage_ok'], 'fires'].sum() / max(g['fires'].sum(), 1)),
        }
    st_tot = table.groupby('STATE')['fires'].sum()
    big_states = st_tot[st_tot >= 1000].index
    has_break = table[table['break']].groupby('STATE').size()
    has_zero = table[table['zero'] & (table['FIRE_YEAR'] >= table['first_year']) & (table['FIRE_YEAR'] <= table['last_year'])] \
        .groupby('STATE').size()
    n_states = int(table['STATE'].nunique())
    claim('coverage.rule', RULE, 'the coverage_ok rule as implemented in analysis/coverage.py', None)
    claim('coverage.n_states', n_states, 'distinct STATE values (states, DC and territories)', n)
    claim('coverage.n_states_ge_1000_records', int(len(big_states)), 'STATE values with at least 1,000 records', n)
    claim('coverage.n_states_with_break', int(len(has_break)),
          'STATE values with at least one flagged break year (rule in coverage.rule)', n)
    claim('coverage.n_states_ge_1000_with_break', int(has_break.reindex(big_states).dropna().shape[0]),
          'same, among STATE values with at least 1,000 records', n)
    claim('coverage.n_break_state_years', int(table['break'].sum()), 'state-years flagged as breaks', n)
    claim('coverage.states_with_interior_zero_years', {s: per_state[s]['zero_years'] for s in has_zero.index},
          'STATE values with a zero-count year between their first and last year with records', n)
    in_win = table.loc[table['coverage_ok'], 'fires'].sum()
    claim('coverage.share_records_in_usable_window', float(in_win / n),
          'share of all records whose state-year lies inside the state usable window', n, unit='share')
    claim('coverage.share_acres_in_usable_window', float(table.loc[table['coverage_ok'], 'acres'].sum() / table['acres'].sum()),
          'share of all acres whose state-year lies inside the state usable window', n, unit='share')
    win_len = table.groupby('STATE')['coverage_ok'].sum()
    claim('coverage.window_length_years', {'median': float(win_len.median()), 'min': int(win_len.min()),
                                           'max': int(win_len.max()),
                                           'n_states_full_29': int((win_len == 29).sum()),
                                           'n_states_lt_10': int((win_len < 10).sum())},
          'length of the usable window in years across STATE values', n, unit='years')
    claim('coverage.usable_window_by_state', {s: per_state[s]['usable_window'] for s in per_state},
          'usable window [start, end] per STATE', n)
    claim('coverage.break_years_by_state', {s: per_state[s]['break_years'] for s in per_state if per_state[s]['break_years']},
          'flagged break years per STATE with the count ratio to the prior non-zero year', n)
    # national count series with and without the mask
    nat = table.groupby('FIRE_YEAR')['fires'].sum()
    nat_ok = table[table['coverage_ok']].groupby('FIRE_YEAR')['fires'].sum().reindex(YEARS, fill_value=0)
    n_states_ok = table[table['coverage_ok']].groupby('FIRE_YEAR')['STATE'].nunique().reindex(YEARS, fill_value=0)
    claim('coverage.national_fires_by_year_all_vs_masked',
          pd.DataFrame({'all_states': nat, 'usable_state_years_only': nat_ok, 'n_states_usable': n_states_ok}),
          'fires per FIRE_YEAR over all state-years and over usable state-years only, with the number of states '
          'contributing', n,
          note='The masked series is not a national series either: the set of contributing states changes by year.')
    # federal agencies: stable?
    fed = ['FS', 'BLM', 'BIA', 'NPS', 'FWS']
    fed_tbl = agency.reindex(columns=[c for c in fed if c in agency.columns], fill_value=0)
    claim('coverage.fires_by_reporting_agency_year', agency, 'records by FIRE_YEAR and NWCG_REPORTING_AGENCY', n)
    ia = agency['IA'] if 'IA' in agency.columns else pd.Series(0, index=YEARS)
    claim('coverage.ia_irwin_switch_2020', {'IA_records_2020': int(ia.get(2020, 0)),
                                            'IA_records_1992_2019': int(ia.loc[:2019].sum()),
                                            'FS_records_2019': int(agency['FS'].get(2019, 0)),
                                            'FS_records_2020': int(agency['FS'].get(2020, 0)),
                                            'source_system_type_2020': {k: int(v) for k, v in sst.loc[2020].items()} if len(sst.columns) else None,
                                            'source_system_type_2019': {k: int(v) for k, v in sst.loc[2019].items()} if len(sst.columns) else None},
          'records with NWCG_REPORTING_AGENCY == IA in 2020 versus earlier years, FS records in 2019 and 2020, '
          'and records by SOURCE_SYSTEM_TYPE in 2019 and 2020', n,
          note='In 2020 the federal source systems (FS-FIRESTAT, DOI-WFMI) were replaced by IA-IRWIN, so '
               'SOURCE_SYSTEM_TYPE jumps from FED to INTERAGCY. NWCG_REPORTING_AGENCY is preserved (FS still has '
               'thousands of 2020 records and IA only a handful), so agency-level series must use '
               'NWCG_REPORTING_AGENCY, and SOURCE_SYSTEM_TYPE series break at 2020.')
    fed_flags = {a: flag_series(fed_tbl[a])['break'].sum() for a in fed_tbl.columns}
    claim('coverage.federal_agency_break_years_1992_2019',
          {a: [int(y) for y in flag_series(fed_tbl[a].loc[:2019]).index[flag_series(fed_tbl[a].loc[:2019])['break']]]
           for a in fed_tbl.columns},
          'break years (same rule) in the national count series of each federal reporting agency, 1992-2019', n,
          note='2020 is excluded because of the IA-IRWIN switch.')
    _ = fed_flags
    if len(sst.columns):
        claim('coverage.fires_by_source_system_type_year', sst, 'records by FIRE_YEAR and SOURCE_SYSTEM_TYPE', n)
        nonfed = sst['NONFED'] / sst.sum(axis=1) if 'NONFED' in sst.columns else None
        if nonfed is not None:
            claim('coverage.nonfed_share_by_year', nonfed, 'share of records with SOURCE_SYSTEM_TYPE == NONFED by year', n,
                  unit='share')
    # region view of the mask
    reg = table.groupby(['REGION', 'FIRE_YEAR']).apply(lambda g: g.loc[g['coverage_ok'], 'fires'].sum() / max(g['fires'].sum(), 1),
                                                       include_groups=False).unstack(0).reindex(columns=REGION_ORDER)
    claim('coverage.share_records_in_window_by_region_year', reg,
          'share of a region-year\'s records that lie inside their state usable window', n, unit='share')
    return {'rule': RULE, 'break_factor': BREAK_FACTOR, 'min_count': MIN_COUNT, 'years': YEARS, 'states': per_state,
            'agency_by_year': {int(y): {str(a): int(v) for a, v in row.items()} for y, row in agency.iterrows()},
            'source_system_type_by_year': {int(y): {str(a): int(v) for a, v in row.items()} for y, row in sst.iterrows()}
            if len(sst.columns) else {}}


# --------------------------------------------------------------------------- figure

def figure(table: pd.DataFrame, n: int, fig_dir: str) -> str:
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    from .figures import SEQ, SURFACE, INK, INK2, MUTED, GRID, AXIS, _clean, _footer, _save, FIG_W

    tot = table.groupby('STATE')['fires'].sum()
    order = []
    for r in REGION_ORDER:
        sts = table[table['REGION'] == r]['STATE'].unique()
        order += sorted(sts, key=lambda s: -tot[s])
    mat = table.pivot(index='STATE', columns='FIRE_YEAR', values='fires').reindex(index=order, columns=YEARS).fillna(0)
    ok = table.pivot(index='STATE', columns='FIRE_YEAR', values='coverage_ok').reindex(index=order, columns=YEARS).fillna(False)
    brk = table.pivot(index='STATE', columns='FIRE_YEAR', values='break').reindex(index=order, columns=YEARS).fillna(False)
    logm = np.log10(mat.where(mat > 0))
    cmap = LinearSegmentedColormap.from_list('seqblue', SEQ)
    cmap.set_bad(GRID)
    h = 0.17 * len(order) + 1.6
    fig, ax = plt.subplots(figsize=(FIG_W, h))
    im = ax.imshow(np.ma.masked_invalid(logm.values), cmap=cmap, aspect='auto', vmin=0, vmax=5,
                   extent=(YEARS[0] - 0.5, YEARS[-1] + 0.5, len(order) - 0.5, -0.5), interpolation='nearest')
    # white hairlines between cells (the 2px surface gap)
    for y in YEARS[1:]:
        ax.axvline(y - 0.5, color=SURFACE, lw=0.8)
    for i in range(1, len(order)):
        ax.axhline(i - 0.5, color=SURFACE, lw=0.8)
    # break marks and window outline
    for i, st in enumerate(order):
        for j, y in enumerate(YEARS):
            if brk.loc[st, y]:
                ax.plot(y, i, marker='x', ms=4, mew=1.2, color=INK, zorder=4)
        w = ok.loc[st]
        if w.any():
            y0, y1 = YEARS[int(np.argmax(w.values))], YEARS[len(YEARS) - 1 - int(np.argmax(w.values[::-1]))]
            ax.add_patch(plt.Rectangle((y0 - 0.5, i - 0.5), y1 - y0 + 1, 1, fill=False, ec=INK2, lw=0.9, zorder=3))
    # region separators
    pos = 0
    for r in REGION_ORDER:
        k = int((table[table['REGION'] == r]['STATE'].nunique()))
        if k == 0:
            continue
        if pos > 0:
            ax.axhline(pos - 0.5, color=INK2, lw=0.6)
        label = {'Alaska': 'AK', 'Hawaii/PR': 'HI/PR'}.get(r, r)
        ax.text(YEARS[-1] + 0.9, pos + k / 2 - 0.5, label, va='center', ha='left', fontsize=7.5, color=INK2,
                rotation=270 if k > 2 else 0)
        pos += k
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels(order, fontsize=7)
    ax.set_xticks(YEARS[::2])
    ax.set_xticklabels([str(y) for y in YEARS[::2]], fontsize=8)
    ax.set_xlim(YEARS[0] - 0.5, YEARS[-1] + 2.5)
    ax.set_xlabel('Discovery year')
    ax.set_title('Fires per state-year, with reporting breaks and usable windows', loc='left', fontsize=11)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.06, ticks=[0, 1, 2, 3, 4, 5])
    cb.ax.set_yticklabels(['1', '10', '100', '1k', '10k', '100k'])
    cb.set_label('Fires in the state-year (log scale)')
    cb.outline.set_visible(False)
    handles = [Line2D([], [], marker='x', color=INK, ls='', ms=5, mew=1.2, label='Break: count changed > 3x vs prior year'),
               Patch(fc='none', ec=INK2, lw=0.9, label='Usable window (longest run with no break)'),
               Patch(fc=GRID, ec='none', label='No records')]
    ax.legend(handles=handles, loc='lower center', bbox_to_anchor=(0.42, -0.075), ncol=3, fontsize=7.5, frameon=False)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    _footer(fig, f'{n:,} fires', 'States grouped by project region, sorted by record count. Break years start a new reporting regime.')
    return _save(fig, fig_dir, 'coverage_state_year.png')


# --------------------------------------------------------------------------- main

def run(out_dir: str, df: pd.DataFrame | None = None) -> pd.DataFrame:
    os.makedirs(out_dir, exist_ok=True)
    fig_dir = os.path.join(out_dir, 'figures')
    t0 = time.time()
    if df is None:
        df = load_fires(COLUMNS)
    n = len(df)
    table, agency, sst = build(df)
    payload = register(table, agency, sst, n)
    table.to_csv(os.path.join(out_dir, 'coverage_state_year.csv'), index=False)
    with open(os.path.join(out_dir, 'coverage.json'), 'w') as f:
        json.dump(payload, f, indent=1)
    figure(table, n, fig_dir)
    log.info(f'coverage done in {time.time() - t0:.1f}s')
    return table


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default='outputs')
    args = ap.parse_args(argv)
    set_source('analysis.coverage')
    run(args.out)
    path = os.path.join(args.out, 'claims_coverage.json')
    print(f'claims: {write_claims(path)} -> {path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
