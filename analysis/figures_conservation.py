"""Static figures for the conservation lens (ICS-209-PLUS outcomes and PAD-US protected areas).

Same style contract as analysis/figures.py (dataviz skill): fixed categorical order, one-hue
sequential ramp, thin marks with a surface gap, legend for two or more series, text in ink
tokens, "n =" in every footer. Style constants are imported from figures.py, not copied.
"""
from __future__ import annotations

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .figures import (AXIS, FIG_W, GRID, INK, INK2, MUTED, NEUTRAL, SEQ, SERIES, SURFACE,  # noqa: E402
                      _clean, _fmt_short, _fmt_thousands, _footer, _save)

GAP_ORDER = ['1', '2', '3', '4', 'none']
GAP_LABEL = {'1': 'GAP 1 (natural state mandate)', '2': 'GAP 2 (some degrading uses)',
             '3': 'GAP 3 (extractive uses allowed)', '4': 'GAP 4 (no conversion mandate)',
             'none': 'Not in PAD-US', 'unmatched': 'Outside PAD-US extent'}
GAP_COLOR = {'1': SERIES[2], '2': SERIES[0], '3': SERIES[3], '4': SERIES[1], 'none': NEUTRAL}


def gap_by_block(fires: pd.DataFrame, acres: pd.DataFrame, n: int, out_dir: str) -> str:
    """Two panels of stacked columns: share of ignitions (top) and of acres (bottom) by GAP status per 5-year block."""
    fig, axes = plt.subplots(2, 1, figsize=(FIG_W, 6.6), sharex=True)
    x = np.arange(len(fires.index))
    for ax, tbl, label in zip(axes, [fires, acres], ['Share of ignitions (%)', 'Share of acres (%)']):
        share = tbl.div(tbl.sum(axis=1), axis=0) * 100
        bottom = np.zeros(len(x))
        for g in GAP_ORDER:
            if g not in share.columns:
                continue
            vals = share[g].values
            ax.bar(x, vals, bottom=bottom, width=0.62, color=GAP_COLOR[g], label=GAP_LABEL[g], edgecolor=SURFACE, lw=1.2)
            for xi, (b, v) in enumerate(zip(bottom, vals)):
                if v >= 6:
                    ax.text(xi, b + v / 2, f'{v:.0f}', ha='center', va='center', fontsize=8, color=SURFACE if g != 'none' else INK2)
            bottom += vals
        ax.set_ylabel(label)
        ax.set_ylim(0, 100)
        _clean(ax)
    axes[0].set_title('Where fires start, by PAD-US protection status', loc='left')
    axes[0].legend(ncol=2, loc='upper center', bbox_to_anchor=(0.5, -0.02), fontsize=8, frameon=False)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(list(fires.index))
    axes[1].set_xlabel('Discovery year block')
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    _footer(fig, f'{n:,} ignition points joined to PAD-US 4.1',
            'GAP status at the ignition point (PAD-US Vector Analysis file, overlaps resolved by GAP priority).')
    return _save(fig, out_dir, 'padus_gap_by_block.png')


def top_units(tbl: pd.DataFrame, n: int, out_dir: str) -> str:
    """Horizontal bars: top protected units by human-caused ignitions, coloured by GAP status, peak month at the tip."""
    tbl = tbl.iloc[::-1]
    fig, ax = plt.subplots(figsize=(FIG_W, 7.4))
    y = np.arange(len(tbl))
    colors = [GAP_COLOR.get(str(g), NEUTRAL) for g in tbl['GAP_Sts']]
    ax.barh(y, tbl['human_ignitions'], height=0.6, color=colors, edgecolor=SURFACE, lw=1)
    for yi, (_, row) in enumerate(tbl.iterrows()):
        ax.text(row['human_ignitions'] + tbl['human_ignitions'].max() * 0.012, yi,
                f"{int(row['human_ignitions']):,}  peak {row['peak_month']}", va='center', fontsize=8, color=INK2)
    labels = [f"{(u[:40] + '...') if len(u) > 43 else u} ({m}, {s})" for u, m, s in zip(tbl.index, tbl['Mang_Name'], tbl['states'])]
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=7.5)
    ax.set_xlabel('Human-caused ignitions inside the unit, 2010-2020')
    ax.set_xlim(0, tbl['human_ignitions'].max() * 1.3)
    fig.suptitle('PAD-US units with the most human-caused ignitions, 2010-2020', x=0.01, y=0.995, ha='left',
                 fontsize=12, fontweight='bold')
    handles = [plt.Rectangle((0, 0), 1, 1, color=GAP_COLOR[g]) for g in GAP_ORDER[:4]]
    ax.legend(handles, [GAP_LABEL[g] for g in GAP_ORDER[:4]], loc='lower right', fontsize=8)
    _clean(ax, y_grid=False)
    ax.xaxis.grid(True)
    ax.set_axisbelow(True)
    fig.tight_layout(rect=(0, 0.04, 1, 0.97))
    _footer(fig, f'{n:,} human-caused ignitions 2010-2020 inside PAD-US units',
            'Unit = PAD-US Unit_Nm at the ignition point. Peak = month with the most human ignitions.')
    return _save(fig, out_dir, 'padus_top_units.png')


def agreement_matrix(share: pd.DataFrame, counts: pd.DataFrame, n: int, out_dir: str) -> str:
    """Row-normalised heatmap: FPA FOD owner class (rows) against PAD-US manager type at the point (columns)."""
    cmap = LinearSegmentedColormap.from_list('seqblue', SEQ)
    fig, ax = plt.subplots(figsize=(FIG_W, 4.9))
    im = ax.imshow(share.values * 100, cmap=cmap, vmin=0, vmax=100, aspect='auto')
    for i in range(share.shape[0]):
        for j in range(share.shape[1]):
            v = share.values[i, j] * 100
            if v >= 1:
                ax.text(j, i, f'{v:.0f}', ha='center', va='center', fontsize=8, color=SURFACE if v > 55 else INK)
    for k in range(1, share.shape[1]):
        ax.axvline(k - 0.5, color=SURFACE, lw=1.5)
    for k in range(1, share.shape[0]):
        ax.axhline(k - 0.5, color=SURFACE, lw=1.5)
    ax.set_xticks(range(share.shape[1]))
    ax.set_xticklabels(list(share.columns), fontsize=8, rotation=30, ha='right')
    ax.set_yticks(range(share.shape[0]))
    ax.set_yticklabels([f'{r} (n = {int(counts.loc[r].sum()):,})' for r in share.index], fontsize=8)
    ax.set_xlabel('PAD-US manager type at the ignition point')
    ax.set_ylabel('FPA FOD owner at origin (OWNER_DESCR)')
    ax.set_title('Does the recorded owner match the PAD-US manager?', loc='left')
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cb.set_label('Percent of the row')
    cb.outline.set_visible(False)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    _footer(fig, f'{n:,} ignitions with a recorded owner', 'Rows sum to 100. Cells under 1% are blank.')
    return _save(fig, out_dir, 'padus_owner_agreement.png')


def structures_by_year_cause(tbl: pd.DataFrame, n: int, out_dir: str) -> str:
    """Stacked columns: structures destroyed per year (ICS-209-PLUS) by FPA FOD cause classification."""
    order = ['Human', 'Natural', 'Missing data/not specified/undetermined']
    color = {'Human': SERIES[1], 'Natural': SERIES[0], 'Missing data/not specified/undetermined': NEUTRAL}
    label = {'Human': 'Human', 'Natural': 'Natural', 'Missing data/not specified/undetermined': 'Cause missing'}
    fig, ax = plt.subplots(figsize=(FIG_W, 4.4))
    x = np.asarray(tbl.index)
    bottom = np.zeros(len(x))
    for c in order:
        if c not in tbl.columns:
            continue
        vals = tbl[c].values
        ax.bar(x, vals, bottom=bottom, width=0.62, color=color[c], label=label[c], edgecolor=SURFACE, lw=1.2)
        bottom += vals
    peak = int(np.argmax(bottom))
    ax.text(x[peak], bottom[peak] * 1.02, f'{int(x[peak])}: {_fmt_short(bottom[peak])}', ha='center', fontsize=9, color=INK2)
    ax.set_ylabel('Structures destroyed')
    ax.set_xlabel('FPA FOD discovery year')
    ax.set_ylim(0, bottom.max() * 1.15)
    ax.set_xticks(x)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(_fmt_thousands))
    ax.set_title('Structures destroyed on ICS-209 incidents, by ignition cause', loc='left')
    ax.legend(loc='upper left')
    _clean(ax)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    _footer(fig, f'{n:,} ICS-209-PLUS incidents joined to FPA FOD fires >= 300 acres, 2010-2020',
            'STR_DESTROYED_TOTAL per incident; cause = NWCG_CAUSE_CLASSIFICATION of the largest joined fire.')
    return _save(fig, out_dir, 'ics_structures_by_year_cause.png')
