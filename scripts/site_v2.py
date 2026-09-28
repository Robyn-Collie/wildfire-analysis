"""Version 2 pages for scripts/build_site.py: the story home page, the map console, place briefs, the prevention
calendar, the largest incidents, drought drivers, the national (NIFC) series and the audit of the first site.

Imported by build_site.main(); every function takes the same ``ctx`` as the version 1 pages and returns HTML.
Numbers are read from the claims ledgers (outputs/claims*.json) and rendered through ``q()`` so each one opens its
definition, n and source. Tables that are too large for a claim (per-state calendars, the largest-incidents list)
are read from outputs/tables/ and offered as CSV downloads.
"""
from __future__ import annotations

import csv
import json
import os

import build_site as B
from build_site import cv, esc, fmt_int, fmt_m, fmt_num, fmt_pct, js, q, qd

MONTHS = B.MONTHS
MISS = 'Missing data/not specified/undetermined'
TABLES = os.path.join(B.OUT_DIR, 'tables')

NAV = [
    ('index.html', 'Story'),
    ('explore.html', 'Map'),
    ('trends.html', 'Trend'),
    ('causes.html', 'Seasons and causes'),
    ('places.html', 'Places'),
    ('conservation.html', 'Protected lands and losses'),
    ('largest.html', 'Largest fires'),
    ('drivers.html', 'Drought'),
    ('model.html', 'Prediction'),
    ('methods.html', 'Data and methods'),
]

CSS = r"""
/* ---- version 2 additions ---- */
main p, main li, main td { overflow-wrap: break-word; }
.hero { display: grid; grid-template-columns: 1fr; gap: 1rem; align-items: start; }
.kicker { text-transform: uppercase; letter-spacing: .06em; font-size: .75rem; color: var(--muted); font-weight: 600; margin-bottom: .25rem; }
.routes { display: grid; grid-template-columns: 1fr; gap: .75rem; margin: 1rem 0 1.5rem; }
@media (min-width: 760px) { .routes { grid-template-columns: repeat(3, 1fr); } }
.route { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: .9rem 1rem; }
.route h3 { margin: 0 0 .35rem; font-size: 1rem; }
.route p { font-size: .9rem; color: var(--ink-2); margin-bottom: .5rem; }
.route a { font-weight: 600; }
.findings { counter-reset: f; list-style: none; padding: 0; margin: 1rem 0; }
.findings > li { counter-increment: f; position: relative; padding: .8rem 1rem .8rem 3rem; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); margin-bottom: .6rem; }
.findings > li::before { content: counter(f); position: absolute; left: 1rem; top: .75rem; font-weight: 700; color: var(--muted); font-size: 1.1rem; }
.findings h3 { margin: 0 0 .3rem; font-size: 1.02rem; }
.findings p { margin: 0; font-size: .92rem; color: var(--ink-2); max-width: none; }
.findings .caveat { margin-top: .35rem; font-size: .84rem; color: var(--muted); }
.verdict { display: inline-block; font-size: .72rem; font-weight: 650; padding: .08rem .45rem; border-radius: 999px; margin-left: .35rem; vertical-align: 2px; border: 1px solid var(--border-strong); }
.verdict.holds { color: var(--s3); border-color: var(--s3); }
.verdict.revised { color: var(--s4); border-color: var(--s4); }
.verdict.wrong { color: var(--s8); border-color: var(--s8); }
.verdict.new { color: var(--s1); border-color: var(--s1); }

/* console */
.console { display: grid; grid-template-columns: 1fr; gap: .75rem; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: .75rem; margin: 1rem 0; }
@media (min-width: 900px) { .console { grid-template-columns: minmax(0, 1fr) 290px; } .console .console-bar { grid-column: 1 / -1; } }
.console-bar { font-size: .82rem; color: var(--ink-2); }
.console-stage { position: relative; width: 100%; min-height: 200px; touch-action: none; }
.console-stage canvas { position: absolute; left: 0; top: 0; }
.console-stage canvas.console-gl { cursor: crosshair; }
.console-stage.failed { min-height: 60px; }
.console-zoom { position: absolute; right: .4rem; top: .4rem; display: flex; gap: .25rem; }
.console-zoom .btn { background: var(--surface); }
.console-probe { position: absolute; z-index: 5; width: 220px; background: var(--surface); border: 1px solid var(--border-strong); border-radius: var(--radius); padding: .5rem .6rem; font-size: .8rem; box-shadow: 0 4px 16px rgba(0,0,0,.18); }
.console-probe .close { position: absolute; right: .3rem; top: .15rem; border: 0; background: none; color: var(--muted); cursor: pointer; font-size: 1rem; }
.console-side { font-size: .85rem; }
.console-n { font-size: 1rem; margin-bottom: .25rem; }
.console-keys { list-style: none; padding: 0; margin: 0 0 .5rem; }
.console-keys li { margin: .15rem 0; }
.console-counts { color: var(--ink-2); font-size: .8rem; margin-bottom: .5rem; }
.console-controls fieldset { border: 0; border-top: 1px solid var(--grid); margin: 0; padding: .45rem 0 .35rem; }
.console-controls legend { font-weight: 600; font-size: .78rem; color: var(--ink-2); padding: 0; }
.console-controls label { display: block; font-size: .82rem; margin: .1rem 0; }
.console-controls label.radio { display: inline-block; margin-right: .6rem; }
.console-controls input[type=range] { width: 100%; }
.console-controls select { font: inherit; font-size: .82rem; max-width: 100%; background: var(--surface); color: var(--ink); border: 1px solid var(--border-strong); border-radius: 6px; padding: .15rem .3rem; }
.console-controls .val { font-weight: 650; font-variant-numeric: tabular-nums; }
.console-controls .load-all { width: 100%; margin-bottom: .4rem; }
.console-controls.compact fieldset:nth-of-type(n+5) { display: none; }

/* place briefs */
.tiles { display: grid; grid-template-columns: repeat(2, 1fr); gap: .5rem; margin: 1rem 0; }
@media (min-width: 760px) { .tiles { grid-template-columns: repeat(4, 1fr); } }
.tiles .tile { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: .6rem .75rem; }
.ratetable td, .ratetable th { text-align: right; font-variant-numeric: tabular-nums; padding: .3rem .35rem; font-size: .8rem; }
.ratetable td:first-child, .ratetable th:first-child { text-align: left; }
.ratetable td.hi { font-weight: 700; }
.ratetable td.thin { color: var(--muted); }
.state-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: .35rem; margin: .5rem 0 1rem; }
.state-grid a { display: block; padding: .3rem .5rem; border: 1px solid var(--border); border-radius: 6px; text-decoration: none; background: var(--surface); font-size: .88rem; }
.state-grid a:hover { background: var(--surface-2); }
.toolbar { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; margin: .5rem 0 1rem; }
.pill { font-size: .75rem; padding: .1rem .5rem; border-radius: 999px; background: var(--surface-2); color: var(--ink-2); }
.bars { list-style: none; padding: 0; margin: .5rem 0 1rem; }
.bars li { display: grid; grid-template-columns: minmax(8rem, 15rem) 1fr auto; gap: .5rem; align-items: center; font-size: .85rem; margin: .2rem 0; }
.bars .bar { height: 10px; background: var(--seq-100); border-radius: 3px; overflow: hidden; }
.bars .bar i { display: block; height: 100%; background: var(--s1); }
.bars .v { font-variant-numeric: tabular-nums; color: var(--ink-2); white-space: nowrap; }
@media print {
  .topbar, footer.site, .console, .toolbar, .chart .foot, .no-print { display: none !important; }
  body { background: #fff; color: #000; font-size: 11pt; }
  main { padding: 0; }
  .chart, .tile, .route { break-inside: avoid; border-color: #bbb; }
  a { color: #000; text-decoration: none; }
  h2 { margin-top: 1.2rem; }
}
"""


def claim_or(c: dict, cid: str, *path, default=None):
    try:
        return cv(c, cid, *path)
    except (KeyError, IndexError, TypeError):
        return default


def read_csv(name: str) -> list[dict]:
    path = os.path.join(TABLES, name)
    if not os.path.exists(path):
        return []
    with open(path, newline='', encoding='utf-8') as fh:
        return list(csv.DictReader(fh))


def data_file(ctx: dict, name: str, key: str, obj) -> str:
    """Write site/data/<name> as window.WF_DATA[key] = obj; return the script path for layout()."""
    B.write(os.path.join(B.SITE_DIR, 'data', name), 'window.WF_DATA = window.WF_DATA || {};\nwindow.WF_DATA.' + key + ' = ' + js(obj) + ';\n')
    return 'data/' + name


# =========================================================================== home

def console_block(el_id: str, opts: dict) -> str:
    return (f'<div id="{el_id}" class="console" aria-label="Map of fire ignition points"></div>'
            f'<noscript><p>The map needs JavaScript. Every number on this site is also in the tables under each chart.</p></noscript>'
            f'<script>document.addEventListener("DOMContentLoaded",function(){{WFConsole.mount("{el_id}",{js(opts)});}});</script>')


def page_home(ctx: dict) -> str:
    c = ctx['claims']
    n_rows = cv(c, 'overview.n_rows')
    hs = claim_or(c, 'calendar.human_share')
    j4 = claim_or(c, 'calendar.july4')
    era = claim_or(c, 'nifc.era_table')
    shift = claim_or(c, 'nifc.floor_median_ceiling_shift')
    fwd = claim_or(c, 'drivers.forward_cv', 'overall')
    loyo = claim_or(c, 'drivers.loyo_cv')
    cap = claim_or(c, 'model.capture_at_top')
    big = claim_or(c, 'incidents.largest')
    dup = claim_or(c, 'incidents.row_top100_duplicates')
    tr_w = claim_or(c, 'class_g.acres_trend_west')
    ics = claim_or(c, 'ics.outcomes_by_cause')

    findings = []
    if era and shift:
        findings.append(('The area burned each year has more than doubled since the 1980s and 1990s',
            f'National totals from the interagency record: a median year burned {q(c, "nifc.era_table", fmt_num(era["1983_1999"]["median"], 2) + " million acres")} in 1983-1999 and '
            f'{q(c, "nifc.era_table", fmt_num(era["2000_2025"]["median"], 2) + " million")} in 2000-2025. The quietest year since 2000 ({q(c, "nifc.era_table", fmt_num(era["2000_2025"]["min"], 2) + "M")}) '
            f'burned about as much as the median year before it: the lowest year rose {q(c, "nifc.floor_median_ceiling_shift", fmt_num(shift["floor_shift"], 2) + " times")}.',
            f'Without the first three years of the series, the floor shift is {q(c, "nifc.floor_shift_sensitivity_drop_1983_85", fmt_num(cv(c, "nifc.floor_shift_sensitivity_drop_1983_85", "floor_shift"), 2) + "x")}. The fire count carries reporting changes and is not a trend.',
            'trends.html', 'holds'))
    if hs:
        findings.append(('People start most fires, but lightning burns most of the land in the largest ones',
            f'People caused {q(c, "calendar.human_share", fmt_pct(hs["known_cause"], 0))} of fires whose cause is known, and {q(c, "calendar.human_share", fmt_pct(hs["large_known_cause"], 0))} of fires that reached 300 acres, '
            f'but only {q(c, "calendar.human_share", fmt_pct(hs["large_acres_known_cause"], 0))} of the acres in those large fires.',
            'Counted inside each state\'s usable reporting years. Cause is not recorded for about one fire in five.', 'causes.html#calendar', 'holds'))
    if j4:
        findings.append(('The Fourth of July is the most predictable fire day of the year',
            f'On 4 July the record holds {q(c, "calendar.july4", fmt_num(j4["jul4_ratio"], 1) + " times")} as many new fires as on a typical day in the surrounding weeks, and 4 July was the single busiest day of the year in '
            f'{q(c, "calendar.july4", str(j4["years_jul4_highest_of_year"]))} of the 29 years. Only {q(c, "calendar.july4", fmt_pct(j4["fireworks_share_jul4_5"], 0))} of 4-5 July fires are coded as fireworks; {q(c, "calendar.july4", fmt_pct(j4["cause_missing_share_jul4_5"], 0))} have no recorded cause.',
            'A prevention calendar by state and month is on the Seasons page.', 'causes.html#calendar', 'new'))
    if ics:
        hum = ics.get('Human', {}).get('structures_destroyed')
        tot = claim_or(c, 'ics.outcomes_total', 'structures_destroyed')
        if hum and tot:
            findings.append(('Human-caused fires destroyed most of the homes and buildings lost',
                f'Of {q(c, "ics.outcomes_total", fmt_int(tot))} structures destroyed in incidents with an ICS-209 report (1999-2020), {q(c, "ics.outcomes_by_cause", fmt_int(hum))} were in human-caused fires.',
                'Only incidents large or complex enough to file an ICS-209 report are counted.', 'conservation.html', 'new'))
    if fwd and loyo:
        findings.append(('Drought explains part of the year-to-year swing in burned area, less than first reported',
            f'A state-by-year model of drought, heat and rain cuts prediction error by {q(c, "drivers.loyo_cv", fmt_num(loyo["skill_pct_mse"], 1) + "%")} against each state\'s usual year when tested by leaving one year out, as the first site reported. '
            f'Tested forward in time, predicting each year from earlier years only, the gain is {q(c, "drivers.forward_cv", fmt_num(fwd["skill_pct_mse"], 1) + "%")}.',
            'The drought signal is strong in Colorado and weak in Arizona and Nevada, where fuel, not dryness, limits fire.', 'drivers.html', 'revised'))
    if cap:
        findings.append(('Where a fire starts says a lot about whether it will grow; the scores are not probabilities',
            f'A model given only what is known on the discovery day put {q(c, "model.capture_at_top", "74%")} of the fires that reached 300 acres in its top tenth of scores, on years it never saw, against 45% for a lookup of each place\'s history.',
            'Read as probabilities its scores failed in 2019, a quiet year, so the site shows ranks only.', 'model.html', 'holds'))
    if big and dup:
        findings.append(('The largest fires, counted once each',
            f'The {q(c, "incidents.largest", big[0]["name"].title())} ({q(c, "incidents.largest", fmt_int(big[0]["acres"]) + " acres")}, {big[0]["year"]}) and the {q(c, "incidents.largest", big[1]["name"].title())} ({q(c, "incidents.largest", fmt_int(big[1]["acres"]) + " acres")}, {big[1]["year"]}) lead the list once complexes are grouped. '
            f'Among the 100 largest records, only {q(c, "incidents.row_top100_duplicates", str(dup["distinct_incidents"]))} distinct incidents appear.',
            'Grouped by ICS-209 incident and complex name; the rule and every component fire are listed.', 'largest.html', 'revised'))

    items = ''.join(f'<li><h3>{esc(t)} <span class="verdict {v}">{ {"holds": "holds up", "revised": "revised", "new": "new in v2", "wrong": "corrected"}[v] }</span></h3>'
                    f'<p>{body}</p><p class="caveat">{cav} <a href="{href}">Details &rarr;</a></p></li>'
                    for t, body, cav, href, v in findings)

    body = f"""
<header class="page-head">
<div class="kicker">US wildfires, 1992-2020, with national totals to 2025</div>
<h1>Where fires start, when, and why some grow: {q(c, 'overview.n_rows', fmt_int(n_rows))} fires, with every number traced to its source</h1>
<p class="lede">The map below holds every fire in the federal Fire Program Analysis record (FPA FOD, 6th edition). Filter it by year, season, cause, size and protected-land status, then click anywhere for the counts around that point.
The pages after it turn the record into things a prevention planner, a land manager or a reporter can use, with what the record cannot tell you stated next to each answer.</p>
</header>
{console_block('home-console', {'compact': True, 'id': 'home'})}
<div class="routes">
  <div class="route"><h3>Planning prevention</h3><p>Which months and causes to target, state by state, and the days, such as 4 July, when ignitions spike.</p><a href="causes.html#calendar">Prevention calendar &rarr;</a></div>
  <div class="route"><h3>Managing land</h3><p>Fire on protected land by GAP status, the units with the most area burned, and what destroyed homes and buildings.</p><a href="conservation.html">Protected lands and losses &rarr;</a></div>
  <div class="route"><h3>Reporting or briefing</h3><p>A one-page brief for each state, the largest fires counted once each, and the national trend to 2025.</p><a href="places.html">State briefs &rarr;</a></div>
</div>

<h2>What the record shows</h2>
<p>Each finding carries its test. "Revised" means the first public version of this site stated it more strongly than a stricter test supports; the <a href="audit.html">audit</a> lists every change.</p>
<ol class="findings">{items}</ol>

<h2>What the record is, and is not</h2>
<p>The FPA FOD compiles fire reports from federal, state and local systems. It is the best national record of where and when fires started, but it is not a census: states joined and left the reporting systems in different years,
so counts of fires can jump for reasons that have nothing to do with fire. This site counts fires only inside each state's usable reporting window, uses acres and national totals for trends, and shows a missing or unknown category on every chart instead of dropping it.
It has no fire perimeters, no burn severity and no prescribed fire. <a href="methods.html">Data and methods &rarr;</a></p>
"""
    return B.layout(ctx, 'index.html', B.SITE_TITLE, body, extra_scripts=['assets/console.js'],
                    description='Every US wildfire 1992-2020 on one map, state briefs, a prevention calendar, and trends, with every number traced to its definition.')


# =========================================================================== explore

def page_explore(ctx: dict) -> str:
    c = ctx['claims']
    body = f"""
<header class="page-head"><h1>Every fire, 1992-2020</h1>
<p class="lede">Each dot is one fire's point of origin. Colour shows the cause, the size, or the protected-area status of the land it started on. The list beside the map counts what is shown, so the picture always comes with its n.</p></header>
{console_block('explore-console', {'id': 'explore'})}
<div class="grid2">
<div><h2>How to read it</h2>
<ul class="tight">
<li>Dots overlap. Where they pile up the colour saturates, so a dense area looks the same whether it holds a thousand fires or ten thousand. Click the map for the actual count around a point.</li>
<li>The map starts with the {fmt_int(ctx['points_meta']['files']['points_c_plus.bin'])} fires of 10 acres or more. Add the {fmt_int(ctx['points_meta']['files']['points_a_b.bin'])} smaller fires with the button; most of them are in the South and East.</li>
<li>Some states did not report small fires in some years (see <a href="trends.html#coverage">coverage</a>). A year where a state looks empty may be a year its records are missing.</li>
<li>"Not in PAD-US" means the point falls outside every protected or public area in the Protected Areas Database; most private land is in that group.</li>
</ul></div>
<div><h2>What is encoded</h2>
<p class="small">Each fire is 8 bytes: its projected position and a 32-bit word with the year, day of year, cause class, size class, protection status, state and general cause. {esc(ctx['points_meta']['projection'])}.
Built by <code>scripts/build_points.py</code> from the same parquet file as every other number here; {fmt_int(ctx['points_meta']['outside_frame'])} fire falls outside the map frame and is not drawn.</p>
<p class="small">Protection status comes from a point-in-polygon join to PAD-US 4.1 (<a href="conservation.html">details</a>). Size classes follow the FPA FOD: A under 0.25 acres, B 0.25-10, C 10-100, D 100-300, E 300-1,000, F 1,000-5,000, G 5,000 and more.</p></div>
</div>
"""
    return B.layout(ctx, 'explore.html', 'Map · ' + B.SITE_TITLE, body, extra_scripts=['assets/console.js'],
                    description='Interactive map of 2.3 million US wildfire ignition points, filterable by year, month, cause, size and protected-area status.')


# =========================================================================== trend: NIFC section

NIFC_JS = r"""
(function(){
  var C = WF.data.claims; if (!C['nifc.annual']) return;
  var a = C['nifc.annual'].value, ys = WF.years(a), roll = C['nifc.rolling_p10_p50_p90'].value, rys = WF.years(roll);
  var ts = C['nifc.theil_sen'].value;
  WF.chart({ el: 'nifc-acres', title: 'Acres burned per year, United States, 1983-2025', claims: ['nifc.annual', 'nifc.rolling_p10_p50_p90', 'nifc.theil_sen', 'nifc.definition'],
    sub: 'National Interagency Coordination Center totals, all jurisdictions. Dotted lines: the 10th and 90th percentile of the 11 years centred on each year.',
    rows: ys.map(function (y) { var r = roll[y] || {}; return { year: y, acres: a[y].acres, fires: a[y].fires, rolling_p10_million: r.p10, rolling_p50_million: r.p50, rolling_p90_million: r.p90 }; }),
    columns: [{ key: 'year' }, { key: 'acres', num: true, fmt: WF.fmt.int }, { key: 'fires', num: true, fmt: WF.fmt.int }, { key: 'rolling_p10_million', label: 'rolling p10 (M acres)', num: true }, { key: 'rolling_p50_million', label: 'rolling median (M)', num: true }, { key: 'rolling_p90_million', label: 'rolling p90 (M)', num: true }],
    height: 340,
    build: function (t) { return { data: [
      // Percentile lines, not a filled band: Plotly draws scatter fills above bars whatever the trace order, so a band hides them.
      { type: 'scatter', mode: 'lines', x: rys, y: rys.map(function (y) { return roll[y].p90 * 1e6; }), line: { color: t.series[0], dash: 'dot', width: 2 }, name: '11-year p10 and p90', legendgroup: 'band', hovertemplate: '%{x}: 11-year p90 %{y:.3s} acres<extra></extra>' },
      { type: 'scatter', mode: 'lines', x: rys, y: rys.map(function (y) { return roll[y].p10 * 1e6; }), line: { color: t.series[0], dash: 'dot', width: 2 }, name: '11-year p10', legendgroup: 'band', showlegend: false, hovertemplate: '%{x}: 11-year p10 %{y:.3s} acres<extra></extra>' },
      { type: 'bar', x: ys, y: ys.map(function (y) { return a[y].acres; }), marker: { color: t.series[1] }, name: 'acres', hovertemplate: '%{x}: %{y:,} acres<extra></extra>' },
      { type: 'scatter', mode: 'lines', x: ys, y: ys.map(function (y) { return (ts.intercept + ts.slope_per_decade / 10 * y) * 1e6; }), line: { color: t.ink2, dash: 'dash', width: 1.5 }, name: 'Theil-Sen', hoverinfo: 'skip' }],
      layout: { yaxis: { title: { text: 'acres' }, tickformat: '.2s', rangemode: 'tozero' }, legend: { y: -0.2 }, barmode: 'overlay' } }; }
  });
})();
"""


def nifc_section(ctx: dict) -> str:
    c = ctx['claims']
    if 'nifc.annual' not in c:
        return ''
    era = cv(c, 'nifc.era_table')
    sh = cv(c, 'nifc.floor_median_ceiling_shift')
    sens = cv(c, 'nifc.floor_shift_sensitivity_drop_1983_85')
    ts = cv(c, 'nifc.theil_sen')
    k = cv(c, 'nifc.kendall')
    rm = cv(c, 'nifc.rolling_min_p10_trend')
    tm = cv(c, 'nifc.ten_million_years')
    fod = cv(c, 'nifc.nifc_vs_fpafod_1992_2020')
    a = cv(c, 'nifc.annual')
    last = max(a, key=int)
    rows = ''.join(f'<tr><td>{lab}</td>' + ''.join(f'<td class="num">{q(c, "nifc.era_table", fmt_num(era[key][s], 2))}</td>' for s in ('min', 'p25', 'median', 'p75', 'max')) + f'<td class="num">{era[key]["n"]}</td></tr>'
                   for lab, key in (('1983-1999', '1983_1999'), ('2000-2025', '2000_2025')))
    return f"""
<h2 id="national">The national total, 1983-{last}</h2>
<p>The interagency record of all fires on all jurisdictions is the longest consistent national series. Burned area rises by {q(c, 'nifc.theil_sen', fmt_num(ts['slope_per_decade'], 2) + ' million acres a decade')} (Theil-Sen, 95% interval {q(c, 'nifc.theil_sen', fmt_num(ts['ci95_per_decade'][0], 2))} to {q(c, 'nifc.theil_sen', fmt_num(ts['ci95_per_decade'][1], 2))}; Kendall tau {q(c, 'nifc.kendall', fmt_num(k['tau'], 2))}).
Three years passed ten million acres: {', '.join(q(c, 'nifc.ten_million_years', f'{y} ({fmt_num(v, 2)}M)') for y, v in tm.items())}. {last}: {q(c, 'nifc.annual', fmt_int(a[last]['acres']) + ' acres')} in {q(c, 'nifc.annual', fmt_int(a[last]['fires']) + ' fires')}.</p>
{B.chart_div('nifc-acres')}
<h3>The highs are higher, and so are the lows, with one caveat</h3>
<div class="table-wrap"><table><thead><tr><th>Million acres a year</th><th class="num">lowest</th><th class="num">25th pct</th><th class="num">median</th><th class="num">75th pct</th><th class="num">highest</th><th class="num">years</th></tr></thead><tbody>{rows}</tbody></table></div>
<p>The lowest year since 2000 burned {q(c, 'nifc.floor_median_ceiling_shift', fmt_num(sh['floor_shift'], 2) + ' times')} the lowest year before it; the median rose {q(c, 'nifc.floor_median_ceiling_shift', fmt_num(sh['median_shift'], 2) + ' times')} and the highest {q(c, 'nifc.floor_median_ceiling_shift', fmt_num(sh['ceiling_shift'], 2) + ' times')}.
The rise of the floor is not an artefact of two chosen endpoints: the rolling 11-year minimum trends up (Kendall tau {q(c, 'nifc.rolling_min_p10_trend', fmt_num(rm['kendall_tau_rolling_min'], 2))}, p = {q(c, 'nifc.rolling_min_p10_trend', fmt_num(rm['p_rolling_min'], 4))}).</p>
<div class="note"><p><strong>Caveat.</strong> The two lowest years in the series are the first two, 1983 and 1984, whose fire counts are also anomalously low ({q(c, 'nifc.count_flag_1983_84', fmt_int(cv(c, 'nifc.count_flag_1983_84', '1983')))} and {q(c, 'nifc.count_flag_1983_84', fmt_int(cv(c, 'nifc.count_flag_1983_84', '1984')))} fires, against 70,000 to 90,000 in the following years), which suggests incomplete early reporting.
Starting in 1986 instead, the floor shift is {q(c, 'nifc.floor_shift_sensitivity_drop_1983_85', fmt_num(sens['floor_shift'], 2) + 'x')} rather than {fmt_num(sh['floor_shift'], 2)}x. The lows rose either way.
The FPA FOD's own annual acres track this series closely (r = {q(c, 'nifc.nifc_vs_fpafod_1992_2020', fmt_num(fod['pearson_r'], 3))} for 1992-2020) and show the same floor rise ({q(c, 'nifc.nifc_vs_fpafod_1992_2020', fmt_num(fod['fod_floor_shift'], 2) + 'x')}), but they are largely the same fires, so they are not independent confirmation.
The fire <em>count</em> in this series is not used as a trend: reporting practice changed over the period.</p></div>
"""


# =========================================================================== causes: prevention calendar

CAL_JS = r"""
(function(){
  var C = WF.data.claims, cal = WF.data.calendar; if (!cal) return;
  var MISS = 'Missing data/not specified/undetermined';
  var gens = cal.general, regions = cal.regions, region = regions[0];
  function grid(r) { var z = gens.map(function (g) { return WF.monthNames.map(function (m, i) { return (cal.counts[r][g] || [])[i] || 0; }); }); return z; }
  var ctrl = document.createElement('div'), mode = 'row';
  var sel = document.createElement('select'); sel.setAttribute('aria-label', 'Region');
  var RL = { Other: 'Midwest and Plains (Other)' };
  var SHORT = { 'Debris and open burning': 'Debris burning', 'Arson/incendiarism': 'Arson', 'Equipment and vehicle use': 'Equipment, vehicles',
    'Recreation and ceremony': 'Recreation', 'Misuse of fire by a minor': 'Children', 'Railroad operations and maintenance': 'Railroads',
    'Power generation/transmission/distribution': 'Power lines', 'Firearms and explosives use': 'Firearms', 'Other causes': 'Other' };
  regions.forEach(function (r) { sel.appendChild(new Option((RL[r] || r) + ' (' + WF.fmt.int(cal.totals[r]) + ' fires)', r)); });
  ctrl.appendChild(sel);
  ctrl.appendChild(WF.segControl([{ label: 'Each cause\'s season', value: 'row' }, { label: 'Share of all fires', value: 'all' }], function (v) { mode = v; entry.render(); }));
  var entry = WF.chart({ el: 'cal-heat', title: 'Prevention calendar: fires by month and general cause', claims: ['calendar.region_month', 'calendar.top_human_cause_by_month'],
    sub: '"Each cause\'s season": every row sums to 100%, so each cause\'s peak months stand out whatever its size (row labels give its fires). "Share of all fires": cells are shares of the region\'s fires. Usable state-years only; state calendars are on each state\'s brief.',
    controls: ctrl, csvName: 'prevention_calendar',
    rows: [].concat.apply([], regions.map(function (r) { return gens.map(function (g) { var o = { region: r, general_cause: g }; WF.monthNames.forEach(function (m, i) { o[m] = (cal.counts[r][g] || [])[i] || 0; }); return o; }); })),
    columns: [{ key: 'region' }, { key: 'general_cause', label: 'general cause' }].concat(WF.monthNames.map(function (m) { return { key: m, num: true, fmt: WF.fmt.int }; })),
    height: 460,
    build: function (t) {
      var z = grid(region), tot = cal.totals[region] || 1;
      var rs = z.map(function (row) { return row.reduce(function (a, b) { return a + b; }, 0); });
      // On a phone the long cause names and a side colour bar leave the grid a few pixels wide: shorten the names and put the bar underneath.
      var narrow = (document.getElementById('cal-heat') || document.body).clientWidth < 600;
      var lab = gens.map(function (g, i) { return (g === MISS ? 'Cause not recorded' : (narrow && SHORT[g]) || g) + (mode === 'row' ? ' (' + WF.fmt.compact(rs[i]) + ')' : ''); });
      var zz = z.map(function (row, i) { return row.map(function (v) { return mode === 'row' ? (rs[i] ? 100 * v / rs[i] : null) : 100 * v / tot; }); });
      var unit = mode === 'row' ? 'of this cause\'s fires' : 'of the region\'s fires';
      var full = gens.map(function (g) { return WF.monthNames.map(function () { return g === MISS ? 'Cause not recorded' : g; }); });
      var cb = narrow ? { title: { text: '%', side: 'right' }, thickness: 8, ticksuffix: '%', orientation: 'h', x: 0, xanchor: 'left', y: -0.08, yanchor: 'top', len: 1 }
                      : { title: { text: '%' }, thickness: 10, ticksuffix: '%' };
      return { data: [{ type: 'heatmap', x: WF.monthNames, y: lab, z: zz, customdata: z, text: full,
        colorscale: WF.seqScale(t), xgap: narrow ? 1 : 2, ygap: 2, zmin: 0, hovertemplate: '%{text}, %{x}: %{customdata:,} fires (%{z:.1f}% ' + unit + ')<extra></extra>', colorbar: cb }],
        layout: { margin: narrow ? { l: 4, r: 4, b: 70 } : { l: 10 }, xaxis: narrow ? { tickfont: { size: 9 }, tickangle: -90, dtick: 1 } : {}, yaxis: { autorange: 'reversed', automargin: true, tickfont: { size: narrow ? 10 : 11 } } } };
    }
  });
  sel.onchange = function () { region = sel.value; entry.render(); };

  var j = C['calendar.july4_by_state'];
  if (j) {
    var rows = j.value.slice(0, 20);
    WF.chart({ el: 'jul4-states', title: 'Fires on 4 July against a normal early-summer day, by state', claims: ['calendar.july4_by_state', 'calendar.july4'],
      sub: 'Ratio of fires discovered on 4 July to the mean of 24 Jun-1 Jul and 8-15 Jul, usable years, states with 30+ fires on 4 July. Bar colour: share coded as fireworks.',
      rows: rows.map(function (r) { return { state: r.state, fires_on_jul4: r.jul4_fires, ratio_to_baseline_day: r.ratio, fireworks_share: r.fireworks_share }; }),
      columns: [{ key: 'state' }, { key: 'fires_on_jul4', label: 'fires on 4 July (all years)', num: true, fmt: WF.fmt.int }, { key: 'ratio_to_baseline_day', label: 'ratio to baseline day', num: true, fmt: function (v) { return WF.fmt.num(v, 1); } }, { key: 'fireworks_share', label: 'coded fireworks', num: true, fmt: function (v) { return WF.fmt.pct(v, 0); } }],
      height: 420,
      build: function (t) { return { data: [{ type: 'bar', orientation: 'h', y: rows.map(function (r) { return r.state; }), x: rows.map(function (r) { return r.ratio; }),
        marker: { color: rows.map(function (r) { return r.fireworks_share; }), colorscale: WF.seqScale(t), cmin: 0, cmax: 0.7, colorbar: { title: { text: 'fireworks' }, tickformat: '.0%', thickness: 10 } },
        customdata: rows.map(function (r) { return [r.jul4_fires, r.fireworks_share]; }), hovertemplate: '%{y}: %{x:.1f}x a normal day<br>%{customdata[0]:,} fires on 4 July; %{customdata[1]:.0%} coded fireworks<extra></extra>' }],
        layout: { yaxis: { autorange: 'reversed' }, xaxis: { title: { text: 'times a normal early-summer day' }, rangemode: 'tozero' }, shapes: [{ type: 'line', x0: 1, x1: 1, yref: 'paper', y0: 0, y1: 1, line: { color: t.axis, dash: 'dot' } }] } }; }
    });
  }
  var cm = C['calendar.cause_missing_by_state'];
  if (cm) {
    var st = Object.keys(cm.value).sort(function (a, b) { return cm.value[b] - cm.value[a]; });
    WF.chart({ el: 'cause-missing', title: 'Share of fires with no recorded cause, by state', claims: ['calendar.cause_missing_by_state'],
      sub: 'Where this is high, a cause calendar describes only the fires whose cause was recorded. States with 1,000+ fires, all years.',
      rows: st.map(function (s) { return { state: s, cause_not_recorded: cm.value[s] }; }), columns: [{ key: 'state' }, { key: 'cause_not_recorded', label: 'cause not recorded', num: true, fmt: function (v) { return WF.fmt.pct(v, 1); } }],
      height: 300,
      build: function (t) { return { data: [{ type: 'bar', x: st, y: st.map(function (s) { return 100 * cm.value[s]; }), marker: { color: t.missing }, hovertemplate: '%{x}: %{y:.1f}% with no recorded cause<extra></extra>' }],
        layout: { yaxis: { ticksuffix: '%', rangemode: 'tozero' }, xaxis: { tickfont: { size: 9 } } } }; }
    });
  }
})();
"""


# The analysis calls this region "Other" (analysis/common.py REGION_DEFINITION); the calendar chart uses the same label.
REGION_LABEL = {'Other': 'Midwest and Plains (Other)'}


def calendar_data() -> dict | None:
    rows = read_csv('calendar_regions.csv')
    if not rows:
        return None
    counts, totals = {}, {}
    gens = []
    for r in rows:
        reg, g, m, n = r['REGION'], r['GENERAL'], int(r['MONTH']), int(r['fires'])
        counts.setdefault(reg, {}).setdefault(g, [0] * 12)[m - 1] += n
        totals[reg] = totals.get(reg, 0) + n
        if g not in gens:
            gens.append(g)
    order = [g for g in ['Debris and open burning', 'Arson/incendiarism', 'Equipment and vehicle use', 'Recreation and ceremony', 'Smoking',
                         'Misuse of fire by a minor', 'Railroad operations and maintenance', 'Power generation/transmission/distribution',
                         'Fireworks', 'Firearms and explosives use', 'Other causes', 'Natural', MISS] if g in gens]
    regions = [r for r in B.REGIONS if r in counts]
    return {'general': order, 'regions': regions, 'counts': counts, 'totals': totals}


def calendar_section(ctx: dict) -> str:
    c = ctx['claims']
    if 'calendar.region_month' not in c:
        return ''
    j4 = cv(c, 'calendar.july4')
    top = cv(c, 'calendar.top_human_cause_by_month')
    deb = cv(c, 'calendar.debris_peak')
    hs = cv(c, 'calendar.human_share')
    jul = top.get('Jul', {})
    return f"""
<h2 id="calendar">Prevention calendar</h2>
<p class="lede">When to run which message, and where. People start {q(c, 'calendar.human_share', fmt_pct(hs['known_cause'], 0))} of fires whose cause is known. Debris and open burning is the most common known human cause in {q(c, 'calendar.top_human_cause_by_month', 'every month but ' + ', '.join(m for m in MONTHS if top.get(m, {}).get('top') != 'Debris and open burning'))}; in July, equipment and vehicle use takes over ({q(c, 'calendar.top_human_cause_by_month', fmt_pct(jul.get('share', 0), 0))} of known human causes).</p>
{B.chart_div('cal-heat')}
<div class="grid2">
<div>
<h3>Debris burning has a season, and it differs by region</h3>
<ul class="tight">{''.join(f'<li><strong>{esc(REGION_LABEL.get(r, r))}</strong>: busiest in {", ".join(v["peak_months"])}; {q(c, "calendar.debris_peak", fmt_pct(v["mar_apr_share"], 0))} in March and April.</li>' for r, v in deb.items())}</ul>
<p class="small">Burn-permit timing and red-flag messaging for debris burning belong in late winter and spring in the South, the Northeast and the Midwest and Plains, and in late spring in the West and Alaska. The Midwest and Plains region is every state not in the other regions, which also puts DC, Delaware and Maryland in it.</p>
</div>
<div>
<h3>4 July</h3>
<p>A typical day in late June or mid July brings {q(c, 'calendar.july4', fmt_int(j4['baseline_mean']))} new fires nationally; 4 July brings {q(c, 'calendar.july4', fmt_int(j4['jul4_mean']))} and 5 July {q(c, 'calendar.july4', fmt_int(j4['jul5_mean']))} (means over 1992-2020).
New Year's Eve and Day together run {q(c, 'calendar.july4', fmt_num(j4['new_year_ratio'], 1) + ' times')} the surrounding days.</p>
<p class="small">Only {q(c, 'calendar.july4', fmt_pct(j4['fireworks_share_jul4_5'], 0))} of 4-5 July fires are coded as fireworks and {q(c, 'calendar.july4', fmt_pct(j4['cause_missing_share_jul4_5'], 0))} have no recorded cause, so the spike is a better measure of fireworks fires than the cause code is. Texas shows the spike with almost no fires coded as fireworks: its state records rarely carry a general cause.</p>
</div></div>
{B.chart_div('jul4-states')}
{B.chart_div('cause-missing')}
"""


# =========================================================================== places

PLACES_JS = r"""
(function(){
  var P = WF.data.places, C = WF.data.claims; if (!P) return;
  var metrics = [
    { key: 'fires_per_year', label: 'Fires a year (usable window)', fmt: function (v) { return WF.fmt.int(v); } },
    { key: 'acres_per_year', label: 'Acres a year (usable window)', fmt: function (v) { return WF.fmt.compact(v); } },
    { key: 'human_share', label: 'Human-caused share', fmt: function (v) { return WF.fmt.pct(v, 0); } },
    { key: 'large_rate', label: 'Share reaching 300 acres', fmt: function (v) { return WF.fmt.pct(v, 1); } },
    { key: 'structures', label: 'Structures destroyed 1999-2020 (ICS-209)', fmt: function (v) { return WF.fmt.int(v); } },
    { key: 'gap12_acres', label: 'Acres on land managed for biodiversity', fmt: function (v) { return WF.fmt.pct(v, 0); } },
    { key: 'cause_missing', label: 'Cause not recorded', fmt: function (v) { return WF.fmt.pct(v, 0); } },
    { key: 'drought_rho', label: 'Drought-acres correlation (Spearman)', fmt: function (v) { return WF.fmt.num(v, 2); } }
  ];
  var m = metrics[0];
  var ctrl = document.createElement('div'); var sel = document.createElement('select'); sel.setAttribute('aria-label', 'Metric');
  metrics.forEach(function (x, i) { sel.appendChild(new Option(x.label, i)); }); ctrl.appendChild(sel);
  var states = P.map(function (r) { return r.state; });
  var entry = WF.chart({ el: 'places-map', title: 'States compared', claims: ['places.window_lengths', 'places.acres_trend_summary'], mapClass: true,
    sub: 'Pick a measure. Grey states have no value (too few fires or not tested). Click a state in the table below for its brief.', controls: ctrl, csvName: 'places_summary',
    rows: P, columns: [{ key: 'state' }, { key: 'name' }].concat(metrics.map(function (x) { return { key: x.key, label: x.label, num: true, fmt: x.fmt }; })),
    height: 420,
    build: function (t) {
      var v = P.map(function (r) { return r[m.key]; });
      var rev = m.key === 'drought_rho';
      return { data: [{ type: 'choropleth', locationmode: 'USA-states', locations: states, z: v, text: P.map(function (r) { return r.name + ': ' + (r[m.key] === null || r[m.key] === undefined ? 'n/a' : m.fmt(r[m.key])); }),
        hovertemplate: '%{text}<extra></extra>', colorscale: WF.seqScale(t), reversescale: rev, marker: { line: { color: t.surface, width: 1 } }, colorbar: { thickness: 10, tickfont: { color: t.muted } } }],
        layout: { geo: { scope: 'usa', bgcolor: 'rgba(0,0,0,0)', lakecolor: 'rgba(0,0,0,0)', showlakes: false, subunitcolor: t.surface }, margin: { l: 0, r: 0, t: 0, b: 0 } } };
    }
  });
  sel.onchange = function () { m = metrics[+sel.value]; entry.render(); };
  var host = document.getElementById('places-table');
  var cols = [{ key: 'name', label: 'State' }, { key: 'region' }, { key: 'window', label: 'usable years' }].concat(metrics.map(function (x) { return { key: x.key, label: x.label, num: true, fmt: x.fmt }; }));
  var tbl = WF.buildTable(cols, P, { sortable: true });
  host.appendChild(tbl);
  var rowsEls = tbl.querySelectorAll('tbody tr');
  function linkify() { var trs = tbl.querySelectorAll('tbody tr'); for (var i = 0; i < trs.length; i++) { var td = trs[i].firstChild; var nm = td.textContent; var r = P.filter(function (x) { return x.name === nm; })[0]; if (r && !td.querySelector('a')) { td.textContent = ''; var a = document.createElement('a'); a.href = 'place-' + r.state + '.html'; a.textContent = nm; td.appendChild(a); } } }
  linkify(); tbl.addEventListener('click', function () { setTimeout(linkify, 0); });
})();
"""


def places_index_rows(c: dict) -> list[dict]:
    rows = []
    rho = claim_or(c, 'drivers.spearman_usable_only', 'by_state', default={}) or {}
    for cid in sorted(k for k in c if k.startswith('places.state.')):
        b = c[cid]['value']
        prot = (b.get('protected') or {}).get('by_gap', {}).get('GAP 1-2 (managed for biodiversity)', {})
        rows.append({
            'state': b['state'], 'name': b['name'], 'region': b['region'], 'window': f'{b["window"][0]}-{b["window"][1]}',
            'fires_per_year': round(b['fires_per_year_in_window'], 1), 'acres_per_year': round(b['acres_per_year_in_window']),
            'human_share': round(b['cause_shares'].get('Human', 0), 4), 'large_rate': round(b['large_rate_overall'] or 0, 5),
            'structures': (b.get('losses') or {}).get('structures_destroyed'),
            'gap12_acres': round(prot['acre_share'], 4) if prot else None,
            'cause_missing': round(b['completeness']['cause_missing_share'], 4),
            'drought_rho': rho.get(b['state']),
        })
    return rows


def page_places(ctx: dict) -> str:
    c = ctx['claims']
    rows = ctx['places_rows']
    ts = cv(c, 'places.acres_trend_summary')
    grid = ''.join(f'<a href="place-{r["state"]}.html">{esc(r["name"])}</a>' for r in sorted(rows, key=lambda r: r['name']))
    body = f"""
<header class="page-head"><h1>Places</h1>
<p class="lede">A brief for every state: when fires start and from what, which ones grow, whether burned area is changing, how much burns on protected land, what destroyed buildings, and how complete the state's record is. Each brief prints on a few pages and links its tables as CSV.</p></header>
<div class="state-grid">{grid}</div>
{B.chart_div('places-map')}
<h2>All states</h2>
<p>Sort by any column. Every count-based number uses the state's usable reporting window, so states are compared on years when their records are complete; the window is listed.
Of the {q(c, 'places.acres_trend_summary', str(ts['states_tested']))} states with a window of 15 years or more, burned area trends upward in {q(c, 'places.acres_trend_summary', str(len(ts['upward_p05'])))} ({', '.join(ts['upward_p05'])}) and downward in {q(c, 'places.acres_trend_summary', str(len(ts['downward_p05'])))} ({', '.join(ts['downward_p05'])}) at p &lt; 0.05. About {q(c, 'places.acres_trend_summary', fmt_num(ts['expected_false_positives_at_p05'], 0))} such results would appear by chance alone.</p>
<div id="places-table" class="table-wrap"></div>
<p class="small"><a href="downloads/places_summary.csv">places_summary.csv</a> · <a href="downloads/state_year.csv">state_year.csv</a> (fires, acres, large fires and the usable flag for every state and year)</p>
"""
    return B.layout(ctx, 'places.html', 'Places · ' + B.SITE_TITLE, body, PLACES_JS, extra_scripts=[ctx['places_data']],
                    description='Fire briefs for every US state: ignition calendar, large-fire rates, trends, protected land, losses and record completeness.')


PLACE_JS = r"""
(function(){
  var st = document.body.getAttribute('data-state'), C = WF.data.claims, id = 'places.state.' + st, b = C[id].value;
  var MISS = 'Missing data/not specified/undetermined', CAUSES = ['Human', 'Natural', MISS], LAB = { Human: 'Human', Natural: 'Natural' }; LAB[MISS] = 'Cause not recorded';
  var cal = b.calendar_per_year;
  WF.chart({ el: 'p-cal', title: 'When fires start: fires a year by month of discovery', claims: [id],
    sub: 'Average per year inside the usable window (' + b.window[0] + '-' + b.window[1] + '), split by cause class.',
    rows: WF.monthNames.map(function (m) { return { month: m, human: cal[m].Human, natural: cal[m].Natural, cause_not_recorded: cal[m][MISS] }; }),
    columns: [{ key: 'month' }, { key: 'human', num: true, fmt: function (v) { return WF.fmt.num(v, 1); } }, { key: 'natural', num: true, fmt: function (v) { return WF.fmt.num(v, 1); } }, { key: 'cause_not_recorded', label: 'cause not recorded', num: true, fmt: function (v) { return WF.fmt.num(v, 1); } }],
    height: 280, csvName: st + '_calendar',
    build: function (t) { return { data: CAUSES.map(function (k) { return { type: 'bar', name: LAB[k], x: WF.monthNames, y: WF.monthNames.map(function (m) { return cal[m][k]; }), marker: { color: WF.causeColor(t, k), line: { color: t.surface, width: 1 } }, hovertemplate: '%{x} ' + LAB[k] + ': %{y:.1f} fires a year<extra></extra>' }; }),
      layout: { barmode: 'stack', yaxis: { title: { text: 'fires a year' } }, legend: { y: -0.22 } } }; }
  });
  var py = b.per_year, ys = WF.years(py);
  WF.chart({ el: 'p-acres', title: 'Acres burned per year', claims: [id],
    sub: 'Grey bars are years outside the usable reporting window: their totals may be missing fires. The trend test uses the usable years only.',
    rows: ys.map(function (y) { return { year: y, acres: py[y].acres, fires: py[y].fires, fires_300_acres_plus: py[y].large_fires, usable: py[y].usable ? 'yes' : 'no' }; }),
    columns: [{ key: 'year' }, { key: 'acres', num: true, fmt: WF.fmt.int }, { key: 'fires', num: true, fmt: WF.fmt.int }, { key: 'fires_300_acres_plus', label: 'fires of 300+ acres', num: true, fmt: WF.fmt.int }, { key: 'usable' }],
    height: 280, csvName: st + '_by_year', caption: b.trend_acres_words + ' ' + b.trend_large_words,
    build: function (t) { return { data: [{ type: 'bar', x: ys, y: ys.map(function (y) { return py[y].acres; }), marker: { color: ys.map(function (y) { return py[y].usable ? t.series[1] : t.gray; }) },
      customdata: ys.map(function (y) { return [py[y].fires, py[y].large_fires, py[y].usable ? 'usable year' : 'outside usable window']; }), hovertemplate: '%{x}: %{y:,.0f} acres<br>%{customdata[0]:,} fires, %{customdata[1]} of 300+ acres<br>%{customdata[2]}<extra></extra>' }],
      layout: { showlegend: false, yaxis: { title: { text: 'acres' }, tickformat: '.2s', rangemode: 'tozero' } } }; }
  });
})();
"""


def _rate_table(b: dict) -> str:
    lr = b['large_rate_by_month']
    heads = ''.join(f'<th>{m}</th>' for m in MONTHS)
    rows = ''
    overall = b['large_rate_overall'] or 0
    for cause, lab in (('Human', 'Human'), ('Natural', 'Natural'), (MISS, 'Not recorded')):
        cells = ''
        for m in MONTHS:
            x = lr.get(cause, {}).get(m)
            if not x or x['fires'] == 0:
                cells += '<td class="thin">-</td>'
                continue
            thin = x['fires'] < 50
            cls = 'thin' if thin else ('hi' if overall and x['rate'] >= 2 * overall else '')
            cells += f'<td class="{cls}" title="{x["large"]} of {x["fires"]:,} fires">{100 * x["rate"]:.1f}%</td>'
        rows += f'<tr><td>{lab}</td>{cells}</tr>'
    return f'<div class="table-wrap"><table class="ratetable"><thead><tr><th>Cause</th>{heads}</tr></thead><tbody>{rows}</tbody></table></div>'


def page_place(ctx: dict, st: str) -> str:
    c = ctx['claims']
    cid = f'places.state.{st}'
    b = c[cid]['value']
    name = b['name']
    comp = b['completeness']
    w0, w1 = b['window']
    human = b['cause_shares'].get('Human', 0)
    tiles = ''.join(f'<div class="tile"><div class="label">{esc(lab)}</div><div class="value">{q(c, cid, val)}</div><div class="sub">{esc(sub)}</div></div>' for lab, val, sub in [
        ('Fires a year', fmt_int(b['fires_per_year_in_window']), f'average, {w0}-{w1}'),
        ('Acres a year', B.fmt_m(b['acres_per_year_in_window']) if b['acres_per_year_in_window'] >= 1e6 else fmt_int(b['acres_per_year_in_window']), f'average, {w0}-{w1}'),
        ('Started by people', fmt_pct(human, 0), f'{fmt_pct(b["cause_shares"].get(MISS, 0), 0)} cause not recorded'),
        ('Reach 300 acres', fmt_pct(b['large_rate_overall'] or 0, 1), f'{fmt_int(b["large_fires"])} such fires, 1992-2020'),
    ])
    breaks = b['break_years']
    window_note = (f'The record for {esc(name)} is usable for {w0}-{w1} ({b["window_years"]} years).'
                   + (f' Reporting breaks in {", ".join(str(y) for y in breaks)}' if breaks else '')
                   + (f'; no records in {", ".join(str(y) for y in b["zero_years"])}' if b['zero_years'] else '')
                   + ('.' if breaks or b['zero_years'] else ' No reporting breaks were found.'))
    top = b['top_human_causes']
    top_html = ''
    if top:
        top_html = '<ul class="bars">' + ''.join(
            f'<li><span>{esc(t["cause"])}</span><span class="bar"><i style="width:{100 * t["share_of_known_human"]:.0f}%"></i></span>'
            f'<span class="v">{q(c, cid, fmt_pct(t["share_of_known_human"], 0))} · peaks {", ".join(t.get("peak_months", []))}</span></li>' for t in top) + '</ul>'
    gen_missing = comp['general_cause_missing_share']
    prot = b.get('protected')
    prot_html = '<p class="muted">Protected-land join not available in this build.</p>'
    if prot:
        g = prot['by_gap']
        prot_html = ('<ul class="bars">' + ''.join(
            f'<li><span>{esc(k)}</span><span class="bar"><i style="width:{100 * v["acre_share"]:.0f}%"></i></span><span class="v">{q(c, cid, fmt_pct(v["acre_share"], 0))} of acres · {q(c, cid, fmt_pct(v["fire_share"], 0))} of fires</span></li>'
            for k, v in g.items()) + '</ul>')
        if prot['top_units']:
            prot_html += '<div class="table-wrap"><table><thead><tr><th>Protected or public unit</th><th class="num">Acres</th><th class="num">Fires</th><th>Manager</th><th>Designation</th></tr></thead><tbody>' + ''.join(
                f'<tr><td>{esc(u["unit"])}</td><td class="num">{q(c, cid, fmt_int(u["acres"]))}</td><td class="num">{q(c, cid, fmt_int(u["fires"]))}</td><td>{esc(u["manager"])}</td><td>{esc(u["designation"])}</td></tr>'
                for u in prot['top_units']) + '</tbody></table></div>'
        if prot['tribal']['fires']:
            prot_html += f'<p class="small">Tribal lands: {q(c, cid, fmt_int(prot["tribal"]["fires"]) + " fires")}, {q(c, cid, fmt_int(prot["tribal"]["acres"]) + " acres")}.</p>'
    loss = b.get('losses')
    loss_html = '<p class="muted">ICS-209-PLUS not available in this build.</p>'
    if loss:
        if loss['incidents']:
            bc = loss['by_cause']
            parts = ', '.join(f'{("cause not recorded" if k == MISS else k.lower())} {q(c, cid, fmt_int(v["destroyed"]))}' for k, v in bc.items())
            loss_html = (f'<p>{q(c, cid, fmt_int(loss["incidents"]) + " incidents")} filed an ICS-209 report in 1999-2020; {q(c, cid, fmt_int(loss["incidents_with_destroyed"]))} of them destroyed at least one structure, '
                         f'{q(c, cid, fmt_int(loss["structures_destroyed"]) + " structures")} in all ({parts}).</p>')
            if loss['top_incidents']:
                loss_html += '<div class="table-wrap"><table><thead><tr><th>Incident</th><th class="num">Year</th><th class="num">Structures destroyed</th><th>Cause</th></tr></thead><tbody>' + ''.join(
                    f'<tr><td>{esc(str(t["name"]).title())}</td><td class="num">{t["year"]}</td><td class="num">{q(c, cid, fmt_int(t["destroyed"]))}</td><td>{esc(t["general_cause"] if t["cause"] == "Human" else ("Natural" if t["cause"] == "Natural" else "Not recorded"))}</td></tr>'
                    for t in loss['top_incidents']) + '</tbody></table></div>'
        else:
            loss_html = '<p>No incident in this state is in the ICS-209-PLUS table for 1999-2020.</p>'
    loss_html += '<p class="small muted">Counts only incidents large or complex enough to file an ICS-209 report, matched to the FPA FOD; smaller fires that destroyed buildings are not here.</p>'

    rho_all = claim_or(c, 'drivers.spearman_by_state', st)
    rho_u = claim_or(c, 'drivers.spearman_usable_only', 'by_state', st)
    r2 = claim_or(c, 'drivers.per_state_oos_r2', st)
    if rho_all is not None or rho_u is not None:
        dro = (f'<p>Across years, drier summers (lower May-October Palmer Drought Severity Index) go with more acres burned when the Spearman correlation below is negative. '
               f'All years: {q(c, "drivers.spearman_by_state", fmt_num(rho_all, 2)) if rho_all is not None else "not computed"}; usable years only: '
               f'{q(c, "drivers.spearman_usable_only", fmt_num(rho_u, 2)) if rho_u is not None else "not computed"}.'
               + (f' The state-year climate model explains {q(c, "drivers.per_state_oos_r2", fmt_num(r2, 2))} of this state\'s year-to-year variance out of sample (R², leave-one-year-out; negative means worse than the state\'s average year).' if r2 is not None else '')
               + ' <a href="drivers.html">How this was tested</a>.</p>')
    else:
        dro = '<p class="muted">Not in the drought analysis (fewer than 25 years with fires or under 50,000 acres in total, or no climate division data).</p>'

    wf = ctx.get('wfigs_states', {}).get(st)
    recent = ''
    if wf:
        recent = (f'<h2>Recent years, 2021-2025</h2><p>From WFIGS, a different reporting system (federal interagency incident reports), so these are not comparable with the counts above: '
                  f'{q(c, "wfigs.per_state_2021_2025", fmt_int(wf.get("fires", 0)) + " fires")}, {q(c, "wfigs.per_state_2021_2025", fmt_int(wf.get("acres", 0)) + " acres")}, {q(c, "wfigs.per_state_2021_2025", fmt_int(wf.get("fires_ge300", 0)))} of 300+ acres. <a href="model.html#wfigs">About WFIGS</a>.</p>')

    body = f"""
<header class="page-head">
<div class="kicker"><a href="places.html">Places</a> · {esc(b['region'])} · {esc(b['gacc'])}</div>
<h1>{esc(name)}</h1>
<p class="lede">{q(c, cid, fmt_int(b['fires']) + ' fires')} and {q(c, cid, fmt_int(b['acres']) + ' acres')} in the FPA FOD, 1992-2020. {window_note}</p>
</header>
<div class="toolbar no-print"><button type="button" class="btn" onclick="window.print()">Print this brief</button>
<a class="btn" href="downloads/calendar/{st}.csv">Calendar CSV</a><a class="btn" href="data/place_{st}.js">All numbers (JSON)</a><span class="pill">claim id: {cid}</span></div>
<div class="tiles">{tiles}</div>

<h2>When fires start</h2>
<p>The busiest month is {q(c, cid, b['busiest_month'] or 'n/a')}, with {q(c, cid, fmt_pct(b['busiest_month_share'] or 0, 0))} of the year's fires. Human-caused fires peak in {q(c, cid, b['human_peak_month'] or 'n/a')}; lightning fires in {q(c, cid, b['natural_peak_month'] or 'n/a')}.</p>
{B.chart_div('p-cal')}
<h3>What people start them with</h3>
<p class="small">Share of human-caused fires with a known general cause, and the three months each cause is most common. The general cause is not recorded for {q(c, cid, fmt_pct(gen_missing, 0))} of this state's fires{', so read this list as describing the minority of fires with a recorded cause' if gen_missing > 0.5 else ''}.</p>
{top_html or '<p class="muted">No human-caused fires with a recorded general cause in the usable window.</p>'}

<h2>Which fires become large</h2>
<p>Share of fires that reached 300 acres, by month and cause, in the usable window. Bold cells are at least twice the state's overall rate ({q(c, cid, fmt_pct(b['large_rate_overall'] or 0, 2))}); grey cells rest on fewer than 50 fires. Hover a cell for its counts.</p>
{_rate_table(b)}
<p class="small">This is the same lookup the <a href="model.html">prediction page</a> uses as its baseline. Lightning fires are more likely to grow large in most Western states; human-caused fires in the South and East rarely do, but there are far more of them.</p>

<h2>Is burned area changing?</h2>
{B.chart_div('p-acres')}

<h2>Protected land</h2>
<p class="small">Where fires started, by the GAP status of the land in the Protected Areas Database (PAD-US 4.1). GAP 1-2 is land managed for biodiversity (wilderness, most national parks, refuges); GAP 3 is multiple-use public land; GAP 4 has no known mandate. "Not in PAD-US" is mostly private land.</p>
{prot_html}

<h2>Buildings destroyed</h2>
{loss_html}

<h2>Drought</h2>
{dro}
{recent}
<h2>How complete this record is</h2>
<ul class="tight">
<li>Cause class not recorded: {q(c, cid, fmt_pct(comp['cause_missing_share'], 1))}; general cause not recorded: {q(c, cid, fmt_pct(comp['general_cause_missing_share'], 1))}.</li>
<li>Land owner not recorded: {q(c, cid, fmt_pct(comp['owner_missing_share'], 1))}.</li>
<li>No containment date: {q(c, cid, fmt_pct(comp['containment_date_missing_share'], 1))}.</li>
<li>Usable reporting window: {w0}-{w1}. Outside it, the count of fires reflects which agencies reported, not how many fires there were.</li>
</ul>
<h2 class="no-print">Map</h2>
<div class="no-print">{console_block('place-console', {'compact': True, 'state': st, 'id': 'place'})}</div>
"""
    return B.layout(ctx, f'place-{st}.html', f'{name} · Places · ' + B.SITE_TITLE, body, PLACE_JS,
                    extra_scripts=[f'data/place_{st}.js', 'assets/console.js'], body_attrs=f'data-state="{st}"', nav_page='places.html',
                    description=f'Wildfire brief for {name}: when fires start and why, which become large, trends, protected land, losses and data completeness.')


# =========================================================================== largest

LARGEST_JS = r"""
(function(){
  var L = WF.data.largest, C = WF.data.claims; if (!L) return;
  var host = document.getElementById('largest-table');
  var input = document.getElementById('largest-search');
  // Acres sits next to the name so it stays on screen on phones, where the secondary columns are dropped.
  var cols = [{ key: 'rank', num: true }, { key: 'name', label: 'Incident' }, { key: 'acres', num: true, fmt: WF.fmt.int }, { key: 'states', label: 'State' }, { key: 'years', label: 'Year' },
    { key: 'components', label: 'fires in it', num: true, hideSm: true }, { key: 'largest_component_acres', label: 'largest single fire', num: true, fmt: WF.fmt.int, hideSm: true },
    { key: 'cause', hideSm: true }, { key: 'component_names', label: 'component fires', hideSm: true }];
  function draw(filter) {
    host.textContent = '';
    var rows = L.filter(function (r) { if (!filter) return +r.rank <= 100; var s = (r.name + ' ' + r.states + ' ' + r.years + ' ' + r.component_names).toLowerCase(); return s.indexOf(filter) >= 0; });
    host.appendChild(WF.buildTable(cols, rows, { sortable: true }));
  }
  draw('');
  input.addEventListener('input', function () { draw(input.value.trim().toLowerCase()); });
  var py = C['incidents.100k_per_year'];
  if (py) {
    var ys = WF.years(py.value);
    WF.chart({ el: 'big-per-year', title: 'Incidents of 100,000 acres or more, per year', claims: ['incidents.100k_per_year', 'incidents.rule'],
      sub: 'Grouped incidents, by the discovery year of the largest component fire.',
      rows: ys.map(function (y) { return { year: y, incidents: py.value[y] }; }), columns: [{ key: 'year' }, { key: 'incidents', num: true }], height: 260,
      build: function (t) { return { data: [{ type: 'bar', x: ys, y: ys.map(function (y) { return py.value[y]; }), marker: { color: t.series[1] }, hovertemplate: '%{x}: %{y} incidents<extra></extra>' }], layout: { showlegend: false, yaxis: { rangemode: 'tozero', title: { text: 'incidents' } } } }; }
    });
  }
})();
"""


def page_largest(ctx: dict) -> str:
    c = ctx['claims']
    if 'incidents.largest' not in c:
        return ''
    dup = cv(c, 'incidents.row_top100_duplicates')
    s = cv(c, 'incidents.largest100_summary')
    g = cv(c, 'incidents.grouping')
    dup_list = ''.join(f'<li><strong>{esc(d["name"].title())}</strong> ({d["state"]}, {d["year"]}): {", ".join(esc(x.title()) for x in d["records"])} at record ranks {", ".join(str(r) for r in d["row_ranks"])}</li>' for d in dup['incidents_with_several_rows'])
    body = f"""
<header class="page-head"><h1>The largest fires, counted once each</h1>
<p class="lede">A complex of fires managed as one incident appears in the FPA FOD as several records. Listing records, as the first version of this site did, counts the same incident more than once and understates it: the August Complex of 2020 is {q(c, 'incidents.largest', fmt_int(cv(c, 'incidents.largest')[1]['acres']) + ' acres')} as an incident, but its largest single record is 589,368.</p></header>
<p>Among the 100 largest records there are {q(c, 'incidents.row_top100_duplicates', str(dup['distinct_incidents']))} distinct incidents; {q(c, 'incidents.row_top100_duplicates', str(dup['rows_sharing_an_incident']))} records share an incident with another record in the list:</p>
<ul class="tight">{dup_list}</ul>
<p class="small">Rule: {esc(cv(c, 'incidents.rule'))} {q(c, 'incidents.grouping', fmt_int(g['multi_record_incidents']))} incidents group more than one record. MTBS perimeter ids are not used for grouping, because one perimeter can span fires managed as separate complexes. <a href="{B.REPO_URL}/blob/main/analysis/incidents.py">analysis/incidents.py</a></p>
<h2>The 100 largest incidents, 1992-2020</h2>
<p>From {q(c, 'incidents.largest100_summary', fmt_int(s['acres_min']))} to {q(c, 'incidents.largest100_summary', fmt_int(s['acres_max']) + ' acres')}. {q(c, 'incidents.largest100_summary', str(s['by_region'].get('Alaska', 0)))} are in Alaska; {q(c, 'incidents.largest100_summary', str(s['since_2010']))} started in 2010 or later.
Lightning started {q(c, 'incidents.largest100_summary', str(s['by_cause'].get('Natural', 0)))} of them and people {q(c, 'incidents.largest100_summary', str(s['by_cause'].get('Human', 0)))}; {q(c, 'incidents.largest100_summary', str(s['by_cause'].get(MISS, 0)))} have no recorded cause.</p>
<div class="toolbar"><input id="largest-search" class="search" type="search" placeholder="Search the 250 largest by name, state or year" aria-label="Search incidents"><a class="btn" href="downloads/largest_incidents.csv">Download the 250 largest (CSV)</a></div>
<div id="largest-table" class="table-wrap"></div>
<p class="small muted">On a narrow screen the table shows rank, name, acres, state and year; the CSV has every column. Acres are the sum of the component records' FIRE_SIZE. When fires merged and each record reports the merged area, the sum overstates; compare it with the largest single fire. The cause and state are those of the largest component. Names are as recorded.</p>
{B.chart_div('big-per-year')}
"""
    return B.layout(ctx, 'largest.html', 'Largest fires · ' + B.SITE_TITLE, body, LARGEST_JS, extra_scripts=[ctx['largest_data']],
                    description='The largest US wildfires 1992-2020, grouped so each incident appears once, with the component fires listed.')


# =========================================================================== drivers

DRIVERS_JS = r"""
(function(){
  var C = WF.data.claims; if (!C['drivers.forward_cv']) return;
  var fw = C['drivers.forward_cv'].value.by_year, ys = WF.years(fw);
  WF.chart({ el: 'd-forward', title: 'Forward-in-time test: skill of the drought model in each year', claims: ['drivers.forward_cv', 'drivers.loyo_cv'],
    sub: 'Each year predicted from a model fitted to earlier years only. Skill = reduction in mean squared error (log10 acres) against each state\'s median year up to then. Below zero: worse than that baseline.',
    rows: ys.map(function (y) { return { year: y, skill_pct: fw[y].skill_pct_mse, oos_r2: fw[y].oos_r2, states: fw[y].n }; }),
    columns: [{ key: 'year' }, { key: 'skill_pct', label: 'skill (%)', num: true, fmt: function (v) { return WF.fmt.num(v, 1); } }, { key: 'oos_r2', label: 'out-of-sample R2', num: true, fmt: function (v) { return WF.fmt.num(v, 3); } }, { key: 'states', num: true }],
    height: 280,
    build: function (t) { return { data: [{ type: 'bar', x: ys, y: ys.map(function (y) { return fw[y].skill_pct_mse; }), marker: { color: ys.map(function (y) { return fw[y].skill_pct_mse < 0 ? t.series[7] : t.series[0]; }) }, hovertemplate: '%{x}: %{y:.1f}% skill<extra></extra>' }],
      layout: { showlegend: false, yaxis: { ticksuffix: '%', zeroline: true, zerolinecolor: t.ink2 } } }; }
  });
  var sp = C['drivers.spearman_by_state'].value, su = C['drivers.spearman_usable_only'].value.by_state;
  var st = Object.keys(sp).sort(function (a, b) { return sp[a] - sp[b]; });
  WF.chart({ el: 'd-spearman', title: 'Drought and burned area, state by state', claims: ['drivers.spearman_by_state', 'drivers.spearman_usable_only', 'drivers.spearman_summary'],
    sub: 'Spearman correlation between May-October mean PDSI and log10 acres burned, 1992-2020. Negative: drier years burn more. Hollow markers: usable reporting years only.',
    rows: st.map(function (s) { return { state: s, rho_all_years: sp[s], rho_usable_years: su[s] === undefined ? null : su[s] }; }),
    columns: [{ key: 'state' }, { key: 'rho_all_years', label: 'rho, all years', num: true, fmt: function (v) { return WF.fmt.num(v, 3); } }, { key: 'rho_usable_years', label: 'rho, usable years', num: true, fmt: function (v) { return WF.fmt.num(v, 3); } }],
    height: 340,
    build: function (t) { return { data: [
      { type: 'scatter', mode: 'markers', x: st, y: st.map(function (s) { return sp[s]; }), name: 'all years', marker: { color: t.series[0], size: 8 }, hovertemplate: '%{x}: rho %{y:.2f} (all years)<extra></extra>' },
      { type: 'scatter', mode: 'markers', x: st, y: st.map(function (s) { return su[s] === undefined ? null : su[s]; }), name: 'usable years only', marker: { color: 'rgba(0,0,0,0)', size: 11, line: { color: t.series[1], width: 2 } }, hovertemplate: '%{x}: rho %{y:.2f} (usable years)<extra></extra>' }],
      layout: { yaxis: { range: [-1, 0.5], zeroline: true, zerolinecolor: t.ink2, title: { text: 'Spearman rho' } }, xaxis: { tickfont: { size: 9 } }, legend: { y: -0.25 } } }; }
  });
})();
"""


def page_drivers(ctx: dict) -> str:
    c = ctx['claims']
    if 'drivers.loyo_cv' not in c:
        return ''
    loyo, fwd = cv(c, 'drivers.loyo_cv'), cv(c, 'drivers.forward_cv', 'overall')
    lm, fm = cv(c, 'drivers.loyo_cv_masked'), cv(c, 'drivers.forward_cv_masked')
    ss = cv(c, 'drivers.spearman_summary')
    su = cv(c, 'drivers.spearman_usable_only')
    sp = cv(c, 'drivers.spearman_by_state')
    mc = cv(c, 'drivers.misses_vs_coverage')
    co = cv(c, 'drivers.model_coefficients')
    rep = cv(c, 'drivers.v1_replication')
    n_match = sum(1 for v in rep.values() if isinstance(v, dict) and v.get('match'))
    n_rep = sum(1 for v in rep.values() if isinstance(v, dict) and 'match' in v)
    misses = cv(c, 'drivers.worst_misses')[:5]
    miss_rows = ''.join(f'<tr><td>{m["STATE"]} {m["year"]}</td><td class="num">{q(c, "drivers.worst_misses", fmt_int(m["actual_acres"]))}</td><td class="num">{q(c, "drivers.worst_misses", fmt_int(m["predicted_acres"]))}</td><td>{"usable" if m["usable"] else "<strong>reporting break</strong>"}</td></tr>' for m in misses)
    body = f"""
<header class="page-head"><h1>Drought and burned area</h1>
<p class="lede">Drier, hotter summers go with more area burned in most states. A simple state-by-year climate model captures part of that, less when it has to predict a year it has not seen. In the desert Southwest the link is weak: there, fuel, not dryness, limits fire.</p></header>
<h2>Replicating the first site</h2>
<p>The first version of this site fitted a model of each state's annual acres burned (log scale) on May-October drought (Palmer index), temperature and precipitation from NOAA's climate divisions, with a term for each state. Rebuilt from the original sources, {q(c, 'drivers.v1_replication', f'{n_match} of {n_rep}')} of its published numbers reproduce exactly, including the headline skill of {q(c, 'drivers.loyo_cv', fmt_num(loyo['skill_pct_mse'], 1) + '%')} (reduction in squared error against each state's median year) and out-of-sample R² {q(c, 'drivers.loyo_cv', fmt_num(loyo['oos_r2'], 3))}.
Drought carries the largest coefficient ({q(c, 'drivers.model_coefficients', fmt_num(co['pdsi'], 4))} per standard deviation of PDSI, against {q(c, 'drivers.model_coefficients', fmt_num(co['temp'], 4))} for temperature and {q(c, 'drivers.model_coefficients', fmt_num(co['precip'], 4))} for precipitation).</p>

<h2>Three stricter tests</h2>
<div class="table-wrap"><table><thead><tr><th>Test</th><th class="num">State-years</th><th class="num">Skill vs state median</th><th class="num">Out-of-sample R²</th></tr></thead><tbody>
<tr><td>Leave one year out, all years (the first site's test)</td><td class="num">{q(c, 'drivers.loyo_cv', fmt_int(loyo['n']))}</td><td class="num">{q(c, 'drivers.loyo_cv', fmt_num(loyo['skill_pct_mse'], 1) + '%')}</td><td class="num">{q(c, 'drivers.loyo_cv', fmt_num(loyo['oos_r2'], 3))}</td></tr>
<tr><td>Forward in time: fit on earlier years, predict 2005-2020</td><td class="num">{q(c, 'drivers.forward_cv', fmt_int(fwd['n']))}</td><td class="num">{q(c, 'drivers.forward_cv', fmt_num(fwd['skill_pct_mse'], 1) + '%')}</td><td class="num">{q(c, 'drivers.forward_cv', fmt_num(fwd['oos_r2'], 3))}</td></tr>
<tr><td>Leave one year out, usable reporting years only</td><td class="num">{q(c, 'drivers.loyo_cv_masked', fmt_int(lm['n']))}</td><td class="num">{q(c, 'drivers.loyo_cv_masked', fmt_num(lm['skill_pct_mse'], 1) + '%')}</td><td class="num">{q(c, 'drivers.loyo_cv_masked', fmt_num(lm['oos_r2'], 3))}</td></tr>
<tr><td>Forward in time, usable reporting years only</td><td class="num">{q(c, 'drivers.forward_cv_masked', fmt_int(fm['n']))}</td><td class="num">{q(c, 'drivers.forward_cv_masked', fmt_num(fm['skill_pct_mse'], 1) + '%')}</td><td class="num">{q(c, 'drivers.forward_cv_masked', fmt_num(fm['oos_r2'], 3))}</td></tr>
</tbody></table></div>
<ul class="tight">
<li><strong>Forward in time.</strong> Leaving one year out lets the model learn from later years. Predicting each year from earlier years only, as a forecaster would have to, the skill falls from {fmt_num(loyo['skill_pct_mse'], 1)}% to {fmt_num(fwd['skill_pct_mse'], 1)}%, and some years are worse than the baseline.</li>
<li><strong>Reporting breaks.</strong> Of the model's 20 worst misses, {q(c, 'drivers.misses_vs_coverage', fmt_pct(mc['top20_unusable_share'], 0))} fall in state-years outside the usable reporting window, against {q(c, 'drivers.misses_vs_coverage', fmt_pct(mc['all_rows_unusable_share'], 0))} of all rows. Several of the first site's "worst misses" were years whose records are incomplete, not years the climate failed to explain. Dropping those years raises leave-one-year-out skill to {fmt_num(lm['skill_pct_mse'], 1)}%.</li>
<li><strong>Both together.</strong> On usable years only, the forward test gives {fmt_num(fm['skill_pct_mse'], 1)}%: the cleaner panel has less between-state noise for the model to explain, and the baseline is harder to beat. The honest summary is that seasonal climate explains a real but modest part of year-to-year burned area, in the range of 10-20% of the error left by knowing a state's usual year.</li>
</ul>
{B.chart_div('d-forward')}
<div class="table-wrap"><table><thead><tr><th>First site's worst misses</th><th class="num">Actual acres</th><th class="num">Predicted</th><th>Reporting status</th></tr></thead><tbody>{miss_rows}</tbody></table></div>

<h2>State by state</h2>
<p>Across {q(c, 'drivers.spearman_summary', str(ss['n_qualifying_states']))} states with enough fire, the median correlation between summer drought and acres burned is {q(c, 'drivers.spearman_summary', fmt_num(ss['median_rho'], 2))}; on usable years only it is {q(c, 'drivers.spearman_usable_only', fmt_num(su['median_rho'], 2))} across {q(c, 'drivers.spearman_usable_only', str(su['n_states']))} states.
Colorado is among the strongest ({q(c, 'drivers.spearman_by_state', fmt_num(sp['CO'], 2))}; {q(c, 'drivers.spearman_usable_only', fmt_num(su['CO'], 2))} on usable years). Arizona ({q(c, 'drivers.spearman_by_state', fmt_num(sp['AZ'], 2))}) and Nevada ({q(c, 'drivers.spearman_by_state', fmt_num(sp['NV'], 2))}) show no significant link in either version:
in these deserts a wet winter grows the grass that carries the next fire, so dry years are not the big fire years. That reading, from the first site, holds.</p>
{B.chart_div('d-spearman')}
<p class="small">Sources: {esc(cv(c, 'drivers.definition'))} Code: <a href="{B.REPO_URL}/blob/main/analysis/drivers.py">analysis/drivers.py</a>; write-up: <a href="{B.DOCS_URL}/findings/nifc_and_drivers.md">docs/findings/nifc_and_drivers.md</a>.</p>
"""
    return B.layout(ctx, 'drivers.html', 'Drought · ' + B.SITE_TITLE, body, DRIVERS_JS,
                    description='How much seasonal drought, heat and rain explain year-to-year burned area by state, replicated and tested forward in time.')


# =========================================================================== audit of v1

AUDIT = [
    ('Map page: California has the "fewest fires of any era" in 2017-2020, and the national count "falls to about 300,000" in 2017-2020',
     'The last era is four years (2017-2020); the others are five. Totals were compared across unequal eras, so the last era looks low by about a fifth for that reason alone.',
     'Corrected', 'Counts are per year, inside each state\'s usable window. See any state brief.'),
    ('"Fewer fires, not smaller ones", and other count-based era comparisons',
     'FPA FOD counts carry reporting breaks: 30 of the 48 states with 1,000+ records have at least one. A falling count can be a state leaving a reporting system.',
     'Corrected', 'Count trends are made only inside usable windows; the national trend uses acres. <a href="trends.html#coverage">Coverage</a>.'),
    ('Drought model: "+17.1% vs climatology", leave-one-year-out',
     'Reproduced exactly. Leave-one-year-out trains on later years; a forward-in-time test gives 14.7%. Three of its five worst misses fall in years with reporting breaks.',
     'Revised', '<a href="drivers.html">Drought</a> shows all four versions of the test.'),
    ('Drought vs acres, per-state Spearman (Colorado -0.72, Arizona and Nevada near zero)',
     'Reproduced exactly. On usable years only, the median moves from -0.45 to -0.48, Colorado to -0.62, Arizona and Nevada unchanged; two states change significance.',
     'Holds', '<a href="drivers.html">Drought</a>.'),
    ('100 largest fires',
     'Complexes were listed as several rows: August Complex (#3 and #26), East Amarillo (#10, #13), Rodeo-Chediski (#49, #80), Taylor, Central and Solstice complexes in Alaska. 100 rows were 92 incidents.',
     'Corrected', '<a href="largest.html">Largest fires</a>, grouped by incident with components listed.'),
    ('"The highs are higher. So are the lows." (NIFC 1983-2025)',
     'Reproduced exactly and holds on rolling tests. The floor shift is partly set by 1983-84, whose fire counts suggest incomplete reporting: 2.02x instead of 2.34x from 1986.',
     'Holds, with caveat', '<a href="trends.html#national">Trend</a>.'),
    ('Home page density "heat field"',
     'A smoothed heat surface hides how many fires sit under each colour.',
     'Replaced', 'The <a href="explore.html">map</a> draws every fire and gives the count around any point.'),
    ('"Every number on this page is audited"',
     'The errors above got through. The claim was about process, not a check a reader could repeat.',
     'Replaced', 'Every number links to its ledger entry (definition, n, source), and an automated test checks the page text against the ledger.'),
]


def page_audit(ctx: dict) -> str:
    rows = ''.join(f'<tr><td>{esc(a)}</td><td>{esc(b_)}</td><td><span class="verdict {"holds" if v.startswith("Holds") else ("revised" if v == "Revised" else ("wrong" if v == "Corrected" else "new"))}">{esc(v)}</span></td><td>{r}</td></tr>' for a, b_, v, r in AUDIT)
    body = f"""
<header class="page-head"><h1>Audit of the first public site</h1>
<p class="lede">The first public version of this project (us-wildfires.netlify.app) set a high bar: national totals to 2025, a drought analysis, a map of every fire, and a habit of featuring its own corrections. This version rebuilt each of its analyses from the original sources, replicated the published numbers, and then tested them more strictly. This page lists what held and what changed.</p></header>
<div class="table-wrap"><table><thead><tr><th>Claim on the first site</th><th>What the audit found</th><th>Verdict</th><th>Where it is now</th></tr></thead><tbody>{rows}</tbody></table></div>
<p>Replications: {q(ctx['claims'], 'nifc.v1_replication', 'national totals')} and {q(ctx['claims'], 'drivers.v1_replication', 'drought analysis')} (click for every number compared). Full write-up: <a href="{B.DOCS_URL}/review/V1_SITE_AUDIT.md">docs/review/V1_SITE_AUDIT.md</a>.</p>
<h2>What carries over, with credit</h2>
<ul class="tight"><li>The NIFC national series and its era table.</li><li>The drought analysis and the fuel-limited reading of Arizona and Nevada.</li><li>A map of every fire, redrawn from the same record as every other number here.</li><li>The literature framing and the practice of stating corrections up front.</li></ul>
"""
    return B.layout(ctx, 'audit.html', 'Audit · ' + B.SITE_TITLE, body, nav_page='methods.html',
                    description='What held and what changed when the first public wildfire site was rebuilt and re-tested.')


def downloads_section(ctx: dict) -> str:
    files = ctx.get('downloads', [])
    if not files:
        return ''
    items = ''.join(f'<li><a href="downloads/{esc(f)}">{esc(f)}</a> <span class="muted small">{esc(d)}</span></li>' for f, d in files)
    return f'<h2 id="downloads">Downloads</h2><p>Every table behind the site, as CSV, and every claims ledger as JSON. The per-state calendars are linked from each state brief.</p><ul class="tight">{items}</ul>'


# =========================================================================== prediction: WFIGS forward test

def wfigs_section(ctx: dict) -> str:
    c = ctx['claims']
    if 'wfigs.forward_test' not in c:
        return ''
    ft = cv(c, 'wfigs.forward_test')
    o = ft['overall']
    boot = ft['bootstrap_pr_auc_95ci_1000_resamples']
    rpy = cv(c, 'wfigs.rows_per_year')
    comp = cv(c, 'wfigs.comparison_fpa_fod_2016_2020')
    miss = cv(c, 'wfigs.share_missing_cause')
    ab = claim_or(c, 'wfigs.forward_test_ablation')
    m, lk = o['model_hgb_reduced'], o['lookup_cell_month_climatology']
    wins = sum(1 for y, v in ft['per_year'].items() if isinstance(v, dict) and 'model_hgb_reduced' in v
               and v['lookup_cell_month_climatology']['pr_auc'] > v['model_hgb_reduced']['pr_auc'])
    per_year = [y for y, v in ft['per_year'].items() if isinstance(v, dict) and 'model_hgb_reduced' in v]
    mean_rows = sum(rpy.values()) / len(rpy)

    def ci(d):
        return f'[{fmt_num(d["low"], 3)}, {fmt_num(d["high"], 3)}]'

    ab_html = ''
    if ab:
        rows = [('Location and season', 'location_season'), ('+ cause', 'location_season_cause'),
                ('+ cause + owner (the pre-specified model)', 'location_season_cause_owner'), ('Lookup: cell x month', 'lookup_cell_month')]
        trs = ''.join(
            f'<tr><td>{esc(lab)}</td><td class="num">{q(c, "wfigs.forward_test_ablation", fmt_num(ab[k]["fpa_fod_2019_2020"]["pr_auc"], 3))}</td>'
            f'<td class="num">{q(c, "wfigs.forward_test_ablation", fmt_num(ab[k]["wfigs_2021_2025"]["pr_auc"], 3))}</td>'
            f'<td class="num">{q(c, "wfigs.forward_test_ablation", fmt_pct(ab[k]["wfigs_2021_2025"]["top_decile_capture"], 0))}</td></tr>' for lab, k in rows)
        osh = ab['owner_class_share']
        ab_html = f"""
<h3>Why it failed: one field means different things in the two systems</h3>
<p>This check was run <em>after</em> seeing the result above, so it explains the failure rather than rescuing the model. The same model was refitted with fewer inputs and scored twice: forward in time inside the FPA FOD (2019-2020), and across to WFIGS.</p>
<div class="table-wrap"><table><thead><tr><th>Inputs</th><th class="num">PR-AUC, FPA FOD 2019-2020</th><th class="num">PR-AUC, WFIGS 2021-2025</th><th class="num">WFIGS top 10% capture</th></tr></thead><tbody>{trs}</tbody></table></div>
<p>Inside the FPA FOD the owner field helps a little. Across systems it breaks the model: {q(c, 'wfigs.forward_test_ablation', fmt_pct(osh['fpa_fod_2010_2020'].get('Missing', 0), 0))} of FPA FOD training fires have no owner recorded, and those rarely become large, because they come mostly from local reporting systems that record many small fires.
WFIGS records an owner for almost every fire ({q(c, 'wfigs.forward_test_ablation', fmt_pct(osh['wfigs_2021_2025'].get('Missing', 0), 2))} missing). Without the owner field, the model ranks 2021-2025 fires better than the lookup (PR-AUC {q(c, 'wfigs.forward_test_ablation', fmt_num(ab['location_season']['wfigs_2021_2025']['pr_auc'], 3))}, interval {q(c, 'wfigs.forward_test_ablation', ci(ab['location_season']['wfigs_2021_2025']['pr_auc_95ci']))}).</p>
<p class="note">This is the model card's warning made concrete: inputs that record how a reporting system codes a fire, such as owner and agency, can carry much of a model's apparent skill and do not transfer to another system. The full model leans on the same kind of inputs, which is one more reason its scores are shown as ranks only.</p>"""

    return f"""
<h2 id="wfigs">After 2020: a test on 2021-2025 fires</h2>
<p>The FPA FOD ends in 2020. For later years the interagency WFIGS incident service records {q(c, 'wfigs.comparability_verdict', fmt_int(mean_rows) + ' fires a year')}, about half the FPA FOD's {q(c, 'wfigs.comparison_fpa_fod_2016_2020', fmt_int(comp['fpa_fod_2016_2020']['mean_rows_per_year']))} a year in 2016-2020, because it misses many small fires handled by local departments. Cause is missing for {q(c, 'wfigs.share_missing_cause', fmt_pct(miss, 0))} of WFIGS fires.
It is a different reporting system, so this site never joins it to the FPA FOD series. It does allow one honest test: train on the FPA FOD, score fires from years the model could not have seen.</p>
<p>The 96-input model cannot be scored on WFIGS, because its fuels, terrain and weather inputs come from a companion dataset that stops in 2020. The test therefore uses a small model with the inputs both systems share: location, day of year, month, cause class and owner class. It was specified before the test was run.</p>
<div class="table-wrap"><table><thead><tr><th>WFIGS 2021-2025, lower 48 ({fmt_int(m['n'])} fires, {fmt_int(m['n_positive'])} reached 300 acres)</th><th class="num">PR-AUC [95%]</th><th class="num">ROC-AUC</th><th class="num">Top 10% of scores capture</th></tr></thead><tbody>
<tr><td>Lookup: 1-degree cell x month (from FPA FOD 2010-2020)</td><td class="num">{q(c, 'wfigs.forward_test', fmt_num(lk['pr_auc'], 3))} {q(c, 'wfigs.forward_test', ci(boot['lookup_cell_month_climatology']))}</td><td class="num">{q(c, 'wfigs.forward_test', fmt_num(lk['roc_auc'], 3))}</td><td class="num">{q(c, 'wfigs.forward_test', fmt_pct(lk['top_decile_capture'], 0))}</td></tr>
<tr><td>Small model, pre-specified inputs</td><td class="num">{q(c, 'wfigs.forward_test', fmt_num(m['pr_auc'], 3))} {q(c, 'wfigs.forward_test', ci(boot['model_hgb_reduced']))}</td><td class="num">{q(c, 'wfigs.forward_test', fmt_num(m['roc_auc'], 3))}</td><td class="num">{q(c, 'wfigs.forward_test', fmt_pct(m['top_decile_capture'], 0))}</td></tr>
</tbody></table></div>
<p><strong>The pre-specified model failed.</strong> It ranked 2021-2025 fires worse than the lookup in {q(c, 'wfigs.forward_test', f'{wins} of {len(per_year)}')} years.</p>
{ab_html}
<p class="small">Source: {q(c, 'wfigs.source_service', 'WFIGS Incident Locations, full history layer')}, wildfires discovered 2021-2025, fetched {esc(cv(c, 'wfigs.access_date'))}. Code: <a href="{B.REPO_URL}/blob/main/analysis/wfigs.py">analysis/wfigs.py</a>; write-up: <a href="{B.DOCS_URL}/findings/wfigs_2021_2025.md">docs/findings/wfigs_2021_2025.md</a>.</p>
"""
