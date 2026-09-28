# The public site: how it is generated, deployed and extended

The site in `site/` is a static, dependency-free rendering of the committed analysis record. It is
written by `scripts/build_site.py` from `outputs/claims*.json`, `outputs/cells_1deg.csv`,
`outputs/coverage.json` and `outputs/figures/*.png`. Nothing on the site is typed in by hand except
prose; every number is a claim with a definition and an n, and the script fails if a claim it
needs is missing from the ledger.

## Version 2 (2026-09-26)

Version 2 rebuilds the first public site (us-wildfires.netlify.app, audited in `docs/review/V1_SITE_AUDIT.md`)
on this repository's ledger, for three audiences: prevention planners, land managers, and the public, reporters
and officials. `scripts/build_site.py` still writes every page; the version 2 pages and sections live in
`scripts/site_v2.py`, the map renderer in `scripts/site_assets/console.js`, and the point files come from
`scripts/build_points.py`.

| Page | Content | Main claims |
|---|---|---|
| `index.html` Story | the map, three audience routes, seven findings with verdicts | several |
| `explore.html` Map | the full map console | `points_meta.json` |
| `trends.html` Trend | NIFC 1983-2025 national series and era table, then the FPA FOD trends and coverage | `nifc.*`, `year.*`, `class_g.*` |
| `causes.html` Seasons and causes | prevention calendar (region x month x general cause), 4 July, debris season, cause-missing by state, then the v1 cause charts | `calendar.*`, `cause.*`, `season.*` |
| `places.html`, `place-XX.html` | state comparison map and table; one printable brief per state (52) | `places.state.XX`, `drivers.*`, `wfigs.per_state_2021_2025` |
| `conservation.html` Protected lands and losses | unchanged from v1 of this repo | `padus.*`, `ics.*` |
| `largest.html` | the 250 largest incidents, grouped, searchable | `incidents.*` |
| `drivers.html` Drought | replication of the first site's drought model and three stricter tests | `drivers.*` |
| `model.html` Prediction | the ranking model, plus the WFIGS 2021-2025 forward test and its diagnostic | `model.*`, `wfigs.*` |
| `methods.html`, `audit.html` | ledger, downloads, errata; audit of the first site | all |

`geography.html` and `ownership.html` are still built and linked from the methods and places pages, but they
are not in the top navigation.

**Map console.** Every FPA FOD fire is one 8-byte record: projected x and y as uint16, plus a uint32 with year,
day of year, cause class, size class, PAD-US protection class, state and general cause. The layout is in
`site/data/points_meta.json`. The page first fetches `points_c_plus.bin` (fires of 10+ acres, 2.6 MB) and
fetches `points_a_b.bin` (1.98 million smaller fires, 15.8 MB) only when the reader asks. Filters run in the
vertex shader. Counts beside the map are computed in JavaScript from the same bits, and a click gives the
counts in a square around the point. No library is used: WebGL 1 with a 2D canvas for the state outlines.
Without WebGL the console says so, and every other page still works.

**Not committed:** `site/data/points_*.bin`. They encode every record's location and attributes, so they are
derived data and follow the repository's no-data-in-git rule. They are rebuilt by `python scripts/build_site.py`,
which needs `data/fires.parquet` and the PAD-US join. A deploy is therefore made from a local build (see Deploy)
and not by Netlify building from git.

**Per-state claims** (`places.state.XX`, about 16 KB each) are not in `site/data/claims.js`. Each state page
loads its own `site/data/place_XX.js`, so the data every page loads stays under 1 MB.

## Generate

```
python scripts/build_site.py
```

Run from the repo root with the project venv. This needs `requirements.txt` plus `requirements-analysis.txt`
(pyproj for the map projection) and the local data files. It rebuilds `site/` from scratch in about 15
seconds and prints the page count, the data size and which ledger files it found. Commit `site/`, except the
point files, with the `outputs/` files that produced it. `tests/test_site_claims.py` checks every number on the
generated pages against the ledger.

What it writes:

| Path | Content |
|---|---|
| `site/*.html` | one page per entry in `NAV` (index, trends, causes, geography, ownership, conservation, model, methods) |
| `site/assets/site.css` | the one stylesheet: colour tokens for light and dark, layout, chart cards, tables |
| `site/assets/site.js` | shared helpers: theme, definition popovers, chart cards, CSV export, table view, sortable tables |
| `site/data/meta.js` | `window.WF_DATA.meta`: generation date, data hash, repo URL, ledger files found and missing |
| `site/data/claims.js` | `window.WF_DATA.claims`: every claim from every `outputs/claims*.json`, keyed by id, plus `_file` |
| `site/data/cells.js` | `window.WF_DATA.cells`: the 1-degree cell table |
| `site/data/coverage.js` | `window.WF_DATA.coverage`: state-by-year counts, usable windows and break years (only when the input exists) |
| `site/figures/*.png` | copies of `outputs/figures/*.png`, linked as "Static PNG" under the matching interactive chart |

Data is shipped as JS files that assign to `window.WF_DATA` rather than as JSON fetched at run
time, so the pages work from `file://` as well as from Netlify. Keep `site/data/` under 5 MB and
the whole site under 10 MB; the script warns when either is exceeded (today: 0.6 MB and 7.6 MB, of which 4.6 MB is Plotly).

Plotly.js 2.35.2 (MIT, license in `scripts/vendor/PLOTLY_LICENSE`) is served from the site itself:
the script copies `scripts/vendor/plotly-2.35.2.min.js` to `site/vendor/plotly.min.js`, and the US
map outline (`scripts/vendor/usa_110m.json`, from Plotly's topojson set) is preloaded as
`window.PlotlyGeoAssets` in `site/vendor/geo_assets.js`, so no page makes a third-party request and
the pages work from `file://`. If the vendored file is removed, the script falls back to
`https://cdn.plot.ly/plotly-2.35.2.min.js`. If the library fails to load, every chart card opens its
table view with a notice, so no number depends on it.

## Deploy to Netlify

1. In Netlify, "Add new site" > "Import an existing project" > pick the GitHub repo.
2. Build command: leave empty. Publish directory: `site`. (`netlify.toml` at the repo root sets
   both, plus cache and security headers, so the UI values only need to agree with it.)
3. Deploy. Every push to the default branch redeploys the committed `site/`; there is no build
   image to configure and no secrets, tokens or API keys anywhere on the site.

   Since version 2 a git-linked deploy does not work: `.gitignore`'s `data/` rule also matches `site/data/`, so
   none of the site's data files are committed (not only the map's point files), and every chart page would fail.
   Version 2 is deployed from a local build instead, with the Netlify CLI or
   the Netlify MCP deploy tool pointed at `site/`. The review deploy is the password-protected project
   `wildfire-record-review`. The public project `us-wildfires` is replaced only on the owner's explicit decision.

Because the site is generated locally and committed, a deploy is exactly what was reviewed in the
pull request. The regeneration step belongs in the same commit as the `outputs/` change that
motivated it; CI can check that `python scripts/build_site.py` leaves the working tree clean.

## Data contract: `outputs/claims*.json`

Every file matching `outputs/claims*.json` is loaded and merged into one ledger. Each file is a
JSON object keyed by claim id; each claim has exactly these fields (extra fields are kept and
shown in the ledger table):

```json
"class_g.acres_trend": {
  "value": {"kendall_tau": 0.433, "kendall_p": 0.00075, "theil_sen_slope": 177560.2, ...},
  "unit": "acres/yr",
  "definition": "Kendall tau and Theil-Sen slope of Class G acres per year, 1992-2020 (29 annual points)",
  "n": 4783,
  "note": "Class G is the size class least affected by the reporting caveat ...",
  "computed_at": "2026-09-25T20:36:46+00:00",
  "source": "analysis.descriptive"
}
```

- `value`: a number, a string, a list, or a nested object of the same. Objects keyed by year use
  string years (`"1992"`); objects keyed by month use `"1"`..`"12"` or `"Jan"`..`"Dec"` (both occur
  in the ledger today; new claims should use `"1"`..`"12"`).
- `unit`: `null`, `"acres"`, `"share"` (a fraction 0-1, rendered as a percentage), `"ratio"`,
  `"hours"`, `"days"`, `"acres/yr"`, `"fires/yr"`, `"rho"`, `"records"`, `"years"`.
- `definition`: the exact filter and formula, in words a reader can audit. This is what the
  popover shows when a number is clicked, so it has to stand on its own.
- `n`: the number of records behind the value (`null` only for definitions). Every chart card
  prints the largest n among its claims as "n = ...".
- `note`: caveat or reading aid, or `null`.
- `computed_at`: ISO timestamp; `source`: the module that computed it.

Ids are `prefix.name`. Prefixes in use: `overview`, `year`, `class_g`, `cause`, `season`, `geo`,
`owner`, `cont`, `ces`, `anom` (claims.json); `conservation`, `coverage`, `padus`, `ics`
(claims_conservation.json); `model` (claims_model.json, see below). A claim id that appears in
two files is taken from the later file in sorted order, with a warning.

Which page reads what:

| Page | Claims it requires | Optional claims it renders when present |
|---|---|---|
| index | `overview.*`, `cont.share_with_cont_date`, `class_g.acres_trend*`, `class_g.half_period_means`, `year.fires_trend`, `owner.fires_and_acres`, `owner.missing_share_fires`, `season.peak_month_by_region`, `geo.cells_1deg_summary`, `ces.spearman_mean_vs_median` | |
| trends | `year.fires_and_acres`, `year.fires_and_acres_peak`, `year.*_trend`, `year.*_share_by_size_class`, `class_g.*`, `anom.northeast_*` | coverage heatmap from `outputs/coverage.json` (or `coverage.fires_by_state_year` + `coverage.usable_window_by_state` + `coverage.break_years_by_state`) |
| causes | `cause.*`, `season.*`, `year.fires_by_size_class`, `year.acres_by_size_class`, `overview.missing_shares` | `cause.by_classification_by_region` ({region: {Human/Natural/Missing: {fires, acres}}}) replaces the transcribed review table |
| geography | `geo.*` and `outputs/cells_1deg.csv` | `geo.completeness_by_state` ({STATE: {share_cont_date, share_known_owner, share_known_cause}}) adds three columns to the state table |
| ownership | `owner.*`, `cont.*`, `ces.*`, `cause.by_classification`, `overview.missing_shares` | |
| conservation | none (page states that `claims_conservation.json` is absent) | `coverage.national_fires_by_year_all_vs_masked` and the `coverage.share_*`, `coverage.n_states*`, `coverage.window_length_years`, `coverage.rule` summary; `padus.by_gap_all_years`, `padus.share_fires_by_block_gap`, `padus.fires_by_block_gap`, `padus.missing_owner_assignment_all_years`, `padus.match_summary`, `padus.owner_agreement_*`, `padus.n_points`, `padus.join_definition`, `padus.source`; `ics.match_rate_by_size_class_2010_2020`, `ics.outcomes_by_cause`, `ics.outcomes_total`, `ics.structures_destroyed_by_region_cause`, `ics.structures_destroyed_distribution`, `ics.sample_n`, `ics.sample_definition`, `ics.n_incidents`, `ics.fod_rows_matched`, `ics.cause_agreement_share` |
| model | none (page states that the duration model was retired) | `model.*`, see the contract below |
| methods | `overview.*`, `geo.cells_1deg_file`, the `anom.verdict_*` claims, `class_g.five_lowest_years`, `cause.top_general_cause_by_size_class`, `ces.*` | the ledger table lists every claim from every file |

### `outputs/coverage.json` (state-by-year coverage)

Written by `analysis/coverage.py`. The site reads `rule` and `states`:
`states[STATE] = {region, n_records, fires: {year: count}, acres: {year: acres}, usable_window: [start, end], break_years: {year: ratio_to_prior_nonzero_year}, zero_years: [...]}`.
The trends page draws the heatmap (log10 count), marks break years with a cross and reports in
the hover whether the state-year is inside the usable window. The same data can instead be
supplied as ledger claims `coverage.fires_by_state_year`, `coverage.usable_window_by_state`,
`coverage.break_years_by_state` and `coverage.rule`.

### `outputs/claims_model.json` (the Prediction page)

The model page renders from these claims; each is optional and the page shows a marked
placeholder for any that is absent. All metrics are on the time-split test set, and every
interval is a 95% bootstrap interval computed the same way for the model and its baselines.

| Claim id | `value` | Notes |
|---|---|---|
| `model.card` | `{name, version, target, horizon, features: [...], train_years, test_years, run_date, experiment_id}` | `target` is a sentence, e.g. "probability that an ignition reaches 300 acres (FIRE_SIZE >= 300)"; `experiment_id` links to docs/EXPERIMENTS.md |
| `model.metrics` | `{metric_names: ["auprc", "brier", "log_loss", "precision_at_top_1pct", ...], rows: [{model: "Gradient boosting", baseline: false, metrics: {auprc: [point, lo, hi], ...}}, {model: "Base rate (predict the training rate)", baseline: true, ...}, {model: "Region x month x cause lookup", baseline: true, ...}]}` | `n` = test fires; `note` = the interval method ("1,000 bootstrap resamples of the test fires, seed 42"). Baseline rows are always present; the page never shows the model without them |
| `model.reliability` | `{bins: [{pred_lo, pred_hi, mean_pred, obs_rate, n}]}` | 10 or 20 equal-count or equal-width bins; bins with n < 100 are drawn but the table marks them |
| `model.pr_curve` | `{base_rate, points: [{threshold, precision, recall, n_flagged}]}` | 20-50 points; `base_rate` is the positive share of the test set and is drawn beside the curve |
| `model.coverage` | `{text, train_share_of_period, test_share_of_period, by_state: {STATE: share}, excluded: "..."}` | `text` is the sentence shown in the coverage note ("Trained on ... fires from ... to ...; Texas ...; see the coverage heatmap"); `by_state` is the share of the state's fires in the period that met the sample rule |
| `model.base_rates` | `{rows: [{region, month, cause, n, rate}]}` | the lookup table a reader can use without the model; rows with n < 100 should carry `rate: null` and the `note` should say so |

Wording rules on that page (from the responsible-AI review): no bare number, base rate beside
every lift, n everywhere, intervals not "±", a reliability diagram not a residual scatter, a
coverage note on every view, baselines always visible, and neutral vocabulary ("expected",
"typical", "range"; never "risk", "danger", "safe").

## Rules every page follows

These come from the panel reviews (docs/review/panel-conservation.md (f), panel-rai.md (e),
panel-fire.md F1, F5) and are enforced by the shared helpers, so a new page gets them by using
`WF.chart` and the `q()` helper rather than raw HTML.

1. **Every chart shows n.** `WF.chart` prints "n = ..." in the card head from the claims it cites
   (or an explicit `n`). Hover text carries the n behind each bar, point or cell.
2. **No number without its definition one click away.** In Python, every number in prose is
   emitted through `q(claims, claim_id, text)` (or `qd(text, definition, source, n)` for the rare
   figure that is not yet a ledger claim). It renders a `button.q` whose popover shows id,
   definition, n, unit, note and source. Chart cards carry a "Definition" button and the claim ids.
3. **Base rates beside any lift.** A chart that shows a rate by group draws the all-group rate as
   a dashed line and states it in the caption (ownership: human share by owner; conservation:
   share reaching 300 acres by GAP status).
4. **Missing and undetermined categories are always visible.** The Missing owner row, the
   undetermined cause and the "not in PAD-US" group are always drawn, in the neutral gray token
   (`--missing`), and never dropped from a denominator without the chart saying so. Table rows for
   them carry `_missing: true` and are shaded.
5. **No kernel-density heat maps.** The map draws 1-degree cells at their centroids, colored only
   when the cell has at least 20 fires (hollow otherwise), with the rule stated in the legend.
6. **No red/green for magnitude.** Magnitude uses one blue ramp (`--seq-100` to `--seq-700`);
   categorical identity uses the fixed dataviz slot order (blue, orange, aqua, yellow, magenta,
   green); Human = slot 1, Natural = slot 2, undetermined = gray; regions take slots 1-6 in the
   order West, South, Northeast, Alaska, Hawaii/PR, Other.
7. **No "risk", "danger" or "safe" wording.** Use "share", "rate", "expected", "typical".
8. **Footer on every page** with the data hash prefix, the generation date, the ledger files used,
   a link to the repo docs and to this file. `layout()` adds it.
9. **Every chart offers CSV of its aggregated rows.** `WF.chart` takes `rows` and `columns`; the
   CSV starts with `#` comment lines that carry the title, the definition string, the claim ids,
   n, the data hash and the generation date (read with `pandas.read_csv(..., comment='#')`).
10. **A table view for every chart** (the "Table" button) so no value is reachable only by hover
    and the light-mode palette's low-contrast slots are always relieved.
11. **One axis per chart.** Two measures of different scale are two charts side by side
    (`.grid2`), never a dual axis.
12. **Dark and light** come from the same tokens: `prefers-color-scheme` plus a `data-theme`
    toggle that wins when set (stored in localStorage, wrapped in try/catch). Plotly layouts read
    the computed tokens at render time and re-render on theme change.
13. **Mobile first:** 16 px gutters, no horizontal scroll (tables scroll inside `.table-wrap`),
    charts are responsive.
14. **Personal details:** the author's name and the repo URL may appear; nothing else.

## Adding a page

1. Add the entry to `NAV` and a `page_<name>(ctx)` function that returns `layout(ctx, file, title,
   body, page_js)`.
2. Build prose with `q()` for every number. Put charts in `chart_div('id')` and define them in the
   page's JS with `WF.chart({el, title, sub, claims, rows, columns, build(t) -> {data, layout},
   caption, staticImg, height})`. `t` is the token set (`t.series[i]`, `t.seq[i]`, `t.missing`,
   `t.gray`, `t.surface`, `t.ink2`, `t.grid`).
3. Guard every optional claim with `if (C['claim.id'])` in JS and `if 'claim.id' in c` in Python,
   and render a `placeholder()` that names the missing claim.
4. Run the build, open the page at 1280 px and 390 px in both colour schemes, and check the
   console for errors before committing.

## Verification done for the first release

Rendered every page with headless Chromium at 1280 px and 390 px in light mode and at 1280 px in
dark mode: no horizontal overflow on any page, no JavaScript errors, all charts rendered when the
CDN answered, and the table-view fallback engaged when it did not.
