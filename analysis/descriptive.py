"""Descriptive analysis of the FPA FOD record: every number registered as a claim.

Usage (from the repo root):
    python -m analysis.descriptive --out outputs/

Writes:
    outputs/claims.json          every computed number with definition, n and source
    outputs/cells_1deg.csv       1-degree cell aggregation
    outputs/figures/*.png        static figures (see analysis/figures.py)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time

import numpy as np
import pandas as pd
from scipy import stats

from . import figures
from .common import (CAUSE_MISSING, GACC_DEFINITION, MONTH_ABBR, NORTHEAST, OWNER_MISSING, REGION_DEFINITION,
                     REGION_ORDER, SIZE_CLASS_DEFINITION, SIZE_CLASSES, claim, gacc_of, load_fires,
                     normalize_owner, region_of, set_source, write_claims)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger('descriptive')

COLUMNS = ['FIRE_YEAR', 'DISCOVERY_MONTH', 'DISCOVERY_TIME', 'CONT_DATE', 'CONT_TIME', 'DISCOVERY_DATETIME',
           'CONT_DATETIME', 'DURATION_HOURS', 'DURATION_DAYS', 'NWCG_CAUSE_CLASSIFICATION', 'NWCG_GENERAL_CAUSE',
           'FIRE_SIZE', 'FIRE_SIZE_CLASS', 'OWNER_DESCR', 'STATE', 'LATITUDE', 'LONGITUDE', 'FIRE_NAME',
           'NWCG_REPORTING_AGENCY']

YEARS = list(range(1992, 2021))
ALL_ROWS = 'all 2,303,566 records in data/fires.parquet (FPA FOD 6th ed., 1992-2020)'


def _trend(series: pd.Series) -> dict:
    """Kendall tau, Theil-Sen slope and intercept for a year-indexed series."""
    x = np.asarray(series.index, dtype=float)
    y = np.asarray(series.values, dtype=float)
    tau = stats.kendalltau(x, y)
    ts = stats.theilslopes(y, x)
    return {'kendall_tau': float(tau.statistic), 'kendall_p': float(tau.pvalue),
            'theil_sen_slope': float(ts.slope), 'theil_sen_intercept': float(ts.intercept),
            'theil_sen_slope_ci95': [float(ts.low_slope), float(ts.high_slope)]}


def _fires_acres(df: pd.DataFrame, by, **kw) -> pd.DataFrame:
    out = df.groupby(by, observed=True, **kw)['FIRE_SIZE'].agg(fires='size', acres='sum')
    out['fires'] = out['fires'].astype(int)
    return out


# --------------------------------------------------------------------------- sections

def overview(df: pd.DataFrame) -> None:
    n = len(df)
    claim('overview.n_rows', n, 'row count of data/fires.parquet (table Fires of FPA_FOD_20221014.sqlite)', n)
    claim('overview.years', [int(df['FIRE_YEAR'].min()), int(df['FIRE_YEAR'].max())],
          'min and max FIRE_YEAR', n)
    claim('overview.total_acres', float(df['FIRE_SIZE'].sum()), 'sum of FIRE_SIZE over all records', n, unit='acres')
    claim('overview.largest_fire_acres', float(df['FIRE_SIZE'].max()), 'max FIRE_SIZE', n, unit='acres',
          note=f"{df.loc[df['FIRE_SIZE'].idxmax(), 'FIRE_NAME']} ({df.loc[df['FIRE_SIZE'].idxmax(), 'STATE']}, "
               f"{int(df.loc[df['FIRE_SIZE'].idxmax(), 'FIRE_YEAR'])})")
    claim('overview.smallest_fire_acres', float(df['FIRE_SIZE'].min()), 'min FIRE_SIZE', n, unit='acres')

    miss = {
        'CONT_DATE': int(df['CONT_DATE'].isna().sum()),
        'CONT_TIME': int(df['CONT_TIME'].isna().sum()),
        'DISCOVERY_TIME': int(df['DISCOVERY_TIME'].isna().sum()),
        'CONT_DATETIME_both_date_and_valid_time': int(df['CONT_DATETIME'].isna().sum()),
        'NWCG_CAUSE_CLASSIFICATION_missing_category': int((df['NWCG_CAUSE_CLASSIFICATION'] == CAUSE_MISSING).sum()),
        'NWCG_GENERAL_CAUSE_missing_category': int((df['NWCG_GENERAL_CAUSE'] == CAUSE_MISSING).sum()),
        'OWNER_DESCR_missing_category': int((normalize_owner(df['OWNER_DESCR']) == OWNER_MISSING).sum()),
        'LATITUDE_or_LONGITUDE_null': int((df['LATITUDE'].isna() | df['LONGITUDE'].isna()).sum()),
    }
    claim('overview.missing_counts', miss,
          'count of records where the field is null, or (for cause and owner) equals the explicit '
          '"Missing data/not specified/undetermined" / "MISSING/NOT SPECIFIED" category', n, unit='records')
    claim('overview.missing_shares', {k: v / n for k, v in miss.items()}, 'the same counts divided by all rows', n,
          unit='share')
    post = df['FIRE_YEAR'] >= 2010
    claim('overview.missing_cont_date_share_2010_plus', float(df.loc[post, 'CONT_DATE'].isna().mean()),
          'share of records with FIRE_YEAR >= 2010 whose CONT_DATE is null', int(post.sum()), unit='share')
    claim('overview.size_class_definition', SIZE_CLASS_DEFINITION, 'FPA FOD coding', None)
    claim('overview.region_definition', REGION_DEFINITION, 'project region scheme', None)
    claim('overview.gacc_definition', GACC_DEFINITION, 'state-level GACC approximation', None,
          note='Only Northwest (OR WA), Southwest (AZ NM), Great Basin members (ID NV UT WY) and the ten GACC '
               'names were verified from gacc.nifc.gov pages fetched 2026-09-25; the rest is unverified.')


def per_year(df: pd.DataFrame, out_dir: str) -> None:
    n = len(df)
    by_year = _fires_acres(df, 'FIRE_YEAR').reindex(YEARS, fill_value=0)
    claim('year.fires_and_acres', by_year, 'fires (row count) and acres (sum FIRE_SIZE) by FIRE_YEAR', n)
    claim('year.fires_trend', _trend(by_year['fires']), 'Kendall tau and Theil-Sen slope of fires per year, 1992-2020',
          n, unit='fires/yr',
          note='Fire counts depend on which agencies reported in each year (reporting caveat), so a count trend '
               'is not a wildfire trend.')
    claim('year.acres_trend', _trend(by_year['acres']), 'Kendall tau and Theil-Sen slope of acres per year, 1992-2020',
          n, unit='acres/yr')
    claim('year.fires_and_acres_peak', {'fires_peak_year': int(by_year['fires'].idxmax()),
                                        'fires_peak': int(by_year['fires'].max()),
                                        'acres_peak_year': int(by_year['acres'].idxmax()),
                                        'acres_peak': float(by_year['acres'].max())},
          'year with the most fires and the year with the most acres', n)

    cls = df.groupby(['FIRE_YEAR', 'FIRE_SIZE_CLASS'], observed=True)['FIRE_SIZE'].agg(fires='size', acres='sum')
    fires_yc = cls['fires'].unstack().reindex(index=YEARS, columns=SIZE_CLASSES, fill_value=0).astype(int)
    acres_yc = cls['acres'].unstack().reindex(index=YEARS, columns=SIZE_CLASSES, fill_value=0.0)
    claim('year.fires_by_size_class', fires_yc, 'fires by FIRE_YEAR and FIRE_SIZE_CLASS', n)
    claim('year.acres_by_size_class', acres_yc, 'acres by FIRE_YEAR and FIRE_SIZE_CLASS', n, unit='acres')
    claim('year.acres_share_by_size_class', acres_yc.sum() / acres_yc.sum().sum(),
          'share of all acres 1992-2020 by FIRE_SIZE_CLASS', n, unit='share')
    claim('year.fires_share_by_size_class', fires_yc.sum() / fires_yc.sum().sum(),
          'share of all fires 1992-2020 by FIRE_SIZE_CLASS', n, unit='share')

    # Class G trend, with and without Alaska.
    g = df[df['FIRE_SIZE_CLASS'] == 'G']
    g_all = g.groupby('FIRE_YEAR')['FIRE_SIZE'].sum().reindex(YEARS, fill_value=0.0)
    g_no_ak = g[g['STATE'] != 'AK'].groupby('FIRE_YEAR')['FIRE_SIZE'].sum().reindex(YEARS, fill_value=0.0)
    g_ak = g[g['STATE'] == 'AK'].groupby('FIRE_YEAR')['FIRE_SIZE'].sum().reindex(YEARS, fill_value=0.0)
    t_all, t_no_ak, t_ak = _trend(g_all), _trend(g_no_ak), _trend(g_ak)
    claim('class_g.acres_by_year', g_all, 'sum of FIRE_SIZE for FIRE_SIZE_CLASS == G by FIRE_YEAR', len(g), unit='acres')
    claim('class_g.acres_by_year_excl_alaska', g_no_ak, 'same, excluding STATE == AK', int((g['STATE'] != 'AK').sum()),
          unit='acres')
    claim('class_g.acres_by_year_alaska', g_ak, 'same, STATE == AK only', int((g['STATE'] == 'AK').sum()), unit='acres')
    claim('class_g.acres_trend', t_all, 'Kendall tau and Theil-Sen slope of Class G acres per year, 1992-2020 '
          '(29 annual points; years with no Class G fires count as 0)', len(g), unit='acres/yr',
          note='Class G is the size class least affected by the reporting caveat: fires of 5,000+ acres are '
               'recorded by every reporting system, so this series is the most comparable across years.')
    claim('class_g.acres_trend_excl_alaska', t_no_ak, 'same, excluding Alaska', int((g['STATE'] != 'AK').sum()),
          unit='acres/yr')
    claim('class_g.acres_trend_alaska', t_ak, 'same, Alaska only', int((g['STATE'] == 'AK').sum()), unit='acres/yr')
    gcount = g.groupby('FIRE_YEAR').size().reindex(YEARS, fill_value=0)
    claim('class_g.fires_by_year', gcount, 'count of FIRE_SIZE_CLASS == G by FIRE_YEAR', len(g))
    claim('class_g.fires_trend', _trend(gcount), 'Kendall tau and Theil-Sen slope of Class G fire counts per year',
          len(g), unit='fires/yr')
    claim('class_g.half_period_means', {'1992_2005': float(g_all.loc[1992:2005].mean()),
                                        '2006_2020': float(g_all.loc[2006:2020].mean()),
                                        '1992_2005_excl_alaska': float(g_no_ak.loc[1992:2005].mean()),
                                        '2006_2020_excl_alaska': float(g_no_ak.loc[2006:2020].mean())},
          'mean annual Class G acres in the first 14 and last 15 years', len(g), unit='acres')
    lows = g_all.sort_values().head(5)
    claim('class_g.five_lowest_years', lows, 'the five lowest Class G acre years', len(g), unit='acres',
          note='Tests "higher lows": if a recent year is among the lowest, the lows are not rising.')
    claim('class_g.alaska_share_of_acres', float(g_ak.sum() / g_all.sum()),
          'Alaska share of all Class G acres 1992-2020', len(g), unit='share')
    # The 11-state West on its own (the headline's region).
    g_west = g[g['REGION'] == 'West'].groupby('FIRE_YEAR')['FIRE_SIZE'].sum().reindex(YEARS, fill_value=0.0)
    n_west = int((g['REGION'] == 'West').sum())
    claim('class_g.acres_by_year_west', g_west, 'same, REGION == West (AZ CA CO ID MT NV NM OR UT WA WY) only',
          n_west, unit='acres')
    claim('class_g.acres_trend_west', _trend(g_west), 'same trend statistics, West only', n_west, unit='acres/yr')
    claim('class_g.half_period_means_west', {'1992_2005': float(g_west.loc[1992:2005].mean()),
                                             '2006_2020': float(g_west.loc[2006:2020].mean())},
          'mean annual Class G acres in the West in the first 14 and last 15 years', n_west, unit='acres')
    claim('class_g.west_ratio_by_state', {str(k): float(v) for k, v in
          (g[g['REGION'] == 'West'].assign(late=lambda d: d['FIRE_YEAR'] >= 2006)
           .groupby(['STATE', 'late'], observed=True)['FIRE_SIZE'].sum().unstack('late')
           .pipe(lambda t: (t[True] / 15) / (t[False] / 14)).sort_values(ascending=False).items())},
          'ratio of mean annual Class G acres 2006-2020 to 1992-2005, per Western state', n_west, unit='ratio')

    fit = {'slope': t_all['theil_sen_slope'], 'intercept': t_all['theil_sen_intercept'],
           'tau': t_all['kendall_tau'], 'p': t_all['kendall_p'],
           'tau_no_ak': t_no_ak['kendall_tau'], 'p_no_ak': t_no_ak['kendall_p']}
    figures.fires_and_acres_by_year(by_year, n, out_dir)
    figures.class_g_acres_trend(g_all, g_no_ak, fit, len(g), int((g['STATE'] != 'AK').sum()), out_dir)


def causes(df: pd.DataFrame, out_dir: str) -> None:
    n = len(df)
    total_acres = df['FIRE_SIZE'].sum()
    cc = _fires_acres(df, 'NWCG_CAUSE_CLASSIFICATION')
    cc['share_fires'] = cc['fires'] / n
    cc['share_acres'] = cc['acres'] / total_acres
    claim('cause.by_classification', cc, 'fires, acres and shares by NWCG_CAUSE_CLASSIFICATION', n)
    claim('cause.natural_acres', float(cc.loc['Natural', 'acres']), 'acres with NWCG_CAUSE_CLASSIFICATION == Natural',
          int(cc.loc['Natural', 'fires']), unit='acres')
    claim('cause.human_to_natural_fire_ratio', float(cc.loc['Human', 'fires'] / cc.loc['Natural', 'fires']),
          'Human fires divided by Natural fires', n, unit='ratio')

    gc = _fires_acres(df, 'NWCG_GENERAL_CAUSE')
    gc['share_fires'] = gc['fires'] / n
    gc['share_acres'] = gc['acres'] / total_acres
    gc['mean_acres'] = gc['acres'] / gc['fires']
    gc = gc.sort_values('acres', ascending=False)
    claim('cause.by_general_cause', gc, 'fires, acres, shares and mean size by NWCG_GENERAL_CAUSE', n)

    # Cause within size class.
    ct = pd.crosstab(df['FIRE_SIZE_CLASS'], df['NWCG_GENERAL_CAUSE']).reindex(SIZE_CLASSES)
    share = ct.div(ct.sum(axis=1), axis=0)
    claim('cause.general_cause_share_by_size_class', share,
          'share of fires in each FIRE_SIZE_CLASS by NWCG_GENERAL_CAUSE (rows sum to 1)', n, unit='share')
    top = {c: {'top_cause': str(share.loc[c].idxmax()), 'share': float(share.loc[c].max()),
               'is_majority': bool(share.loc[c].max() > 0.5),
               'top3': {str(k): float(v) for k, v in share.loc[c].sort_values(ascending=False).head(3).items()}}
           for c in SIZE_CLASSES}
    claim('cause.top_general_cause_by_size_class', top, 'most common NWCG_GENERAL_CAUSE within each size class', n)
    cls_share = pd.crosstab(df['FIRE_SIZE_CLASS'], df['NWCG_CAUSE_CLASSIFICATION'], values=df['FIRE_SIZE'],
                            aggfunc='sum').reindex(SIZE_CLASSES).fillna(0)
    cls_share = cls_share.div(cls_share.sum(axis=1), axis=0)
    claim('cause.classification_acre_share_by_size_class', cls_share,
          'share of acres in each FIRE_SIZE_CLASS by NWCG_CAUSE_CLASSIFICATION', n, unit='share')
    # Cause classification by region: shares of fires and of acres, undetermined shown.
    rc = pd.crosstab(df['REGION'], df['NWCG_CAUSE_CLASSIFICATION'])
    ra = pd.crosstab(df['REGION'], df['NWCG_CAUSE_CLASSIFICATION'], values=df['FIRE_SIZE'], aggfunc='sum').fillna(0)
    by_region = {str(r): {'fires': int(rc.loc[r].sum()), 'acres': float(ra.loc[r].sum()),
                          'share_fires': {str(c): float(v) for c, v in (rc.loc[r] / rc.loc[r].sum()).items()},
                          'share_acres': {str(c): float(v) for c, v in (ra.loc[r] / ra.loc[r].sum()).items()}}
                 for r in rc.index}
    claim('cause.by_region_classification', by_region,
          'fires, acres and their shares by region and NWCG_CAUSE_CLASSIFICATION (Missing shown, not excluded)', n)
    claim('cause.by_classification_by_region',
          {str(r): {str(cl): {'fires': int(rc.loc[r, cl]), 'acres': float(ra.loc[r, cl])} for cl in rc.columns}
           for r in rc.index},
          'fires and acres by region (REGION_DEFINITION) and NWCG_CAUSE_CLASSIFICATION, Missing included; '
          'the form the site\'s causes page reads', n)
    known = df[df['NWCG_CAUSE_CLASSIFICATION'] != CAUSE_MISSING]
    hs = (known['NWCG_CAUSE_CLASSIFICATION'] == 'Human').groupby(known['FIRE_SIZE_CLASS'], observed=True).mean()
    claim('cause.human_share_known_by_size_class', hs.reindex(SIZE_CLASSES),
          'share of fires with a known cause classification that are Human, by FIRE_SIZE_CLASS', len(known),
          unit='share')
    figures.cause_share_fires_vs_acres(gc[['share_fires', 'share_acres']], n, out_dir)


def seasonality(df: pd.DataFrame, out_dir: str) -> None:
    n = len(df)
    m = _fires_acres(df, 'DISCOVERY_MONTH').reindex(range(1, 13), fill_value=0)
    m.index = [MONTH_ABBR[i - 1] for i in m.index]
    claim('season.fires_and_acres_by_month', m, 'fires and acres by DISCOVERY_MONTH (month of DISCOVERY_DATE)', n)
    claim('season.peak_months', {'fires': str(m['fires'].idxmax()), 'acres': str(m['acres'].idxmax())},
          'month with the most fires and the month with the most acres', n)

    rm = df.groupby(['REGION', 'DISCOVERY_MONTH'], observed=True)['FIRE_SIZE'].agg(fires='size', acres='sum')
    fires_rm = rm['fires'].unstack(0).reindex(index=range(1, 13), columns=REGION_ORDER, fill_value=0).astype(int)
    acres_rm = rm['acres'].unstack(0).reindex(index=range(1, 13), columns=REGION_ORDER, fill_value=0.0)
    claim('season.fires_by_region_month', fires_rm, 'fires by region (REGION_DEFINITION) and DISCOVERY_MONTH', n)
    claim('season.acres_by_region_month', acres_rm, 'acres by region and DISCOVERY_MONTH', n, unit='acres')
    claim('season.peak_month_by_region', {r: {'fires': MONTH_ABBR[int(fires_rm[r].idxmax()) - 1],
                                              'acres': MONTH_ABBR[int(acres_rm[r].idxmax()) - 1]}
                                          for r in REGION_ORDER}, 'peak month of fires and of acres per region', n)
    claim('season.fires_by_region', fires_rm.sum(), 'fires per region, all months', n)
    claim('season.acres_by_region', acres_rm.sum(), 'acres per region, all months', n, unit='acres')

    g = df[df['FIRE_SIZE_CLASS'] == 'G']
    g_rm = pd.crosstab(g['DISCOVERY_MONTH'], g['REGION']).reindex(index=range(1, 13), columns=REGION_ORDER,
                                                                  fill_value=0)
    g_rm_acres = pd.crosstab(g['DISCOVERY_MONTH'], g['REGION'], values=g['FIRE_SIZE'], aggfunc='sum') \
        .reindex(index=range(1, 13), columns=REGION_ORDER).fillna(0.0)
    claim('season.class_g_fires_by_region_month', g_rm, 'Class G fire counts by DISCOVERY_MONTH and region', len(g))
    claim('season.class_g_acres_by_region_month', g_rm_acres, 'Class G acres by DISCOVERY_MONTH and region', len(g),
          unit='acres')
    lead = g_rm.idxmax(axis=1)
    claim('season.class_g_leading_region_by_month', {MONTH_ABBR[i - 1]: str(v) for i, v in lead.items()},
          'region with the most Class G fires in each month', len(g))

    # Day-level duration by region (fires with a containment date, all years).
    ok = df['DURATION_DAYS'].notna()
    dur = df.loc[ok].groupby('REGION', observed=True)['DURATION_DAYS'].agg(['mean', 'median', 'size'])
    claim('season.duration_days_by_region', dur.reindex(REGION_ORDER),
          'mean and median DURATION_DAYS (CONT_DATE minus DISCOVERY_DATE in whole days) by region, records with a '
          'containment date, all years', int(ok.sum()), unit='days')
    west = df[ok & (df['REGION'] == 'West')]
    wm = west.groupby('DISCOVERY_MONTH', observed=True)['DURATION_DAYS'].mean().reindex(range(1, 13))
    claim('season.west_mean_duration_days_by_month', {MONTH_ABBR[i - 1]: float(v) for i, v in wm.items()},
          'mean DURATION_DAYS of West fires with a containment date by DISCOVERY_MONTH', len(west), unit='days')

    # GACC-level seasonality kept as a table for the site.
    gm = df.groupby(['GACC', 'DISCOVERY_MONTH'], observed=True).size().unstack(0).reindex(index=range(1, 13),
                                                                                           fill_value=0)
    claim('season.fires_by_gacc_month', gm.astype(int), 'fires by state-level GACC approximation and DISCOVERY_MONTH', n)

    figures.seasonality_by_region(fires_rm / fires_rm.sum(), acres_rm / acres_rm.sum(), n, out_dir)
    figures.monthly_class_g_by_region(g_rm, len(g), out_dir)


def geography(df: pd.DataFrame, out_dir: str, fig_dir: str) -> None:
    n = len(df)
    st = _fires_acres(df, 'STATE').sort_values('acres', ascending=False)
    st['share_acres'] = st['acres'] / st['acres'].sum()
    st['share_fires'] = st['fires'] / n
    claim('geo.fires_and_acres_by_state', st, 'fires and acres by STATE', n)
    claim('geo.top5_states_acres', st.head(5)['acres'], 'five states with the most acres', n, unit='acres')
    claim('geo.top5_states_fires', st.sort_values('fires', ascending=False).head(5)['fires'],
          'five states with the most fires', n)
    claim('geo.fires_and_acres_by_gacc', _fires_acres(df, 'GACC').sort_values('acres', ascending=False),
          'fires and acres by state-level GACC approximation (see overview.gacc_definition)', n)

    has = df['LATITUDE'].notna() & df['LONGITUDE'].notna()
    d = df.loc[has, ['LATITUDE', 'LONGITUDE', 'FIRE_SIZE', 'NWCG_CAUSE_CLASSIFICATION']].copy()
    d['cell_lat'] = np.floor(d['LATITUDE']).astype(int)
    d['cell_lon'] = np.floor(d['LONGITUDE']).astype(int)
    d['human'] = (d['NWCG_CAUSE_CLASSIFICATION'] == 'Human').astype(int)
    d['natural'] = (d['NWCG_CAUSE_CLASSIFICATION'] == 'Natural').astype(int)
    cells = d.groupby(['cell_lat', 'cell_lon']).agg(n_fires=('FIRE_SIZE', 'size'), acres=('FIRE_SIZE', 'sum'),
                                                    n_human=('human', 'sum'), n_natural=('natural', 'sum')).reset_index()
    cells['n_missing_cause'] = cells['n_fires'] - cells['n_human'] - cells['n_natural']
    known = cells['n_human'] + cells['n_natural']
    cells['human_share_known'] = np.where(known > 0, cells['n_human'] / known.replace(0, np.nan), np.nan)
    cells['human_share_all'] = cells['n_human'] / cells['n_fires']
    cells['lat_centroid'] = cells['cell_lat'] + 0.5
    cells['lon_centroid'] = cells['cell_lon'] + 0.5
    cells = cells.sort_values('n_fires', ascending=False)
    path = os.path.join(out_dir, 'cells_1deg.csv')
    cells.to_csv(path, index=False)
    claim('geo.cells_1deg_file', os.path.relpath(path, os.getcwd()),
          '1-degree cells: cell_lat/cell_lon = floor(LATITUDE)/floor(LONGITUDE) (south-west corner); n_fires; '
          'acres = sum FIRE_SIZE; n_human, n_natural, n_missing_cause from NWCG_CAUSE_CLASSIFICATION; '
          'human_share_known = n_human / (n_human + n_natural); human_share_all = n_human / n_fires', int(has.sum()))
    claim('geo.cells_1deg_summary', {'n_cells': int(len(cells)), 'n_cells_ge_20_fires': int((cells['n_fires'] >= 20).sum()),
                                     'top_cell': cells.iloc[0][['cell_lat', 'cell_lon', 'n_fires', 'acres',
                                                                'human_share_known']].to_dict(),
                                     'share_of_fires_in_top_50_cells': float(cells['n_fires'].head(50).sum() / has.sum()),
                                     'share_of_acres_in_top_50_cells_by_acres': float(
                                         cells.sort_values('acres', ascending=False)['acres'].head(50).sum()
                                         / cells['acres'].sum())},
          'summary of the 1-degree cell table', int(has.sum()))
    figures.cells_1deg_map(cells, int(has.sum()), fig_dir)


def ownership(df: pd.DataFrame, out_dir: str) -> None:
    n = len(df)
    ow = _fires_acres(df, 'OWNER').sort_values('acres', ascending=False)
    ow['share_acres'] = ow['acres'] / ow['acres'].sum()
    ow['share_fires'] = ow['fires'] / n
    known = df[df['NWCG_CAUSE_CLASSIFICATION'] != CAUSE_MISSING]
    ow['human_share_known'] = (known['NWCG_CAUSE_CLASSIFICATION'] == 'Human').groupby(known['OWNER']).mean()
    ow['n_known_cause'] = known.groupby('OWNER').size()
    claim('owner.fires_and_acres', ow,
          'fires, acres and shares by OWNER_DESCR (upper-cased so "Private" merges into "PRIVATE"); '
          'human_share_known = share of fires with a known NWCG_CAUSE_CLASSIFICATION that are Human', n)
    claim('owner.top4_acres', ow.head(4)['acres'], 'four owner categories with the most acres', n, unit='acres')
    claim('owner.missing_share_fires', float(ow.loc[OWNER_MISSING, 'share_fires']),
          'share of fires whose OWNER_DESCR is MISSING/NOT SPECIFIED', n, unit='share')
    claim('owner.missing_share_acres', float(ow.loc[OWNER_MISSING, 'share_acres']),
          'share of acres whose OWNER_DESCR is MISSING/NOT SPECIFIED', n, unit='share')
    top = ow[ow['fires'] >= 5000].head(11)
    figures.ownership_acres(top[['acres', 'human_share_known']], n, out_dir)


def containment(df: pd.DataFrame, out_dir: str) -> None:
    n = len(df)
    has = df['CONT_DATE'].notna()
    claim('cont.share_with_cont_date', float(has.mean()), 'share of all records with a non-null CONT_DATE', n, unit='share')
    by_year = has.groupby(df['FIRE_YEAR']).mean().reindex(YEARS)
    claim('cont.share_with_cont_date_by_year', by_year, 'share with CONT_DATE by FIRE_YEAR', n, unit='share')
    claim('cont.share_with_cont_date_by_owner', has.groupby(df['OWNER']).mean().sort_values(),
          'share with CONT_DATE by OWNER_DESCR (upper-cased)', n, unit='share')
    claim('cont.share_with_cont_date_by_region', has.groupby(df['REGION']).mean().reindex(REGION_ORDER),
          'share with CONT_DATE by region', n, unit='share')

    # 2010+ fires with both discovery and containment date-times.
    post = df[(df['FIRE_YEAR'] >= 2010) & df['DURATION_HOURS'].notna()]
    n_post = len(post)
    claim('cont.n_2010_plus_with_both_datetimes', n_post,
          'records with FIRE_YEAR >= 2010 and non-null DURATION_HOURS (both DISCOVERY_DATETIME and CONT_DATETIME '
          'exist, i.e. date and a valid HHMM time on both ends)', n_post,
          note='Includes 0-hour records; excludes nothing else.')
    claim('cont.hours_percentiles_2010_plus', {str(p): float(post['DURATION_HOURS'].quantile(p))
                                              for p in [0.1, 0.25, 0.5, 0.75, 0.9, 0.99]},
          'percentiles of DURATION_HOURS for that sample', n_post, unit='hours')
    claim('cont.share_zero_hours_2010_plus', float((post['DURATION_HOURS'] == 0).mean()),
          'share of that sample with DURATION_HOURS == 0 (containment time equals discovery time)', n_post,
          unit='share')
    med_cls = post.groupby('FIRE_SIZE_CLASS', observed=True)['DURATION_HOURS'].agg(['median', 'mean', 'size']) \
        .reindex(SIZE_CLASSES)
    claim('cont.hours_by_size_class_2010_plus', med_cls, 'median and mean DURATION_HOURS by FIRE_SIZE_CLASS, that sample',
          n_post, unit='hours')
    top_owners = post['OWNER'].value_counts().head(8).index.tolist()
    med_own = post[post['OWNER'].isin(top_owners)].groupby('OWNER')['DURATION_HOURS'] \
        .agg(['median', 'mean', 'size']).loc[top_owners]
    claim('cont.hours_by_owner_2010_plus', med_own, 'median and mean DURATION_HOURS by OWNER_DESCR, eight most '
          'frequent owners in that sample', n_post, unit='hours')
    co = post[post['OWNER'].isin(top_owners[:6])]
    med_co = co.groupby(['FIRE_SIZE_CLASS', 'OWNER'], observed=True)['DURATION_HOURS'].median().unstack() \
        .reindex(index=SIZE_CLASSES, columns=top_owners[:6])
    n_co = co.groupby(['FIRE_SIZE_CLASS', 'OWNER'], observed=True).size().unstack() \
        .reindex(index=SIZE_CLASSES, columns=top_owners[:6]).fillna(0).astype(int)
    claim('cont.median_hours_by_size_class_and_owner_2010_plus', med_co,
          'median DURATION_HOURS by FIRE_SIZE_CLASS and OWNER_DESCR, six most frequent owners, that sample', n_post,
          unit='hours')
    claim('cont.n_by_size_class_and_owner_2010_plus', n_co, 'cell counts behind the previous claim', n_post)

    # Control Efficiency Score, as originally defined, with mean and median.
    c = df[df['DURATION_HOURS'] > 0].copy()
    c['APH'] = c['FIRE_SIZE'] / c['DURATION_HOURS']
    ces = c.groupby('OWNER')['APH'].agg(['size', 'mean', 'median'])
    ces = ces[ces['size'] >= 1000].copy()
    ces['ces_mean_based'] = 1 / ces['mean']
    ces['ces_median_based'] = 1 / ces['median']
    ces['rank_mean_based'] = ces['ces_mean_based'].rank(ascending=False).astype(int)
    ces['rank_median_based'] = ces['ces_median_based'].rank(ascending=False).astype(int)
    ces = ces.sort_values('size', ascending=False)
    claim('ces.by_owner', ces,
          'Control Efficiency Score = 1 / (acres per hour to containment) aggregated per OWNER_DESCR with the mean '
          '(original definition) and the median; acres per hour = FIRE_SIZE / DURATION_HOURS; records of all years '
          'with DURATION_HOURS > 0; owners with at least 1,000 such records', len(c),
          note='Rank 1 = highest score = fewest acres per hour.')
    claim('ces.rank_shift', {o: int(ces.loc[o, 'rank_mean_based'] - ces.loc[o, 'rank_median_based'])
                             for o in ces.index},
          'rank under the mean-based score minus rank under the median-based score, per owner', len(c),
          note='A large positive value means the owner looks much worse under the original mean-based score.')
    claim('ces.spearman_mean_vs_median', float(stats.spearmanr(ces['ces_mean_based'], ces['ces_median_based']).statistic),
          'Spearman correlation between the two owner rankings', len(ces), unit='rho')
    claim('ces.median_aph_by_size_class', c.groupby('FIRE_SIZE_CLASS', observed=True)['APH'].median().reindex(SIZE_CLASSES),
          'median acres per hour by FIRE_SIZE_CLASS, same sample', len(c), unit='acres/hour',
          note='Shows that acres per hour is mostly a function of final size, which the score does not control for.')

    figures.containment_hours_by_class_owner(med_co.iloc[:, :4], n_post, out_dir)


def anomalies(df: pd.DataFrame, out_dir: str) -> None:
    n = len(df)
    # 1. "June spike in Class G acreage in Arkansas".
    g = df[df['FIRE_SIZE_CLASS'] == 'G']
    june_g = g[g['DISCOVERY_MONTH'] == 6]
    js = _fires_acres(june_g, 'STATE').sort_values('acres', ascending=False)
    ar_g = g[g['STATE'] == 'AR']
    ar_by_month = _fires_acres(ar_g, 'DISCOVERY_MONTH').reindex(range(1, 13), fill_value=0)
    ar_by_month.index = MONTH_ABBR
    claim('anom.june_class_g_by_state_top10', js.head(10), 'Class G fires discovered in June, fires and acres by STATE, '
          'top 10 by acres', len(june_g))
    claim('anom.arkansas_class_g', {'n_class_g_fires_all_months': int(len(ar_g)), 'n_in_june': int(len(ar_g[ar_g['DISCOVERY_MONTH'] == 6])),
                                    'by_month': ar_by_month.to_dict('index'),
                                    'fires': ar_g[['FIRE_YEAR', 'DISCOVERY_MONTH', 'FIRE_NAME', 'FIRE_SIZE', 'OWNER']]
                                    .sort_values('FIRE_SIZE', ascending=False).to_dict('records')},
          'all Class G fires with STATE == AR', len(ar_g))
    ar_all = _fires_acres(df[df['STATE'] == 'AR'], 'DISCOVERY_MONTH').reindex(range(1, 13), fill_value=0)
    ar_all.index = MONTH_ABBR
    claim('anom.arkansas_all_fires_by_month', ar_all, 'all Arkansas fires and acres by DISCOVERY_MONTH',
          int((df['STATE'] == 'AR').sum()))
    for s in ['AZ', 'AK']:
        sg = _fires_acres(g[g['STATE'] == s], 'DISCOVERY_MONTH').reindex(range(1, 13), fill_value=0)
        sg.index = MONTH_ABBR
        claim(f'anom.{s.lower()}_class_g_by_month', sg, f'Class G fires and acres in {s} by DISCOVERY_MONTH',
              int((g['STATE'] == s).sum()))
    verdict_ar = ('Refuted: Arkansas has ' + str(len(ar_g)) + ' Class G fires in 29 years and none in June. '
                  'June is the peak Class G month for Arizona and Alaska; the README most likely mislabels AZ or AK as AR.')
    claim('anom.verdict_arkansas_june', verdict_ar, 'verdict from the two claims above', len(g))
    plot = js.head(8).copy()
    if 'AR' not in plot.index:
        plot.loc['AR'] = {'fires': 0, 'acres': 0.0}
    figures.june_class_g_states(plot, len(june_g), out_dir)

    # 2. "December fires in Texas".
    tx = df[df['STATE'] == 'TX']
    txm = _fires_acres(tx, 'DISCOVERY_MONTH').reindex(range(1, 13), fill_value=0)
    txm['rank_fires_desc'] = txm['fires'].rank(ascending=False).astype(int)
    txm['rank_acres_desc'] = txm['acres'].rank(ascending=False).astype(int)
    txm['class_g_fires'] = tx[tx['FIRE_SIZE_CLASS'] == 'G'].groupby('DISCOVERY_MONTH').size().reindex(range(1, 13),
                                                                                                        fill_value=0)
    txm.index = MONTH_ABBR
    claim('anom.texas_by_month', txm, 'Texas fires, acres, their descending ranks across the 12 months, and Class G '
          'counts by DISCOVERY_MONTH', len(tx))
    dec = tx[tx['DISCOVERY_MONTH'] == 12].groupby('FIRE_YEAR')['FIRE_SIZE'].agg(['size', 'sum']).reindex(YEARS, fill_value=0)
    claim('anom.texas_december_by_year', dec, 'Texas December fires and acres by FIRE_YEAR', int(len(tx[tx['DISCOVERY_MONTH'] == 12])))
    dec_sorted = dec['sum'].sort_values(ascending=False)
    ratio = float(dec_sorted.iloc[0] / dec_sorted.iloc[1]) if dec_sorted.iloc[1] > 0 else float('inf')
    claim('anom.texas_december_top_year', {'year': int(dec_sorted.index[0]), 'acres': float(dec_sorted.iloc[0]),
                                           'ratio_to_second': ratio},
          'largest Texas December by acres and its ratio to the second largest', int(dec['size'].sum()))
    claim('anom.texas_missing_cont_date_share_2010_plus',
          float(tx.loc[tx['FIRE_YEAR'] >= 2010, 'CONT_DATE'].isna().mean()),
          'share of Texas records 2010+ with null CONT_DATE', int((tx['FIRE_YEAR'] >= 2010).sum()), unit='share')
    verdict_tx = (f"Not a general pattern: December ranks {int(txm.loc['Dec', 'rank_fires_desc'])} of 12 Texas months "
                  f"by fires and {int(txm.loc['Dec', 'rank_acres_desc'])} of 12 by acres. Texas's big-fire season is "
                  f"January to April. One December stands out: {int(dec_sorted.index[0])} with "
                  f"{dec_sorted.iloc[0]:,.0f} acres, {ratio:.1f}x the next largest December.")
    claim('anom.verdict_texas_december', verdict_tx, 'verdict from the Texas claims above', len(tx))

    # 3. "2010 outlier in the Northeast".
    ne = df[df['REGION'] == 'Northeast']
    ney = _fires_acres(ne, 'FIRE_YEAR').reindex(YEARS, fill_value=0)
    z_n = (ney['fires'] - ney['fires'].mean()) / ney['fires'].std()
    z_a = (ney['acres'] - ney['acres'].mean()) / ney['acres'].std()
    ney['z_fires'] = z_n
    ney['z_acres'] = z_a
    claim('anom.northeast_by_year', ney, 'Northeast (' + ' '.join(NORTHEAST) + ') fires, acres and their z-scores '
          '(against the 29-year mean and sd) by FIRE_YEAR', len(ne))
    claim('anom.northeast_2010', {'fires': int(ney.loc[2010, 'fires']), 'acres': float(ney.loc[2010, 'acres']),
                                  'z_fires': float(z_n[2010]), 'z_acres': float(z_a[2010]),
                                  'rank_fires_desc': int(ney['fires'].rank(ascending=False)[2010]),
                                  'rank_acres_desc': int(ney['acres'].rank(ascending=False)[2010]),
                                  'max_z_fires_year': int(z_n.idxmax()), 'max_z_fires': float(z_n.max()),
                                  'max_z_acres_year': int(z_a.idxmax()), 'max_z_acres': float(z_a.max())},
          'the 2010 Northeast values against the other years', len(ne))
    by_state_year = ne.groupby(['STATE', 'FIRE_YEAR'], observed=True).size().unstack(fill_value=0) \
        .reindex(index=NORTHEAST, columns=YEARS, fill_value=0)
    claim('anom.northeast_fires_by_state_year', by_state_year, 'Northeast fires by STATE and FIRE_YEAR', len(ne))
    zero_years = {s: [int(y) for y in by_state_year.columns[by_state_year.loc[s] == 0]] for s in NORTHEAST}
    claim('anom.northeast_zero_report_years', {k: v for k, v in zero_years.items() if v},
          'years in which a Northeast state has zero records', len(ne),
          note='Zero-record years are reporting gaps, not fire-free years.')
    ny_share = float(by_state_year.loc['NY'].sum() / by_state_year.values.sum())
    claim('anom.northeast_ny_share_of_fires', ny_share, 'New York share of Northeast fires 1992-2020', len(ne), unit='share')
    # Largest year-over-year jumps in the count series (reporting-regime shifts).
    jumps = ney['fires'].diff().dropna().sort_values(ascending=False).head(3)
    claim('anom.northeast_largest_yoy_count_jumps', {int(k): int(v) for k, v in jumps.items()},
          'three largest year-over-year increases in Northeast fire counts', len(ne))
    # 2010 per state, acres too.
    s2010 = _fires_acres(ne[ne['FIRE_YEAR'] == 2010], 'STATE').reindex(NORTHEAST, fill_value=0)
    claim('anom.northeast_2010_by_state', s2010, 'Northeast 2010 fires and acres by STATE', int(ney.loc[2010, 'fires']))
    verdict_ne = (f"Not reproduced with this region definition: 2010 has z = {z_n[2010]:.2f} on fires and "
                  f"z = {z_a[2010]:.2f} on acres, ranking {int(ney['fires'].rank(ascending=False)[2010])} of 29 years "
                  f"by fires. The series is dominated by reporting shifts (largest jumps in "
                  f"{', '.join(str(int(k)) for k in jumps.index)}) and by states with zero-record years.")
    claim('anom.verdict_northeast_2010', verdict_ne, 'verdict from the Northeast claims above', len(ne))


# --------------------------------------------------------------------------- main

def run(out_dir: str) -> tuple[int, list[str]]:
    set_source('analysis.descriptive')
    os.makedirs(out_dir, exist_ok=True)
    fig_dir = os.path.join(out_dir, 'figures')
    t0 = time.time()
    df = load_fires(COLUMNS)
    df['REGION'] = region_of(df['STATE'])
    df['GACC'] = gacc_of(df['STATE'])
    df['OWNER'] = normalize_owner(df['OWNER_DESCR'])
    log.info(f'loaded {len(df):,} rows in {time.time() - t0:.1f}s')
    for name, fn in [('overview', lambda: overview(df)), ('per_year', lambda: per_year(df, fig_dir)),
                     ('causes', lambda: causes(df, fig_dir)), ('seasonality', lambda: seasonality(df, fig_dir)),
                     ('geography', lambda: geography(df, out_dir, fig_dir)),
                     ('ownership', lambda: ownership(df, fig_dir)),
                     ('containment', lambda: containment(df, fig_dir)), ('anomalies', lambda: anomalies(df, fig_dir))]:
        t = time.time()
        fn()
        log.info(f'{name} done in {time.time() - t:.1f}s')
    path = os.path.join(out_dir, 'claims.json')
    n_claims = write_claims(path)
    figs = sorted(f for f in os.listdir(fig_dir) if f.endswith('.png'))
    log.info(f'wrote {n_claims} claims to {path} in {time.time() - t0:.1f}s total')
    return n_claims, figs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default='outputs', help='output directory (default: outputs/)')
    args = ap.parse_args(argv)
    n_claims, figs = run(args.out)
    print(f'claims: {n_claims}')
    print('figures:')
    for f in figs:
        print(f'  {os.path.join(args.out, "figures", f)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
