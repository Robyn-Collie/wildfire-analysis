"""Generate the static site in site/ from the committed analysis record.

Usage (from the repo root, with the venv active):
    python scripts/build_site.py

Reads:
    outputs/claims*.json      every claims ledger (claims.json today; claims_conservation.json,
                              claims_model.json, claims_coverage.json when they exist; same schema)
    outputs/cells_1deg.csv    the 1-degree cell table
    outputs/coverage.json     optional state-by-year record counts (see docs/SITE.md)
    outputs/figures/*.png     static figures (copied to site/figures/)

Writes site/ in full: HTML pages, assets/site.css, assets/site.js, data/*.js (window.WF_DATA),
figures/*.png. No build tooling, no templating library, no network access.
See docs/SITE.md for the data contract and the presentation rules every page follows.
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import html
import json
import os
import re
import shutil
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, 'outputs')
SITE_DIR = os.path.join(REPO_ROOT, 'site')
REPO_URL = 'https://github.com/Robyn-Collie/wildfire-analysis'
DOCS_URL = REPO_URL + '/tree/main/docs'
AUTHOR = 'Robyn Collie'
PLOTLY_CDN = 'https://cdn.plot.ly/plotly-2.35.2.min.js'
# Plotly is served from the site itself when the vendored copy exists (MIT, scripts/vendor/PLOTLY_LICENSE),
# so pages make no third-party requests; the CDN is the fallback only if the file is missing.
PLOTLY_VENDORED = os.path.join(REPO_ROOT, 'scripts', 'vendor', 'plotly-2.35.2.min.js')
PLOTLY_SRC = 'vendor/plotly.min.js' if os.path.exists(PLOTLY_VENDORED) else PLOTLY_CDN
SITE_TITLE = 'US wildfire record, 1992-2020'

NAV = [
    ('index.html', 'Overview'),
    ('trends.html', 'Trends'),
    ('causes.html', 'Causes and seasons'),
    ('geography.html', 'Geography'),
    ('ownership.html', 'Ownership'),
    ('conservation.html', 'Conservation'),
    ('model.html', 'Prediction'),
    ('methods.html', 'Methods and ledger'),
]

MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
REGIONS = ['West', 'South', 'Northeast', 'Alaska', 'Hawaii/PR', 'Other']
SIZE_CLASSES = ['A', 'B', 'C', 'D', 'E', 'F', 'G']


# --------------------------------------------------------------------------- inputs

def read_hash_prefix() -> tuple[str, str]:
    """Return (full sha256, 8-char prefix) from data.sha256."""
    path = os.path.join(REPO_ROOT, 'data.sha256')
    with open(path) as fh:
        full = fh.read().split()[0]
    return full, full[:8]


def load_claims() -> tuple[dict, list[str], list[str]]:
    """Merge every outputs/claims*.json into one dict keyed by claim id.

    Each claim gets an extra ``_file`` field with the ledger file it came from. Returns the merged
    dict, the list of ledger files found and the list of expected-but-missing ledger files.
    """
    files = sorted(glob.glob(os.path.join(OUT_DIR, 'claims*.json')))
    merged: dict = {}
    for path in files:
        with open(path) as fh:
            data = json.load(fh)
        base = os.path.basename(path)
        for cid, claim in data.items():
            if not isinstance(claim, dict) or 'value' not in claim:
                raise ValueError(f'{base}: claim {cid!r} does not follow the claims schema')
            row = dict(claim)
            row.setdefault('definition', '')
            row.setdefault('unit', None)
            row.setdefault('n', None)
            row.setdefault('note', None)
            row.setdefault('source', base)
            row['_file'] = base
            if cid in merged:
                print(f'warning: claim {cid} in {base} overrides {merged[cid]["_file"]}', file=sys.stderr)
            merged[cid] = row
    expected = ['claims.json', 'claims_conservation.json', 'claims_model.json', 'claims_coverage.json']
    found = [os.path.basename(p) for p in files]
    missing = [f for f in expected if f not in found]
    return merged, found, missing


def load_cells() -> list[dict]:
    path = os.path.join(OUT_DIR, 'cells_1deg.csv')
    rows = []
    with open(path, newline='') as fh:
        for r in csv.DictReader(fh):
            rows.append({
                'lat': float(r['lat_centroid']), 'lon': float(r['lon_centroid']),
                'n': int(float(r['n_fires'])), 'acres': round(float(r['acres']), 1),
                'human': int(float(r['n_human'])), 'natural': int(float(r['n_natural'])),
                'missing': int(float(r['n_missing_cause'])),
                'hk': (round(float(r['human_share_known']), 4) if r['human_share_known'] not in ('', 'nan') else None),
            })
    return rows


def load_coverage(claims: dict) -> dict | None:
    """State-by-year record counts with usable windows and break years.

    Source, in order of preference: outputs/coverage.json (written by analysis/coverage.py: keys ``states``
    -> {STATE: {region, n_records, fires: {year: n}, usable_window, break_years, zero_years}}, ``rule``),
    or the ledger claims ``coverage.fires_by_state_year`` (+ ``coverage.usable_window_by_state``,
    ``coverage.break_years_by_state``). Returns None when neither exists.
    """
    path = os.path.join(OUT_DIR, 'coverage.json')
    if os.path.exists(path):
        with open(path) as fh:
            data = json.load(fh)
        states = data.get('states') or {}
        if states:
            return {
                'by_state_year': {st: {str(y): int(n) for y, n in v['fires'].items()} for st, v in states.items()},
                'windows': {st: v.get('usable_window') for st, v in states.items()},
                'breaks': {st: v.get('break_years') or {} for st, v in states.items()},
                'regions': {st: v.get('region') for st, v in states.items()},
                'rule': data.get('rule', ''),
                'definition': 'records by STATE and FIRE_YEAR (outputs/coverage.json, analysis/coverage.py); usable window and break years per the rule: ' + data.get('rule', ''),
                'n': sum(int(v.get('n_records', 0)) for v in states.values()), 'source': 'outputs/coverage.json (analysis/coverage.py)',
            }
    if 'coverage.fires_by_state_year' in claims:
        c = claims['coverage.fires_by_state_year']
        return {'by_state_year': c['value'], 'windows': claims.get('coverage.usable_window_by_state', {}).get('value', {}),
                'breaks': claims.get('coverage.break_years_by_state', {}).get('value', {}), 'regions': {},
                'rule': claims.get('coverage.rule', {}).get('value', ''), 'definition': c['definition'], 'n': c['n'], 'source': c['_file']}
    return None


# --------------------------------------------------------------------------- helpers

def V():
    """The version 2 page module (scripts/site_v2.py), imported lazily because it imports this module."""
    sys.modules.setdefault('build_site', sys.modules[__name__])
    import site_v2
    return site_v2


# Letter groups in incident names that are acronyms or initials, kept upper case by name_case().
NAME_UPPER = {'NW', 'NE', 'SW', 'SE', 'SQF', 'SHF', 'BJ', 'MM', 'MP', 'BLM', 'USFS', 'NPS', 'II', 'III', 'IV'}


def name_case(s) -> str:
    """Title-case an upper-case incident name without str.title()'s slips: 'NW OKLAHOMA COMPLEX' ->
    'NW Oklahoma Complex' (not 'Nw'), "COX'S WELL" -> "Cox's Well" (not "Cox'S")."""
    def word(m):
        w = m.group(0)
        return w.upper() if w.upper() in NAME_UPPER else w[0].upper() + w[1:].lower()
    return re.sub(r"[A-Za-z]+(?:'[A-Za-z]+)?", word, str(s))


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def fmt_int(x) -> str:
    return f'{int(round(float(x))):,}'


def fmt_num(x, d=1) -> str:
    return f'{float(x):,.{d}f}'


def fmt_pct(x, d=1) -> str:
    return f'{100 * float(x):.{d}f}%'


def fmt_m(x, d=2) -> str:
    """Millions with a suffix."""
    return f'{float(x) / 1e6:,.{d}f}M'


def cv(claims: dict, cid: str, *path):
    """Claim value, optionally descending into a nested dict/list by keys."""
    v = claims[cid]['value']
    for p in path:
        v = v[p]
    return v


def q(claims: dict, cid: str, text: str, *path) -> str:
    """A number with its definition one click away (data-claim popover)."""
    if cid not in claims:
        raise KeyError(f'claim {cid} missing from the ledger')
    return f'<button type="button" class="q" data-claim="{esc(cid)}">{esc(text)}</button>'


def qd(text: str, definition: str, source: str, n=None) -> str:
    """A number whose definition is inline (not a ledger claim), still one click away."""
    n_attr = f' data-n="{esc(n)}"' if n is not None else ''
    return (f'<button type="button" class="q" data-def="{esc(definition)}" data-src="{esc(source)}"{n_attr}>'
            f'{esc(text)}</button>')


def js(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


# --------------------------------------------------------------------------- stylesheet

CSS = r"""
/* Generated by scripts/build_site.py. Tokens follow the dataviz reference palette; dark mode is a
   selected set of steps, not an automatic flip. */
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb; --surface-2: #f0efec;
  --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10); --border-strong: rgba(11,11,11,0.22);
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a; --s4: #eda100; --s5: #e87ba4; --s6: #008300;
  --s7: #4a3aa7; --s8: #e34948;
  --missing: #9a9890; --emph-gray: #cfcdc4;
  --seq-100: #cde2fb; --seq-200: #9ec5f4; --seq-300: #6da7ec; --seq-400: #3987e5; --seq-500: #256abf;
  --seq-600: #184f95; --seq-700: #0d366b;
  --link: #1c5cab; --focus: #2a78d6;
  --note-bg: #fbf4e4; --note-border: #e6cf8e; --scroll-shadow: rgba(11,11,11,0.22);
  --radius: 8px; --gutter: 16px; --maxw: 1080px;
  --font: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19; --surface-2: #242423;
    --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10); --border-strong: rgba(255,255,255,0.24);
    --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500; --s5: #d55181; --s6: #008300;
    --s7: #9085e9; --s8: #e66767;
    --missing: #7d7b74; --emph-gray: #454440;
    --seq-100: #0d366b; --seq-200: #184f95; --seq-300: #256abf; --seq-400: #3987e5; --seq-500: #6da7ec;
    --seq-600: #9ec5f4; --seq-700: #cde2fb;
    --link: #86b6ef; --focus: #86b6ef;
    --note-bg: #2a2416; --note-border: #5c4b1e; --scroll-shadow: rgba(255,255,255,0.22);
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19; --surface-2: #242423;
  --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10); --border-strong: rgba(255,255,255,0.24);
  --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500; --s5: #d55181; --s6: #008300;
  --s7: #9085e9; --s8: #e66767;
  --missing: #7d7b74; --emph-gray: #454440;
  --seq-100: #0d366b; --seq-200: #184f95; --seq-300: #256abf; --seq-400: #3987e5; --seq-500: #6da7ec;
  --seq-600: #9ec5f4; --seq-700: #cde2fb;
  --link: #86b6ef; --focus: #86b6ef;
  --note-bg: #2a2416; --note-border: #5c4b1e; --scroll-shadow: rgba(255,255,255,0.22);
}

* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0; background: var(--page); color: var(--ink); font-family: var(--font);
  font-size: 16px; line-height: 1.5; overflow-x: hidden;
}
a { color: var(--link); }
a:focus-visible, button:focus-visible, input:focus-visible, select:focus-visible {
  outline: 2px solid var(--focus); outline-offset: 2px;
}
h1, h2, h3 { line-height: 1.2; margin: 0 0 .5rem; font-weight: 650; letter-spacing: -0.01em; }
h1 { font-size: clamp(1.6rem, 4.5vw, 2.4rem); }
h2 { font-size: clamp(1.25rem, 3vw, 1.6rem); margin-top: 2.5rem; }
h3 { font-size: 1.1rem; margin-top: 1.5rem; }
p { margin: 0 0 1rem; max-width: 72ch; }
p.lede { font-size: 1.1rem; color: var(--ink-2); }
small, .small { font-size: .875rem; }
.muted { color: var(--muted); }
.ink2 { color: var(--ink-2); }
code, pre { font-family: var(--mono); font-size: .85em; }
pre { background: var(--surface-2); padding: .75rem; border-radius: var(--radius); overflow-x: auto; }
img { max-width: 100%; height: auto; }
table { border-collapse: collapse; width: 100%; font-size: .9rem; }
th, td { text-align: left; padding: .4rem .5rem; border-bottom: 1px solid var(--grid); vertical-align: top; }
th { color: var(--ink-2); font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.table-wrap { overflow-x: auto; max-width: 100%;
  /* Scroll shadows: a soft edge shows on whichever side has more table to scroll to. */
  background: linear-gradient(90deg, var(--wrap-bg, var(--page)) 30%, transparent) left center / 2rem 100% no-repeat local,
              linear-gradient(270deg, var(--wrap-bg, var(--page)) 30%, transparent) right center / 2rem 100% no-repeat local,
              radial-gradient(farthest-side at 0 50%, var(--scroll-shadow), transparent) left center / .75rem 100% no-repeat scroll,
              radial-gradient(farthest-side at 100% 50%, var(--scroll-shadow), transparent) right center / .75rem 100% no-repeat scroll; }
.chart { --wrap-bg: var(--surface); }
.note { --wrap-bg: var(--note-bg); }
@media (max-width: 600px) { th.hide-sm, td.hide-sm { display: none; } }
hr { border: 0; border-top: 1px solid var(--grid); margin: 2rem 0; }

.wrap { max-width: var(--maxw); margin: 0 auto; padding: 0 var(--gutter); }

/* top nav */
.topbar { border-bottom: 1px solid var(--grid); background: var(--surface); position: sticky; top: 0; z-index: 20; }
.topbar .wrap { display: flex; align-items: center; gap: .75rem; flex-wrap: wrap; padding-top: .5rem; padding-bottom: .5rem; }
.brand { font-weight: 700; text-decoration: none; color: var(--ink); white-space: nowrap; }
.brand span { color: var(--muted); font-weight: 500; }
/* Brand and theme button share the first row; the nav takes its own full-width row and wraps, so every link is visible at every width. */
nav.main { order: 3; flex: 1 1 100%; display: flex; flex-wrap: wrap; gap: .15rem .25rem; margin: 0 -.6rem; }
nav.main a { text-decoration: none; color: var(--ink-2); padding: .35rem .6rem; border-radius: 6px; white-space: nowrap; font-size: .95rem; }
nav.main a:hover { background: var(--surface-2); }
nav.main a[aria-current="page"] { background: var(--surface-2); color: var(--ink); font-weight: 600; }
.theme-btn { order: 2; margin-left: auto; border: 1px solid var(--border-strong); background: transparent; color: var(--ink-2); border-radius: 6px; padding: .3rem .55rem; cursor: pointer; font: inherit; font-size: .85rem; }
@media (max-width: 720px) {
  .topbar { position: static; }
  .brand { white-space: normal; min-width: 0; flex: 1 1 auto; }
  .brand span { display: block; font-size: .8rem; }
  nav.main { margin: 0 -.45rem; gap: 0; }
  nav.main a { padding: .4rem .45rem; font-size: .9rem; }
}

main { padding: 1.5rem 0 3rem; }
header.page-head { margin-bottom: 1rem; }

/* completeness strip */
.strip { display: grid; grid-template-columns: repeat(2, 1fr); gap: .5rem; margin: 1rem 0 1.5rem; }
@media (min-width: 720px) { .strip { grid-template-columns: repeat(4, 1fr); } }
.strip .tile { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: .6rem .75rem; }
.tile .label { color: var(--ink-2); font-size: .8rem; }
.tile .value { font-size: 1.4rem; font-weight: 650; }
.tile .sub { color: var(--muted); font-size: .78rem; }
.meter { height: 6px; background: var(--seq-100); border-radius: 3px; margin-top: .4rem; overflow: hidden; }
.meter > i { display: block; height: 100%; background: var(--seq-500); }

/* cards */
.cards { display: grid; grid-template-columns: 1fr; gap: .75rem; margin: 1rem 0; }
@media (min-width: 720px) { .cards { grid-template-columns: repeat(2, 1fr); } }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 1rem; }
.card h3 { margin-top: 0; }
.card .n { color: var(--muted); font-size: .8rem; }
.card details { margin-top: .5rem; }
.card summary { cursor: pointer; color: var(--link); font-size: .9rem; }
.card .go { display: inline-block; margin-top: .5rem; font-weight: 600; }

/* notes */
.note { background: var(--note-bg); border: 1px solid var(--note-border); border-radius: var(--radius); padding: .75rem 1rem; margin: 1rem 0; }
.note p:last-child { margin-bottom: 0; }
.placeholder { border: 1px dashed var(--border-strong); border-radius: var(--radius); padding: 1rem; color: var(--ink-2); background: var(--surface); margin: 1rem 0; }
.placeholder h3 { margin-top: 0; }
.tag { display: inline-block; font-size: .75rem; padding: .1rem .45rem; border-radius: 999px; border: 1px solid var(--border-strong); color: var(--ink-2); vertical-align: middle; }

/* inline numbers with a definition */
button.q { font: inherit; color: inherit; background: none; border: 0; padding: 0; cursor: pointer;
  border-bottom: 1px dotted var(--link); font-variant-numeric: tabular-nums; text-align: left; display: inline; }
button.q:hover { color: var(--link); }
/* Touch screens: a taller hit area on inline numbers and more room between lines that carry several of them. */
@media (pointer: coarse) { button.q { padding: .3rem 0; } main p:has(button.q) { line-height: 1.75; } }
.popover { position: absolute; z-index: 50; max-width: min(92vw, 420px); background: var(--surface); color: var(--ink);
  border: 1px solid var(--border-strong); border-radius: var(--radius); padding: .75rem .9rem; font-size: .85rem;
  box-shadow: 0 6px 24px rgba(0,0,0,.18); }
.popover dt { color: var(--muted); font-size: .75rem; margin-top: .4rem; }
.popover dt:first-child { margin-top: 0; }
.popover dd { margin: 0; }
.popover .close { position: absolute; top: .3rem; right: .4rem; background: none; border: 0; color: var(--muted); cursor: pointer; font-size: 1rem; }

/* chart card */
.chart { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: .9rem 1rem 1rem; margin: 1.25rem 0; }
.chart .head { display: flex; flex-wrap: wrap; gap: .25rem .75rem; align-items: baseline; }
.chart .head h3 { margin: 0; font-size: 1.05rem; }
.chart .head .n { color: var(--muted); font-size: .8rem; white-space: nowrap; }
.chart .sub { color: var(--ink-2); font-size: .875rem; margin: .25rem 0 .5rem; }
.chart .plot { width: 100%; min-height: 240px; }
.chart .plot.map { min-height: 380px; }
.chart .foot { display: flex; flex-wrap: wrap; gap: .4rem .75rem; align-items: center; margin-top: .5rem; font-size: .8rem; color: var(--muted); }
.chart .foot button, .btn { font: inherit; font-size: .8rem; border: 1px solid var(--border-strong); background: transparent; color: var(--ink-2);
  border-radius: 6px; padding: .2rem .55rem; cursor: pointer; }
.chart .foot button:hover, .btn:hover { background: var(--surface-2); }
.chart .caption { font-size: .85rem; color: var(--ink-2); margin: .5rem 0 0; max-width: none; }
.chart .tableview { margin-top: .5rem; }
.chart .tableview table { font-size: .82rem; }
.chart .fallback { padding: .75rem; border: 1px dashed var(--border-strong); border-radius: 6px; color: var(--ink-2); font-size: .875rem; }
.seg { display: inline-flex; border: 1px solid var(--border-strong); border-radius: 6px; overflow: hidden; margin: .25rem 0 .5rem; }
.seg button { font: inherit; font-size: .82rem; background: transparent; border: 0; color: var(--ink-2); padding: .3rem .7rem; cursor: pointer; }
.seg button + button { border-left: 1px solid var(--border-strong); }
.seg button[aria-pressed="true"] { background: var(--surface-2); color: var(--ink); font-weight: 600; }
.legend-note { font-size: .8rem; color: var(--ink-2); display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; margin-top: .25rem; }
.swatch { display: inline-block; width: 12px; height: 12px; border-radius: 2px; vertical-align: -1px; }
.swatch.hollow { border: 2px solid var(--missing); background: transparent; }
.grid2 { display: grid; grid-template-columns: 1fr; gap: 1rem; }
@media (min-width: 860px) { .grid2 { grid-template-columns: 1fr 1fr; } .grid2 .chart { margin: .5rem 0; } }

/* sortable and searchable tables */
th.sortable { cursor: pointer; user-select: none; white-space: nowrap; }
th.sortable::after { content: " \2195"; color: var(--muted); font-size: .8em; }
th.sortable[aria-sort="ascending"]::after { content: " \2191"; color: var(--ink); }
th.sortable[aria-sort="descending"]::after { content: " \2193"; color: var(--ink); }
input.search { font: inherit; padding: .4rem .6rem; border: 1px solid var(--border-strong); border-radius: 6px; background: var(--surface); color: var(--ink); width: 100%; max-width: 420px; }
.ledger td { font-size: .82rem; }
.ledger td.id { font-family: var(--mono); font-size: .8rem; overflow-wrap: anywhere; }
.ledger details summary { cursor: pointer; color: var(--link); }
.ledger pre { max-height: 240px; overflow: auto; margin: .3rem 0 0; font-size: .8rem; }
tr.missing-row td { background: var(--surface-2); }

dl.glossary dt { font-weight: 650; margin-top: .75rem; }
dl.glossary dd { margin: .2rem 0 0; color: var(--ink-2); }

footer.site { border-top: 1px solid var(--grid); color: var(--ink-2); font-size: .85rem; padding: 1.25rem 0 2rem; }
footer.site p { max-width: none; margin: 0 0 .4rem; }
figure { margin: 1rem 0; }
figure img { border: 1px solid var(--border); border-radius: var(--radius); background: #fff; }
figcaption { font-size: .85rem; color: var(--ink-2); }
.two { columns: 2; column-gap: 2rem; }
@media (max-width: 720px) { .two { columns: 1; } }
ul.tight { margin: 0 0 1rem; padding-left: 1.2rem; }
ul.tight li { margin-bottom: .25rem; }
"""


# --------------------------------------------------------------------------- shared script

SITE_JS = r"""
/* Generated by scripts/build_site.py. Shared helpers: theme, definitions popover, chart cards,
   CSV export, table views, sortable tables. No dependencies beyond Plotly (optional). */
(function () {
  'use strict';
  var WF = window.WF = window.WF || {};
  var D = window.WF_DATA || {};
  WF.data = D;

  /* ---------------- theme ---------------- */
  function savedTheme() { try { return localStorage.getItem('wf-theme'); } catch (e) { return null; } }
  function applyTheme(t) {
    if (t === 'dark' || t === 'light') document.documentElement.setAttribute('data-theme', t);
    else document.documentElement.removeAttribute('data-theme');
  }
  applyTheme(savedTheme());
  WF.isDark = function () {
    var t = document.documentElement.getAttribute('data-theme');
    if (t) return t === 'dark';
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  };
  WF.toggleTheme = function () {
    var next = WF.isDark() ? 'light' : 'dark';
    try { localStorage.setItem('wf-theme', next); } catch (e) {}
    applyTheme(next);
    WF.rerenderAll();
    updateThemeButtons();
  };
  function updateThemeButtons() {
    var btns = document.querySelectorAll('.theme-btn');
    for (var i = 0; i < btns.length; i++) btns[i].textContent = WF.isDark() ? 'Light mode' : 'Dark mode';
  }
  if (window.matchMedia) {
    var mq = window.matchMedia('(prefers-color-scheme: dark)');
    var onChange = function () { WF.rerenderAll(); updateThemeButtons(); };
    if (mq.addEventListener) mq.addEventListener('change', onChange); else if (mq.addListener) mq.addListener(onChange);
  }

  /* ---------------- tokens ---------------- */
  WF.tokens = function () {
    var cs = getComputedStyle(document.documentElement);
    var g = function (n) { return cs.getPropertyValue(n).trim(); };
    return {
      surface: g('--surface'), surface2: g('--surface-2'), page: g('--page'), ink: g('--ink'), ink2: g('--ink-2'), muted: g('--muted'),
      grid: g('--grid'), axis: g('--axis'), missing: g('--missing'), gray: g('--emph-gray'),
      series: [g('--s1'), g('--s2'), g('--s3'), g('--s4'), g('--s5'), g('--s6'), g('--s7'), g('--s8')],
      seq: [g('--seq-100'), g('--seq-200'), g('--seq-300'), g('--seq-400'), g('--seq-500'), g('--seq-600'), g('--seq-700')]
    };
  };
  WF.seqScale = function (t) {
    var s = t.seq; return [[0, s[0]], [0.17, s[1]], [0.33, s[2]], [0.5, s[3]], [0.67, s[4]], [0.83, s[5]], [1, s[6]]];
  };
  WF.regionColor = function (t, region) {
    var order = ['West', 'South', 'Northeast', 'Alaska', 'Hawaii/PR', 'Other'];
    var i = order.indexOf(region); return i < 0 ? t.missing : t.series[i];
  };
  WF.causeColor = function (t, c) {
    if (c === 'Human') return t.series[0];
    if (c === 'Natural') return t.series[1];
    return t.missing;
  };

  /* ---------------- formatting ---------------- */
  WF.fmt = {
    int: function (x) { return (x === null || x === undefined || isNaN(x)) ? '' : Math.round(x).toLocaleString('en-US'); },
    num: function (x, d) { if (x === null || x === undefined || isNaN(x)) return ''; return Number(x).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }); },
    pct: function (x, d) { if (x === null || x === undefined || isNaN(x)) return ''; return (100 * x).toFixed(d === undefined ? 1 : d) + '%'; },
    compact: function (x) {
      if (x === null || x === undefined || isNaN(x)) return '';
      var a = Math.abs(x);
      if (a >= 1e6) return (x / 1e6).toFixed(a >= 1e7 ? 1 : 2) + 'M';
      if (a >= 1e3) return (x / 1e3).toFixed(a >= 1e4 ? 0 : 1) + 'K';
      return Number(x).toLocaleString('en-US', { maximumFractionDigits: 2 });
    }
  };
  WF.claim = function (id) { return (D.claims || {})[id]; };
  WF.claimN = function (ids) {
    var best = null;
    (ids || []).forEach(function (id) { var c = WF.claim(id); if (c && typeof c.n === 'number' && (best === null || c.n > best)) best = c.n; });
    return best;
  };

  /* ---------------- definitions popover ---------------- */
  var pop = null;
  function closePop() { if (pop && pop.parentNode) pop.parentNode.removeChild(pop); pop = null; }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; }
  function dtdd(dl, k, v) { if (v === undefined || v === null || v === '') return; dl.appendChild(el('dt', null, k)); dl.appendChild(el('dd', null, String(v))); }
  WF.showDefinition = function (btn) {
    closePop();
    var p = el('div', 'popover'); p.setAttribute('role', 'dialog');
    var x = el('button', 'close', '×'); x.setAttribute('aria-label', 'Close'); x.onclick = closePop; p.appendChild(x);
    var dl = el('dl');
    var id = btn.getAttribute('data-claim');
    if (id) {
      var c = WF.claim(id);
      if (c) {
        dtdd(dl, 'Claim id', id);
        dtdd(dl, 'Definition', c.definition);
        dtdd(dl, 'n (records behind this number)', typeof c.n === 'number' ? WF.fmt.int(c.n) : c.n);
        dtdd(dl, 'Unit', c.unit);
        dtdd(dl, 'Note', c.note);
        dtdd(dl, 'Source', c.source + ' (' + c._file + ', computed ' + (c.computed_at || '').slice(0, 10) + ')');
        dtdd(dl, 'Other claims in this chart', btn.getAttribute('data-claims'));
      } else { dtdd(dl, 'Claim id', id); dtdd(dl, 'Definition', 'not found in the loaded ledger'); }
    } else {
      dtdd(dl, 'Definition', btn.getAttribute('data-def'));
      dtdd(dl, 'n', btn.getAttribute('data-n'));
      dtdd(dl, 'Source', btn.getAttribute('data-src'));
    }
    p.appendChild(dl);
    document.body.appendChild(p);
    var r = btn.getBoundingClientRect();
    var top = r.bottom + window.scrollY + 6;
    var left = Math.max(8, Math.min(r.left + window.scrollX, window.innerWidth - p.offsetWidth - 8));
    p.style.top = top + 'px'; p.style.left = left + 'px';
    pop = p;
  };
  document.addEventListener('click', function (ev) {
    var b = ev.target.closest && ev.target.closest('button.q');
    if (b) { ev.preventDefault(); WF.showDefinition(b); return; }
    if (pop && !pop.contains(ev.target)) closePop();
  });
  document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') closePop(); });

  /* ---------------- CSV ---------------- */
  function csvCell(v) {
    if (v === null || v === undefined) return '';
    var s = String(v);
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }
  WF.downloadCSV = function (name, columns, rows, meta) {
    var lines = [];
    var m = meta || {};
    lines.push('# ' + (m.title || name));
    if (m.definition) lines.push('# definition: ' + m.definition.replace(/\n/g, ' '));
    if (m.claims && m.claims.length) lines.push('# claim ids: ' + m.claims.join(' '));
    if (m.n !== undefined && m.n !== null) lines.push('# n: ' + m.n);
    lines.push('# data: FPA FOD 6th ed. (Short 2022), SHA-256 ' + (D.meta ? D.meta.hash_prefix : '') + '; generated ' + (D.meta ? D.meta.generated : '') + '; ' + (D.meta ? D.meta.repo : ''));
    lines.push(columns.map(function (c) { return csvCell(c.label || c.key); }).join(','));
    rows.forEach(function (r) { lines.push(columns.map(function (c) { return csvCell(r[c.key]); }).join(',')); });
    var blob = new Blob([lines.join('\n') + '\n'], { type: 'text/csv;charset=utf-8' });
    var a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name + '.csv';
    document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  };

  /* ---------------- table view ---------------- */
  /* Column classes: num right-aligns; hideSm drops a secondary column on narrow screens (the CSV keeps it). */
  function colClass(c) { var k = [c.num ? 'num' : '', c.hideSm ? 'hide-sm' : ''].join(' ').trim(); return k || null; }
  WF.buildTable = function (columns, rows, opts) {
    var t = el('table'); if (opts && opts.cls) t.className = opts.cls;
    var thead = el('thead'), tr = el('tr');
    columns.forEach(function (c) { var th = el('th', colClass(c), c.label || c.key); if (opts && opts.sortable) { th.className += ' sortable'; th.setAttribute('data-key', c.key); th.setAttribute('data-num', c.num ? '1' : '0'); } tr.appendChild(th); });
    thead.appendChild(tr); t.appendChild(thead);
    var tb = el('tbody');
    rows.forEach(function (r) {
      var row = el('tr'); if (r._missing) row.className = 'missing-row';
      columns.forEach(function (c) {
        var v = r[c.key]; var td = el('td', colClass(c));
        if (c.fmt && v !== null && v !== undefined && v !== '') td.textContent = c.fmt(v); else td.textContent = (v === null || v === undefined) ? '' : String(v);
        row.appendChild(td);
      });
      tb.appendChild(row);
    });
    t.appendChild(tb);
    if (opts && opts.sortable) WF.sortable(t, rows, columns);
    return t;
  };
  WF.sortable = function (table, rows, columns) {
    var ths = table.querySelectorAll('th.sortable');
    var state = { key: null, dir: 1 };
    function render() {
      var tb = table.querySelector('tbody'); tb.textContent = '';
      var sorted = rows.slice();
      if (state.key) {
        var col = columns.filter(function (c) { return c.key === state.key; })[0];
        sorted.sort(function (a, b) {
          var x = a[state.key], y = b[state.key];
          if (x === null || x === undefined || x === '') return 1; if (y === null || y === undefined || y === '') return -1;
          if (col && col.num) return (Number(x) - Number(y)) * state.dir;
          return String(x).localeCompare(String(y)) * state.dir;
        });
      }
      sorted.forEach(function (r) {
        var row = el('tr'); if (r._missing) row.className = 'missing-row';
        columns.forEach(function (c) { var v = r[c.key]; var td = el('td', colClass(c)); td.textContent = (c.fmt && v !== null && v !== undefined && v !== '') ? c.fmt(v) : ((v === null || v === undefined) ? '' : String(v)); row.appendChild(td); });
        tb.appendChild(row);
      });
      for (var i = 0; i < ths.length; i++) { var k = ths[i].getAttribute('data-key'); if (k === state.key) ths[i].setAttribute('aria-sort', state.dir > 0 ? 'ascending' : 'descending'); else ths[i].removeAttribute('aria-sort'); }
    }
    for (var i = 0; i < ths.length; i++) {
      ths[i].addEventListener('click', function () {
        var k = this.getAttribute('data-key');
        if (state.key === k) state.dir = -state.dir; else { state.key = k; state.dir = this.getAttribute('data-num') === '1' ? -1 : 1; }
        render();
      });
    }
  };

  /* ---------------- chart cards ---------------- */
  var charts = [];
  WF.baseLayout = function (t, extra) {
    var base = {
      paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
      font: { family: 'system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif', size: 12, color: t.ink2 },
      margin: { l: 56, r: 16, t: 12, b: 44 },
      xaxis: { gridcolor: t.grid, zerolinecolor: t.axis, linecolor: t.axis, tickcolor: t.axis, tickfont: { color: t.muted }, automargin: true },
      yaxis: { gridcolor: t.grid, zerolinecolor: t.axis, linecolor: t.axis, tickcolor: t.axis, tickfont: { color: t.muted }, automargin: true },
      legend: { orientation: 'h', y: -0.18, x: 0, font: { color: t.ink2 }, bgcolor: 'rgba(0,0,0,0)' },
      hoverlabel: { bgcolor: t.surface, bordercolor: t.axis, font: { color: t.ink, size: 12 } },
      colorway: t.series,
      bargap: 0.35, bargroupgap: 0.08
    };
    return deepMerge(base, extra || {});
  };
  function deepMerge(a, b) {
    var out = {}; var k;
    for (k in a) out[k] = a[k];
    for (k in b) {
      if (b[k] && typeof b[k] === 'object' && !Array.isArray(b[k]) && a[k] && typeof a[k] === 'object' && !Array.isArray(a[k])) out[k] = deepMerge(a[k], b[k]);
      else out[k] = b[k];
    }
    return out;
  }
  WF.config = { displayModeBar: false, responsive: true, displaylogo: false };

  /* spec: {el, title, sub, claims:[ids], n, rows, columns, build(t) -> {data, layout}, caption, csvName, staticImg, mapClass} */
  WF.chart = function (spec) {
    var host = typeof spec.el === 'string' ? document.getElementById(spec.el) : spec.el;
    if (!host) return null;
    host.classList.add('chart');
    host.textContent = '';
    var head = el('div', 'head');
    var h3 = el('h3', null, spec.title); head.appendChild(h3);
    var n = spec.n !== undefined ? spec.n : WF.claimN(spec.claims);
    var nEl = el('span', 'n', 'n = ' + (typeof n === 'number' ? WF.fmt.int(n) : (n || 'see definition')));
    head.appendChild(nEl);
    host.appendChild(head);
    if (spec.sub) { var sub = el('div', 'sub'); sub.textContent = spec.sub; host.appendChild(sub); }
    if (spec.controls) host.appendChild(spec.controls);
    var plot = el('div', 'plot' + (spec.mapClass ? ' map' : '')); host.appendChild(plot);
    if (spec.legendNote) { var ln = el('div', 'legend-note'); ln.innerHTML = spec.legendNote; host.appendChild(ln); }
    if (spec.caption) { var cap = el('p', 'caption'); cap.innerHTML = spec.caption; host.appendChild(cap); }
    var foot = el('div', 'foot');
    var tbtn = el('button', null, 'Table'); tbtn.type = 'button'; tbtn.setAttribute('aria-expanded', 'false');
    var cbtn = el('button', null, 'Download CSV'); cbtn.type = 'button';
    foot.appendChild(tbtn); foot.appendChild(cbtn);
    var defBtn = null;
    if (spec.claims && spec.claims.length) {
      defBtn = el('button', 'q', 'Definition'); defBtn.type = 'button'; defBtn.setAttribute('data-claim', spec.claims[0]);
      // Every claim id behind the chart is listed in the definition popover rather than printed under the chart.
      if (spec.claims.length > 1) defBtn.setAttribute('data-claims', spec.claims.slice(1).join(' '));
      foot.appendChild(defBtn);
    } else if (spec.definition) {
      defBtn = el('button', 'q', 'Definition'); defBtn.type = 'button'; defBtn.setAttribute('data-def', spec.definition); defBtn.setAttribute('data-src', spec.source || '');
      foot.appendChild(defBtn);
    }
    if (spec.staticImg) { var a = el('a', null, 'Static PNG'); a.href = spec.staticImg; foot.appendChild(a); }
    host.appendChild(foot);
    var tv = el('div', 'tableview'); tv.hidden = true; host.appendChild(tv);
    var tableBuilt = false;
    function showTable(force) {
      if (!tableBuilt) { var wrap = el('div', 'table-wrap'); wrap.appendChild(WF.buildTable(spec.columns, spec.rows)); tv.appendChild(wrap); tableBuilt = true; }
      var open = force === true ? true : tv.hidden;
      tv.hidden = !open; tbtn.setAttribute('aria-expanded', String(open)); tbtn.textContent = open ? 'Hide table' : 'Table';
    }
    tbtn.onclick = function () { showTable(); };
    var def0 = spec.claims && spec.claims.length && WF.claim(spec.claims[0]) ? WF.claim(spec.claims[0]).definition : (spec.definition || '');
    cbtn.onclick = function () { WF.downloadCSV(spec.csvName || (spec.el && spec.el.id) || spec.el || 'chart', spec.columns, spec.rows, { title: spec.title, definition: def0, claims: spec.claims, n: n }); };
    var entry = { spec: spec, plot: plot, showTable: showTable, rendered: false };
    entry.render = function () {
      if (!window.Plotly) {
        plot.textContent = ''; var fb = el('div', 'fallback', 'The chart library (Plotly, loaded from cdn.plot.ly) did not load. The table below holds the same numbers.');
        plot.appendChild(fb); plot.style.minHeight = '0'; showTable(true); return;
      }
      var t = WF.tokens();
      var built = spec.build(t);
      var layout = WF.baseLayout(t, built.layout || {});
      if (spec.height) layout.height = spec.height;
      Plotly.react(plot, built.data, layout, WF.config);
      entry.rendered = true;
    };
    charts.push(entry);
    entry.render();
    return entry;
  };
  WF.rerenderAll = function () { charts.forEach(function (c) { try { c.render(); } catch (e) { if (window.console) console.error(e); } }); };

  /* ---------------- helpers for pages ---------------- */
  WF.monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  WF.years = function (obj) { return Object.keys(obj).map(Number).sort(function (a, b) { return a - b; }); };
  WF.hoverN = function (label, n) { return label + '<br>n = ' + WF.fmt.int(n); };
  WF.segControl = function (options, onChange) {
    var box = el('div', 'seg'); box.setAttribute('role', 'group');
    options.forEach(function (o, i) {
      var b = el('button', null, o.label); b.type = 'button'; b.setAttribute('aria-pressed', i === 0 ? 'true' : 'false');
      b.onclick = function () { var bs = box.querySelectorAll('button'); for (var j = 0; j < bs.length; j++) bs[j].setAttribute('aria-pressed', 'false'); b.setAttribute('aria-pressed', 'true'); onChange(o.value); };
      box.appendChild(b);
    });
    return box;
  };

  document.addEventListener('DOMContentLoaded', function () {
    updateThemeButtons();
    var b = document.querySelectorAll('.theme-btn'); for (var i = 0; i < b.length; i++) b[i].addEventListener('click', WF.toggleTheme);
  });
})();
"""


# --------------------------------------------------------------------------- page shell

def layout(ctx: dict, page: str, title: str, body: str, page_js: str = '', description: str = '',
           extra_scripts: list[str] | tuple = (), body_attrs: str = '', nav_page: str | None = None) -> str:
    current = nav_page or page
    nav = ''.join(
        f'<a href="{href}"{" aria-current=\"page\"" if href == current else ""}>{esc(label)}</a>' for href, label in NAV)
    data_scripts = ''.join(f'<script src="data/{f}"></script>' for f in ctx['data_files'])
    data_scripts += ''.join(f'<script src="{esc(f)}"></script>' for f in extra_scripts if not f.startswith('assets/'))
    asset_scripts = ''.join(f'<script src="{esc(f)}"></script>' for f in extra_scripts if f.startswith('assets/'))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description or SITE_TITLE)}">
<link rel="stylesheet" href="assets/site.css">
<script>(function(){{try{{var t=localStorage.getItem('wf-theme');if(t)document.documentElement.setAttribute('data-theme',t);}}catch(e){{}}}})();</script>
</head>
<body{(' ' + body_attrs) if body_attrs else ''}>
<div class="topbar"><div class="wrap">
  <a class="brand" href="index.html">US wildfires <span>1992-2020 · totals to 2025</span></a>
  <nav class="main" aria-label="Pages">{nav}</nav>
  <button type="button" class="theme-btn" aria-label="Toggle dark or light mode">Dark mode</button>
</div></div>
<main><div class="wrap">
{body}
</div></main>
<footer class="site"><div class="wrap">
  <p>Data: FPA FOD 6th edition (Short 2022), SHA-256 <code>{esc(ctx['hash_prefix'])}</code> (full hash in <a href="{DOCS_URL}/DATA_VERSION.md">docs/DATA_VERSION.md</a>).
  Site generated {esc(ctx['generated'])} by <code>scripts/build_site.py</code> from {esc(', '.join(ctx['claims_files']))}.</p>
  <p>Every number on this page links to its definition and n (click it). Charts: Table view and CSV download under each one. <a href="audit.html">What changed from the first public site</a>.
  <a href="{DOCS_URL}">Repository docs</a> · <a href="{DOCS_URL}/SITE.md">How this site is built</a> · <a href="{REPO_URL}">{esc(REPO_URL.replace('https://', ''))}</a> · {esc(AUTHOR)}.</p>
</div></footer>
{data_scripts}
{'<script src="vendor/geo_assets.js"></script>' if PLOTLY_SRC != PLOTLY_CDN else ''}
<script src="{PLOTLY_SRC}" charset="utf-8"></script>
<script src="assets/site.js"></script>
{asset_scripts}
{('<script>' + page_js + '</script>') if page_js else ''}
</body>
</html>
"""


def chart_div(cid: str) -> str:
    return f'<div id="{cid}" class="chart" aria-live="polite"></div>'


def placeholder(title: str, text: str) -> str:
    return f'<div class="placeholder"><h3>{esc(title)} <span class="tag">placeholder</span></h3><p>{text}</p></div>'


# --------------------------------------------------------------------------- index

def page_index(ctx: dict) -> str:
    c = ctx['claims']
    n_rows = cv(c, 'overview.n_rows')
    owner_known = 1 - cv(c, 'overview.missing_shares', 'OWNER_DESCR_missing_category')
    cause_known = 1 - cv(c, 'overview.missing_shares', 'NWCG_CAUSE_CLASSIFICATION_missing_category')
    gen_cause_known = 1 - cv(c, 'overview.missing_shares', 'NWCG_GENERAL_CAUSE_missing_category')
    cont = cv(c, 'cont.share_with_cont_date')
    tr = cv(c, 'class_g.acres_trend')
    tr_x = cv(c, 'class_g.acres_trend_excl_alaska')
    ftr = cv(c, 'year.fires_trend')
    hp = cv(c, 'class_g.half_period_means')
    own = cv(c, 'owner.fires_and_acres')
    peak = cv(c, 'season.peak_month_by_region')
    geo = cv(c, 'geo.cells_1deg_summary')

    def tile(label, value, sub, cid, share=None):
        meter = f'<div class="meter" aria-hidden="true"><i style="width:{100 * share:.1f}%"></i></div>' if share is not None else ''
        return (f'<div class="tile"><div class="label">{esc(label)}</div>'
                f'<div class="value">{q(c, cid, value)}</div><div class="sub">{esc(sub)}</div>{meter}</div>')

    strip = '<div class="strip" aria-label="Data completeness">' + ''.join([
        tile('Records', fmt_int(n_rows), 'ignition points, 1992-2020', 'overview.n_rows'),
        tile('Known land owner', fmt_pct(owner_known), f'{fmt_pct(1 - owner_known)} MISSING/NOT SPECIFIED', 'overview.missing_shares', owner_known),
        tile('Known cause class', fmt_pct(cause_known), f'human or natural; general cause known for {fmt_pct(gen_cause_known)}', 'overview.missing_shares', cause_known),
        tile('Containment date', fmt_pct(cont), 'records with a CONT_DATE', 'cont.share_with_cont_date', cont),
    ]) + '</div>'

    cards = [
        ('Large fires burn more acres than in the 1990s',
         f'Acres in fires of 5,000+ acres (Class G) rise by {q(c, "class_g.acres_trend", fmt_int(tr["theil_sen_slope"]) + " acres a year")} '
         f'(Theil-Sen; Kendall tau {q(c, "class_g.acres_trend", fmt_num(tr["kendall_tau"], 2))}, p = {q(c, "class_g.acres_trend", fmt_num(tr["kendall_p"], 4))}). '
         f'Without Alaska: tau {q(c, "class_g.acres_trend_excl_alaska", fmt_num(tr_x["kendall_tau"], 2))}, p = {q(c, "class_g.acres_trend_excl_alaska", fmt_num(tr_x["kendall_p"], 3))}. '
         f'Mean annual Class G acres: {q(c, "class_g.half_period_means", fmt_m(hp["1992_2005"]))} in 1992-2005, {q(c, "class_g.half_period_means", fmt_m(hp["2006_2020"]))} in 2006-2020.',
         'class_g.acres_trend', 'trends.html', 'Trends'),
        ('The number of recorded fires shows no trend',
         f'Kendall tau {q(c, "year.fires_trend", fmt_num(ftr["kendall_tau"], 2))} (p = {q(c, "year.fires_trend", fmt_num(ftr["kendall_p"], 2))}) on fires per year. '
         f'Counts follow which agencies reported: Texas goes from 1,040 records in 2004 to 15,019 in 2006, New York from 129 in 1994 to 7,700 in 2005. '
         f'Area burned is more robust than counts because large fires are reported by every system.',
         'year.fires_trend', 'trends.html', 'Trends'),
        ('Human ignitions dominate on private and unrecorded land; lightning dominates on BLM and USFS land',
         f'Human share of fires with a known cause: BLM {q(c, "owner.fires_and_acres", fmt_pct(own["BLM"]["human_share_known"], 0))}, '
         f'USFS {q(c, "owner.fires_and_acres", fmt_pct(own["USFS"]["human_share_known"], 0))}, '
         f'State {q(c, "owner.fires_and_acres", fmt_pct(own["STATE"]["human_share_known"], 0))}, '
         f'Private {q(c, "owner.fires_and_acres", fmt_pct(own["PRIVATE"]["human_share_known"], 0))}, '
         f'owner not recorded {q(c, "owner.fires_and_acres", fmt_pct(own["MISSING/NOT SPECIFIED"]["human_share_known"], 0))}. '
         f'Ownership is missing for {q(c, "owner.missing_share_fires", fmt_pct(cv(c, "owner.missing_share_fires")))} of fires.',
         'owner.fires_and_acres', 'ownership.html', 'Ownership'),
        ('Fire seasons differ by region',
         f'Peak month for fires: South {q(c, "season.peak_month_by_region", peak["South"]["fires"])}, '
         f'West {q(c, "season.peak_month_by_region", peak["West"]["fires"])} (acres peak in {q(c, "season.peak_month_by_region", peak["West"]["acres"])}), '
         f'Alaska {q(c, "season.peak_month_by_region", peak["Alaska"]["fires"])}, Northeast {q(c, "season.peak_month_by_region", peak["Northeast"]["fires"])}. '
         f'Class G fires: the South leads November to April, the West May to October.',
         'season.peak_month_by_region', 'causes.html', 'Causes and seasons'),
    ]
    cards_html = '<div class="cards">' + ''.join(
        f'<div class="card"><h3>{esc(title)}</h3><div class="n">n = {fmt_int(c[cid]["n"])} records · '
        f'{q(c, cid, "definition")}</div>'
        f'<details><summary>What the number means</summary><p class="small">{text}</p></details>'
        f'<a class="go" href="{href}">{esc(label)} &rarr;</a></div>'
        for title, text, cid, href, label in cards) + '</div>'

    where = (f'The 50 busiest 1-degree cells hold {q(c, "geo.cells_1deg_summary", fmt_pct(geo["share_of_fires_in_top_50_cells"]))} of fires; '
             f'the 50 largest by acreage hold {q(c, "geo.cells_1deg_summary", fmt_pct(geo["share_of_acres_in_top_50_cells_by_acres"]))} of acres, and they are different cells.')

    body = f"""
<header class="page-head">
<h1>Large US wildfires burn more acres than in the 1990s, especially in the West. The number of recorded fires shows no trend, and the record's coverage varies by state and year.</h1>
<p class="lede">The data is the FPA FOD, a compilation of federal, state and local wildfire reports for 1992-2020: ignition points with a date, a size and a cause.
It has no fire perimeters, no prescribed fire, no burn severity and no losses, and not every state reports in every year.</p>
</header>
{strip}
<p class="small muted">Completeness of the whole record. Percentages are shares of all {q(c, 'overview.n_rows', fmt_int(n_rows))} records; click any number for its definition. Missing and undetermined categories stay visible on every chart in this site.</p>

<h2>Four facts that hold up</h2>
<p>Each card carries the number of records behind it and a link to the definition. The full ledger of {ctx['n_claims']} computed claims is on the <a href="methods.html#ledger">Methods page</a>.</p>
{cards_html}

<h2>Where</h2>
<p>{where} Human share among known causes is above 90% across the South and East and drops to 20-50% in the interior West and Alaska. <a href="geography.html">Map and state table &rarr;</a></p>

<h2>What was retired</h2>
<p>An earlier version of this project ranked land-management agencies with a "Control Efficiency Score" and shipped a fire-duration model. Both are retired: the score's ranking flips when the mean is swapped for the median
(Spearman {q(c, 'ces.spearman_mean_vs_median', fmt_num(cv(c, 'ces.spearman_mean_vs_median'), 2))} between the two rankings), and the model lost to "predict zero days" on mean absolute error.
<a href="ownership.html#ces">Why the score was retired</a> · <a href="model.html">What replaces the model</a> · <a href="methods.html#errata">Errata</a>.</p>
"""
    return layout(ctx, 'index.html', SITE_TITLE, body,
                  description='Descriptive analysis of 2.3 million US wildfire records, 1992-2020, with every number traced to a definition.')


# --------------------------------------------------------------------------- trends

TRENDS_JS = r"""
(function(){
  var C = WF.data.claims;
  var ya = C['year.fires_and_acres'].value, years = WF.years(ya);
  var fpk = C['year.fires_and_acres_peak'].value;
  WF.chart({ el: 'fires-year', title: 'Fires recorded per year', claims: ['year.fires_and_acres', 'year.fires_trend'],
    sub: 'Count of records by FIRE_YEAR. The count depends on which reporting systems were included in each year.',
    rows: years.map(function (y) { return { year: y, fires: ya[y].fires }; }),
    columns: [{ key: 'year', label: 'year' }, { key: 'fires', label: 'fires', num: true, fmt: WF.fmt.int }],
    staticImg: 'figures/fires_and_acres_by_year.png', height: 280,
    build: function (t) { return {
      data: [{ type: 'bar', x: years, y: years.map(function (y) { return ya[y].fires; }), marker: { color: t.series[0] }, name: 'fires',
        hovertemplate: '%{x}<br>%{y:,} fires<extra></extra>' }],
      layout: { showlegend: false, yaxis: { title: { text: 'fires' }, rangemode: 'tozero', tickformat: ',' },
        annotations: [{ x: fpk.fires_peak_year, y: fpk.fires_peak, text: fpk.fires_peak_year + ': ' + WF.fmt.int(fpk.fires_peak) + ' (a reporting peak)', showarrow: true, arrowhead: 0, ax: -40, ay: -28, font: { color: t.ink2, size: 11 }, arrowcolor: t.axis }] } }; }
  });
  WF.chart({ el: 'acres-year', title: 'Acres burned per year', claims: ['year.fires_and_acres', 'year.acres_trend'],
    sub: 'Sum of FIRE_SIZE by FIRE_YEAR, all size classes.',
    rows: years.map(function (y) { return { year: y, acres: Math.round(ya[y].acres) }; }),
    columns: [{ key: 'year', label: 'year' }, { key: 'acres', label: 'acres', num: true, fmt: WF.fmt.int }],
    staticImg: 'figures/fires_and_acres_by_year.png', height: 280,
    build: function (t) { return {
      data: [{ type: 'bar', x: years, y: years.map(function (y) { return ya[y].acres; }), marker: { color: t.series[0] }, name: 'acres',
        hovertemplate: '%{x}<br>%{y:,.0f} acres<extra></extra>' }],
      layout: { showlegend: false, yaxis: { title: { text: 'acres' }, rangemode: 'tozero', tickformat: '.2s' },
        annotations: [{ x: fpk.acres_peak_year, y: fpk.acres_peak, text: fpk.acres_peak_year + ': ' + WF.fmt.compact(fpk.acres_peak) + ' acres', showarrow: true, arrowhead: 0, ax: -60, ay: -20, font: { color: t.ink2, size: 11 }, arrowcolor: t.axis }] } }; }
  });

  var ga = C['class_g.acres_by_year'].value, gx = C['class_g.acres_by_year_excl_alaska'].value, gk = C['class_g.acres_by_year_alaska'].value;
  var tA = C['class_g.acres_trend'].value, tX = C['class_g.acres_trend_excl_alaska'].value;
  var gy = WF.years(ga);
  function ts(tr, y) { return tr.theil_sen_intercept + tr.theil_sen_slope * y; }
  WF.chart({ el: 'classg-acres', title: 'Class G acres per year, with and without Alaska', claims: ['class_g.acres_by_year', 'class_g.acres_by_year_excl_alaska', 'class_g.acres_by_year_alaska', 'class_g.acres_trend', 'class_g.acres_trend_excl_alaska', 'class_g.acres_trend_alaska'],
    sub: 'Fires of 5,000 acres and more (FIRE_SIZE_CLASS G). Dashed lines are Theil-Sen fits over the 29 annual points.',
    rows: gy.map(function (y) { return { year: y, acres_all: Math.round(ga[y]), acres_excl_alaska: Math.round(gx[y]), acres_alaska: Math.round(gk[y]), theil_sen_all: Math.round(ts(tA, y)), theil_sen_excl_alaska: Math.round(ts(tX, y)) }; }),
    columns: [{ key: 'year', label: 'year' }, { key: 'acres_all', label: 'acres, all states', num: true, fmt: WF.fmt.int }, { key: 'acres_excl_alaska', label: 'acres, excluding Alaska', num: true, fmt: WF.fmt.int }, { key: 'acres_alaska', label: 'acres, Alaska', num: true, fmt: WF.fmt.int }, { key: 'theil_sen_all', label: 'Theil-Sen fit, all', num: true, fmt: WF.fmt.int }, { key: 'theil_sen_excl_alaska', label: 'Theil-Sen fit, excl. Alaska', num: true, fmt: WF.fmt.int }],
    staticImg: 'figures/class_g_acres_trend.png', height: 360,
    caption: 'All states: Kendall tau ' + tA.kendall_tau.toFixed(2) + ' (p = ' + tA.kendall_p.toFixed(4) + '), Theil-Sen slope ' + WF.fmt.int(tA.theil_sen_slope) + ' acres a year (95% interval ' + WF.fmt.int(tA.theil_sen_slope_ci95[0]) + ' to ' + WF.fmt.int(tA.theil_sen_slope_ci95[1]) + '). ' +
      'Excluding Alaska: tau ' + tX.kendall_tau.toFixed(2) + ' (p = ' + tX.kendall_p.toFixed(4) + '), slope ' + WF.fmt.int(tX.theil_sen_slope) + ' acres a year (' + WF.fmt.int(tX.theil_sen_slope_ci95[0]) + ' to ' + WF.fmt.int(tX.theil_sen_slope_ci95[1]) + '). ' +
      'Alaska alone: tau ' + C['class_g.acres_trend_alaska'].value.kendall_tau.toFixed(2) + ' (p = ' + C['class_g.acres_trend_alaska'].value.kendall_p.toFixed(2) + '), no trend. Plain Kendall p-values, no serial-correlation adjustment; n is the number of Class G fires behind the series.',
    build: function (t) {
      var L = function (obj, name, color) { return { type: 'scatter', mode: 'lines+markers', name: name, x: gy, y: gy.map(function (y) { return obj[y]; }), line: { color: color, width: 2 }, marker: { size: 7, color: color, line: { color: t.surface, width: 2 } }, hovertemplate: '%{x}<br>%{y:,.0f} acres<extra>' + name + '</extra>' }; };
      var F = function (tr, name, color) { return { type: 'scatter', mode: 'lines', name: name, x: gy, y: gy.map(function (y) { return ts(tr, y); }), line: { color: color, width: 1.5, dash: 'dash' }, hoverinfo: 'skip', showlegend: true }; };
      return { data: [L(ga, 'All states', t.series[0]), L(gx, 'Excluding Alaska', t.series[1]), L(gk, 'Alaska', t.series[2]), F(tA, 'Theil-Sen, all', t.series[0]), F(tX, 'Theil-Sen, excl. Alaska', t.series[1])],
        layout: { yaxis: { title: { text: 'acres' }, rangemode: 'tozero', tickformat: '.2s' }, legend: { y: -0.22 }, hovermode: 'x unified' } };
    }
  });

  var gf = C['class_g.fires_by_year'].value, tF = C['class_g.fires_trend'].value;
  WF.chart({ el: 'classg-fires', title: 'Class G fires per year', claims: ['class_g.fires_by_year', 'class_g.fires_trend'],
    sub: 'Count of fires of 5,000+ acres. These are recorded by every reporting system, so the count is comparable across years.',
    rows: gy.map(function (y) { return { year: y, class_g_fires: gf[y] }; }),
    columns: [{ key: 'year', label: 'year' }, { key: 'class_g_fires', label: 'Class G fires', num: true, fmt: WF.fmt.int }], height: 260,
    caption: 'Kendall tau ' + tF.kendall_tau.toFixed(2) + ' (p = ' + tF.kendall_p.toFixed(3) + '), Theil-Sen slope ' + tF.theil_sen_slope.toFixed(1) + ' fires a year (95% interval ' + tF.theil_sen_slope_ci95[0].toFixed(1) + ' to ' + tF.theil_sen_slope_ci95[1].toFixed(1) + ').',
    build: function (t) { return { data: [{ type: 'bar', x: gy, y: gy.map(function (y) { return gf[y]; }), marker: { color: t.series[0] }, hovertemplate: '%{x}<br>%{y} Class G fires<extra></extra>' },
      { type: 'scatter', mode: 'lines', x: gy, y: gy.map(function (y) { return ts(tF, y); }), line: { color: t.series[0], dash: 'dash', width: 1.5 }, hoverinfo: 'skip', name: 'Theil-Sen' }],
      layout: { showlegend: false, yaxis: { title: { text: 'fires' }, rangemode: 'tozero' } } }; }
  });

  var ne = C['anom.northeast_fires_by_state_year'].value, neStates = Object.keys(ne).sort(), neYears = WF.years(ne[neStates[0]]);
  WF.chart({ el: 'ne-states', title: 'Northeast fire counts by state and year: a reporting series', claims: ['anom.northeast_fires_by_state_year', 'anom.northeast_zero_report_years', 'anom.northeast_largest_yoy_count_jumps'],
    sub: 'New York highlighted; the other eight Northeast states in gray. Zero-record years are reporting gaps, not fire-free years.',
    rows: neYears.map(function (y) { var r = { year: y }; neStates.forEach(function (s) { r[s] = ne[s][y]; }); return r; }),
    columns: [{ key: 'year', label: 'year' }].concat(neStates.map(function (s) { return { key: s, label: s, num: true, fmt: WF.fmt.int }; })), height: 300,
    build: function (t) {
      var data = neStates.filter(function (s) { return s !== 'NY'; }).map(function (s) { return { type: 'scatter', mode: 'lines', name: s, x: neYears, y: neYears.map(function (y) { return ne[s][y]; }), line: { color: t.gray, width: 1.5 }, hovertemplate: '%{x} ' + s + ': %{y:,}<extra></extra>', showlegend: false }; });
      data.push({ type: 'scatter', mode: 'lines+markers', name: 'NY', x: neYears, y: neYears.map(function (y) { return ne['NY'][y]; }), line: { color: t.series[0], width: 2 }, marker: { size: 6, color: t.series[0], line: { color: t.surface, width: 2 } }, hovertemplate: '%{x} NY: %{y:,}<extra></extra>' });
      return { data: data, layout: { showlegend: false, yaxis: { title: { text: 'fires' }, rangemode: 'tozero', tickformat: ',' },
        annotations: [{ x: 2005, y: ne['NY']['2005'], text: 'NY 2005: ' + WF.fmt.int(ne['NY']['2005']), showarrow: true, arrowhead: 0, ax: -50, ay: -25, font: { size: 11, color: t.ink2 }, arrowcolor: t.axis }, { x: 1994, y: ne['NY']['1994'], text: 'NY 1994: ' + ne['NY']['1994'], showarrow: true, arrowhead: 0, ax: 30, ay: -30, font: { size: 11, color: t.ink2 }, arrowcolor: t.axis }] } };
    }
  });

  var cov = WF.data.coverage;
  if (cov) {
    var st = Object.keys(cov.by_state_year).sort(), cy = WF.years(cov.by_state_year[st[0]]);
    var inWin = function (s, y) { var w = cov.windows && cov.windows[s]; return w ? (y >= w[0] && y <= w[1]) : null; };
    var z = st.map(function (s) { return cy.map(function (y) { var v = cov.by_state_year[s][y]; return (v === undefined || v === null || v === 0) ? null : Math.log10(v); }); });
    var rows = []; st.forEach(function (s) { cy.forEach(function (y) { var br = cov.breaks && cov.breaks[s] && cov.breaks[s][y]; rows.push({ state: s, year: y, records: cov.by_state_year[s][y] || 0, inside_usable_window: inWin(s, y) === null ? '' : (inWin(s, y) ? 'yes' : 'no'), break_year: br ? 'yes' : '', ratio_to_prior_nonzero_year: br || '' }); }); });
    var bx = [], by = [], bt = []; st.forEach(function (s) { var b = cov.breaks && cov.breaks[s]; if (b) Object.keys(b).forEach(function (y) { bx.push(Number(y)); by.push(s); bt.push(s + ' ' + y + ': break, ' + b[y] + 'x the prior non-zero year'); }); });
    WF.chart({ el: 'coverage', title: 'Records by state and year: reporting coverage', definition: cov.definition, source: cov.source, n: cov.n, csvName: 'coverage_state_year',
      sub: 'Color is log10 of the record count; blank cells have zero records. Crosses mark break years (count more than 3x or less than a third of the prior non-zero year). Rows are grouped by region.',
      rows: rows, columns: [{ key: 'state' }, { key: 'year' }, { key: 'records', num: true, fmt: WF.fmt.int }, { key: 'inside_usable_window', label: 'inside usable window' }, { key: 'break_year', label: 'break year' }, { key: 'ratio_to_prior_nonzero_year', label: 'ratio to prior non-zero year', num: true }],
      staticImg: 'figures/coverage_state_year.png', height: Math.max(560, 15 * st.length + 80),
      build: function (t) {
        var order = st.slice().sort(function (a, b) { var ra = (cov.regions && cov.regions[a]) || '', rb = (cov.regions && cov.regions[b]) || ''; return ra === rb ? (a < b ? -1 : 1) : (ra < rb ? -1 : 1); });
        var zz = order.map(function (s) { return z[st.indexOf(s)]; });
        var cd = order.map(function (s) { return cy.map(function (y) { var w = inWin(s, y); return [cov.by_state_year[s][y] || 0, w === null ? '' : (w ? 'inside usable window' : 'outside usable window')]; }); });
        var ylab = order.map(function (s) { return s + ((cov.regions && cov.regions[s]) ? ' · ' + cov.regions[s] : ''); });
        return { data: [{ type: 'heatmap', z: zz, x: cy, y: ylab, colorscale: WF.seqScale(t), xgap: 1, ygap: 1, hoverongaps: false, customdata: cd,
          hovertemplate: '%{y} %{x}: %{customdata[0]:,} records<br>%{customdata[1]}<extra></extra>', colorbar: { title: { text: 'records (log10)' }, thickness: 10, tickvals: [1, 2, 3, 4], ticktext: ['10', '100', '1,000', '10,000'], tickfont: { color: t.muted } } },
          { type: 'scatter', mode: 'markers', x: bx, y: by.map(function (s) { return ylab[order.indexOf(s)]; }), text: bt, hovertemplate: '%{text}<extra></extra>', marker: { symbol: 'x-thin', size: 7, color: t.ink, line: { width: 1.5, color: t.ink } }, name: 'break year', showlegend: false }],
          layout: { margin: { l: 10, t: 6 }, yaxis: { autorange: 'reversed', tickfont: { size: 9 }, automargin: true }, xaxis: { side: 'top', dtick: 2 } } };
      }
    });
  }
})();
"""


def page_trends(ctx: dict) -> str:
    c = ctx['claims']
    ftr = cv(c, 'year.fires_trend')
    tr = cv(c, 'class_g.acres_trend')
    hp = cv(c, 'class_g.half_period_means')
    low = cv(c, 'class_g.five_lowest_years')
    ak_share = cv(c, 'class_g.alaska_share_of_acres')
    ne_jumps = cv(c, 'anom.northeast_largest_yoy_count_jumps')
    ne_zero = cv(c, 'anom.northeast_zero_report_years')
    ny = cv(c, 'anom.northeast_fires_by_state_year', 'NY')
    fire_src = 'docs/review/panel-fire.md section F1 (records by STATE and FIRE_YEAR; counted in the review, not yet a ledger claim)'
    if ctx['coverage']:
        cov_html = chart_div('coverage')
    else:
        cov_html = placeholder('State-by-year coverage heatmap',
                               'Not rendered: neither a <code>coverage.fires_by_state_year</code> claim nor <code>outputs/coverage.json</code> exists yet. '
                               'When one appears (contract in <a href="' + DOCS_URL + '/SITE.md">docs/SITE.md</a>) this section becomes a state x year heatmap of record counts with reporting breaks marked.')
    body = f"""
<header class="page-head"><h1>Trend</h1>
<p class="lede">National burned area has risen since the 1980s, in the bad years and the quiet ones. In the FPA FOD, acres burned by the largest fires rise over 1992-2020. The number of recorded fires does not, and it could not tell you if it did, because the record's coverage changes from year to year.</p></header>

{V().nifc_section(ctx)}
<h2>Fires and acres per year in the FPA FOD, 1992-2020</h2>
<p>The most fires in one year is {q(c, 'year.fires_and_acres_peak', fmt_int(cv(c, 'year.fires_and_acres_peak', 'fires_peak')))} in {q(c, 'year.fires_and_acres_peak', str(cv(c, 'year.fires_and_acres_peak', 'fires_peak_year')))}, a reporting peak rather than a fire peak.
The most acres is {q(c, 'year.fires_and_acres_peak', fmt_m(cv(c, 'year.fires_and_acres_peak', 'acres_peak')))} in {q(c, 'year.fires_and_acres_peak', str(cv(c, 'year.fires_and_acres_peak', 'acres_peak_year')))}.
Total acres trend upward (Kendall tau {q(c, 'year.acres_trend', fmt_num(cv(c, 'year.acres_trend', 'kendall_tau'), 2))}, p = {q(c, 'year.acres_trend', fmt_num(cv(c, 'year.acres_trend', 'kendall_p'), 3))}); fire counts do not (tau {q(c, 'year.fires_trend', fmt_num(ftr['kendall_tau'], 2))}, p = {q(c, 'year.fires_trend', fmt_num(ftr['kendall_p'], 2))}).</p>
<div class="grid2">{chart_div('fires-year')}{chart_div('acres-year')}</div>

<h2>The largest fires: Class G acres</h2>
<p>Class G fires (5,000+ acres) are {q(c, 'year.fires_share_by_size_class', fmt_pct(cv(c, 'year.fires_share_by_size_class', 'G'), 2))} of records and {q(c, 'year.acres_share_by_size_class', fmt_pct(cv(c, 'year.acres_share_by_size_class', 'G')))} of all acres, and they are recorded by every reporting system, so their series is the most comparable across years.
Mean annual Class G acres: {q(c, 'class_g.half_period_means', fmt_m(hp['1992_2005']))} in 1992-2005 and {q(c, 'class_g.half_period_means', fmt_m(hp['2006_2020']))} in 2006-2020; without Alaska {q(c, 'class_g.half_period_means', fmt_m(hp['1992_2005_excl_alaska']))} and {q(c, 'class_g.half_period_means', fmt_m(hp['2006_2020_excl_alaska']))}.
Alaska holds {q(c, 'class_g.alaska_share_of_acres', fmt_pct(ak_share))} of Class G acres and has no trend of its own, so the national rise comes from the lower 48, and mostly from the West.</p>
{chart_div('classg-acres')}
<div class="note"><p><strong>What the trend is not.</strong> "Higher highs and higher lows" was the earlier wording. The highs are higher; the lows are not: {q(c, 'class_g.five_lowest_years', '2010')} ({q(c, 'class_g.five_lowest_years', fmt_m(low['2010']))} acres) is the fifth-lowest of the 29 years.
The trend is carried by extreme years, which is what a fire regime driven by a few severe seasons looks like. This dataset has no weather, fuels or exposure data, so it cannot say why.</p></div>
{chart_div('classg-fires')}

<h2 id="counts">Why the count of fires is not a trend</h2>
<p>The FPA FOD is a compilation of reporting systems, not a census. State and local records were not available for every state in every year, so the national count of fires per year tracks which systems reported. The national count has no trend
(tau {q(c, 'year.fires_trend', fmt_num(ftr['kendall_tau'], 2))}, p = {q(c, 'year.fires_trend', fmt_num(ftr['kendall_p'], 2))}, Theil-Sen {q(c, 'year.fires_trend', fmt_int(ftr['theil_sen_slope']))} fires a year with a 95% interval of {q(c, 'year.fires_trend', fmt_int(ftr['theil_sen_slope_ci95'][0]))} to {q(c, 'year.fires_trend', fmt_int(ftr['theil_sen_slope_ci95'][1]))}), and single states show the breaks directly:</p>
<ul class="tight">
<li><strong>Texas</strong>: {qd('1,040', 'Texas records with FIRE_YEAR 2004', fire_src)} records in 2004, {qd('6,901', 'Texas records with FIRE_YEAR 2005', fire_src)} in 2005, {qd('15,019', 'Texas records with FIRE_YEAR 2006', fire_src)} in 2006. The Texas A&M Forest Service compilation of state and local fires starts in 2005.</li>
<li><strong>New York</strong>: {q(c, 'anom.northeast_fires_by_state_year', fmt_int(ny['1994']))} records in 1994, {q(c, 'anom.northeast_fires_by_state_year', fmt_int(ny['2000']))} in 2000, {q(c, 'anom.northeast_fires_by_state_year', fmt_int(ny['2005']))} in 2005, as local fire departments began reporting.</li>
<li><strong>Northeast as a whole</strong>: the three largest year-over-year count jumps are {', '.join(q(c, 'anom.northeast_largest_yoy_count_jumps', f'+{fmt_int(v)} in {k}') for k, v in sorted(ne_jumps.items(), key=lambda kv: -kv[1]))}. Rhode Island has zero records in {q(c, 'anom.northeast_zero_report_years', str(len(ne_zero['RI'])))} of the 29 years; Connecticut in {', '.join(str(y) for y in ne_zero['CT'])}.</li>
</ul>
<p>Area burned is less affected than counts, because very large fires are reported by several agencies and are captured whichever system a state used. That is why the trend claim on this site is made on Class G acres and not on counts.</p>
{chart_div('ne-states')}

<h2 id="coverage">Coverage by state and year</h2>
{cov_html}
"""
    return layout(ctx, 'trends.html', 'Trend · ' + SITE_TITLE, body, V().NIFC_JS + TRENDS_JS,
                  description='Fires and acres per year, the Class G acreage trend with and without Alaska, and why fire counts are not a trend.')


# --------------------------------------------------------------------------- causes and seasons

CAUSES_JS = r"""
(function(){
  var C = WF.data.claims, MISS = 'Missing data/not specified/undetermined';
  var CAUSES = ['Human', 'Natural', MISS], LABEL = { 'Human': 'Human', 'Natural': 'Natural', 'Missing data/not specified/undetermined': 'Undetermined / missing' };
  var bc = C['cause.by_classification'].value;
  function stack100(rowsLabels, getShare, getN, t, hoverUnit) {
    return CAUSES.map(function (k) { return { type: 'bar', orientation: 'h', name: LABEL[k], y: rowsLabels, x: rowsLabels.map(function (r) { return 100 * getShare(r, k); }),
      marker: { color: WF.causeColor(t, k), line: { color: t.surface, width: 2 } },
      customdata: rowsLabels.map(function (r) { return [getN(r, k), LABEL[k]]; }),
      hovertemplate: '%{y} · %{customdata[1]}: %{x:.1f}%<br>' + hoverUnit + ' %{customdata[0]:,}<extra></extra>' }; });
  }
  WF.chart({ el: 'cause-national', title: 'Cause classification: share of fires and share of acres', claims: ['cause.by_classification', 'cause.human_to_natural_fire_ratio', 'cause.natural_acres'],
    sub: 'NWCG_CAUSE_CLASSIFICATION, all records. Undetermined stays in the denominator.',
    rows: CAUSES.map(function (k) { return { cause: LABEL[k], fires: bc[k].fires, share_of_fires: bc[k].share_fires, acres: Math.round(bc[k].acres), share_of_acres: bc[k].share_acres, _missing: k === MISS }; }),
    columns: [{ key: 'cause', label: 'cause classification' }, { key: 'fires', label: 'fires', num: true, fmt: WF.fmt.int }, { key: 'share_of_fires', label: 'share of fires', num: true, fmt: function (v) { return WF.fmt.pct(v, 1); } }, { key: 'acres', label: 'acres', num: true, fmt: WF.fmt.int }, { key: 'share_of_acres', label: 'share of acres', num: true, fmt: function (v) { return WF.fmt.pct(v, 1); } }],
    height: 220,
    build: function (t) { return { data: stack100(['Acres', 'Fires'], function (r, k) { return r === 'Fires' ? bc[k].share_fires : bc[k].share_acres; }, function (r, k) { return r === 'Fires' ? bc[k].fires : Math.round(bc[k].acres); }, t, 'n ='),
      layout: { barmode: 'stack', bargap: 0.45, xaxis: { ticksuffix: '%', range: [0, 100] }, margin: { l: 50 }, legend: { y: -0.35 } } }; }
  });

  var byRegion = C['cause.by_classification_by_region'];
  if (byRegion) {
    var br = byRegion.value, regions = Object.keys(br);
    var rows = []; regions.forEach(function (r) { CAUSES.forEach(function (k) { var v = br[r][k] || { fires: 0, acres: 0 }; rows.push({ region: r, cause: LABEL[k], fires: v.fires, acres: Math.round(v.acres), _missing: k === MISS }); }); });
    var tot = function (r, m) { return CAUSES.reduce(function (s, k) { return s + ((br[r][k] || {})[m] || 0); }, 0); };
    ['fires', 'acres'].forEach(function (m) {
      WF.chart({ el: 'cause-region-' + m, title: 'Cause classification by region: share of ' + m, claims: ['cause.by_classification_by_region', 'overview.region_definition'],
        rows: rows, columns: [{ key: 'region' }, { key: 'cause' }, { key: 'fires', num: true, fmt: WF.fmt.int }, { key: 'acres', num: true, fmt: WF.fmt.int }], height: 300,
        build: function (t) { return { data: stack100(regions, function (r, k) { return ((br[r][k] || {})[m] || 0) / tot(r, m); }, function (r, k) { return Math.round((br[r][k] || {})[m] || 0); }, t, m + ' ='),
          layout: { barmode: 'stack', xaxis: { ticksuffix: '%', range: [0, 100] }, margin: { l: 80 }, legend: { y: -0.25 } } }; }
      });
    });
  }

  var ac = C['cause.classification_acre_share_by_size_class'].value, classes = ['A', 'B', 'C', 'D', 'E', 'F', 'G'];
  var fy = C['year.acres_by_size_class'].value, yrs = WF.years(fy);
  var acresByClass = {}; classes.forEach(function (k) { acresByClass[k] = yrs.reduce(function (s, y) { return s + fy[y][k]; }, 0); });
  var fbc = C['year.fires_by_size_class'].value; var firesByClass = {}; classes.forEach(function (k) { firesByClass[k] = yrs.reduce(function (s, y) { return s + fbc[y][k]; }, 0); });
  var classLabel = { A: 'A (<0.26 ac)', B: 'B (0.26-9.9)', C: 'C (10-99.9)', D: 'D (100-299)', E: 'E (300-999)', F: 'F (1,000-4,999)', G: 'G (5,000+)' };
  WF.chart({ el: 'cause-size-acres', title: 'Share of acres by cause classification within each size class', claims: ['cause.classification_acre_share_by_size_class', 'overview.size_class_definition'],
    sub: 'Each bar sums to 100% of the acres in that size class. Hover shows the acres in the class.',
    rows: classes.map(function (k) { return { size_class: classLabel[k], acres_in_class: Math.round(acresByClass[k]), human: ac[k]['Human'], natural: ac[k]['Natural'], undetermined: ac[k][MISS] }; }),
    columns: [{ key: 'size_class' }, { key: 'acres_in_class', label: 'acres in class', num: true, fmt: WF.fmt.int }, { key: 'human', label: 'human share', num: true, fmt: function (v) { return WF.fmt.pct(v); } }, { key: 'natural', label: 'natural share', num: true, fmt: function (v) { return WF.fmt.pct(v); } }, { key: 'undetermined', label: 'undetermined share', num: true, fmt: function (v) { return WF.fmt.pct(v); } }],
    height: 320,
    build: function (t) { return { data: CAUSES.map(function (k) { return { type: 'bar', name: LABEL[k], x: classes.map(function (s) { return classLabel[s]; }), y: classes.map(function (s) { return 100 * ac[s][k]; }), marker: { color: WF.causeColor(t, k), line: { color: t.surface, width: 2 } },
        customdata: classes.map(function (s) { return Math.round(acresByClass[s]); }), hovertemplate: '%{x}<br>' + LABEL[k] + ': %{y:.1f}% of %{customdata:,} acres<extra></extra>' }; }),
      layout: { barmode: 'stack', yaxis: { ticksuffix: '%', range: [0, 100] }, legend: { y: -0.3 } } }; }
  });
  var hk = C['cause.human_share_known_by_size_class'].value;
  WF.chart({ el: 'human-size', title: 'Human share of fires with a known cause, by size class', claims: ['cause.human_share_known_by_size_class'],
    sub: 'Denominator excludes undetermined causes. Hover shows all fires in the class (including undetermined).',
    rows: classes.map(function (k) { return { size_class: classLabel[k], fires_in_class: firesByClass[k], human_share_of_known: hk[k] }; }),
    columns: [{ key: 'size_class' }, { key: 'fires_in_class', label: 'fires in class (all causes)', num: true, fmt: WF.fmt.int }, { key: 'human_share_of_known', label: 'human share of known', num: true, fmt: function (v) { return WF.fmt.pct(v); } }],
    height: 280,
    build: function (t) { return { data: [{ type: 'bar', x: classes.map(function (s) { return classLabel[s]; }), y: classes.map(function (s) { return 100 * hk[s]; }), marker: { color: t.series[0] }, text: classes.map(function (s) { return (100 * hk[s]).toFixed(0) + '%'; }), textposition: 'outside', textfont: { color: t.ink2 }, customdata: classes.map(function (s) { return firesByClass[s]; }), hovertemplate: '%{x}<br>%{y:.1f}% human among known causes<br>%{customdata:,} fires in class<extra></extra>' }],
      layout: { showlegend: false, yaxis: { ticksuffix: '%', range: [0, 105] } } }; }
  });

  var gc = C['cause.by_general_cause'].value, gcNames = Object.keys(gc).sort(function (a, b) { return gc[a].share_fires - gc[b].share_fires; });
  WF.chart({ el: 'general-cause', title: 'General cause: share of fires against share of acres', claims: ['cause.by_general_cause'],
    sub: 'NWCG_GENERAL_CAUSE, 13 categories including the undetermined one. Natural means lightning and other non-human ignition.',
    rows: gcNames.slice().reverse().map(function (k) { return { general_cause: k, fires: gc[k].fires, share_of_fires: gc[k].share_fires, acres: Math.round(gc[k].acres), share_of_acres: gc[k].share_acres, mean_acres: gc[k].mean_acres, _missing: k === MISS }; }),
    columns: [{ key: 'general_cause' }, { key: 'fires', num: true, fmt: WF.fmt.int }, { key: 'share_of_fires', label: 'share of fires', num: true, fmt: function (v) { return WF.fmt.pct(v); } }, { key: 'acres', num: true, fmt: WF.fmt.int }, { key: 'share_of_acres', label: 'share of acres', num: true, fmt: function (v) { return WF.fmt.pct(v); } }, { key: 'mean_acres', label: 'mean acres per fire', num: true, fmt: function (v) { return WF.fmt.num(v, 1); } }],
    staticImg: 'figures/cause_share_fires_vs_acres.png', height: 420,
    build: function (t) { var lab = gcNames.map(function (k) { return k === MISS ? 'Undetermined / missing' : k; }); return { data: [
      { type: 'bar', orientation: 'h', name: 'Share of fires', y: lab, x: gcNames.map(function (k) { return 100 * gc[k].share_fires; }), marker: { color: t.series[0] }, customdata: gcNames.map(function (k) { return gc[k].fires; }), hovertemplate: '%{y}<br>%{x:.1f}% of fires (n = %{customdata:,})<extra></extra>' },
      { type: 'bar', orientation: 'h', name: 'Share of acres', y: lab, x: gcNames.map(function (k) { return 100 * gc[k].share_acres; }), marker: { color: t.series[1] }, customdata: gcNames.map(function (k) { return Math.round(gc[k].acres); }), hovertemplate: '%{y}<br>%{x:.1f}% of acres (%{customdata:,} acres)<extra></extra>' }],
      layout: { barmode: 'group', bargap: 0.3, xaxis: { ticksuffix: '%' }, margin: { l: 10 }, yaxis: { automargin: true, tickfont: { size: 11 } }, legend: { y: -0.12 } } }; }
  });

  var REG = ['West', 'South', 'Northeast', 'Alaska', 'Hawaii/PR', 'Other'];
  var fm = C['season.fires_by_region_month'].value, am = C['season.acres_by_region_month'].value;
  var fr = C['season.fires_by_region'].value, ar = C['season.acres_by_region'].value;
  var mode = 'fires';
  var seasonRows = []; REG.forEach(function (r) { for (var m = 1; m <= 12; m++) seasonRows.push({ region: r, month: WF.monthNames[m - 1], fires: fm[m][r], share_of_region_fires: fm[m][r] / fr[r], acres: Math.round(am[m][r]), share_of_region_acres: am[m][r] / ar[r] }); });
  var seasonChart = WF.chart({ el: 'season-heat', title: 'Seasonality by region: share of the region\'s fires (or acres) in each month', claims: ['season.fires_by_region_month', 'season.acres_by_region_month', 'season.fires_by_region', 'season.acres_by_region', 'overview.region_definition'],
    sub: 'Each row sums to 100%. Month is the month of discovery. Row labels carry the region\'s total n.',
    controls: WF.segControl([{ label: 'Fires', value: 'fires' }, { label: 'Acres', value: 'acres' }], function (v) { mode = v; seasonChart.render(); }),
    rows: seasonRows, columns: [{ key: 'region' }, { key: 'month' }, { key: 'fires', num: true, fmt: WF.fmt.int }, { key: 'share_of_region_fires', label: 'share of region fires', num: true, fmt: function (v) { return WF.fmt.pct(v); } }, { key: 'acres', num: true, fmt: WF.fmt.int }, { key: 'share_of_region_acres', label: 'share of region acres', num: true, fmt: function (v) { return WF.fmt.pct(v); } }],
    staticImg: 'figures/seasonality_by_region.png', height: 320,
    build: function (t) {
      var src = mode === 'fires' ? fm : am, totals = mode === 'fires' ? fr : ar;
      var y = REG.map(function (r) { return r + ' (n = ' + WF.fmt.compact(totals[r]) + (mode === 'fires' ? ' fires)' : ' acres)'); });
      var z = REG.map(function (r) { return WF.monthNames.map(function (_, i) { return 100 * src[i + 1][r] / totals[r]; }); });
      var cd = REG.map(function (r) { return WF.monthNames.map(function (_, i) { return Math.round(src[i + 1][r]); }); });
      return { data: [{ type: 'heatmap', z: z, x: WF.monthNames, y: y, customdata: cd, colorscale: WF.seqScale(t), xgap: 2, ygap: 2, zmin: 0,
        hovertemplate: '%{y}<br>%{x}: %{z:.1f}% of the region\'s ' + mode + ' (%{customdata:,})<extra></extra>', colorbar: { title: { text: '% of region' }, thickness: 10, ticksuffix: '%', tickfont: { color: t.muted } } }],
        layout: { margin: { l: 10 }, yaxis: { autorange: 'reversed', automargin: true } } };
    }
  });

  var cg = C['season.class_g_fires_by_region_month'].value, lead = C['season.class_g_leading_region_by_month'].value;
  var cgRows = []; for (var m = 1; m <= 12; m++) REG.forEach(function (r) { cgRows.push({ month: WF.monthNames[m - 1], region: r, class_g_fires: cg[m][r], leading_region: lead[WF.monthNames[m - 1]] }); });
  WF.chart({ el: 'classg-month', title: 'Class G fires by month of discovery, stacked by region', claims: ['season.class_g_fires_by_region_month', 'season.class_g_leading_region_by_month'],
    sub: 'Fires of 5,000+ acres, 1992-2020. The South leads November to April, the West May to October.',
    rows: cgRows, columns: [{ key: 'month' }, { key: 'region' }, { key: 'class_g_fires', label: 'Class G fires', num: true, fmt: WF.fmt.int }, { key: 'leading_region', label: 'leading region that month' }],
    staticImg: 'figures/monthly_class_g_by_region.png', height: 320,
    build: function (t) { return { data: REG.map(function (r) { return { type: 'bar', name: r, x: WF.monthNames, y: WF.monthNames.map(function (_, i) { return cg[i + 1][r]; }), marker: { color: WF.regionColor(t, r), line: { color: t.surface, width: 1.5 } }, hovertemplate: '%{x} ' + r + ': %{y} fires<extra></extra>' }; }),
      layout: { barmode: 'stack', yaxis: { title: { text: 'Class G fires' } }, legend: { y: -0.22 } } }; }
  });
})();
"""


def page_causes(ctx: dict) -> str:
    c = ctx['claims']
    bc = cv(c, 'cause.by_classification')
    miss = 'Missing data/not specified/undetermined'
    top = cv(c, 'cause.top_general_cause_by_size_class')
    peak = cv(c, 'season.peak_month_by_region')
    lead = cv(c, 'season.class_g_leading_region_by_month')
    fire_src = 'docs/review/panel-fire.md section F5, table "Share of fires and of acres by cause class" (computed in the review with a seven-way region split; not yet a ledger claim)'
    if 'cause.by_classification_by_region' in c:
        region_html = chart_div('cause-region-fires') + chart_div('cause-region-acres')
    else:
        panel_rows = [('West', 752490, 57.6, 32.1, 10.3, 102.5, 32.8, 61.8, 5.4), ('South', 1082568, 87.9, 5.4, 6.7, 32.9, 68.9, 19.5, 11.6),
                      ('Alaska', 15195, 63.5, 33.5, 3.0, 36.7, 4.9, 93.9, 1.2), ('Plains/Midwest', 236276, 91.9, 5.5, 2.6, 7.0, 68.6, 21.5, 9.9),
                      ('Northeast', 180427, 92.5, 4.9, 2.5, 0.4, 90.1, 4.6, 5.3), ('Hawaii', 9970, 2.0, 0.4, 97.5, 0.3, 29.6, 5.5, 64.9),
                      ('Puerto Rico', 22202, 1.3, 0.0, 98.6, 0.1, 7.0, 0.0, 93.0)]
        trs = ''.join(
            f'<tr><td>{r[0]}</td><td class="num">{qd(fmt_int(r[1]), f"fires with STATE in the {r[0]} group, 1992-2020", fire_src)}</td>'
            + ''.join(f'<td class="num">{qd(f"{v:.1f}%", f"{lab} in {r[0]}", fire_src, r[1])}</td>' for v, lab in
                      [(r[2], 'human share of fires'), (r[3], 'natural share of fires'), (r[4], 'undetermined share of fires')])
            + f'<td class="num">{qd(f"{r[5]:.1f}M", f"acres in {r[0]}", fire_src)}</td>'
            + ''.join(f'<td class="num">{qd(f"{v:.1f}%", f"{lab} in {r[0]}", fire_src, r[1])}</td>' for v, lab in
                      [(r[6], 'human share of acres'), (r[7], 'natural share of acres'), (r[8], 'undetermined share of acres')]) + '</tr>'
            for r in panel_rows)
        region_html = f"""
<div class="placeholder"><h3>Cause by region <span class="tag">from the review, pending a ledger claim</span></h3>
<p>The ledger has no <code>cause.by_classification_by_region</code> claim yet, so this table is transcribed from the fire-science review (docs/review/panel-fire.md, F5), which used a seven-way region split (Plains/Midwest separate; Hawaii and Puerto Rico separate). When the claim is added, an interactive chart replaces this table.</p>
<div class="table-wrap"><table><thead><tr><th>Region</th><th class="num">Fires</th><th class="num">Human</th><th class="num">Natural</th><th class="num">Undetermined</th><th class="num">Acres</th><th class="num">Human</th><th class="num">Natural</th><th class="num">Undetermined</th></tr>
<tr><th></th><th></th><th colspan="3" class="muted">share of fires</th><th></th><th colspan="3" class="muted">share of acres</th></tr></thead><tbody>{trs}</tbody></table></div>
<p class="small">Hawaii and Puerto Rico are 97-99% undetermined and should be excluded from cause comparisons. In the West the fires story (58% human) and the acres story (62% natural) point in opposite directions.</p></div>"""
    top_rows = ''.join(
        f'<tr><td>{k}</td><td>{esc(top[k]["top_cause"] if top[k]["top_cause"] != miss else "Undetermined / missing")}</td>'
        f'<td class="num">{q(c, "cause.top_general_cause_by_size_class", fmt_pct(top[k]["share"]))}</td>'
        f'<td>{"plurality" if not top[k]["is_majority"] else "majority"}</td>'
        f'<td class="small">{esc("; ".join(f"{(n if n != miss else "Undetermined")} {100 * s:.1f}%" for n, s in sorted(top[k]["top3"].items(), key=lambda kv: -kv[1])))}</td></tr>'
        for k in SIZE_CLASSES)
    lead_row = ''.join(f'<td>{esc(lead[m])}</td>' for m in MONTHS)
    body = f"""
<header class="page-head"><h1>Seasons and causes</h1>
<p class="lede">Counting every record from 1992 to 2020, human ignitions are {q(c, 'cause.by_classification', fmt_pct(bc['Human']['share_fires']))} of fires but {q(c, 'cause.by_classification', fmt_pct(bc['Human']['share_acres']))} of acres. Natural ignitions are {q(c, 'cause.by_classification', fmt_pct(bc['Natural']['share_fires']))} of fires and {q(c, 'cause.by_classification', fmt_pct(bc['Natural']['share_acres']))} of acres.
The cause is undetermined for {q(c, 'cause.by_classification', fmt_pct(bc[miss]['share_fires']))} of fires, and that share is never dropped from a chart on this site.</p></header>

{V().calendar_section(ctx)}
<h2>Human, natural, undetermined</h2>
<p>Human fires outnumber natural ones {q(c, 'cause.human_to_natural_fire_ratio', fmt_num(cv(c, 'cause.human_to_natural_fire_ratio'), 1) + ' to 1')}; natural fires burn {q(c, 'cause.natural_acres', fmt_m(cv(c, 'cause.natural_acres')))} acres, most of it in the West and Alaska. The general cause (13 categories) is undetermined for a larger share, {q(c, 'overview.missing_shares', fmt_pct(cv(c, 'overview.missing_shares', 'NWCG_GENERAL_CAUSE_missing_category')))} of records.</p>
{chart_div('cause-national')}
<h3>By region</h3>
{region_html}

<h2>Cause within size class</h2>
<p>Among fires with a known cause, the human share falls with size: {q(c, 'cause.human_share_known_by_size_class', fmt_pct(cv(c, 'cause.human_share_known_by_size_class', 'B'), 0))} in Class B, {q(c, 'cause.human_share_known_by_size_class', fmt_pct(cv(c, 'cause.human_share_known_by_size_class', 'G'), 0))} in Class G. Natural causes are the majority only in Class G ({q(c, 'cause.classification_acre_share_by_size_class', fmt_pct(cv(c, 'cause.classification_acre_share_by_size_class', 'G', 'Natural')))} of Class G acres).</p>
<div class="grid2">{chart_div('cause-size-acres')}{chart_div('human-size')}</div>
<h3>Most common general cause in each size class</h3>
<p>The earlier wording was that Classes B and C are "most often" debris burning. It is the most common single category, but never a majority, and in Class C arson is within 1.2 points. The undetermined category is the most common in Classes A and D.</p>
<div class="table-wrap"><table><thead><tr><th>Size class</th><th>Top general cause</th><th class="num">Share</th><th>Majority?</th><th>Top three</th></tr></thead><tbody>{top_rows}</tbody></table></div>
<p class="small muted">n = {q(c, 'cause.top_general_cause_by_size_class', fmt_int(c['cause.top_general_cause_by_size_class']['n']))} records; {q(c, 'cause.top_general_cause_by_size_class', 'definition')}.</p>
{chart_div('general-cause')}

<h2 id="seasons">Seasonality by region</h2>
<p>Peak month for fires and for acres: South {q(c, 'season.peak_month_by_region', peak['South']['fires'])} and {q(c, 'season.peak_month_by_region', peak['South']['acres'])}; West {q(c, 'season.peak_month_by_region', peak['West']['fires'])} and {q(c, 'season.peak_month_by_region', peak['West']['acres'])}; Alaska {q(c, 'season.peak_month_by_region', peak['Alaska']['fires'])} and {q(c, 'season.peak_month_by_region', peak['Alaska']['acres'])}; Northeast {q(c, 'season.peak_month_by_region', peak['Northeast']['fires'])}; Other (Midwest, Plains) {q(c, 'season.peak_month_by_region', peak['Other']['fires'])}. Nationally, {q(c, 'season.peak_months', cv(c, 'season.peak_months', 'fires'))} has the most fires and the most acres.</p>
{chart_div('season-heat')}
<div class="note"><p><strong>Prevention-calendar reading.</strong> Fires in the South peak in February to April (dormant grass, debris burning), in the West in June to August, in Alaska in May to July. A prevention message timed to the region's own peak reaches people in the weeks that matter; a national campaign timed to the Western summer misses the South's season entirely. Region membership is in the <a href="methods.html#glossary">glossary</a>.</p></div>
<h3>The largest fires move from the South in winter to the West in summer</h3>
<div class="table-wrap"><table><thead><tr>{''.join(f'<th>{m}</th>' for m in MONTHS)}</tr></thead><tbody><tr>{lead_row}</tr></tbody></table></div>
<p class="small muted">Region with the most Class G fires in each month; n = {q(c, 'season.class_g_leading_region_by_month', fmt_int(c['season.class_g_leading_region_by_month']['n']))} Class G fires.</p>
{chart_div('classg-month')}
"""
    return layout(ctx, 'causes.html', 'Seasons and causes · ' + SITE_TITLE, body, CAUSES_JS + V().CAL_JS, extra_scripts=[ctx['calendar_data']] if ctx.get('calendar_data') else [],
                  description='Human, natural and undetermined causes by fires and acres, cause within size class, and seasonality by region.')


# --------------------------------------------------------------------------- geography

GEO_JS = r"""
(function(){
  var C = WF.data.claims, cells = WF.data.cells, MIN = 20;
  var mode = 'n';
  var rows = cells.map(function (c) { return { lat_centroid: c.lat, lon_centroid: c.lon, n_fires: c.n, acres: c.acres, n_human: c.human, n_natural: c.natural, n_missing_cause: c.missing, human_share_known: c.hk, drawn_in_color: c.n >= MIN ? 'yes' : 'no (fewer than ' + MIN + ' fires)' }; });
  var mapChart = WF.chart({ el: 'cell-map', title: '1-degree cells: fires, acres and human share', claims: ['geo.cells_1deg_file', 'geo.cells_1deg_summary'], n: C['geo.cells_1deg_file'].n, mapClass: true,
    sub: 'Each square is a 1 x 1 degree cell drawn at its centroid. Color is the selected measure; cells with fewer than ' + MIN + ' fires are drawn hollow and never colored. Hover for n.',
    controls: WF.segControl([{ label: 'Fires', value: 'n' }, { label: 'Acres', value: 'acres' }, { label: 'Human share of known cause', value: 'hk' }], function (v) { mode = v; mapChart.render(); }),
    legendNote: '<span class="swatch hollow"></span> fewer than ' + MIN + ' fires: outline only, no color · <span class="swatch" style="background:var(--seq-500)"></span> colored cells have at least ' + MIN + ' fires · one hue, darker = more · Puerto Rico cells are in the table, outside the map frame',
    rows: rows, columns: [{ key: 'lat_centroid', label: 'lat (centroid)', num: true }, { key: 'lon_centroid', label: 'lon (centroid)', num: true }, { key: 'n_fires', label: 'fires', num: true, fmt: WF.fmt.int }, { key: 'acres', num: true, fmt: WF.fmt.int }, { key: 'n_human', label: 'human', num: true, fmt: WF.fmt.int }, { key: 'n_natural', label: 'natural', num: true, fmt: WF.fmt.int }, { key: 'n_missing_cause', label: 'undetermined', num: true, fmt: WF.fmt.int }, { key: 'human_share_known', label: 'human share of known', num: true, fmt: function (v) { return WF.fmt.pct(v); } }, { key: 'drawn_in_color', label: 'colored on map' }],
    staticImg: 'figures/cells_1deg_map.png', csvName: 'cells_1deg', height: 520,
    build: function (t) {
      var big = cells.filter(function (c) { return c.n >= MIN; }), small = cells.filter(function (c) { return c.n < MIN; });
      var val, title, tickvals, ticktext, hoverfmt;
      if (mode === 'n') { val = function (c) { return Math.log10(c.n); }; title = 'fires (log scale)'; tickvals = [Math.log10(20), 2, 3, 4]; ticktext = ['20', '100', '1,000', '10,000']; }
      else if (mode === 'acres') { val = function (c) { return Math.log10(Math.max(c.acres, 1)); }; title = 'acres (log scale)'; tickvals = [2, 3, 4, 5, 6]; ticktext = ['100', '1K', '10K', '100K', '1M']; }
      else { val = function (c) { return c.hk === null ? null : 100 * c.hk; }; title = 'human share of known cause'; tickvals = [0, 25, 50, 75, 100]; ticktext = ['0%', '25%', '50%', '75%', '100%']; }
      var hover = function (c) { return c.lat.toFixed(1) + ', ' + c.lon.toFixed(1) + '<br>n = ' + WF.fmt.int(c.n) + ' fires · ' + WF.fmt.int(c.acres) + ' acres<br>human share of known cause ' + (c.hk === null ? 'n/a' : WF.fmt.pct(c.hk, 0)) + ' (known n = ' + WF.fmt.int(c.human + c.natural) + ', undetermined ' + WF.fmt.int(c.missing) + ')'; };
      var data = [
        { type: 'scattergeo', name: 'fewer than ' + MIN + ' fires', lat: small.map(function (c) { return c.lat; }), lon: small.map(function (c) { return c.lon; }), mode: 'markers', marker: { symbol: 'square-open', size: 7, color: t.missing, line: { width: 1.2, color: t.missing } }, text: small.map(hover), hovertemplate: '%{text}<extra>below minimum count</extra>', showlegend: false },
        { type: 'scattergeo', name: title, lat: big.map(function (c) { return c.lat; }), lon: big.map(function (c) { return c.lon; }), mode: 'markers', text: big.map(hover), hovertemplate: '%{text}<extra></extra>', showlegend: false,
          marker: { symbol: 'square', size: 9, color: big.map(val), colorscale: WF.seqScale(t), cmin: tickvals[0], cmax: tickvals[tickvals.length - 1], line: { width: 0.5, color: t.surface },
            colorbar: { title: { text: title, side: 'right' }, thickness: 10, len: 0.6, tickvals: tickvals, ticktext: ticktext, tickfont: { color: t.muted } } } }
      ];
      return { data: data, layout: { geo: { scope: 'usa', projection: { type: 'albers usa' }, bgcolor: 'rgba(0,0,0,0)', showland: true, landcolor: t.surface2 || t.page, showlakes: false, subunitcolor: t.grid, countrycolor: t.axis, showcountries: true, showframe: false, lakecolor: t.page }, margin: { l: 0, r: 0, t: 0, b: 0 }, dragmode: false } };
    }
  });

  var st = C['geo.fires_and_acres_by_state'].value, comp = C['geo.completeness_by_state'] ? C['geo.completeness_by_state'].value : null;
  var srows = Object.keys(st).sort().map(function (s) { var r = { state: s, fires: st[s].fires, share_of_fires: st[s].share_fires, acres: Math.round(st[s].acres), share_of_acres: st[s].share_acres }; if (comp && comp[s]) { r.share_with_cont_date = comp[s].share_cont_date; r.share_known_owner = comp[s].share_known_owner; r.share_known_cause = comp[s].share_known_cause; } return r; });
  var cols = [{ key: 'state' }, { key: 'fires', num: true, fmt: WF.fmt.int }, { key: 'share_of_fires', label: 'share of fires', num: true, fmt: function (v) { return WF.fmt.pct(v, 2); } }, { key: 'acres', num: true, fmt: WF.fmt.int }, { key: 'share_of_acres', label: 'share of acres', num: true, fmt: function (v) { return WF.fmt.pct(v, 2); } }];
  if (comp) cols = cols.concat([{ key: 'share_with_cont_date', label: 'with containment date', num: true, fmt: function (v) { return WF.fmt.pct(v); } }, { key: 'share_known_owner', label: 'with known owner', num: true, fmt: function (v) { return WF.fmt.pct(v); } }, { key: 'share_known_cause', label: 'with known cause', num: true, fmt: function (v) { return WF.fmt.pct(v); } }]);
  var host = document.getElementById('state-table');
  host.appendChild(WF.buildTable(cols, srows, { sortable: true }));
  var b = document.getElementById('state-csv'); b.onclick = function () { WF.downloadCSV('fires_and_acres_by_state', cols, srows, { title: 'Fires and acres by state', definition: C['geo.fires_and_acres_by_state'].definition, claims: ['geo.fires_and_acres_by_state'].concat(comp ? ['geo.completeness_by_state'] : []), n: C['geo.fires_and_acres_by_state'].n }); };
})();
"""


def page_geography(ctx: dict) -> str:
    c = ctx['claims']
    g = cv(c, 'geo.cells_1deg_summary')
    top5a = cv(c, 'geo.top5_states_acres')
    top5f = cv(c, 'geo.top5_states_fires')
    n_pr = sum(1 for r in ctx['cells'] if 17 <= r['lat'] <= 19 and -68 <= r['lon'] <= -65)
    if 'geo.completeness_by_state' in c:
        comp_note = 'Containment-date, known-owner and known-cause shares come from <code>geo.completeness_by_state</code>.'
    else:
        comp_note = ('Share with a containment date and share with a known owner are not yet computed per state (the ledger has them by owner, region and year, on the '
                     '<a href="ownership.html">Ownership</a> page). When a <code>geo.completeness_by_state</code> claim is added to the ledger, those columns appear here automatically.')
    body = f"""
<header class="page-head"><h1>Geography</h1>
<p class="lede">Ignition points aggregated to 1-degree cells. {q(c, 'geo.cells_1deg_summary', fmt_int(g['n_cells']))} cells contain fires; {q(c, 'geo.cells_1deg_summary', fmt_int(g['n_cells_ge_20_fires']))} have at least 20. The 50 busiest cells hold {q(c, 'geo.cells_1deg_summary', fmt_pct(g['share_of_fires_in_top_50_cells']))} of fires; the 50 largest by acreage hold {q(c, 'geo.cells_1deg_summary', fmt_pct(g['share_of_acres_in_top_50_cells_by_acres']))} of acres, and they are different cells.</p></header>
{chart_div('cell-map')}
<p class="small">Cell = floor(LATITUDE), floor(LONGITUDE), drawn at the cell centroid. No coordinates are null. The busiest cell is {q(c, 'geo.cells_1deg_summary', f"{g['top_cell']['cell_lat']:.0f}N {abs(g['top_cell']['cell_lon']):.0f}W")} (South Carolina Piedmont) with {q(c, 'geo.cells_1deg_summary', fmt_int(g['top_cell']['n_fires']))} fires, {q(c, 'geo.cells_1deg_summary', fmt_pct(g['top_cell']['human_share_known'], 0))} human among known causes. Human share among known causes is above 90% across the South and East and drops to 20-50% in the interior West and Alaska.
{n_pr} Puerto Rico cells fall outside the map frame and are in the table and CSV. No kernel-density smoothing is used anywhere on this site: every colored cell is a count you can audit.</p>

<h2 id="states">States</h2>
<p>Most acres: {', '.join(q(c, 'geo.top5_states_acres', f'{k} {fmt_m(v)}') for k, v in sorted(top5a.items(), key=lambda kv: -kv[1]))}. Most fires: {', '.join(q(c, 'geo.top5_states_fires', f'{k} {fmt_int(v)}') for k, v in sorted(top5f.items(), key=lambda kv: -kv[1]))}.
Fire counts by state depend on which years that state's local reporting was included (see <a href="trends.html#counts">why counts are not a trend</a>). {comp_note}</p>
<p><button type="button" class="btn" id="state-csv">Download CSV</button> <span class="small muted">n = {q(c, 'geo.fires_and_acres_by_state', fmt_int(c['geo.fires_and_acres_by_state']['n']))} · {q(c, 'geo.fires_and_acres_by_state', 'definition')} · click a column header to sort</span></p>
<div class="table-wrap" id="state-table"></div>
"""
    return layout(ctx, 'geography.html', 'Geography · ' + SITE_TITLE, body, GEO_JS,
                  description='1-degree cell map of fires, acres and human share, with a sortable state table.')


# --------------------------------------------------------------------------- ownership

OWNER_JS = r"""
(function(){
  var C = WF.data.claims, MISS = 'MISSING/NOT SPECIFIED';
  var ow = C['owner.fires_and_acres'].value, owners = Object.keys(ow);
  var label = function (o) { return o === MISS ? 'Missing / not specified' : o; };
  function ownerBars(id, title, key, shareKey, unit, staticImg) {
    var ord = owners.slice().sort(function (a, b) { return ow[a][key] - ow[b][key]; });
    WF.chart({ el: id, title: title, claims: ['owner.fires_and_acres', key === 'acres' ? 'owner.missing_share_acres' : 'owner.missing_share_fires'],
      sub: 'OWNER_DESCR (upper-cased). The Missing row is the owner recorded as MISSING/NOT SPECIFIED; it is drawn in gray and never removed.',
      rows: ord.slice().reverse().map(function (o) { return { owner: label(o), fires: ow[o].fires, share_of_fires: ow[o].share_fires, acres: Math.round(ow[o].acres), share_of_acres: ow[o].share_acres, _missing: o === MISS }; }),
      columns: [{ key: 'owner' }, { key: 'fires', num: true, fmt: WF.fmt.int }, { key: 'share_of_fires', label: 'share of fires', num: true, fmt: function (v) { return WF.fmt.pct(v, 2); } }, { key: 'acres', num: true, fmt: WF.fmt.int }, { key: 'share_of_acres', label: 'share of acres', num: true, fmt: function (v) { return WF.fmt.pct(v, 2); } }],
      staticImg: staticImg, height: 440,
      build: function (t) { return { data: [{ type: 'bar', orientation: 'h', y: ord.map(label), x: ord.map(function (o) { return ow[o][key]; }), marker: { color: ord.map(function (o) { return o === MISS ? t.missing : t.series[0]; }) },
        customdata: ord.map(function (o) { return 100 * ow[o][shareKey]; }), hovertemplate: '%{y}<br>%{x:,.0f} ' + unit + ' (%{customdata:.1f}% of all)<extra></extra>' }],
        layout: { showlegend: false, bargap: 0.3, margin: { l: 10 }, yaxis: { automargin: true, tickfont: { size: 11 } }, xaxis: { tickformat: '.2s', title: { text: unit } } } }; }
    });
  }
  ownerBars('owner-acres', 'Acres by land owner at the ignition point', 'acres', 'share_acres', 'acres', 'figures/ownership_acres.png');
  ownerBars('owner-fires', 'Fires by land owner at the ignition point', 'fires', 'share_fires', 'fires', null);

  var bc = C['cause.by_classification'].value, base = bc.Human.fires / (bc.Human.fires + bc.Natural.fires);
  var hs = owners.filter(function (o) { return ow[o].n_known_cause >= 1000; }).sort(function (a, b) { return ow[a].human_share_known - ow[b].human_share_known; });
  WF.chart({ el: 'owner-human', title: 'Human share of fires with a known cause, by owner', claims: ['owner.fires_and_acres', 'cause.by_classification'],
    sub: 'Owners with at least 1,000 fires of known cause. The dashed line is the base rate: the human share among all fires with a known cause.',
    rows: hs.slice().reverse().map(function (o) { return { owner: label(o), fires_with_known_cause: ow[o].n_known_cause, human_share_of_known: ow[o].human_share_known, base_rate_all_owners: base, _missing: o === MISS }; }),
    columns: [{ key: 'owner' }, { key: 'fires_with_known_cause', label: 'fires with known cause (n)', num: true, fmt: WF.fmt.int }, { key: 'human_share_of_known', label: 'human share of known', num: true, fmt: function (v) { return WF.fmt.pct(v); } }, { key: 'base_rate_all_owners', label: 'base rate, all owners', num: true, fmt: function (v) { return WF.fmt.pct(v); } }],
    height: 420,
    caption: 'Base rate: ' + WF.fmt.pct(base) + ' of all fires with a known cause are human-caused (n = ' + WF.fmt.int(bc.Human.fires + bc.Natural.fires) + '). Undetermined causes are excluded from this denominator; they are ' + WF.fmt.pct(bc['Missing data/not specified/undetermined'].share_fires) + ' of all fires.',
    build: function (t) { return { data: [{ type: 'bar', orientation: 'h', y: hs.map(label), x: hs.map(function (o) { return 100 * ow[o].human_share_known; }), marker: { color: hs.map(function (o) { return o === MISS ? t.missing : t.series[0]; }) },
        customdata: hs.map(function (o) { return ow[o].n_known_cause; }), hovertemplate: '%{y}<br>%{x:.1f}% human of known cause<br>n = %{customdata:,} fires with known cause<extra></extra>' }],
      layout: { showlegend: false, bargap: 0.3, margin: { l: 10 }, yaxis: { automargin: true, tickfont: { size: 11 } }, xaxis: { ticksuffix: '%', range: [0, 100] },
        shapes: [{ type: 'line', x0: 100 * base, x1: 100 * base, y0: -0.5, y1: hs.length - 0.5, line: { color: t.ink2, width: 1.5, dash: 'dash' } }],
        annotations: [{ x: 100 * base, y: hs.length - 0.5, text: 'base rate ' + WF.fmt.pct(base, 0), showarrow: false, xanchor: 'right', yanchor: 'bottom', font: { size: 11, color: t.ink2 } }] } }; }
  });

  var cs = C['cont.share_with_cont_date_by_owner'].value, co = Object.keys(cs).sort(function (a, b) { return cs[a] - cs[b]; });
  WF.chart({ el: 'cont-share-owner', title: 'Share of records with a containment date, by owner', claims: ['cont.share_with_cont_date_by_owner', 'cont.share_with_cont_date'],
    sub: 'Any containment-time analysis is limited to the records that have a date, which depends on the reporting system.',
    rows: co.slice().reverse().map(function (o) { return { owner: label(o), fires: ow[o] ? ow[o].fires : null, share_with_containment_date: cs[o], _missing: o === MISS }; }),
    columns: [{ key: 'owner' }, { key: 'fires', label: 'fires (n)', num: true, fmt: WF.fmt.int }, { key: 'share_with_containment_date', label: 'share with containment date', num: true, fmt: function (v) { return WF.fmt.pct(v); } }],
    height: 440,
    build: function (t) { return { data: [{ type: 'bar', orientation: 'h', y: co.map(label), x: co.map(function (o) { return 100 * cs[o]; }), marker: { color: co.map(function (o) { return o === MISS ? t.missing : t.series[0]; }) }, customdata: co.map(function (o) { return ow[o] ? ow[o].fires : 0; }), hovertemplate: '%{y}<br>%{x:.1f}% with a containment date<br>n = %{customdata:,} fires<extra></extra>' }],
      layout: { showlegend: false, bargap: 0.3, margin: { l: 10 }, yaxis: { automargin: true, tickfont: { size: 11 } }, xaxis: { ticksuffix: '%', range: [0, 100] } } }; }
  });

  var mh = C['cont.median_hours_by_size_class_and_owner_2010_plus'].value, nn = C['cont.n_by_size_class_and_owner_2010_plus'].value;
  var classes = ['A', 'B', 'C', 'D', 'E', 'F', 'G'], cOwners = ['USFS', 'BLM', 'BIA', 'STATE', 'PRIVATE', MISS];
  var hrows = []; classes.forEach(function (k) { cOwners.forEach(function (o) { hrows.push({ size_class: k, owner: label(o), median_hours_to_containment: mh[k][o], n: nn[k][o], _missing: o === MISS }); }); });
  WF.chart({ el: 'cont-hours', title: 'Median hours from discovery to the containment declaration, by size class and owner', claims: ['cont.median_hours_by_size_class_and_owner_2010_plus', 'cont.n_by_size_class_and_owner_2010_plus', 'cont.n_2010_plus_with_both_datetimes'],
    sub: 'Fires from 2010 on with both a discovery and a containment date-time. Log scale. Hover shows the n behind each point.',
    rows: hrows, columns: [{ key: 'size_class', label: 'size class' }, { key: 'owner' }, { key: 'median_hours_to_containment', label: 'median hours', num: true, fmt: function (v) { return WF.fmt.num(v, 1); } }, { key: 'n', num: true, fmt: WF.fmt.int }],
    staticImg: 'figures/containment_hours_by_class_owner.png', height: 380,
    build: function (t) { return { data: cOwners.map(function (o, i) { var col = o === MISS ? t.missing : t.series[i]; return { type: 'scatter', mode: 'lines+markers', name: label(o), x: classes, y: classes.map(function (k) { return mh[k][o]; }), line: { color: col, width: 2 }, marker: { size: 8, color: col, line: { color: t.surface, width: 2 } }, customdata: classes.map(function (k) { return nn[k][o]; }), hovertemplate: 'Class %{x} · ' + label(o) + '<br>median %{y:.1f} h<br>n = %{customdata:,}<extra></extra>' }; }),
      layout: { yaxis: { type: 'log', title: { text: 'median hours (log)' } }, xaxis: { title: { text: 'size class' } }, legend: { y: -0.25 }, hovermode: 'x unified' } }; }
  });

  var ces = C['ces.by_owner'].value, cOrd = Object.keys(ces).sort(function (a, b) { return ces[b].rank_mean_based - ces[a].rank_mean_based; });
  WF.chart({ el: 'ces-ranks', title: 'Retired Control Efficiency Score: owner rank under the mean against the median', claims: ['ces.by_owner', 'ces.rank_shift', 'ces.spearman_mean_vs_median', 'ces.median_aph_by_size_class'],
    sub: 'Rank 1 = fewest acres per hour to containment. The same data, aggregated two defensible ways, gives two unrelated rankings.',
    rows: cOrd.slice().reverse().map(function (o) { return { owner: label(o), n: ces[o].size, mean_acres_per_hour: ces[o].mean, median_acres_per_hour: ces[o].median, rank_mean_based: ces[o].rank_mean_based, rank_median_based: ces[o].rank_median_based, _missing: o === MISS }; }),
    columns: [{ key: 'owner' }, { key: 'n', num: true, fmt: WF.fmt.int }, { key: 'mean_acres_per_hour', label: 'mean acres/hour', num: true, fmt: function (v) { return WF.fmt.num(v, 2); } }, { key: 'median_acres_per_hour', label: 'median acres/hour', num: true, fmt: function (v) { return WF.fmt.num(v, 3); } }, { key: 'rank_mean_based', label: 'rank (mean)', num: true }, { key: 'rank_median_based', label: 'rank (median)', num: true }],
    height: 440,
    build: function (t) { var y = cOrd.map(label); return { data: [
      { type: 'scatter', mode: 'lines', x: cOrd.reduce(function (a, o) { return a.concat([ces[o].rank_mean_based, ces[o].rank_median_based, null]); }, []), y: cOrd.reduce(function (a, o) { return a.concat([label(o), label(o), null]); }, []), line: { color: t.gray, width: 2 }, hoverinfo: 'skip', showlegend: false },
      { type: 'scatter', mode: 'markers', name: 'Rank, mean-based (original score)', x: cOrd.map(function (o) { return ces[o].rank_mean_based; }), y: y, marker: { size: 10, color: t.seq[2], line: { color: t.surface, width: 2 } }, customdata: cOrd.map(function (o) { return ces[o].size; }), hovertemplate: '%{y}<br>rank %{x} (mean-based)<br>n = %{customdata:,}<extra></extra>' },
      { type: 'scatter', mode: 'markers', name: 'Rank, median-based', x: cOrd.map(function (o) { return ces[o].rank_median_based; }), y: y, marker: { size: 10, color: t.seq[5], line: { color: t.surface, width: 2 } }, customdata: cOrd.map(function (o) { return ces[o].size; }), hovertemplate: '%{y}<br>rank %{x} (median-based)<br>n = %{customdata:,}<extra></extra>' }],
      layout: { margin: { l: 10 }, yaxis: { automargin: true, tickfont: { size: 11 } }, xaxis: { title: { text: 'rank (1 = fewest acres per hour)' }, dtick: 1, range: [0.5, cOrd.length + 0.5] }, legend: { y: -0.15 } } }; }
  });
})();
"""


def page_ownership(ctx: dict) -> str:
    c = ctx['claims']
    ow = cv(c, 'owner.fires_and_acres')
    top4 = cv(c, 'owner.top4_acres')
    ces = cv(c, 'ces.by_owner')
    aph = cv(c, 'ces.median_aph_by_size_class')
    pct = cv(c, 'cont.hours_percentiles_2010_plus')
    mh = cv(c, 'cont.median_hours_by_size_class_and_owner_2010_plus')
    body = f"""
<header class="page-head"><h1>Ownership</h1>
<p class="lede">The owner of the land at the ignition point is recorded for {q(c, 'owner.missing_share_fires', fmt_pct(1 - cv(c, 'owner.missing_share_fires')))} of fires. The Missing row is the fourth-largest owner by acres and the largest by fires, and it stays on every chart.</p></header>

<h2>Acres and fires by owner</h2>
<p>Most acres: {', '.join(q(c, 'owner.top4_acres', f'{("Missing" if k == "MISSING/NOT SPECIFIED" else k)} {fmt_m(v)}') for k, v in sorted(top4.items(), key=lambda kv: -kv[1]))}.
Ownership is missing for {q(c, 'owner.missing_share_fires', fmt_pct(cv(c, 'owner.missing_share_fires')))} of fires and {q(c, 'owner.missing_share_acres', fmt_pct(cv(c, 'owner.missing_share_acres')))} of acres. Owner labels are upper-cased so that the two spellings of "Private" merge.</p>
<div class="grid2">{chart_div('owner-acres')}{chart_div('owner-fires')}</div>

<h2>Human share of known cause by owner</h2>
<p>Federal land agencies burn the most acres from the fewest human ignitions; private and unrecorded land burn less area from mostly human ignitions. Human share of fires with a known cause: BLM {q(c, 'owner.fires_and_acres', fmt_pct(ow['BLM']['human_share_known'], 0))}, USFS {q(c, 'owner.fires_and_acres', fmt_pct(ow['USFS']['human_share_known'], 0))}, NPS {q(c, 'owner.fires_and_acres', fmt_pct(ow['NPS']['human_share_known'], 0))}, FWS {q(c, 'owner.fires_and_acres', fmt_pct(ow['FWS']['human_share_known'], 0))}, BIA {q(c, 'owner.fires_and_acres', fmt_pct(ow['BIA']['human_share_known'], 0))}, State {q(c, 'owner.fires_and_acres', fmt_pct(ow['STATE']['human_share_known'], 0))}, Private {q(c, 'owner.fires_and_acres', fmt_pct(ow['PRIVATE']['human_share_known'], 0))}, Missing {q(c, 'owner.fires_and_acres', fmt_pct(ow['MISSING/NOT SPECIFIED']['human_share_known'], 0))}.</p>
{chart_div('owner-human')}

<h2 id="containment">Time to a containment declaration</h2>
<div class="note"><p><strong>Read this before the chart.</strong> The containment fields record when a reporting system declared the fire contained, under that system's own convention. They do not measure response speed, and they are missing for {q(c, 'overview.missing_shares', fmt_pct(cv(c, 'overview.missing_shares', 'CONT_DATE')))} of all records, unevenly by owner: {q(c, 'cont.share_with_cont_date_by_owner', fmt_pct(cv(c, 'cont.share_with_cont_date_by_owner', 'BLM')))} of BLM records have a containment date, {q(c, 'cont.share_with_cont_date_by_owner', fmt_pct(cv(c, 'cont.share_with_cont_date_by_owner', 'MISSING/NOT SPECIFIED')))} of records with no recorded owner.
A Class A fire is under a quarter of an acre wherever it burns, yet the USFS median is {q(c, 'cont.median_hours_by_size_class_and_owner_2010_plus', fmt_num(mh['A']['USFS'], 1))} hours and the unrecorded-owner median {q(c, 'cont.median_hours_by_size_class_and_owner_2010_plus', fmt_num(mh['A']['MISSING/NOT SPECIFIED'], 1))} hours: that is a difference in what "contained" means to each system, not in the fire.</p></div>
<p>For the {q(c, 'cont.n_2010_plus_with_both_datetimes', fmt_int(cv(c, 'cont.n_2010_plus_with_both_datetimes')))} fires from 2010 on with both a discovery and a containment date-time, the median time to the containment declaration is {q(c, 'cont.hours_percentiles_2010_plus', fmt_num(pct['0.5'], 2))} hours (75th percentile {q(c, 'cont.hours_percentiles_2010_plus', fmt_num(pct['0.75'], 1))}, 90th {q(c, 'cont.hours_percentiles_2010_plus', fmt_num(pct['0.9'], 0))}, 99th {q(c, 'cont.hours_percentiles_2010_plus', fmt_num(pct['0.99'], 0))} hours); {q(c, 'cont.share_zero_hours_2010_plus', fmt_pct(cv(c, 'cont.share_zero_hours_2010_plus')))} are recorded as zero hours.</p>
<div class="grid2">{chart_div('cont-share-owner')}{chart_div('cont-hours')}</div>

<h2 id="ces">The Control Efficiency Score was retired</h2>
<p>The earlier version of this project ranked owners with a Control Efficiency Score, defined as 1 divided by the mean acres burned per hour to containment. It was retired for two reasons that the data shows directly:</p>
<ul class="tight">
<li><strong>The ranking is an artefact of the aggregation.</strong> With the mean, USFS ranks {q(c, 'ces.by_owner', str(ces['USFS']['rank_mean_based']))} of 14 owners; with the median it ranks {q(c, 'ces.by_owner', str(ces['USFS']['rank_median_based']))}. BLM moves from {q(c, 'ces.by_owner', str(ces['BLM']['rank_mean_based']))} to {q(c, 'ces.by_owner', str(ces['BLM']['rank_median_based']))}, Private from {q(c, 'ces.by_owner', str(ces['PRIVATE']['rank_mean_based']))} to {q(c, 'ces.by_owner', str(ces['PRIVATE']['rank_median_based']))}. The Spearman correlation between the two rankings is {q(c, 'ces.spearman_mean_vs_median', fmt_num(cv(c, 'ces.spearman_mean_vs_median'), 2))}: they are unrelated.</li>
<li><strong>The score mostly measures final fire size.</strong> Median acres per hour rise from {q(c, 'ces.median_aph_by_size_class', fmt_num(aph['A'], 2))} in Class A to {q(c, 'ces.median_aph_by_size_class', fmt_num(aph['G'], 1))} in Class G, so an owner's score follows the size mix of its fires and the containment convention of its reporting system, not its response.</li>
</ul>
<p>Neither version measures response quality, and no agency or owner ranking on speed or efficiency appears on this site. The chart below is kept as the record of why.</p>
{chart_div('ces-ranks')}
"""
    return layout(ctx, 'ownership.html', 'Ownership · ' + SITE_TITLE, body, OWNER_JS,
                  description='Acres and fires by land owner including the Missing row, human share by owner, containment declaration times, and why the Control Efficiency Score was retired.')


# --------------------------------------------------------------------------- methods and ledger

METHODS_JS = r"""
(function(){
  var C = WF.data.claims, ids = Object.keys(C).sort();
  var host = document.getElementById('ledger-body'), input = document.getElementById('ledger-search'), count = document.getElementById('ledger-count');
  function short(v) {
    if (v === null || v === undefined) return '';
    if (typeof v === 'number') return Number.isInteger(v) ? WF.fmt.int(v) : (Math.abs(v) < 1 ? v.toPrecision(4) : WF.fmt.num(v, 3));
    if (typeof v === 'string') return v.length > 160 ? v.slice(0, 157) + '...' : v;
    if (Array.isArray(v)) return 'list of ' + v.length;
    return 'object with ' + Object.keys(v).length + ' keys';
  }
  function row(id) {
    var c = C[id], tr = document.createElement('tr'), v = c.value;
    var tdId = document.createElement('td'); tdId.className = 'id'; tdId.textContent = id; tr.appendChild(tdId);
    var tdV = document.createElement('td');
    if (v !== null && typeof v === 'object') {
      var d = document.createElement('details'), s = document.createElement('summary'); s.textContent = short(v); d.appendChild(s);
      var pre = document.createElement('pre'); pre.textContent = JSON.stringify(v, null, 1); d.appendChild(pre); tdV.appendChild(d);
    } else tdV.textContent = short(v);
    tr.appendChild(tdV);
    [c.unit || '', typeof c.n === 'number' ? WF.fmt.int(c.n) : (c.n || ''), c.definition + (c.note ? ' Note: ' + c.note : ''), c.source + ' · ' + c._file + ' · ' + (c.computed_at || '').slice(0, 10)].forEach(function (x, i) { var td = document.createElement('td'); if (i === 1) td.className = 'num'; td.textContent = x; tr.appendChild(td); });
    tr.setAttribute('data-text', (id + ' ' + c.definition + ' ' + (c.note || '') + ' ' + c.source + ' ' + c._file + ' ' + (typeof v === 'string' ? v : '')).toLowerCase());
    return tr;
  }
  ids.forEach(function (id) { host.appendChild(row(id)); });
  // The full ledger is tens of thousands of pixels tall on a phone: show the first rows until the reader searches or asks for all.
  var FIRST = 20, all = false, more = document.getElementById('ledger-all');
  function filter() {
    var qv = (input.value || '').toLowerCase().trim(), n = 0;
    for (var i = 0; i < host.children.length; i++) { var tr = host.children[i]; var show = (!qv || tr.getAttribute('data-text').indexOf(qv) >= 0) && (qv || all || i < FIRST); tr.hidden = !show; if (show) n++; }
    count.textContent = (qv ? n + ' of ' + ids.length : (all ? 'All ' + ids.length : 'First ' + n + ' of ' + ids.length)) + ' claims';
    more.hidden = !!qv || all;
  }
  more.onclick = function () { all = true; filter(); };
  input.addEventListener('input', filter); filter();
  document.getElementById('ledger-csv').onclick = function () {
    var cols = [{ key: 'id' }, { key: 'value' }, { key: 'unit' }, { key: 'n' }, { key: 'definition' }, { key: 'note' }, { key: 'source' }, { key: 'file' }, { key: 'computed_at' }];
    var rows = ids.map(function (id) { var c = C[id]; return { id: id, value: typeof c.value === 'object' ? JSON.stringify(c.value) : c.value, unit: c.unit, n: c.n, definition: c.definition, note: c.note, source: c.source, file: c._file, computed_at: c.computed_at }; });
    WF.downloadCSV('claims_ledger', cols, rows, { title: 'Claims ledger', definition: 'every claim in outputs/claims*.json' });
  };
})();
"""


def page_methods(ctx: dict) -> str:
    c = ctx['claims']
    miss = cv(c, 'overview.missing_counts')
    missing_files = ctx['claims_missing']
    errata = [
        ('A June spike in Class G acreage in Arkansas', 'anom.verdict_arkansas_june', ['anom.arkansas_class_g', 'anom.june_class_g_by_state_top10']),
        ('December fires in Texas as a recurring pattern', 'anom.verdict_texas_december', ['anom.texas_by_month', 'anom.texas_december_top_year']),
        ('A 2010 outlier in the Northeast', 'anom.verdict_northeast_2010', ['anom.northeast_2010', 'anom.northeast_largest_yoy_count_jumps', 'anom.northeast_zero_report_years']),
    ]
    errata_html = ''.join(
        f'<div class="card"><h3>{esc(title)}</h3><p class="small"><strong>What was claimed:</strong> {esc(title)}, in the earlier README.</p>'
        f'<p class="small"><strong>What the check found:</strong> {esc(cv(c, vid))}</p>'
        f'<p class="n">n = {fmt_int(c[vid]["n"])} · {q(c, vid, "definition")} · evidence claims: <code>{esc(" ".join(ev))}</code></p></div>'
        for title, vid, ev in errata)
    extra_errata = f"""
<div class="card"><h3>"Higher highs and higher lows" for Class G acres</h3><p class="small"><strong>What was claimed:</strong> the Class G acreage trend has higher highs and higher lows.</p>
<p class="small"><strong>What the check found:</strong> the upward trend holds (Kendall tau {q(c, 'class_g.acres_trend', fmt_num(cv(c, 'class_g.acres_trend', 'kendall_tau'), 2))}), but 2010 ({q(c, 'class_g.five_lowest_years', fmt_m(cv(c, 'class_g.five_lowest_years', '2010')))} acres) is the fifth-lowest of 29 years, so the lows are not rising.</p>
<p class="n">n = {fmt_int(c['class_g.five_lowest_years']['n'])} · {q(c, 'class_g.five_lowest_years', 'definition')}</p></div>
<div class="card"><h3>Classes B and C are "most often" debris burning</h3><p class="small"><strong>What the check found:</strong> debris and open burning is the most common single general cause in B ({q(c, 'cause.top_general_cause_by_size_class', fmt_pct(cv(c, 'cause.top_general_cause_by_size_class', 'B', 'share')))}) and C ({q(c, 'cause.top_general_cause_by_size_class', fmt_pct(cv(c, 'cause.top_general_cause_by_size_class', 'C', 'share')))}), a plurality and not a majority; in Class C arson is within 1.2 points.</p>
<p class="n">n = {fmt_int(c['cause.top_general_cause_by_size_class']['n'])} · {q(c, 'cause.top_general_cause_by_size_class', 'definition')}</p></div>
<div class="card"><h3>The Control Efficiency Score ranks agencies on response</h3><p class="small"><strong>What the check found:</strong> the ranking flips between the mean-based and median-based versions (Spearman {q(c, 'ces.spearman_mean_vs_median', fmt_num(cv(c, 'ces.spearman_mean_vs_median'), 2))}); the score follows final fire size and reporting convention. Retired; see <a href="ownership.html#ces">Ownership</a>.</p>
<p class="n">n = {fmt_int(c['ces.by_owner']['n'])} · {q(c, 'ces.by_owner', 'definition')}</p></div>
<div class="card"><h3>The duration model "does well on short fires"</h3><p class="small"><strong>What the check found:</strong> the Random Forest reproduces exactly but loses to predicting zero days on mean absolute error (1.38 against 1.09 days); see <a href="model.html">Prediction</a>.</p>
<p class="n">Source: docs/review/REPRODUCTION.md and outputs/reproduction_model.json</p></div>"""
    body = f"""
<header class="page-head"><h1>Methods and ledger</h1>
<p class="lede">Every number on this site is a claim in a JSON ledger produced by the analysis code, with its definition, the number of records behind it and the time it was computed. The site is generated from that ledger; nothing is typed in by hand except the prose.</p></header>

<h2 id="data">Data version</h2>
<div class="table-wrap"><table><tbody>
<tr><th>Dataset</th><td>Short, Karen C. 2022. Spatial wildfire occurrence data for the United States, 1992-2020 [FPA_FOD_20221014]. 6th edition. Forest Service Research Data Archive. <a href="https://doi.org/10.2737/RDS-2013-0009.6">doi:10.2737/RDS-2013-0009.6</a></td></tr>
<tr><th>File</th><td><code>data/FPA_FOD_20221014.sqlite</code>, table <code>Fires</code>; analysed through the typed cache <code>data/fires.parquet</code> with the same rows</td></tr>
<tr><th>SHA-256</th><td><code>{esc(ctx['hash_full'])}</code></td></tr>
<tr><th>Records</th><td>{q(c, 'overview.n_rows', fmt_int(cv(c, 'overview.n_rows')))} rows, FIRE_YEAR {q(c, 'overview.years', str(cv(c, 'overview.years')[0]))} to {q(c, 'overview.years', str(cv(c, 'overview.years')[1]))}; fire sizes from {q(c, 'overview.smallest_fire_acres', str(cv(c, 'overview.smallest_fire_acres')))} to {q(c, 'overview.largest_fire_acres', fmt_int(cv(c, 'overview.largest_fire_acres')))} acres; {q(c, 'overview.total_acres', fmt_m(cv(c, 'overview.total_acres')))} acres in total</td></tr>
<tr><th>What it is</th><td>A compilation of federal, state and local wildfire reports: one row per reported fire with a discovery date, a final size and a point location at least as precise as a PLSS section. Nonfederal records were not available from every state for every year, so counts underrepresent activity in some places and periods.</td></tr>
<tr><th>What it is not</th><td>No perimeters (points only), no prescribed fire, no burn severity, no structures or losses, no weather or fuels.</td></tr>
<tr><th>Missing fields</th><td>Containment date null in {q(c, 'overview.missing_counts', fmt_int(miss['CONT_DATE']))} records; discovery time in {q(c, 'overview.missing_counts', fmt_int(miss['DISCOVERY_TIME']))}; containment time in {q(c, 'overview.missing_counts', fmt_int(miss['CONT_TIME']))}; owner not specified in {q(c, 'overview.missing_counts', fmt_int(miss['OWNER_DESCR_missing_category']))}; general cause undetermined in {q(c, 'overview.missing_counts', fmt_int(miss['NWCG_GENERAL_CAUSE_missing_category']))}; cause classification undetermined in {q(c, 'overview.missing_counts', fmt_int(miss['NWCG_CAUSE_CLASSIFICATION_missing_category']))}; coordinates null in {q(c, 'overview.missing_counts', str(miss['LATITUDE_or_LONGITUDE_null']))}.</td></tr>
<tr><th>Ledger files</th><td>{esc(', '.join(ctx['claims_files']))} ({ctx['n_claims']} claims). {('Not present yet: ' + esc(', '.join(missing_files)) + '.') if missing_files else ''}</td></tr>
</tbody></table></div>

<h2 id="glossary">Glossary</h2>
<dl class="glossary">
<dt>Regions</dt><dd>{esc(cv(c, 'overview.region_definition'))} ({q(c, 'overview.region_definition', 'definition')})</dd>
<dt>Size classes</dt><dd>{esc(cv(c, 'overview.size_class_definition'))}</dd>
<dt>Large fire</dt><dd>On this site, "large" means at least 300 acres (Classes E, F and G), the size at which ICS-209 incident reporting becomes common. The trend claim uses Class G (5,000+ acres) because those fires are captured by every reporting system. MTBS maps burn severity only for fires of at least 1,000 acres in the West and 500 acres in the East, so severity data exists for a subset of "large" fires.</dd>
<dt>Ownership classes</dt><dd>OWNER_DESCR as recorded at the ignition point, upper-cased so the two spellings of "Private" merge: BIA, BLM, BOR, COUNTY, FOREIGN, FWS, MISSING/NOT SPECIFIED, MUNICIPAL/LOCAL, NPS, OTHER FEDERAL, PRIVATE, STATE, STATE OR PRIVATE, TRIBAL, UNDEFINED FEDERAL, USFS. Ownership at the ignition point is not ownership of the area burned.</dd>
<dt>Missing rules</dt><dd>The explicit categories "Missing data/not specified/undetermined" (cause) and "MISSING/NOT SPECIFIED" (owner) are counted as missing; those fields have no nulls. Missing categories are always shown. "Human share of known cause" always excludes the undetermined category from the denominator and says so. Zero-record state-years are reporting gaps, not fire-free years.</dd>
<dt>Month</dt><dd>DISCOVERY_MONTH, the month of the discovery date: a fire counts in the month it was found, not the months it burned.</dd>
<dt>Containment time</dt><dd>DURATION_HOURS = CONT_DATETIME minus DISCOVERY_DATETIME, defined only when both a date and a valid HHMM time exist; DURATION_DAYS = CONT_DATE minus DISCOVERY_DATE in whole days. Both measure a containment declaration under the reporting system's convention, not response speed.</dd>
<dt>Trend tests</dt><dd>Kendall tau and the Theil-Sen slope on 29 annual points, plain p-values with no serial-correlation adjustment; the 95% interval is the Theil-Sen slope interval.</dd>
<dt>1-degree cells</dt><dd>{esc(c['geo.cells_1deg_file']['definition'])}</dd>
<dt>GACC approximation</dt><dd>{esc(cv(c, 'overview.gacc_definition'))} {esc(c['overview.gacc_definition']['note'] or '')}</dd>
</dl>

<h2 id="ledger">Claims ledger</h2>
<p>Search by id, definition or source. Object values expand in place. <button type="button" class="btn" id="ledger-csv">Download CSV</button></p>
<p><input class="search" id="ledger-search" type="search" placeholder="Search claims, e.g. class_g or containment" aria-label="Search claims"> <span class="small muted" id="ledger-count"></span> <button type="button" class="btn" id="ledger-all">Show all claims</button></p>
<div class="table-wrap"><table class="ledger"><thead><tr><th>id</th><th>value</th><th>unit</th><th class="num">n</th><th>definition</th><th>source</th></tr></thead><tbody id="ledger-body"></tbody></table></div>

{V().downloads_section(ctx)}
<h2 id="audit">Audit of the first public site</h2>
<p>The first public version of this project was rebuilt from its sources and re-tested; <a href="audit.html">what held and what changed</a>.</p>
<h2 id="errata">Errata</h2>
<p>Claims from the earlier version of this project that did not survive the check, kept next to what the check found.</p>
<div class="cards">{errata_html}{extra_errata}</div>

<h2 id="docs">Repository documents</h2>
<ul class="tight">
<li><a href="{DOCS_URL}/findings/descriptive.md">docs/findings/descriptive.md</a>: verdicts on every descriptive claim, with claim ids</li>
<li><a href="{DOCS_URL}/review/REPRODUCTION.md">docs/review/REPRODUCTION.md</a>: the Phase 0 reproduction of every earlier README number</li>
<li><a href="{DOCS_URL}/review">docs/review/</a>: the adversarial panel reviews (fire science, conservation, responsible AI, machine learning, reproducibility)</li>
<li><a href="{DOCS_URL}/DATA_VERSION.md">docs/DATA_VERSION.md</a> and <a href="{DOCS_URL}/EXPERIMENTS.md">docs/EXPERIMENTS.md</a></li>
<li><a href="{DOCS_URL}/SITE.md">docs/SITE.md</a>: how this site is generated and the rules its pages follow</li>
<li><a href="{REPO_URL}/blob/main/analysis/descriptive.py">analysis/descriptive.py</a>: the code that writes the ledger; <a href="{REPO_URL}/blob/main/scripts/build_site.py">scripts/build_site.py</a>: the code that writes this site</li>
</ul>
<h3>Static figures</h3>
<p class="small muted">Rendered by analysis/figures.py from the same ledger; the interactive charts above are the primary view.</p>
<div class="cards">{''.join(f'<figure><a href="figures/{esc(f)}"><img src="figures/{esc(f)}" alt="{esc(f.replace("_", " ").replace(".png", ""))}" loading="lazy"></a><figcaption>{esc(f)}</figcaption></figure>' for f in ctx['figures'])}</div>
"""
    return layout(ctx, 'methods.html', 'Data and methods · ' + SITE_TITLE, body, METHODS_JS,
                  description='Data version and hash, definitions glossary, the searchable claims ledger and the errata.')


# --------------------------------------------------------------------------- conservation

CONS_JS = r"""
(function(){
  var C = WF.data.claims, MISS = 'Missing data/not specified/undetermined';
  var LAB = { 'Human': 'Human', 'Natural': 'Natural', 'Missing data/not specified/undetermined': 'Undetermined / missing' };
  var GAPS = ['1', '2', '3', '4', 'none', 'unmatched'], GLAB = { '1': 'GAP 1', '2': 'GAP 2', '3': 'GAP 3', '4': 'GAP 4', 'none': 'not in PAD-US', 'unmatched': 'unmatched (PR, offshore)' };
  function gapColor(t, g) { if (g === 'none') return t.missing; if (g === 'unmatched') return t.gray; return t.seq[[6, 5, 3, 1]['1234'.indexOf(g)]]; }

  var nm = C['coverage.national_fires_by_year_all_vs_masked'];
  if (nm) {
    var v = nm.value, ys = WF.years(v);
    WF.chart({ el: 'cov-masked', title: 'Fires per year: all state-years against usable state-years only', claims: ['coverage.national_fires_by_year_all_vs_masked', 'coverage.rule', 'coverage.share_records_in_usable_window'],
      sub: 'Usable = inside the state\'s usable window (no reporting break). Hover shows how many states contribute; the masked series is not a national series either.',
      rows: ys.map(function (y) { return { year: y, all_states: v[y].all_states, usable_state_years_only: v[y].usable_state_years_only, n_states_usable: v[y].n_states_usable }; }),
      columns: [{ key: 'year' }, { key: 'all_states', label: 'all state-years', num: true, fmt: WF.fmt.int }, { key: 'usable_state_years_only', label: 'usable state-years only', num: true, fmt: WF.fmt.int }, { key: 'n_states_usable', label: 'states usable', num: true }], height: 300,
      build: function (t) { return { data: [
        { type: 'scatter', mode: 'lines+markers', name: 'All state-years', x: ys, y: ys.map(function (y) { return v[y].all_states; }), line: { color: t.gray, width: 2 }, marker: { size: 6, color: t.gray, line: { color: t.surface, width: 2 } }, hovertemplate: '%{x}: %{y:,} fires (all)<extra></extra>' },
        { type: 'scatter', mode: 'lines+markers', name: 'Usable state-years only', x: ys, y: ys.map(function (y) { return v[y].usable_state_years_only; }), line: { color: t.series[0], width: 2 }, marker: { size: 6, color: t.series[0], line: { color: t.surface, width: 2 } }, customdata: ys.map(function (y) { return v[y].n_states_usable; }), hovertemplate: '%{x}: %{y:,} fires from %{customdata} usable states<extra></extra>' }],
        layout: { yaxis: { rangemode: 'tozero', tickformat: ',' }, hovermode: 'x unified', legend: { y: -0.22 } } }; }
    });
  }

  var bg = C['padus.by_gap_all_years'];
  if (bg) {
    var g = bg.value, gaps = GAPS.filter(function (k) { return g[k]; });
    var totF = gaps.reduce(function (s, k) { return s + g[k].fires; }, 0), totF300 = gaps.reduce(function (s, k) { return s + g[k].fires_ge_300; }, 0);
    var rows = gaps.map(function (k) { return { gap: GLAB[k], fires: g[k].fires, share_of_fires: g[k].share_fires, acres: Math.round(g[k].acres), share_of_acres: g[k].share_acres, fires_ge_300: g[k].fires_ge_300, share_ge_300_within_gap: g[k].share_ge_300_within_gap, n_known_cause: g[k].n_known_cause, human_share_known_cause: g[k].human_share_known_cause, _missing: k === 'none' || k === 'unmatched' }; });
    var cols = [{ key: 'gap', label: 'GAP status at ignition point' }, { key: 'fires', num: true, fmt: WF.fmt.int }, { key: 'share_of_fires', label: 'share of fires', num: true, fmt: function (x) { return WF.fmt.pct(x, 2); } }, { key: 'acres', num: true, fmt: WF.fmt.int }, { key: 'share_of_acres', label: 'share of acres', num: true, fmt: function (x) { return WF.fmt.pct(x, 2); } }, { key: 'fires_ge_300', label: 'fires >= 300 acres', num: true, fmt: WF.fmt.int }, { key: 'share_ge_300_within_gap', label: 'share >= 300 acres within group', num: true, fmt: function (x) { return WF.fmt.pct(x, 2); } }, { key: 'n_known_cause', label: 'fires with known cause', num: true, fmt: WF.fmt.int }, { key: 'human_share_known_cause', label: 'human share of known cause', num: true, fmt: function (x) { return WF.fmt.pct(x); } }];
    WF.chart({ el: 'gap-shares', title: 'Ignitions and acres by GAP status of the land at the ignition point, 1992-2020', claims: ['padus.by_gap_all_years', 'padus.join_definition', 'padus.source'],
      sub: 'GAP 1 is the most protected, GAP 4 the least; "not in PAD-US" is mostly private land. Gray rows are not protected-area categories.',
      rows: rows, columns: cols, staticImg: 'figures/padus_gap_by_block.png', height: 300,
      build: function (t) { return { data: [
        { type: 'bar', name: 'Share of fires', x: gaps.map(function (k) { return GLAB[k]; }), y: gaps.map(function (k) { return 100 * g[k].share_fires; }), marker: { color: t.series[0] }, customdata: gaps.map(function (k) { return g[k].fires; }), hovertemplate: '%{x}<br>%{y:.1f}% of fires (n = %{customdata:,})<extra></extra>' },
        { type: 'bar', name: 'Share of acres', x: gaps.map(function (k) { return GLAB[k]; }), y: gaps.map(function (k) { return 100 * g[k].share_acres; }), marker: { color: t.series[1] }, customdata: gaps.map(function (k) { return Math.round(g[k].acres); }), hovertemplate: '%{x}<br>%{y:.1f}% of acres (%{customdata:,} acres)<extra></extra>' }],
        layout: { barmode: 'group', yaxis: { ticksuffix: '%' }, legend: { y: -0.3 } } }; }
    });
    var base300 = totF300 / totF, bc = C['cause.by_classification'] ? C['cause.by_classification'].value : null, baseH = bc ? bc.Human.fires / (bc.Human.fires + bc.Natural.fires) : null;
    WF.chart({ el: 'gap-rates', title: 'Within each GAP group: share of ignitions reaching 300 acres, and human share of known cause', claims: ['padus.by_gap_all_years', 'conservation.large_fire_definition'],
      sub: 'Dashed lines are the base rates over all ignitions. Hover shows the n behind each bar.',
      rows: rows, columns: cols, height: 320,
      caption: 'Base rates: ' + WF.fmt.pct(base300, 2) + ' of all ' + WF.fmt.int(totF) + ' ignitions reached 300 acres' + (baseH !== null ? '; ' + WF.fmt.pct(baseH) + ' of fires with a known cause are human-caused' : '') + '.',
      build: function (t) { var x = gaps.map(function (k) { return GLAB[k]; }); return { data: [
        { type: 'bar', name: 'Share reaching 300 acres', x: x, y: gaps.map(function (k) { return 100 * g[k].share_ge_300_within_gap; }), marker: { color: t.series[0] }, customdata: gaps.map(function (k) { return [g[k].fires_ge_300, g[k].fires]; }), hovertemplate: '%{x}<br>%{y:.2f}% reached 300 acres (%{customdata[0]:,} of %{customdata[1]:,})<extra></extra>', xaxis: 'x', yaxis: 'y' },
        { type: 'bar', name: 'Human share of known cause', x: x, y: gaps.map(function (k) { return 100 * g[k].human_share_known_cause; }), marker: { color: t.series[1] }, customdata: gaps.map(function (k) { return g[k].n_known_cause; }), hovertemplate: '%{x}<br>%{y:.1f}% human (known-cause n = %{customdata:,})<extra></extra>', xaxis: 'x2', yaxis: 'y2' }],
        layout: { grid: { rows: 1, columns: 2, pattern: 'independent' }, showlegend: false, yaxis: { title: { text: '% reaching 300 acres' }, ticksuffix: '%' }, yaxis2: { title: { text: '% human of known cause' }, ticksuffix: '%', range: [0, 100], gridcolor: t.grid }, xaxis: { tickfont: { size: 10 } }, xaxis2: { tickfont: { size: 10 } },
          shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 0.45, y0: 100 * base300, y1: 100 * base300, yref: 'y', line: { color: t.ink2, width: 1.5, dash: 'dash' } }].concat(baseH !== null ? [{ type: 'line', xref: 'paper', x0: 0.55, x1: 1, y0: 100 * baseH, y1: 100 * baseH, yref: 'y2', line: { color: t.ink2, width: 1.5, dash: 'dash' } }] : []),
          annotations: [{ xref: 'paper', x: 0.45, yref: 'y', y: 100 * base300, text: 'base rate ' + WF.fmt.pct(base300, 2), showarrow: false, xanchor: 'right', yanchor: 'bottom', font: { size: 10, color: t.ink2 } }].concat(baseH !== null ? [{ xref: 'paper', x: 1, yref: 'y2', y: 100 * baseH, text: 'base rate ' + WF.fmt.pct(baseH, 0), showarrow: false, xanchor: 'right', yanchor: 'bottom', font: { size: 10, color: t.ink2 } }] : []) } }; }
    });
  }
  var fb = C['padus.share_fires_by_block_gap'];
  if (fb) {
    var sb = fb.value, nb = C['padus.fires_by_block_gap'].value, blocks = Object.keys(sb);
    var brows = []; blocks.forEach(function (b) { GAPS.forEach(function (k) { if (sb[b][k] !== undefined) brows.push({ block: b, gap: GLAB[k], fires: nb[b][k], share_of_block: sb[b][k], _missing: k === 'none' || k === 'unmatched' }); }); });
    WF.chart({ el: 'gap-blocks', title: 'Share of ignitions by GAP status, by 5-year block', claims: ['padus.share_fires_by_block_gap', 'padus.fires_by_block_gap'],
      sub: 'Each bar sums to 100% of the block\'s ignitions. GAP 1-4 in one hue (darker = more protected); not in PAD-US and unmatched in gray.',
      rows: brows, columns: [{ key: 'block' }, { key: 'gap' }, { key: 'fires', num: true, fmt: WF.fmt.int }, { key: 'share_of_block', label: 'share of block', num: true, fmt: function (x) { return WF.fmt.pct(x, 2); } }], height: 320,
      build: function (t) { return { data: GAPS.map(function (k) { return { type: 'bar', name: GLAB[k], x: blocks, y: blocks.map(function (b) { return 100 * (sb[b][k] || 0); }), marker: { color: gapColor(t, k), line: { color: t.surface, width: 2 } }, customdata: blocks.map(function (b) { return nb[b][k] || 0; }), hovertemplate: '%{x} · ' + GLAB[k] + ': %{y:.2f}% (n = %{customdata:,})<extra></extra>' }; }),
        layout: { barmode: 'stack', yaxis: { ticksuffix: '%', range: [0, 100] }, legend: { y: -0.3 } } }; }
    });
  }
  var mo = C['padus.missing_owner_assignment_all_years'];
  if (mo) {
    var m = mo.value, keys = Object.keys(m).sort(function (a, b) { return m[a].fires - m[b].fires; });
    var MT = { FED: 'Federal', STAT: 'State', LOC: 'Local', DIST: 'District', NGO: 'NGO', PVT: 'Private (in PAD-US)', TRIB: 'Tribal', JNT: 'Joint', UNK: 'Unknown', 'Not in PAD-US': 'Not in PAD-US (mostly private)', unmatched: 'unmatched' };
    WF.chart({ el: 'missing-owner', title: 'Where the fires with no recorded owner fall: PAD-US manager type at the ignition point', claims: ['padus.missing_owner_assignment_all_years'],
      sub: 'Records with OWNER_DESCR = MISSING/NOT SPECIFIED, all years. The spatial join recovers a manager type for the share that falls inside a PAD-US unit.',
      rows: keys.slice().reverse().map(function (k) { return { manager_type: MT[k] || k, fires: m[k].fires, share_of_missing_owner_fires: m[k].share_fires, acres: Math.round(m[k].acres), share_of_missing_owner_acres: m[k].share_acres }; }),
      columns: [{ key: 'manager_type', label: 'PAD-US manager type' }, { key: 'fires', num: true, fmt: WF.fmt.int }, { key: 'share_of_missing_owner_fires', label: 'share of missing-owner fires', num: true, fmt: function (x) { return WF.fmt.pct(x, 2); } }, { key: 'acres', num: true, fmt: WF.fmt.int }, { key: 'share_of_missing_owner_acres', label: 'share of missing-owner acres', num: true, fmt: function (x) { return WF.fmt.pct(x, 2); } }], height: 360,
      build: function (t) { return { data: [{ type: 'bar', orientation: 'h', y: keys.map(function (k) { return MT[k] || k; }), x: keys.map(function (k) { return 100 * m[k].share_fires; }), marker: { color: t.series[0] }, customdata: keys.map(function (k) { return m[k].fires; }), hovertemplate: '%{y}<br>%{x:.2f}% of missing-owner fires (n = %{customdata:,})<extra></extra>' }],
        layout: { showlegend: false, margin: { l: 10 }, yaxis: { automargin: true, tickfont: { size: 11 } }, xaxis: { ticksuffix: '%' } } }; }
    });
  }

  var mr = C['ics.match_rate_by_size_class_2010_2020'];
  if (mr) {
    var r = mr.value, cl = Object.keys(r).sort();
    WF.chart({ el: 'ics-match', title: 'Share of fires with a matched ICS-209-PLUS incident report, by size class, 2010-2020', claims: ['ics.match_rate_by_size_class_2010_2020', 'ics.fod_rows_matched'],
      sub: 'Incident reports (structures, evacuations, personnel) exist mainly for fires of 300 acres and more.',
      rows: cl.map(function (k) { return { size_class: k, fires: r[k].fires, matched: r[k].matched, share_matched: r[k].share_matched }; }),
      columns: [{ key: 'size_class', label: 'size class' }, { key: 'fires', num: true, fmt: WF.fmt.int }, { key: 'matched', num: true, fmt: WF.fmt.int }, { key: 'share_matched', label: 'share matched', num: true, fmt: function (x) { return WF.fmt.pct(x); } }], height: 260,
      build: function (t) { return { data: [{ type: 'bar', x: cl, y: cl.map(function (k) { return 100 * r[k].share_matched; }), marker: { color: t.series[0] }, text: cl.map(function (k) { return (100 * r[k].share_matched).toFixed(1) + '%'; }), textposition: 'outside', textfont: { color: t.ink2 }, customdata: cl.map(function (k) { return [r[k].matched, r[k].fires]; }), hovertemplate: 'Class %{x}<br>%{y:.1f}% matched (%{customdata[0]:,} of %{customdata[1]:,})<extra></extra>' }],
        layout: { showlegend: false, yaxis: { ticksuffix: '%', range: [0, 105] }, xaxis: { title: { text: 'size class' } } } }; }
    });
  }
  var sr = C['ics.structures_destroyed_by_region_cause'];
  if (sr) {
    var sv = sr.value, regs = ['West', 'South', 'Other', 'Alaska', 'Northeast', 'Hawaii/PR'].filter(function (k) { return sv[k]; });
    var causes = ['Human', 'Natural', MISS];
    var srows = []; regs.forEach(function (rg) { causes.forEach(function (c) { srows.push({ region: rg, cause: LAB[c], structures_destroyed: Math.round(sv[rg][c]), _missing: c === MISS }); }); });
    WF.chart({ el: 'ics-structures', title: 'Structures destroyed by region and cause classification of the largest joined fire', claims: ['ics.structures_destroyed_by_region_cause', 'ics.sample_definition'],
      sub: 'ICS-209-PLUS incidents joined to FPA FOD, 2010-2020, fires of 300 acres and more. Cause is the FPA FOD classification.',
      rows: srows, columns: [{ key: 'region' }, { key: 'cause' }, { key: 'structures_destroyed', label: 'structures destroyed', num: true, fmt: WF.fmt.int }], staticImg: 'figures/ics_structures_by_year_cause.png', height: 320,
      build: function (t) { return { data: causes.map(function (c) { return { type: 'bar', name: LAB[c], x: regs, y: regs.map(function (rg) { return sv[rg][c]; }), marker: { color: WF.causeColor(t, c), line: { color: t.surface, width: 2 } }, hovertemplate: '%{x} · ' + LAB[c] + ': %{y:,.0f} structures<extra></extra>' }; }),
        layout: { barmode: 'stack', yaxis: { tickformat: ',' }, legend: { y: -0.25 } } }; }
    });
  }
})();
"""


def page_conservation(ctx: dict) -> str:
    c = ctx['claims']
    if 'padus.by_gap_all_years' not in c and 'ics.outcomes_by_cause' not in c:
        body = f"""
<header class="page-head"><h1>Conservation</h1>
<p class="lede">Not rendered: <code>outputs/claims_conservation.json</code> is not present. When it is, this page shows the PAD-US protected-area join (ignitions by GAP status, where the missing-owner fires fall), the ICS-209-PLUS outcomes join (structures, evacuations, personnel for fires of 300 acres and more) and the reporting-coverage mask.</p></header>
{placeholder('Conservation joins', 'Run <code>python -m analysis.conservation --out outputs/</code> and rebuild the site. Contract in <a href="' + DOCS_URL + '/SITE.md">docs/SITE.md</a>.')}
"""
        return layout(ctx, 'conservation.html', 'Protected lands and losses · ' + SITE_TITLE, body)

    def has(cid):
        return cid in c

    ms = cv(c, 'padus.match_summary') if has('padus.match_summary') else None
    g = cv(c, 'padus.by_gap_all_years') if has('padus.by_gap_all_years') else None
    oc = cv(c, 'ics.outcomes_by_cause') if has('ics.outcomes_by_cause') else None
    ot = cv(c, 'ics.outcomes_total') if has('ics.outcomes_total') else None
    sd = cv(c, 'ics.structures_destroyed_distribution') if has('ics.structures_destroyed_distribution') else None
    miss = 'Missing data/not specified/undetermined'

    cov_html = ''
    if has('coverage.share_records_in_usable_window'):
        wl = cv(c, 'coverage.window_length_years')
        cov_html = f"""
<h2 id="coverage">Reporting coverage mask</h2>
<p>A state-year is usable when it lies inside the state's longest run of years without a reporting break (rule: {q(c, 'coverage.rule', 'count more than 3x or less than a third of the prior non-zero year')}).
{q(c, 'coverage.n_states_with_break', str(cv(c, 'coverage.n_states_with_break')))} of {q(c, 'coverage.n_states', str(cv(c, 'coverage.n_states')))} states have at least one break; {q(c, 'coverage.window_length_years', str(wl['n_states_full_29']))} have a full 29-year window and {q(c, 'coverage.window_length_years', str(wl['n_states_lt_10']))} have fewer than 10 usable years.
{q(c, 'coverage.share_records_in_usable_window', fmt_pct(cv(c, 'coverage.share_records_in_usable_window')))} of records and {q(c, 'coverage.share_acres_in_usable_window', fmt_pct(cv(c, 'coverage.share_acres_in_usable_window')))} of acres fall inside a usable window. The state-by-year heatmap is on the <a href="trends.html#coverage">Trends page</a>.</p>
{chart_div('cov-masked')}"""

    padus_html = ''
    if g and ms:
        oa = cv(c, 'padus.owner_agreement_by_class') if has('padus.owner_agreement_by_class') else {}
        oa_rows = ''.join(f'<tr><td>{esc(k)}</td><td class="num">{q(c, "padus.owner_agreement_by_class", fmt_pct(v))}</td></tr>' for k, v in sorted(oa.items(), key=lambda kv: -kv[1]))
        padus_html = f"""
<h2 id="padus">Protected land: the PAD-US join</h2>
<p>Every ignition point was joined to the PAD-US 4.1 protected-areas layer ({q(c, 'padus.n_points', fmt_int(cv(c, 'padus.n_points')))} points): {q(c, 'padus.match_summary', fmt_int(ms['in_padus_unit']))} fall inside a PAD-US unit, {q(c, 'padus.match_summary', fmt_int(ms['non_padus_area']))} in the non-PAD-US area (predominantly private land) and {q(c, 'padus.match_summary', fmt_int(ms['unmatched']))} in no polygon ({fmt_int(ms['unmatched_by_state'].get('PR', 0))} of them in Puerto Rico, which the layer does not cover).
GAP status runs from 1 (managed for biodiversity, disturbance events allowed to proceed) to 4 (no known mandate for protection). {q(c, 'padus.join_definition', 'Join method')}; {q(c, 'padus.source', 'layer source')}.</p>
{chart_div('gap-shares')}
{chart_div('gap-rates')}
{chart_div('gap-blocks')}
<h3>Recovering the missing owner</h3>
<p>{q(c, 'padus.missing_owner_assignment_all_years', fmt_int(c['padus.missing_owner_assignment_all_years']['n']))} records have no recorded owner. The spatial join says where they are: {q(c, 'padus.missing_owner_assignment_all_years', fmt_pct(cv(c, 'padus.missing_owner_assignment_all_years', 'Not in PAD-US', 'share_fires')))} fall outside any PAD-US unit, which is mostly private land.
Where an owner is recorded, it agrees with the PAD-US manager type for {q(c, 'padus.owner_agreement_overall', fmt_pct(cv(c, 'padus.owner_agreement_overall')))} of records (n = {q(c, 'padus.owner_agreement_overall', fmt_int(c['padus.owner_agreement_overall']['n']))}), with the agreement rule per class in the definition.</p>
{chart_div('missing-owner')}
<div class="table-wrap"><table><thead><tr><th>Owner class (FPA FOD)</th><th class="num">Agreement with PAD-US manager type</th></tr></thead><tbody>{oa_rows}</tbody></table></div>
<p class="small muted">{q(c, 'padus.owner_agreement_by_class', 'definition')}; {esc(cv(c, 'conservation.owner_class_definition')) if has('conservation.owner_class_definition') else ''}</p>"""

    ics_html = ''
    if oc and ot:
        def orow(label, d, cid, missing=False):
            return (f'<tr{" class=\"missing-row\"" if missing else ""}><td>{esc(label)}</td><td class="num">{q(c, cid, fmt_int(d["incidents"]))}</td>'
                    f'<td class="num">{q(c, cid, fmt_int(d["structures_destroyed"]))}</td><td class="num">{q(c, cid, fmt_pct(d["share_incidents_with_structures_destroyed"]))}</td>'
                    f'<td class="num">{q(c, cid, fmt_num(d["structures_destroyed_per_1000_acres"], 2))}</td><td class="num">{q(c, cid, fmt_int(d["evacuation_reported_incidents"]))}</td>'
                    f'<td class="num">{q(c, cid, fmt_int(d["fatalities"]))}</td><td class="num">{q(c, cid, fmt_m(d["fod_acres"]))}</td></tr>')
        rows = orow('Human', oc['Human'], 'ics.outcomes_by_cause') + orow('Natural', oc['Natural'], 'ics.outcomes_by_cause') + orow('Undetermined / missing', oc[miss], 'ics.outcomes_by_cause', True) + orow('All incidents (base rate)', ot, 'ics.outcomes_total')
        ics_html = f"""
<h2 id="ics">Outcomes: the ICS-209-PLUS join</h2>
<p>The FPA FOD has no losses. ICS-209-PLUS, the compiled incident-status reports, does: {q(c, 'ics.fod_rows_matched', fmt_int(cv(c, 'ics.fod_rows_matched')))} FPA FOD records match one of {q(c, 'ics.n_incidents', fmt_int(cv(c, 'ics.n_incidents')))} incidents, and matching is common only for fires of 300 acres and more. The outcome sample is {q(c, 'ics.sample_n', fmt_int(cv(c, 'ics.sample_n')))} incidents ({q(c, 'ics.sample_definition', 'definition')}).
Cause agrees between the two sources for {q(c, 'ics.cause_agreement_share', fmt_pct(cv(c, 'ics.cause_agreement_share')))} of incidents where both record one.</p>
{chart_div('ics-match')}
<h3>Outcomes by cause classification</h3>
<div class="table-wrap"><table><thead><tr><th>Cause</th><th class="num">Incidents</th><th class="num">Structures destroyed</th><th class="num">Incidents with any structure destroyed</th><th class="num">Structures per 1,000 acres</th><th class="num">Incidents reporting evacuation</th><th class="num">Fatalities</th><th class="num">FPA FOD acres</th></tr></thead><tbody>{rows}</tbody></table></div>
<p class="small muted">n = {q(c, 'ics.outcomes_by_cause', fmt_int(c['ics.outcomes_by_cause']['n']))} incidents. {esc(c['ics.outcomes_total']['note'] or '')}
Losses are concentrated: {q(c, 'ics.structures_destroyed_distribution', fmt_pct(sd['share_zero']))} of incidents destroyed no structure and the ten largest incidents hold {q(c, 'ics.structures_destroyed_distribution', fmt_pct(sd['share_of_total_in_top_10_incidents']))} of all structures destroyed.</p>
{chart_div('ics-structures')}"""

    body = f"""
<header class="page-head"><h1>Conservation</h1>
<p class="lede">The ignition record on its own cannot say what burned or what was lost. Two joins add that: PAD-US 4.1 for the protection status of the land at the ignition point, and ICS-209-PLUS incident reports for structures, evacuations and personnel on the larger fires. Both are joins to points, not to burned areas, and both say so.</p></header>
{cov_html}
{padus_html}
{ics_html}
<h2>What these joins do not do</h2>
<p>They attach attributes to the ignition point. A fire that started on private land and burned into a wilderness area is counted as private-land ignition here; area actually burned inside protected units needs fire perimeters (MTBS), which are not yet joined. ICS-209 reports exist for a minority of fires and are filed by incident teams under time pressure, so the outcome fields are incomplete (fill rates are in the ledger, <code>ics.field_fill_rates_sample</code>).</p>
"""
    return layout(ctx, 'conservation.html', 'Protected lands and losses · ' + SITE_TITLE, body, CONS_JS,
                  description='Ignitions by protected-area status (PAD-US), where the missing-owner fires fall, and losses from ICS-209-PLUS incident reports.')


# --------------------------------------------------------------------------- prediction

MODEL_JS = r"""
(function(){
  var C = WF.data.claims, has = function (id) { return !!C[id]; };
  if (!has('model.metrics')) return;
  var card = has('model.card') ? C['model.card'].value : {};
  var m = C['model.metrics'].value, names = m.metric_names || Object.keys((m.rows[0] || {}).metrics || {});
  var cols = [{ key: 'model' }, { key: 'kind' }].concat(names.map(function (k) { return { key: k, label: k + ' [95% interval]' }; }));
  var rows = m.rows.map(function (r) { var o = { model: r.model, kind: r.baseline ? 'baseline' : 'model' }; names.forEach(function (k) { var v = r.metrics[k]; o[k] = v ? (WF.fmt.num(v[0], 3) + ' [' + WF.fmt.num(v[1], 3) + ', ' + WF.fmt.num(v[2], 3) + ']') : ''; }); return o; });
  var host = document.getElementById('model-metrics'); host.appendChild(WF.buildTable(cols, rows));
  if (has('model.capture_at_top')) {
    var cap = C['model.capture_at_top'].value.rows, capHost = document.getElementById('model-capture');
    var pc = function (v) { return WF.fmt.pct(v, 0); };
    capHost.appendChild(WF.buildTable([{ key: 'model' }, { key: 'top_1pct', label: 'top 1% of scores', num: true, fmt: pc }, { key: 'top_5pct', label: 'top 5%', num: true, fmt: pc }, { key: 'top_10pct', label: 'top 10%', num: true, fmt: pc }, { key: 'top_20pct', label: 'top 20%', num: true, fmt: pc }],
      cap.map(function (r) { return { model: r.model + (r.baseline ? '' : ' (this model)'), top_1pct: r.top_1pct, top_5pct: r.top_5pct, top_10pct: r.top_10pct, top_20pct: r.top_20pct, _missing: /random/.test(r.model) }; })));
    var cp = document.createElement('p'); cp.className = 'small muted'; cp.textContent = 'n = ' + WF.fmt.int(C['model.capture_at_top'].n) + ' holdout fires, of which the share that reached 300 acres is the base rate. ' + C['model.capture_at_top'].definition + '. ' + (C['model.capture_at_top'].note || ''); capHost.appendChild(cp);
  }
  var p = document.createElement('p'); p.className = 'small muted'; p.textContent = 'n = ' + WF.fmt.int(C['model.metrics'].n) + ' test fires · ' + C['model.metrics'].definition + (C['model.metrics'].note ? ' · ' + C['model.metrics'].note : ''); host.appendChild(p);
  if (has('model.reliability')) {
    var rel = C['model.reliability'].value.bins;
    WF.chart({ el: 'model-reliability', title: 'Reliability: mean score against the share that reached 300 acres, per tenth of fires', claims: ['model.reliability'],
      sub: 'If scores were probabilities, points would sit on the diagonal. The top bin sits far below it: that is why this site shows ranks, not probabilities. Marker size is the bin n.',
      rows: rel.map(function (b) { return { pred_lo: b.pred_lo, pred_hi: b.pred_hi, mean_predicted: b.mean_pred, observed_rate: b.obs_rate, n: b.n }; }),
      columns: [{ key: 'pred_lo', num: true }, { key: 'pred_hi', num: true }, { key: 'mean_predicted', num: true, fmt: function (v) { return WF.fmt.num(v, 3); } }, { key: 'observed_rate', num: true, fmt: function (v) { return WF.fmt.num(v, 3); } }, { key: 'n', num: true, fmt: WF.fmt.int }], height: 360,
      build: function (t) { var mx = Math.max.apply(null, rel.map(function (b) { return b.n; })); return { data: [
        { type: 'scatter', mode: 'lines', x: [0, 0.5], y: [0, 0.5], line: { color: t.gray, width: 1.5 }, hoverinfo: 'skip', showlegend: false },
        { type: 'scatter', mode: 'lines+markers', name: 'bins', x: rel.map(function (b) { return b.mean_pred; }), y: rel.map(function (b) { return b.obs_rate; }), line: { color: t.series[0], width: 2 }, marker: { color: t.series[0], size: rel.map(function (b) { return 8 + 16 * Math.sqrt(b.n / mx); }), line: { color: t.surface, width: 2 } }, customdata: rel.map(function (b) { return b.n; }), hovertemplate: 'predicted %{x:.3f}<br>observed %{y:.3f}<br>n = %{customdata:,}<extra></extra>' }],
        layout: { showlegend: false, xaxis: { title: { text: 'mean score in the bin' }, range: [0, 1.1 * Math.max.apply(null, rel.map(function (b) { return Math.max(b.mean_pred, b.obs_rate); }))] }, yaxis: { title: { text: 'share that reached 300 acres' }, range: [0, 1.1 * Math.max.apply(null, rel.map(function (b) { return Math.max(b.mean_pred, b.obs_rate); }))] } } }; }
    });
  }
  if (has('model.pr_curve')) {
    var pr = C['model.pr_curve'].value, pts = pr.points;
    WF.chart({ el: 'model-pr', title: 'Precision and recall by threshold', claims: ['model.pr_curve'],
      sub: 'The dashed line is the base rate (precision of flagging every fire). Hover shows the score cutoff and the number of fires flagged.',
      rows: pts.map(function (q) { return { threshold: q.threshold, precision: q.precision, recall: q.recall, n_flagged: q.n_flagged, base_rate: pr.base_rate }; }),
      columns: [{ key: 'threshold', num: true }, { key: 'precision', num: true, fmt: function (v) { return WF.fmt.num(v, 3); } }, { key: 'recall', num: true, fmt: function (v) { return WF.fmt.num(v, 3); } }, { key: 'n_flagged', num: true, fmt: WF.fmt.int }, { key: 'base_rate', num: true, fmt: function (v) { return WF.fmt.num(v, 4); } }], height: 360,
      build: function (t) { return { data: [
        { type: 'scatter', mode: 'lines', x: [0, 1], y: [pr.base_rate, pr.base_rate], line: { color: t.ink2, width: 1.5, dash: 'dash' }, name: 'base rate ' + WF.fmt.pct(pr.base_rate, 2), hoverinfo: 'skip' },
        { type: 'scatter', mode: 'lines', name: 'model', x: pts.map(function (q) { return q.recall; }), y: pts.map(function (q) { return q.precision; }), line: { color: t.series[0], width: 2 }, customdata: pts.map(function (q) { return [q.threshold, q.n_flagged]; }), hovertemplate: 'recall %{x:.3f}, precision %{y:.3f}<br>score cutoff %{customdata[0]:.3f}<br>flagged n = %{customdata[1]:,}<extra></extra>' }],
        layout: { xaxis: { title: { text: 'recall' }, range: [0, 1] }, yaxis: { title: { text: 'precision' }, range: [0, 1] }, legend: { y: -0.25 } } }; }
    });
  }
  if (has('model.base_rates')) {
    var br = C['model.base_rates'].value.rows, host2 = document.getElementById('model-base-rates');
    var MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    var bcols = [{ key: 'region' }, { key: 'month' }, { key: 'cause' }, { key: 'n', label: 'fires 2010-2018', num: true, fmt: WF.fmt.int },
      { key: 'rate', label: 'share reaching 300 acres', num: true, fmt: function (v) { return v == null ? 'fewer than 100 fires' : WF.fmt.pct(v, 1); } }];
    var brows = br.map(function (r) { return { region: r.region, month: MON[r.month - 1] || r.month, cause: r.cause, n: r.n, rate: r.rate, _missing: r.cause === 'Missing' }; });
    host2.style.maxHeight = '420px'; host2.style.overflowY = 'auto';
    host2.appendChild(WF.buildTable(bcols, brows, { sortable: true }));
  }
})();
"""


def page_model(ctx: dict) -> str:
    c = ctx['claims']
    has_model = 'model.metrics' in c
    src = 'docs/review/REPRODUCTION.md and outputs/reproduction_model.json (scripts/reproduce.py, 126,011 test fires, random 80/20 split, seed 42)'
    retired = f"""
<h2>The previous duration model was retired</h2>
<p>The earlier version of this project fitted a Random Forest to predict how many days a fire would burn from its location, day of year and recorded cause. It reproduces exactly, and it is retired because it is not useful:</p>
<ul class="tight">
<li>On mean absolute error it loses to predicting zero days for every fire: {qd('1.38', 'test MAE of the Random Forest, in days', src, 126011)} against {qd('1.09', 'test MAE of the constant prediction 0 days', src, 126011)} days.</li>
<li>{qd('84%', 'share of model-sample fires (2010+, with a containment date) whose duration is 0 whole days: 83.7%', src, 630053)} of fires are contained on the day they are found, so a constant is a strong baseline that any model has to beat before it says anything.</li>
<li>Its sample dropped {q(c, 'overview.missing_cont_date_share_2010_plus', fmt_pct(cv(c, 'overview.missing_cont_date_share_2010_plus')))} of fires from 2010 on because they lack a containment date, and unevenly: {q(c, 'anom.texas_missing_cont_date_share_2010_plus', fmt_pct(cv(c, 'anom.texas_missing_cont_date_share_2010_plus')))} of Texas records are missing it. The containment date is a reporting-system convention, not a measure of the fire (see <a href="ownership.html#containment">Ownership</a>).</li>
</ul>
<p>No duration prediction appears on this site.</p>"""
    if has_model:
        card = cv(c, 'model.card') if 'model.card' in c else {}
        cf = cv(c, 'model.calibration_failure') if 'model.calibration_failure' in c else None
        cap = {r['model']: r for r in cv(c, 'model.capture_at_top')['rows']} if 'model.capture_at_top' in c else {}
        me = next((r for r in cap.values() if not r['baseline']), None)
        lk = next((r for k, r in cap.items() if k.startswith('Lookup')), None)
        fail_html = ''
        if cf:
            by = cf['brier_skill_vs_base_rate_by_year']
            fail_html = f"""<div class="note"><p><strong>These are ranks, not probabilities.</strong> For the tenth of 2019-2020 fires it scored highest, the model's mean score was {q(c, 'model.calibration_failure', fmt_pct(cf['top_decile_mean_score']))}; the share that actually reached 300 acres was {q(c, 'model.calibration_failure', fmt_pct(cf['top_decile_observed_rate']))}.
Read as probabilities, the scores do worse than a single constant rate (Brier skill {q(c, 'model.calibration_failure', fmt_num(cf['brier_skill_vs_base_rate_overall'], 2))}, where 0 is no better than always predicting the average rate and below 0 is worse), mostly in 2019, a quiet year after two large seasons ({q(c, 'model.calibration_failure', fmt_num(by.get('2019'), 2))} in 2019, {q(c, 'model.calibration_failure', fmt_num(by.get('2020'), 2))} in 2020). So this page shows how well the model <em>orders</em> fires and never a percent chance for a fire.</p></div>"""
        lead = ''
        if me and lk:
            lead = (f"On fires from 2019 and 2020 that it never saw, the model's top tenth of scores held {q(c, 'model.capture_at_top', fmt_pct(me['top_10pct'], 0))} of the fires that went on to reach 300 acres, "
                    f"against {q(c, 'model.capture_at_top', fmt_pct(lk['top_10pct'], 0))} for a lookup of each place's historical rate by month.")
        body = f"""
<header class="page-head"><h1>Prediction: which new fires become large?</h1>
<p class="lede">A model that ranks newly discovered fires by how likely they are to reach 300 acres, using only what is known on the discovery day. {lead}
Trained on {esc(card.get('train_years', '?'))}, tested once on {esc(card.get('test_years', '?'))}. Where a fire starts (its fuels, terrain and land status) carries the ranking; weather on the discovery day adds nothing measurable.</p></header>
{fail_html}
<div class="note"><p><strong>Coverage.</strong> {esc(cv(c, 'model.coverage', 'text') if 'model.coverage' in c and isinstance(cv(c, 'model.coverage'), dict) and 'text' in cv(c, 'model.coverage') else 'See the coverage claim in the ledger.')}
CONUS is the lower 48 states and DC; Class G fires are those of 5,000 acres or more.</p></div>
<h2>How many large fires the top of the ranking finds</h2>
<p>Share of the 2019-2020 fires that reached 300 acres found among each model's highest-scored fires. Flagging fires at random finds the same share as the share flagged.</p>
<div class="table-wrap" id="model-capture"></div>
<h2>Metrics with baselines</h2>
<p>Every row uses the same test fires and the same interval method. Baselines are always shown with the model. The model wins on the ranking metrics (PR-AUC, ROC-AUC) and loses on Brier skill, which scores the numbers as probabilities.</p>
<div class="table-wrap" id="model-metrics"></div>
<h2>Where it does not work</h2>
<ul class="tight">
<li>It ranks Southern fires worse than the place-and-month lookup, except in Texas ({q(c, 'model.holdout_per_region', 'regional metrics')}).</li>
<li>Alaska, Hawaii and Puerto Rico are outside it.</li>
<li>Owner, reporting agency and protection status carry much of the ranking: they record where fires are fought, reported and allowed to burn, not only how they behave. A place's score says nothing about the quality of its land management.</li>
<li>It is not for any decision about an actual fire. The full list is in the <a href="{REPO_URL}/blob/main/docs/MODEL_CARD.md">model card</a>.</li>
</ul>
<h2>Calibration</h2>
{chart_div('model-reliability') if 'model.reliability' in c else placeholder('Reliability diagram', 'Add a <code>model.reliability</code> claim to render it.')}
<h2>Precision and recall</h2>
{chart_div('model-pr') if 'model.pr_curve' in c else placeholder('Precision-recall curve', 'Add a <code>model.pr_curve</code> claim to render it.')}
<h2>Base rates</h2>
<p>The lookup a reader can use without the model: the share of 2010-2018 ignitions that reached 300 acres, by region, discovery month and cause classification. These are observed historical shares, not model output; groups with fewer than 100 fires are left blank.</p>
<div class="table-wrap" id="model-base-rates">{'' if 'model.base_rates' in c else placeholder('Base-rate table', 'Add a <code>model.base_rates</code> claim to render it.')}</div>
{retired}
"""
    else:
        body = f"""
<header class="page-head"><h1>Prediction</h1>
<p class="lede">No prediction is published yet. A large-fire probability model (does an ignition reach 300 acres?) with a time-split evaluation, bootstrap intervals, a calibration plot and baselines is in progress. This page renders from <code>outputs/claims_model.json</code> when that file exists.</p></header>
<div class="placeholder"><h3>What will appear here</h3>
<ul class="tight">
<li>A metrics table with the model and its baselines (predict the base rate; a region x month x cause lookup) on the same time-split test fires, every metric with a 95% bootstrap interval.</li>
<li>A reliability diagram (mean predicted probability against observed rate per bin, with bin n) in place of a residual scatter.</li>
<li>A precision-recall curve with the base rate drawn beside it, and the number of fires flagged at each threshold.</li>
<li>A coverage note: which fires the model was trained and tested on, and which states or reporting systems it does not cover.</li>
<li>A base-rate lookup table (region, month, cause, n, share reaching 300 acres) that a reader can use without the model.</li>
</ul>
<p>Data contract: <a href="{DOCS_URL}/SITE.md">docs/SITE.md</a>, section "claims_model.json". Wording on this page will use "expected", "typical" and "range", never "risk", "danger" or "safe", and no red/green scale.</p></div>
{retired}
"""
    body += V().wfigs_section(ctx)
    return layout(ctx, 'model.html', 'Prediction · ' + SITE_TITLE, body, MODEL_JS if has_model else '',
                  description='A model that ranks new fires by how likely they are to become large, tested once on 2019-2020, with the calibration failure shown; and the retired duration model.')


# --------------------------------------------------------------------------- main

def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)


def main() -> int:
    global NAV
    v2 = V()
    NAV = v2.NAV
    claims, files, missing = load_claims()
    if not files:
        print('error: no outputs/claims*.json found; run `python -m analysis.descriptive --out outputs/` first', file=sys.stderr)
        return 1
    cells = load_cells()
    coverage = load_coverage(claims)
    hash_full, hash_prefix = read_hash_prefix()
    generated = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%d')

    # Start clean so removed pages do not linger, but keep nothing that is not generated.
    if os.path.isdir(SITE_DIR):
        shutil.rmtree(SITE_DIR)
    for d in ('data', 'assets', 'figures', 'downloads'):
        os.makedirs(os.path.join(SITE_DIR, d))
    if PLOTLY_SRC != PLOTLY_CDN:
        os.makedirs(os.path.join(SITE_DIR, 'vendor'))
        shutil.copy2(PLOTLY_VENDORED, os.path.join(SITE_DIR, 'vendor', 'plotly.min.js'))
        shutil.copy2(os.path.join(os.path.dirname(PLOTLY_VENDORED), 'PLOTLY_LICENSE'),
                     os.path.join(SITE_DIR, 'vendor', 'PLOTLY_LICENSE.txt'))
        # Map outlines preloaded as window.PlotlyGeoAssets, which Plotly reads before fetching from its CDN;
        # works from file:// and https alike, so maps make no third-party request.
        with open(os.path.join(os.path.dirname(PLOTLY_VENDORED), 'usa_110m.json')) as f:
            topo = f.read().strip()
        write(os.path.join(SITE_DIR, 'vendor', 'geo_assets.js'),
              'window.PlotlyGeoAssets = {topojson: {usa_110m: ' + topo + '}};\n')

    figures = []
    for src in sorted(glob.glob(os.path.join(OUT_DIR, 'figures', '*.png'))):
        shutil.copy2(src, os.path.join(SITE_DIR, 'figures', os.path.basename(src)))
        figures.append(os.path.basename(src))

    # Map console: point files, outlines and the renderer.
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    import build_points
    build_points.main(['--site', SITE_DIR])
    with open(os.path.join(SITE_DIR, 'data', 'points_meta.json')) as fh:
        points_meta = json.load(fh)
    shutil.copy2(os.path.join(here, 'site_assets', 'console.js'), os.path.join(SITE_DIR, 'assets', 'console.js'))

    # Per-state claims are large; each state page loads only its own, and the global ledger file carries the rest.
    place_ids = sorted(k for k in claims if k.startswith('places.state.'))
    shared = {k: v for k, v in claims.items() if not k.startswith('places.state.')}
    meta = {'generated': generated, 'hash_prefix': hash_prefix, 'hash': hash_full, 'repo': REPO_URL,
            'claims_files': files, 'claims_missing': missing, 'n_claims': len(claims), 'author': AUTHOR,
            'n_place_claims_on_state_pages': len(place_ids)}
    write(os.path.join(SITE_DIR, 'data', 'meta.js'), 'window.WF_DATA = window.WF_DATA || {};\nwindow.WF_DATA.meta = ' + js(meta) + ';\n')
    write(os.path.join(SITE_DIR, 'data', 'claims.js'), 'window.WF_DATA = window.WF_DATA || {};\nwindow.WF_DATA.claims = ' + js(shared) + ';\n')
    write(os.path.join(SITE_DIR, 'data', 'cells.js'), 'window.WF_DATA = window.WF_DATA || {};\nwindow.WF_DATA.cells = ' + js(cells) + ';\n')
    data_files = ['meta.js', 'claims.js', 'cells.js']
    if coverage:
        write(os.path.join(SITE_DIR, 'data', 'coverage.js'), 'window.WF_DATA = window.WF_DATA || {};\nwindow.WF_DATA.coverage = ' + js(coverage) + ';\n')
        data_files.append('coverage.js')
    for cid in place_ids:
        st = cid.rsplit('.', 1)[1]
        write(os.path.join(SITE_DIR, 'data', f'place_{st}.js'),
              'window.WF_DATA = window.WF_DATA || {};\nwindow.WF_DATA.claims = window.WF_DATA.claims || {};\n'
              f'window.WF_DATA.claims[{js(cid)}] = ' + js(claims[cid]) + ';\n')

    write(os.path.join(SITE_DIR, 'assets', 'site.css'), CSS.strip() + '\n' + v2.CSS.strip() + '\n')
    write(os.path.join(SITE_DIR, 'assets', 'site.js'), SITE_JS.strip() + '\n')

    # Downloads: every table behind the site and every ledger.
    downloads = []
    tab = os.path.join(OUT_DIR, 'tables')
    for name, desc in [('places_summary.csv', 'one row per state'), ('state_year.csv', 'fires, acres, large fires and the usable flag per state-year'),
                       ('calendar_regions.csv', 'fires by region, month and general cause, usable state-years'),
                       ('largest_incidents.csv', 'the 250 largest incidents, grouped, with component fires')]:
        if os.path.exists(os.path.join(tab, name)):
            shutil.copy2(os.path.join(tab, name), os.path.join(SITE_DIR, 'downloads', name))
            downloads.append((name, desc))
    if os.path.isdir(os.path.join(tab, 'calendar')):
        shutil.copytree(os.path.join(tab, 'calendar'), os.path.join(SITE_DIR, 'downloads', 'calendar'))
    shutil.copy2(os.path.join(OUT_DIR, 'coverage_state_year.csv'), os.path.join(SITE_DIR, 'downloads', 'coverage_state_year.csv'))
    downloads.append(('coverage_state_year.csv', 'record counts, breaks and usable windows per state-year'))
    for f in files:
        shutil.copy2(os.path.join(OUT_DIR, f), os.path.join(SITE_DIR, 'downloads', f))
        downloads.append((f, 'claims ledger'))

    ctx = {'claims': claims, 'cells': cells, 'coverage': coverage, 'hash_full': hash_full, 'hash_prefix': hash_prefix,
           'generated': generated, 'claims_files': files, 'claims_missing': missing, 'n_claims': len(claims),
           'data_files': data_files, 'figures': figures, 'points_meta': points_meta, 'downloads': downloads}
    cal = v2.calendar_data()
    if cal:
        ctx['calendar_data'] = v2.data_file(ctx, 'calendar.js', 'calendar', cal)
    ctx['places_rows'] = v2.places_index_rows(claims)
    ctx['places_data'] = v2.data_file(ctx, 'places.js', 'places', ctx['places_rows'])
    largest = v2.read_csv('largest_incidents.csv')
    for r in largest:
        for k in ('acres', 'largest_component_acres'):
            r[k] = round(float(r[k]), 1)
        r['components'] = int(r['components'])
        r['rank'] = int(r['rank'])
        r['name'] = name_case(r['name'])
        r['component_names'] = name_case(r['component_names'])
        r['cause'] = 'Not recorded' if r['cause'] == v2.MISS else r['cause']
        for k in ('mtbs_id', 'ics209_id', 'latitude', 'longitude', 'general_cause', 'first_discovery', 'lead_fire', ''):
            r.pop(k, None)
    ctx['largest_data'] = v2.data_file(ctx, 'largest.js', 'largest', largest)
    ctx['wfigs_states'] = {r['state']: r for r in (claims.get('wfigs.per_state_2021_2025', {}).get('value') or [])}

    pages = {
        'index.html': v2.page_home, 'explore.html': v2.page_explore, 'trends.html': page_trends, 'causes.html': page_causes,
        'places.html': v2.page_places, 'conservation.html': page_conservation, 'largest.html': v2.page_largest,
        'drivers.html': v2.page_drivers, 'model.html': page_model, 'methods.html': page_methods, 'audit.html': v2.page_audit,
        'geography.html': page_geography, 'ownership.html': page_ownership,
    }
    for name, fn in pages.items():
        html_text = fn(ctx)
        if html_text:
            write(os.path.join(SITE_DIR, name), html_text)
    for cid in place_ids:
        st = cid.rsplit('.', 1)[1]
        write(os.path.join(SITE_DIR, f'place-{st}.html'), v2.page_place(ctx, st))

    write(os.path.join(SITE_DIR, 'robots.txt'), 'User-agent: *\nAllow: /\n')

    total = 0
    for root, _, fnames in os.walk(SITE_DIR):
        for f in fnames:
            total += os.path.getsize(os.path.join(root, f))
    shared_total = sum(os.path.getsize(os.path.join(SITE_DIR, 'data', f)) for f in data_files)
    print(f'site written to {SITE_DIR}: {len(pages) + len(place_ids)} pages ({len(place_ids)} state briefs), {len(figures)} figures, '
          f'data loaded on every page {shared_total / 1e6:.2f} MB, total {total / 1e6:.2f} MB')
    print(f'claims files: {", ".join(files)}; not present: {", ".join(missing) or "none"}; coverage: {"yes" if coverage else "placeholder"}')
    if shared_total > 3e6:
        print('warning: data loaded on every page exceeds 3 MB', file=sys.stderr)
    if total > 40e6:
        print('warning: site exceeds 40 MB', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
