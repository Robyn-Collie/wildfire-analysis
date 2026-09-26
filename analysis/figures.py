"""Static figures for the descriptive analysis (matplotlib, 150 dpi PNG).

Style follows the dataviz skill: one fixed categorical order (never cycled), one-hue
sequential ramp, thin marks, hairline grid, legend whenever there are two or more
series, text in ink tokens (never the series colour), and "n =" on every chart.
Colours are the mid-band steps that clear contrast on both the light and dark
surfaces; the PNGs render on the light surface so they read as a light card in dark UIs.
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .common import MONTH_ABBR, REGION_ORDER, SIZE_CLASSES  # noqa: E402

# ---- palette (reference instance from the dataviz skill; fixed slot order) ----
SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948']
SEQ = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b']  # blue 100..700
SURFACE = '#fcfcfb'
INK = '#0b0b0b'
INK2 = '#52514e'
MUTED = '#898781'
GRID = '#e1e0d9'
AXIS = '#c3c2b7'
NEUTRAL = '#c3c2b7'  # de-emphasised marks

REGION_COLOR = {r: SERIES[i] for i, r in enumerate(REGION_ORDER)}
DPI = 150
FIG_W = 7.2  # inches; at 150 dpi = 1080 px, readable on a phone when scaled to width

plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['DejaVu Sans', 'Arial', 'Helvetica'],
    'font.size': 10,
    'axes.titlesize': 12,
    'axes.titleweight': 'bold',
    'axes.labelsize': 10,
    'axes.edgecolor': AXIS,
    'axes.linewidth': 0.8,
    'axes.labelcolor': INK2,
    'axes.facecolor': SURFACE,
    'figure.facecolor': SURFACE,
    'savefig.facecolor': SURFACE,
    'xtick.color': MUTED,
    'ytick.color': MUTED,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'grid.color': GRID,
    'grid.linewidth': 0.8,
    'grid.linestyle': '-',
    'legend.frameon': False,
    'legend.fontsize': 9,
    'text.color': INK,
})


def _fmt_thousands(x, _pos=None):
    if abs(x) >= 1e6:
        return f'{x / 1e6:g}M'
    if abs(x) >= 1e3:
        return f'{x / 1e3:g}k'
    return f'{x:g}'


def _fmt_short(x):
    if abs(x) >= 1e6:
        return f'{x / 1e6:.1f}M'
    if abs(x) >= 1e3:
        return f'{x / 1e3:.0f}k'
    return f'{x:g}'


def _clean(ax, y_grid=True):
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.spines['bottom'].set_color(AXIS)
    ax.tick_params(length=0)
    if y_grid:
        ax.yaxis.grid(True)
        ax.set_axisbelow(True)


def _footer(fig, n_text: str, extra: str = ''):
    txt = f'n = {n_text}' + (f'.  {extra}' if extra else '')
    fig.text(0.01, 0.005, txt, ha='left', va='bottom', fontsize=8, color=MUTED, wrap=True)


def _save(fig, out_dir: str, name: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


# --------------------------------------------------------------------------- figures

def fires_and_acres_by_year(by_year: pd.DataFrame, n: int, out_dir: str) -> str:
    """Two stacked panels, one axis each: fires per year and acres per year (no dual axis)."""
    fig, axes = plt.subplots(2, 1, figsize=(FIG_W, 6.2), sharex=True)
    for ax, col, label in zip(axes, ['fires', 'acres'], ['Fires reported', 'Acres burned']):
        y = by_year[col]
        ax.plot(y.index, y.values, color=SERIES[0], lw=2, solid_joinstyle='round')
        ax.scatter([y.index[-1]], [y.values[-1]], s=40, color=SERIES[0], edgecolor=SURFACE, lw=2, zorder=3)
        imax = y.idxmax()
        if imax != y.index[-1]:
            ax.annotate(_fmt_short(y.values[-1]), (y.index[-1], y.values[-1]), xytext=(6, 0),
                        textcoords='offset points', va='center', fontsize=9, color=INK2)
        ax.annotate(f'{int(imax)}: {_fmt_short(y[imax])}', (imax, y[imax]), xytext=(0, 6),
                    textcoords='offset points', ha='center', fontsize=9, color=INK2)
        ax.set_ylabel(label)
        ax.set_ylim(0, y.max() * 1.15)
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(_fmt_thousands))
        _clean(ax)
    axes[0].set_title('Fires and acres burned per year, 1992-2020', loc='left')
    axes[1].set_xlabel('Discovery year')
    axes[1].set_xlim(by_year.index.min() - 0.5, by_year.index.max() + 2.5)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    _footer(fig, f'{n:,} fires', 'Source: FPA FOD 6th ed. Counts depend on which agencies reported in each year.')
    return _save(fig, out_dir, 'fires_and_acres_by_year.png')


def class_g_acres_trend(g_all: pd.Series, g_no_ak: pd.Series, fit: dict, n_all: int, n_no_ak: int,
                        out_dir: str) -> str:
    """Class G acres per year, with and without Alaska, plus the Theil-Sen line for the all-states series."""
    fig, ax = plt.subplots(figsize=(FIG_W, 4.4))
    x = np.asarray(g_all.index)
    ax.plot(x, g_all.values, color=SERIES[0], lw=2, label=f'All states (n = {n_all:,} fires)')
    ax.plot(x, g_no_ak.values, color=SERIES[1], lw=2, label=f'Excluding Alaska (n = {n_no_ak:,} fires)')
    ax.plot(x, fit['intercept'] + fit['slope'] * x, color=SERIES[0], lw=1, alpha=0.6,
            label=f"Theil-Sen fit, all states: +{fit['slope'] / 1e3:,.0f}k acres/yr")
    for s, c in [(g_all, SERIES[0]), (g_no_ak, SERIES[1])]:
        ax.scatter([s.index[-1]], [s.values[-1]], s=40, color=c, edgecolor=SURFACE, lw=2, zorder=3)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(_fmt_thousands))
    ax.set_ylim(0, g_all.max() * 1.1)
    ax.set_ylabel('Class G acres burned (5,000+ acre fires)')
    ax.set_xlabel('Discovery year')
    ax.set_title('Large-fire acreage trends up, mostly outside Alaska', loc='left')
    ax.legend(loc='upper left')
    _clean(ax)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    _footer(fig, f'{n_all:,} Class G fires 1992-2020',
            f"Kendall tau = {fit['tau']:.2f} (p = {fit['p']:.3g}) all states; {fit['tau_no_ak']:.2f} "
            f"(p = {fit['p_no_ak']:.3g}) without Alaska.")
    return _save(fig, out_dir, 'class_g_acres_trend.png')


def cause_share_fires_vs_acres(tbl: pd.DataFrame, n: int, out_dir: str) -> str:
    """Grouped horizontal bars: share of fires vs share of acres for each general cause."""
    tbl = tbl.sort_values('share_acres', ascending=True)
    y = np.arange(len(tbl))
    h = 0.36
    fig, ax = plt.subplots(figsize=(FIG_W, 5.6))
    ax.barh(y + h / 2, tbl['share_fires'] * 100, height=h, color=SERIES[0], label='Share of fires',
            edgecolor=SURFACE, lw=1)
    ax.barh(y - h / 2, tbl['share_acres'] * 100, height=h, color=SERIES[1], label='Share of acres',
            edgecolor=SURFACE, lw=1)
    for yi, (f, a) in enumerate(zip(tbl['share_fires'], tbl['share_acres'])):
        ax.text(f * 100 + 0.6, yi + h / 2, f'{f * 100:.0f}%', va='center', fontsize=8, color=INK2)
        ax.text(a * 100 + 0.6, yi - h / 2, f'{a * 100:.0f}%', va='center', fontsize=8, color=INK2)
    ax.set_yticks(y)
    ax.set_yticklabels([s.replace('Missing data/not specified/undetermined', 'Missing / undetermined')
                        for s in tbl.index], fontsize=9)
    ax.set_xlabel('Percent of national total, 1992-2020')
    ax.set_xlim(0, max(tbl['share_fires'].max(), tbl['share_acres'].max()) * 100 + 8)
    ax.set_title('Natural causes: 14% of fires, 59% of acres', loc='left')
    ax.legend(loc='lower right')
    _clean(ax, y_grid=False)
    ax.xaxis.grid(True)
    ax.set_axisbelow(True)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    _footer(fig, f'{n:,} fires', 'Cause = NWCG_GENERAL_CAUSE.')
    return _save(fig, out_dir, 'cause_share_fires_vs_acres.png')


def seasonality_by_region(fires_share: pd.DataFrame, acres_share: pd.DataFrame, n: int, out_dir: str) -> str:
    """Month profile per region: share of the region's own fires (top) and acres (bottom) by month."""
    fig, axes = plt.subplots(2, 1, figsize=(FIG_W, 6.6), sharex=True)
    for ax, tbl, label in zip(axes, [fires_share, acres_share], ['Share of region\'s fires', 'Share of region\'s acres']):
        for r in REGION_ORDER:
            if r not in tbl.columns:
                continue
            ax.plot(tbl.index, tbl[r] * 100, color=REGION_COLOR[r], lw=2, label=r)
        ax.set_ylabel(label + ' (%)')
        ax.set_ylim(0, tbl.max().max() * 100 * 1.1)
        _clean(ax)
    axes[0].set_title('When fires happen: month profile by region', loc='left')
    axes[0].legend(ncol=3, loc='upper left')
    axes[1].set_xticks(range(1, 13))
    axes[1].set_xticklabels(MONTH_ABBR)
    axes[1].set_xlabel('Discovery month')
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    _footer(fig, f'{n:,} fires', 'Each region sums to 100% within a panel. Regions defined in analysis/common.py.')
    return _save(fig, out_dir, 'seasonality_by_region.png')


def monthly_class_g_by_region(counts: pd.DataFrame, n: int, out_dir: str) -> str:
    """Stacked columns of Class G fire counts by month, segmented by region (2px surface gaps)."""
    fig, ax = plt.subplots(figsize=(FIG_W, 4.6))
    bottom = np.zeros(12)
    x = np.arange(1, 13)
    for r in REGION_ORDER:
        if r not in counts.columns:
            continue
        vals = counts[r].reindex(x, fill_value=0).values
        ax.bar(x, vals, bottom=bottom, width=0.62, color=REGION_COLOR[r], label=r, edgecolor=SURFACE, lw=1.2)
        bottom += vals
    peak = int(np.argmax(bottom)) + 1
    ax.text(peak, bottom[peak - 1] + 15, f'{MONTH_ABBR[peak - 1]}: {int(bottom[peak - 1]):,}', ha='center',
            fontsize=9, color=INK2)
    ax.set_xticks(x)
    ax.set_xticklabels(MONTH_ABBR)
    ax.set_ylabel('Class G fires (5,000+ acres)')
    ax.set_xlabel('Discovery month')
    ax.set_ylim(0, bottom.max() * 1.25)
    ax.set_title('Large fires start in the South in winter, the West in summer', loc='left')
    ax.legend(ncol=3, loc='upper left')
    _clean(ax)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    _footer(fig, f'{n:,} Class G fires 1992-2020')
    return _save(fig, out_dir, 'monthly_class_g_by_region.png')


def ownership_acres(tbl: pd.DataFrame, n: int, out_dir: str) -> str:
    """Horizontal bars of acres burned by land owner, value at the tip, human share in muted text."""
    tbl = tbl.sort_values('acres', ascending=True)
    fig, ax = plt.subplots(figsize=(FIG_W, 5.2))
    y = np.arange(len(tbl))
    colors = [NEUTRAL if 'MISSING' in o else SERIES[0] for o in tbl.index]
    ax.barh(y, tbl['acres'] / 1e6, height=0.55, color=colors, edgecolor=SURFACE, lw=1)
    for yi, (o, row) in enumerate(tbl.iterrows()):
        ax.text(row['acres'] / 1e6 + 0.4, yi, f"{row['acres'] / 1e6:.1f}M  ({row['human_share_known'] * 100:.0f}% human)",
                va='center', fontsize=8.5, color=INK2)
    ax.set_yticks(y)
    ax.set_yticklabels([o.title().replace('Usfs', 'USFS').replace('Blm', 'BLM').replace('Bia', 'BIA')
                        .replace('Nps', 'NPS').replace('Fws', 'FWS').replace('Bor', 'BOR') for o in tbl.index], fontsize=9)
    ax.set_xlabel('Million acres burned, 1992-2020')
    ax.set_xlim(0, tbl['acres'].max() / 1e6 * 1.45)
    ax.set_title('Acres burned by land owner, 1992-2020', loc='left')
    _clean(ax, y_grid=False)
    ax.xaxis.grid(True)
    ax.set_axisbelow(True)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    _footer(fig, f'{n:,} fires', 'Grey = ownership not recorded. In brackets: human share of fires with a known cause.')
    return _save(fig, out_dir, 'ownership_acres.png')


def containment_hours_by_class_owner(med: pd.DataFrame, n: int, out_dir: str) -> str:
    """Median hours from discovery to containment by size class, one line per owner (log y)."""
    fig, ax = plt.subplots(figsize=(FIG_W, 4.6))
    x = np.arange(len(SIZE_CLASSES))
    owners = list(med.columns)[:4]
    for i, o in enumerate(owners):
        vals = med[o].reindex(SIZE_CLASSES).values
        ax.plot(x, vals, color=SERIES[i], lw=2, marker='o', ms=6, mec=SURFACE, mew=1.5, label=o.title()
                .replace('Usfs', 'USFS').replace('Blm', 'BLM').replace('Bia', 'BIA'))
    ax.set_yscale('log')
    ax.set_xticks(x)
    ax.set_xticklabels([f'{c}' for c in SIZE_CLASSES])
    ax.set_xlabel('Fire size class (A < 0.26 ac ... G 5,000+ ac)')
    ax.set_ylabel('Median hours to containment (log scale)')
    ax.set_title('Time to containment rises with final size for every owner', loc='left')
    ax.legend(loc='upper left')
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, p: f'{v:g}'))
    _clean(ax)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    _footer(fig, f'{n:,} fires 2010-2020 with both date-times', 'Four most frequent OWNER_DESCR values.')
    return _save(fig, out_dir, 'containment_hours_by_class_owner.png')


def cells_1deg_map(cells: pd.DataFrame, n: int, out_dir: str) -> str:
    """Scatter of 1-degree cell centroids sized by fire count, coloured by human share (one-hue ramp)."""
    cmap = LinearSegmentedColormap.from_list('seqblue', SEQ)
    c = cells[cells['n_fires'] >= 20].copy()
    size = 4 + 60 * np.sqrt(c['n_fires'] / c['n_fires'].max())
    fig, ax = plt.subplots(figsize=(FIG_W, 4.9))
    sc = ax.scatter(c['lon_centroid'], c['lat_centroid'], s=size, c=c['human_share_known'], cmap=cmap, vmin=0,
                    vmax=1, edgecolor=SURFACE, lw=0.5, alpha=0.95)
    ax.set_xlim(-170, -63)
    ax.set_ylim(16, 72)
    ax.set_aspect(1.3)
    ax.set_xlabel('Longitude')
    ax.set_ylabel('Latitude')
    ax.set_title('Where fires happen and who starts them, 1-degree cells', loc='left')
    cb = fig.colorbar(sc, ax=ax, fraction=0.03, pad=0.02)
    cb.set_label('Human share of fires with a known cause')
    cb.outline.set_visible(False)
    for s_n, lab in [(100, '100'), (10_000, '10k'), (100_000, '100k')]:
        ax.scatter([], [], s=4 + 60 * np.sqrt(s_n / c['n_fires'].max()), c=MUTED, label=f'{lab} fires')
    ax.legend(loc='lower center', title='Cell size', labelspacing=1.2, borderpad=1, ncol=3)
    _clean(ax, y_grid=False)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    _footer(fig, f'{n:,} fires with coordinates', 'Cells with fewer than 20 fires are not drawn.')
    return _save(fig, out_dir, 'cells_1deg_map.png')


def june_class_g_states(june: pd.DataFrame, n_june_g: int, out_dir: str) -> str:
    """June Class G acres by state (top states plus Arkansas), the AR/AZ/AK check."""
    june = june.sort_values('acres', ascending=True)
    fig, ax = plt.subplots(figsize=(FIG_W, 4.6))
    y = np.arange(len(june))
    colors = [SERIES[1] if s == 'AR' else SERIES[0] for s in june.index]
    ax.barh(y, june['acres'] / 1e6, height=0.55, color=colors, edgecolor=SURFACE, lw=1)
    for yi, (st, row) in enumerate(june.iterrows()):
        txt = f"{row['acres'] / 1e6:.2f}M acres, {int(row['fires'])} fires" if row['fires'] > 0 else '0 fires'
        ax.text(row['acres'] / 1e6 + 0.15, yi, txt, va='center', fontsize=8.5, color=INK2)
    ax.set_yticks(y)
    ax.set_yticklabels(list(june.index))
    ax.set_xlabel('Million acres in June Class G fires, 1992-2020')
    ax.set_xlim(0, june['acres'].max() / 1e6 * 1.35)
    ax.set_title('June Class G acreage: Alaska and Arizona, not Arkansas', loc='left')
    _clean(ax, y_grid=False)
    ax.xaxis.grid(True)
    ax.set_axisbelow(True)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    _footer(fig, f'{n_june_g:,} Class G fires discovered in June', 'Arkansas, the state the README names, has none.')
    return _save(fig, out_dir, 'june_class_g_states.png')
