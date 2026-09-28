# Backlog

Source of truth for the improvement program. Every story is mirrored as a GitHub issue by `scripts/sync_backlog.py` (labels `epic:*`, `P0`/`P1`/`P2`, `type:*`; one milestone per epic). Findings are cited by panel report (`docs/review/PANEL_REPORT.md`, "PR-n" = surviving finding n), persona review (`panel-ml` etc.), reproduction (`R`), research (`docs/research/DATA_SOURCES.md` = DS, `LITERATURE.md` = LIT) or experiment log entry (`E-nnn`).

Priorities: **P0** must be done before the repo goes public. **P1** next. **P2** later. Sizes: S under a day, M a few days, L a week or more.

Status as of 2026-09-27. v2 merged to main via #69 on 2026-09-26, and the stacked PRs #2-#5 and #60-#65 were closed as shipped. #70 (site v2) is the only open PR. "In Review" means built and waiting in an open PR or on an owner decision; issues close when their work reaches main.

---

## Epic 1: Reproducibility foundation

Pinned environment, verified data, tests, CI, and a `src/` that can be reused without silent corruption. Panel: PR-10, PR-11, PR-12, PR-16; `panel-repro` throughout.

### [S-1.1] Pin the environment, hash the data, regenerate every README number
- Status: Done
- Issue: #13
- Priority: P0 · Size: S · Depends: none
- Description: `requirements.txt` pinned, `requirements.lock`, `data.sha256`, `docs/DATA_VERSION.md`, `scripts/reproduce.py` that checks the hash and reproduces every README number with same-split baselines (R).
- Acceptance: `python scripts/reproduce.py --part all` reproduces n = 630,053, CV RMSE 6.3322, test RMSE 6.5957, MAE 1.3768 and prints predict-zero MAE 1.094.
- Key files: `scripts/reproduce.py`, `data.sha256`, `docs/DATA_VERSION.md`, `docs/review/REPRODUCTION.md`

### [S-1.2] Parquet cache of the Fires table
- Status: Done
- Issue: #14
- Priority: P0 · Size: S · Depends: S-1.1
- Description: `scripts/build_cache.py` writes a typed `data/fires.parquet` with parsed timestamps and hour-level duration, recording the database hash in its metadata, so analyses stop re-querying the 1 GB SQLite file.
- Acceptance: cache builds in under 2 minutes; metadata `db_sha256` matches `data.sha256`; second run is a no-op.
- Key files: `scripts/build_cache.py`

### [S-1.3] Tests on a synthetic database, and CI
- Status: Done
- Issue: #15
- Priority: P0 · Size: M · Depends: S-1.2
- Description: pytest suite (66 tests) on a 300-row synthetic SQLite fixture with the real column names and types; GitHub Actions on push and PR; no data download in CI. Tests named `_DEFECT` pin current behaviour that should change (`panel-repro` T1, C1-C9).
- Acceptance: `pytest -q` green locally and in Actions on PR #2 (it is).
- Key files: `tests/`, `.github/workflows/ci.yml`, `pytest.ini`, `docs/findings/tests_summary.md`

### [S-1.4] Fix the silent-corruption paths in `src/` and the download script
- Status: Done · PR #61
- Issue: #16
- Priority: P0 · Size: M · Depends: S-1.3
- Description: `load_data` raises instead of `sys.exit` and orders rows by `FOD_ID`; fixed cause category list so the one-hot schema is stable; leap-aware day-of-year angle; no `fillna(0)` on coordinates; NaN and negative durations counted separately; `n_jobs` from one setting; plots to an `out_dir`; metrics returned as a dict; download to `.part`, verify `Content-Length` and SHA-256, resume, select the zip member by name (PR-10, PR-12, PR-16; `panel-repro` C1-C10, P1-P4; `panel-ml` 11).
- Acceptance: all `_DEFECT` tests rewritten to assert the fixed behaviour and green; `reproduce.py` re-run and the new numbers logged as E-009 next to E-001 with the difference explained; `requirements.lock` regenerated from the venv and includes `pyarrow` and `duckdb`.
- Key files: `src/data_loader.py`, `src/features.py`, `src/train_model.py`, `scripts/download_data.py`, `requirements.txt`, `requirements.lock`, `docs/EXPERIMENTS.md`

### [S-1.5] Retire or re-execute the notebook, and regenerate `docs/img`
- Status: Done · PR #65
- Issue: #17
- Priority: P0 · Size: S · Depends: S-1.4
- Description: the committed figures are byte-identical to an out-of-order notebook run on Python 3.14.2 (PR-11; `panel-repro` N1-N4). Either delete the notebook and point to `run_pipeline.py`, or strip outputs and re-execute top to bottom on the pinned interpreter. Replace `docs/img/*` with figures written by `reproduce.py`, captioned with run date and data hash.
- Acceptance: no committed figure lacks a generating script; the notebook, if kept, has sequential execution counts and the pinned kernel.
- Key files: `notebooks/wildfire_duration_model.ipynb`, `docs/img/`, `scripts/reproduce.py`

### [S-1.6] Claims-ledger test: every number in the README and the site traces to a claim
- Status: Done · PR #65
- Issue: #18
- Priority: P0 · Size: M · Depends: S-5.1, S-7.1, S-7.2
- Description: a test that parses the README and the generated site for numbers tagged with claim ids and asserts they equal the value in `outputs/claims*.json` (`panel-repro` test plan item 6). Prevents the drift that produced the unverified 7.05 and the phantom Arkansas spike.
- Acceptance: test fails when a README number is edited by hand; passes on the rewritten README.
- Key files: `tests/test_claims_ledger.py`, `README.md`, `scripts/build_site.py`

### [S-1.7] Installable package layout
- Status: Open
- Issue: #19
- Priority: P1 · Size: M · Depends: S-1.4
- Description: `pyproject.toml`, `analysis/` as the single package (absorbing `src/`), remove the three `sys.path` hacks and the duplicate module names (`panel-repro` D7, section d).
- Acceptance: `pip install -e .` then `python -m analysis.descriptive` works from any directory; no `sys.path` edits remain.
- Key files: `pyproject.toml`, `analysis/`, `src/`, `run_pipeline.py`, `scripts/`

### [S-1.8] Nightly golden-numbers job
- Status: Open
- Issue: #20
- Priority: P2 · Size: S · Depends: S-1.4
- Description: the full-CV reproduction takes 14 minutes on one core (`panel-repro` run record), too slow for every PR. A scheduled Actions job that downloads the data, checks the hash and asserts the E-009 numbers.
- Acceptance: nightly job green; failure opens an issue.
- Key files: `.github/workflows/nightly.yml`

---

## Epic 2: Honest evaluation

Baselines that match the target, forward-in-time and spatially blocked validation, a locked holdout, calibration, intervals, and documentation that says what the model is for and not for. Panel: PR-1, PR-3, PR-8, PR-9, PR-15.

### [S-2.1] Naive baselines on the same test rows
- Status: Done
- Issue: #21
- Priority: P0 · Size: S · Depends: S-1.1
- Description: predict-mean, predict-zero, per-cause median and mean scored on the original test rows (E-002). Result: the RF loses to predict-zero on MAE by 26%.
- Acceptance: E-002 table in `docs/EXPERIMENTS.md`.
- Key files: `scripts/reproduce.py`, `docs/EXPERIMENTS.md`

### [S-2.2] Temporal and spatial validation of the duration model
- Status: Done
- Issue: #22
- Priority: P0 · Size: M · Depends: S-2.1
- Description: forward-in-time split (train 2010-2017, test 2018-2020) and GroupKFold by 1-degree cell (E-004, E-005). Result: RMSE gain over the mean falls from 9% to 3% and is absent in 2018 (PR-1).
- Acceptance: E-004 and E-005 logged with per-year values.
- Key files: `docs/EXPERIMENTS.md`, `docs/review/panel-ml.md`

### [S-2.3] Locked holdout and evaluation protocol
- Status: Done
- Issue: #23
- Priority: P0 · Size: S · Depends: S-2.2
- Description: 2019-2020 holdout defined before any Phase D modelling, with the one exploratory look (E-008) disclosed; expanding-window temporal CV, spatial block check, required baselines and metrics (`panel-ml` d).
- Acceptance: the "Locked holdout" section exists in `docs/EXPERIMENTS.md` and every later model entry cites it.
- Key files: `docs/EXPERIMENTS.md`

### [S-2.4] Retire the duration regressor and document it as a negative result
- Status: Done · PR #65
- Issue: #24
- Priority: P0 · Size: S · Depends: S-7.1
- Description: the README's Part 2 is replaced by a short negative-result section citing E-001 to E-007: what was tried, why it fails (random-split artefact, loses to a constant on the typical fire, geography lookup), and the coverage gap (PR-1, PR-4, PR-9). Keep the code runnable for the record.
- Acceptance: README Part 2 contains no claim the ledger marks Refuted; the recall/precision table from `panel-rai` CRIT-1 appears under "Could this be an early warning? No."
- Key files: `README.md`, `docs/EXPERIMENTS.md`

### [S-2.5] Model card for the replacement model
- Status: Done · PR #63
- Issue: #25
- Priority: P0 · Size: S · Depends: S-4.1
- Description: `docs/MODEL_CARD.md` in the Mitchell et al. structure, filled from the skeleton in `panel-rai` Appendix E1, including the out-of-scope uses, factors, metrics with intervals, evaluation data, and the disclosed spent look (PR-3).
- Acceptance: every section filled; no `[TODO]` left except fields only Robyn can supply (contact).
- Key files: `docs/MODEL_CARD.md`

### [S-2.6] Bootstrap intervals on every reported metric
- Status: Done · PR #63
- Issue: #26
- Priority: P0 · Size: S · Depends: S-4.1
- Description: 1,000-resample bootstrap 95% intervals on all holdout metrics; the "± 0.13" fold std is never presented as an interval again (PR-8; `panel-rai` MAJ-1).
- Acceptance: every metric in the README, model card and site carries an interval or a fold range labelled as such.
- Key files: `analysis/large_fire.py`, `docs/MODEL_CARD.md`

### [S-2.7] Datasheet for the dataset
- Status: Open
- Issue: #27
- Priority: P1 · Size: S · Depends: S-5.2
- Description: `docs/DATASHEET.md` in the Gebru et al. structure from `panel-rai` Appendix E2, with the composition section carrying the coverage numbers by state, owner and reporter (PR-4, PR-5).
- Acceptance: all seven sections filled; coverage table matches `outputs/coverage.json`.
- Key files: `docs/DATASHEET.md`

### [S-2.8] Secondary target: P(containment declared 7+ days after discovery) with a hurdle structure
- Status: Open
- Issue: #28
- Priority: P1 · Size: M · Depends: S-4.1, S-6.1
- Description: the duration outcome that still shows skill (E-008: Brier skill 0.17) on the containment-date sample, with its coverage caveat, and on the ICS-209-PLUS subset where daily containment exists (LIT implications 3; `panel-fire` F2).
- Acceptance: evaluated under the locked protocol against climatology; coverage note on every table.
- Key files: `analysis/large_fire.py`, `docs/EXPERIMENTS.md`

### [S-2.9] Forward-in-time calibration with a regime indicator
- Status: Open
- Issue: #66
- Priority: P1 · Size: M · Depends: S-4.1
- Description: the large-fire model ranks well but its scores overstated the chance for top-ranked fires in 2019 (16.5% scored, 9.4% observed; Brier skill -0.85) after two large seasons (E-015). Add an input known at discovery that says what kind of year it is (season-to-date large-fire count, a drought index, or the seasonal outlook) and recalibrate on a rolling window; evaluate on a new holdout (2021+ via S-4.5), since 2019-2020 is spent.
- Acceptance: Brier skill against the base rate positive in every test year with an interval that excludes zero; reliability within 20% relative in every bin with 20+ large fires.
- Key files: `analysis/large_fire.py`, `docs/EXPERIMENTS.md`

---

## Epic 3: Weather and fuels

Weather, fuels and terrain at the point and day of discovery, and ablations showing what each adds over climatology. Panel: PR-9; `panel-fire` F7; DS source 1; LIT implications 1 and 7.

### [S-3.1] Build the FPA FOD-Attributes table for 2010-2020
- Status: Done · PR #63
- Issue: #29
- Priority: P0 · Size: M · Depends: S-1.2
- Description: download the annual CSVs from Zenodo (10.5281/zenodo.8381129, CC BY 4.0), verify the 100% FOD_ID join, keep about 80 documented columns, exclude every `*_5D_*` field (two post-discovery days), record hashes and null rates (DS source 1).
- Acceptance: `data/attributes_2010_2020.parquet` exists; join rate 100% per year; hashes in `docs/DATA_JOINS.md`; null-rate table in `outputs/model/`.
- Key files: `scripts/download_attributes.py`, `docs/DATA_JOINS.md`

### [S-3.2] Ablation: what weather, fuels, terrain and suppression context add over climatology
- Status: Done · PR #63 (result: same-day weather adds nothing measurable)
- Issue: #30
- Priority: P0 · Size: M · Depends: S-3.1, S-2.3
- Description: nested feature groups G0 (geography+season) to G6 (suppression context and a drawdown proxy) on the temporal folds; PR-AUC and Brier skill per group per fold. The panel showed geography alone ranks half of large fires into the top decile (E-008); this story answers whether weather changes that.
- Acceptance: ablation table in `docs/findings/large_fire_model.md` and `outputs/claims_model.json`; a plain sentence stating the gain (or lack of it) from same-day weather.
- Key files: `analysis/large_fire.py`, `docs/findings/large_fire_model.md`

### [S-3.3] Full 1992-2020 attributes table for descriptive context
- Status: Open
- Issue: #31
- Priority: P2 · Size: M · Depends: S-3.1
- Description: extend the build to all 29 years (10.1 GB download) so descriptive pages can show ERC percentiles and fuel types alongside ignitions.
- Acceptance: parquet for all years; site pages can filter by ERC percentile bin.
- Key files: `scripts/download_attributes.py`

### [S-3.4] LANDFIRE fuel model (FBFM40) at the ignition point
- Status: Open
- Issue: #32
- Priority: P2 · Size: M · Depends: S-3.1
- Description: the one fuel variable the Attributes file lacks (DS "after these three"); sample the 30 m raster in a 3x3 window per the LANDFIRE guidance.
- Acceptance: FBFM40 column joined for CONUS 2010-2020 fires; ablation re-run.
- Key files: `scripts/download_external.py`, `analysis/large_fire.py`

### [S-3.5] Alaska weather
- Status: Open
- Issue: #33
- Priority: P2 · Size: L · Depends: S-3.1
- Description: gridMET and the Attributes file cover CONUS only; Alaska holds 26% of Class G acres (`panel-fire` F4). ERA5-Land or the Alaska Fire Service's weather products are the candidates (DS weather section).
- Acceptance: an Alaska-inclusive model variant or a documented decision not to build one.
- Key files: `docs/research/DATA_SOURCES.md`

---

## Epic 4: Large-fire risk

The prediction piece practitioners can use: a calibrated probability that a new fire reaches 300 acres, evaluated forward in time against climatology. Panel: PR-1, PR-9; `panel-ml` c and d; `panel-fire` F7; `panel-conservation` question 10.

### [S-4.1] P(fire reaches 300 acres) under the locked protocol
- Status: Done · PR #63 (result: ranks well, not calibrated forward in time)
- Issue: #34
- Priority: P0 · Size: L · Depends: S-2.3, S-3.1
- Description: HistGradientBoosting on all CONUS fires 2010-2020 with the features in S-3.2; expanding-window temporal CV, GroupKFold spatial check, small tuning grid logged, isotonic calibration if needed, one final evaluation on 2019-2020 with bootstrap intervals, per-year, per-region and per-state values; grouped permutation importance; baselines (base rate, cell x month climatology, logistic, geography-only) in every table.
- Acceptance: E-010 onward in `docs/EXPERIMENTS.md`; `outputs/claims_model.json`; reliability, PR-curve, ablation and importance figures; the holdout touched once.
- Key files: `analysis/large_fire.py`, `docs/EXPERIMENTS.md`, `outputs/claims_model.json`

### [S-4.2] MTBS-mapped fire as a second label
- Status: Done · PR #63
- Issue: #35
- Priority: P0 · Size: S · Depends: S-4.1
- Description: `MTBS_ID` present is an outcome independent of reported `FIRE_SIZE` (DS adoption order 2; LIT implication 2). Report the same metrics for it.
- Acceptance: both labels in the results tables with their base rates and the West/East thresholds stated.
- Key files: `analysis/large_fire.py`

### [S-4.3] Area-of-applicability statement and per-state metrics
- Status: Done · PR #63
- Issue: #36
- Priority: P0 · Size: S · Depends: S-4.1
- Description: where the training data are thin or reporting differs (Texas coverage, missing-cause states, non-CONUS excluded) and what that means for use (LIT implication 6; PR-4).
- Acceptance: statement in the model card and on the site's model page; per-state table for the ten largest states.
- Key files: `docs/MODEL_CARD.md`, `docs/findings/large_fire_model.md`

### [S-4.4] Practitioner lookup table
- Status: Done · PR #64 (lookup table on the Prediction page)
- Issue: #37
- Priority: P1 · Size: S · Depends: S-4.1
- Description: the plain climatology a duty officer can read: P(300+ acres) by region x cause x month with n (`panel-fire` d question 2). Published as a CSV and a site table.
- Acceptance: table generated from `outputs/claims_model.json`; every cell shows n; cells under 100 fires greyed.
- Key files: `analysis/large_fire.py`, `scripts/build_site.py`

### [S-4.5] Forward test on post-2020 incidents
- Status: Open
- Issue: #38
- Priority: P2 · Size: L · Depends: S-4.1
- Description: NIFC WFIGS 2021+ incident locations as a true out-of-sample test (DS WFIGS section), with the caveat that the reporting population differs.
- Acceptance: metrics on 2021-2023 ignitions reported next to the 2019-2020 holdout.
- Key files: `scripts/download_external.py`, `analysis/large_fire.py`

### [S-4.6] Inference demo on the site
- Status: Won't do · the scores are not calibrated forward in time (E-015); revisit only if S-2.9 succeeds
- Issue: #39
- Priority: P2 · Size: M · Depends: S-4.1, S-7.4
- Description: only if the model shows skill over climatology: export the model (ONNX or a compact tree dump) and serve a "what does the model say for this place, date and weather" widget via a Netlify function, always beside the base rate and the calibration table (`panel-rai` e rules).
- Acceptance: widget shows probability, base rate, n for the bin, and the coverage note; no red/green.
- Key files: `site/`, `netlify/functions/`

### [S-4.7] Why the model loses to the lookup in the South
- Status: Open
- Issue: #67
- Priority: P1 · Size: S · Depends: S-4.1
- Description: on the holdout the model ranks Southern fires worse than a cell-by-month lookup (PR-AUC 0.111 against 0.121, 497 large fires) and is worst calibrated there (Brier skill -1.20), while it beats the lookup in Texas (E-015). Break the South down by state and reporting system; test whether local-reporter coverage breaks (`outputs/coverage.json`) or the cause-missing indicator explain it.
- Acceptance: a per-state table for the Southern states with n large fires, and a stated explanation or an honest "not explained"; the model card updated either way.
- Key files: `analysis/large_fire.py`, `docs/MODEL_CARD.md`

---

## Epic 5: Descriptive analysis in code

Every Tableau finding recomputed from the data with stated definitions, a coverage mask for the record itself, and the efficiency score retired. Panel: PR-2, PR-6, PR-7, PR-13, PR-14.

### [S-5.1] Port the descriptive findings to code with a claims file
- Status: Done
- Issue: #40
- Priority: P0 · Size: M · Depends: S-1.2
- Description: `analysis/descriptive.py` registers 95 claims with definition and n in `outputs/claims.json`; nine figures; a verdict per README Part 1 sentence (PR #3).
- Acceptance: `python -m analysis.descriptive` runs in under a minute; verdict table in `docs/findings/descriptive.md`.
- Key files: `analysis/descriptive.py`, `analysis/figures.py`, `outputs/claims.json`, `docs/findings/descriptive.md`

### [S-5.2] Coverage mask and coverage map
- Status: Done · PR #62
- Issue: #41
- Priority: P0 · Size: S · Depends: S-5.1
- Description: state x year record counts, break flags (>3x or <1/3 year-over-year, zero years), usable windows, reporter entry and exit, the 2020 IRWIN switch; a heatmap; a `coverage_ok(state, year)` rule used by every count trend (PR-2; `panel-fire` F1, d question 7).
- Acceptance: `outputs/coverage.json` and the heatmap exist; the site's trends page renders the map; no national count-per-year line appears without the mask.
- Key files: `analysis/coverage.py`, `outputs/coverage.json`

### [S-5.3] Retire the Control Efficiency Score; keep a stratified containment table
- Status: Done · PR #65
- Issue: #42
- Priority: P0 · Size: S · Depends: S-5.1, S-7.1
- Description: the score's ranking flips between mean and median (Spearman 0.09); within every size class the owner gap is a reporting convention (PR-6; `panel-fire` F3). The replacement is a descriptive median-hours-to-containment-declaration table by size class and reporting system, labelled as such.
- Acceptance: the score appears in the README only in the errata; the stratified table appears with its caveat.
- Key files: `README.md`, `analysis/descriptive.py`

### [S-5.4] Errata for the three anomalies
- Status: Done · PR #65
- Issue: #43
- Priority: P0 · Size: S · Depends: S-7.1
- Description: Arkansas June (does not exist; Arizona and Alaska peak in June), Texas December (one 2005 event in the first year of Texas A&M's compilation), Northeast 2010 (z = 0.98; a reporting series). What was claimed, what the check found, the probable mistake (PR-7; `panel-rai` MAJ-2).
- Acceptance: an "Errata" section in the README and on the site's methods page.
- Key files: `README.md`, `site/methods.html`

### [S-5.5] Prevention calendar
- Status: Open
- Issue: #44
- Priority: P1 · Size: S · Depends: S-5.2
- Description: human-caused ignitions and human-caused large fires by region x month x general cause with the undetermined share shown, on coverage-masked state-years (`panel-fire` d question 1; `panel-conservation` Table C).
- Acceptance: a figure and a claims section; the Fourth of July spike checked from DOY 185-186.
- Key files: `analysis/descriptive.py`

### [S-5.6] MTBS area-burned series as the reporting-independent trend
- Status: Open
- Issue: #45
- Priority: P1 · Size: M · Depends: S-6.3
- Description: MTBS perimeters give an area-burned series that does not depend on non-federal reporting (DS adoption order 2; LIT implication 8). Show it next to the Class G series.
- Acceptance: both series on the trends page with their definitions.
- Key files: `analysis/descriptive.py`, `scripts/download_external.py`

### [S-5.7] Document the 2020 reporting and cause-standard breaks
- Status: Open
- Issue: #46
- Priority: P1 · Size: S · Depends: none
- Description: FS-FIRESTAT and DOI-WFMI replaced by IA-IRWIN in 2020; cause standard updated August 2020 with recoding (`panel-fire` F1, e). Record in `docs/DATA_VERSION.md` and flag 2020 on every cause chart.
- Acceptance: paragraph in `DATA_VERSION.md`; 2020 annotated on cause charts.
- Key files: `docs/DATA_VERSION.md`, `analysis/figures.py`

---

## Epic 6: Conservation lens

Ignitions and large fires against protected areas, outcomes and communities, using the join keys the record already carries. Panel: PR-5; `panel-conservation` c, d, e; DS adoption order 2 and 3.

### [S-6.1] ICS-209-PLUS outcomes join
- Status: Done · PR #62
- Issue: #47
- Priority: P0 · Size: S · Depends: S-1.2
- Description: 33,494 fires carry the join id (80% of 2010-2020 fires over 300 acres). Structures destroyed and threatened, personnel, cost and evacuations by cause, owner class and region; top 25 fires by structures destroyed (`panel-conservation` Table G, e; DS ICS-209-PLUS).
- Acceptance: match rate by year and size class reported; claims in `outputs/claims_conservation.json`; hash in `docs/DATA_JOINS.md`.
- Key files: `scripts/download_external.py`, `analysis/conservation.py`, `docs/DATA_JOINS.md`

### [S-6.2] PAD-US protection status at the ignition point, and the ownership-gap fix
- Status: Done · PR #62
- Issue: #48
- Priority: P0 · Size: M · Depends: S-1.2
- Description: point-in-polygon of 2.3M ignitions into PAD-US 4.1; share of ignitions and acres by GAP status; human share by GAP status; top protected units by human-caused ignitions with peak months; agreement between PAD-US manager type and `OWNER_DESCR`, and what PAD-US assigns to the 46% with no recorded owner (PR-5; `panel-conservation` C2, d questions 1-2).
- Acceptance: `data/external/padus/fires_padus.parquet`; agreement matrix figure; claims registered.
- Key files: `analysis/conservation.py`, `docs/findings/conservation.md`

### [S-6.3] MTBS perimeters and severity on protected lands
- Status: Open
- Issue: #49
- Priority: P1 · Size: L · Depends: S-6.2
- Description: join on `MTBS_ID` (94% of Class G fires), overlay perimeters on GAP 1-2 polygons and, later, severity mosaics: area actually burned inside conservation lands, by cause and year (`panel-conservation` d questions 2, 4, 6).
- Acceptance: acres burned inside GAP 1-2 lands per year; caveat that points are not footprints.
- Key files: `scripts/download_external.py`, `analysis/conservation.py`

### [S-6.4] Distance to the wildland-urban interface
- Status: Open
- Issue: #50
- Priority: P1 · Size: M · Depends: S-6.2
- Description: SILVIS WUI 1990-2020 by census block; distance from ignition to the nearest WUI block using the vintage closest to the fire year; share of large fires within N km and its trend (`panel-conservation` d question 3; DS SILVIS).
- Acceptance: distance column for CONUS fires; a figure of share within 1 km and 5 km by year.
- Key files: `scripts/download_external.py`, `analysis/conservation.py`

### [S-6.5] Critical habitat overlay
- Status: Open
- Issue: #51
- Priority: P2 · Size: M · Depends: S-6.3
- Description: USFWS critical habitat polygons (398-418 MB shapefile); ignitions inside and, with MTBS, area burned inside (`panel-conservation` d question 6).
- Acceptance: table of species-habitat units by ignitions and burned area.
- Key files: `scripts/download_external.py`, `analysis/conservation.py`

### [S-6.6] Conservation page on the site
- Status: Done · PR #64
- Issue: #52
- Priority: P0 · Size: S · Depends: S-6.1, S-6.2, S-7.2
- Description: render `outputs/claims_conservation.json`: GAP-status shares, top units, human-ignition hotspots (eastern Oklahoma, Cumberland Plateau), ICS-209 outcomes, with the completeness strip and the "which decision does this inform" line per chart (`panel-conservation` f).
- Acceptance: page renders from the claims file; every chart shows n and a definition.
- Key files: `scripts/build_site.py`, `site/conservation.html`

---

## Epic 7: Communication

The README, the site, the figures, and a write-up, all generated from the same claims and saying exactly what the evidence supports. Panel: PR-3, PR-7, PR-8, PR-17; `panel-rai` e and f.

### [S-7.1] Rewrite the README to the claims ledger
- Status: Done · PR #65
- Issue: #53
- Priority: P0 · Size: M · Depends: S-4.1, S-5.2, S-6.2
- Description: the headline from `PANEL_REPORT.md` section 4; "what this data is and is not"; findings with claim ids and n; the coverage table; the negative result for the duration model; the new model's holdout table with intervals and out-of-scope uses; errata; data terms; how to run. Every Refuted sentence removed; every Weakened one restated (PR-3, PR-7; `panel-fire` e; `panel-rai` f; `panel-repro` e).
- Acceptance: S-1.6 passes; no sentence the ledger marks Refuted remains; the LA anecdote decision recorded as Robyn's.
- Key files: `README.md`

### [S-7.2] Static site generated from the claims files, published on Netlify
- Status: Done · PR #64
- Issue: #54
- Priority: P0 · Size: L · Depends: S-5.1
- Description: `scripts/build_site.py` writes `site/` (index, trends, causes, geography, ownership, methods, model, conservation) from `outputs/claims*.json`; `netlify.toml` publishes `site/` with no build step; every chart shows n, offers CSV, follows the ten uncertainty rules; completeness strip on every page (`panel-conservation` f; `panel-rai` e).
- Acceptance: site builds locally; Playwright screenshots at 1280 and 390 px with no console errors; under 10 MB.
- Key files: `scripts/build_site.py`, `site/`, `netlify.toml`, `docs/SITE.md`

### [S-7.3] Data terms and attribution
- Status: Done · PR #65
- Issue: #55
- Priority: P0 · Size: S · Depends: S-7.2
- Description: `docs/DATA_TERMS.md` with the Short 2022 citation, the statement that aggregates are project-derived, the USFS distribution-liability sentence, the FPA FOD-Attributes CC BY 4.0 and ICS-209-PLUS CC BY 4.0 attributions, and that the MIT license covers code only; footer on every site page (PR-17; `panel-repro` L1).
- Acceptance: file exists; footer present on every page; `LICENSE` untouched.
- Key files: `docs/DATA_TERMS.md`, `scripts/build_site.py`

### [S-7.4] Model page on the site
- Status: Done · PR #64
- Issue: #56
- Priority: P0 · Size: S · Depends: S-4.1, S-7.2
- Description: render `outputs/claims_model.json`: holdout table with baselines and intervals, reliability diagram, PR curve, ablation, per-region metrics, the area-of-applicability statement, and the retired duration model as a negative result (`panel-rai` e rules).
- Acceptance: page renders from the claims file with no hand-typed numbers.
- Key files: `scripts/build_site.py`, `site/model.html`

### [S-7.5] Deploy on Netlify
- Status: Done · v2 is live at us-wildfires.netlify.app since 2026-09-28 (deployed from a local build of main at 2e9e0db; rollback deploy 6a5508527111d0505efaf807)
- Issue: #57
- Priority: P0 · Size: S · Depends: S-7.2
- Description: Robyn links the GitHub repo in Netlify with publish directory `site/` and no build command (`docs/SITE.md`). A `NETLIFY_AUTH_TOKEN` in the cloud environment would let the session deploy directly; not required.
- Acceptance: the site is reachable at a Netlify URL; the URL is in the README.
- Key files: `netlify.toml`, `docs/SITE.md`

### [S-7.6] Short public write-up
- Status: Open
- Issue: #58
- Priority: P1 · Size: M · Depends: S-7.1
- Description: a 1,000-word piece Robyn can publish: the question, what reproduced, what did not, the headline, what the model can and cannot do, and what she got wrong and fixed. The errata paragraph is the centrepiece (`panel-rai` f).
- Acceptance: draft in `docs/WRITEUP.md`; every number carries a claim id.
- Key files: `docs/WRITEUP.md`

### [S-7.7] Finer map with filters
- Status: Open
- Issue: #59
- Priority: P2 · Size: M · Depends: S-7.2, S-5.2
- Description: 25 km bins in addition to 1 degree; filters for state, ownership class (Missing on by default), cause, year range with reporter breaks marked, size class; minimum-count rule; PAD-US as a separate layer (`panel-conservation` f).
- Acceptance: filters work client-side under 5 MB of data; hollow cells under the minimum count.
- Key files: `scripts/build_site.py`, `site/geography.html`

### [S-7.8] Audit the existing us-wildfires site against the panel findings
- Status: Done · audit in `docs/review/V1_SITE_AUDIT.md`; owner's decision (2026-09-28): retire it, keep it for the record at us-wildfires.netlify.app/archive/ (noindex, bannered), and replace it with this site; its old page addresses redirect to the v2 pages
- Issue: #68
- Priority: P1 · Size: M · Depends: none
- Description: the owner's Netlify team already has a public site, us-wildfires ("the fire record, 1983-2025"), built outside this repo. It may repeat claims the panel refuted or weakened (the Arkansas June spike, "higher lows", count trends read as fire trends, the Control Efficiency Score, a duration model). Check each of its numbers against `docs/review/PANEL_REPORT.md` and the claims files, and decide whether to retire it, merge it with this site, or correct it.
- Acceptance: a table of the site's claims with Supported / Weakened / Refuted and the source for each; a decision recorded by the owner.
- Key files: `docs/review/PANEL_REPORT.md`, `outputs/claims*.json`

### [S-7.9] Decide whether Geography and Ownership stay on the site
- Status: Open
- Issue: #73
- Priority: P2 · Size: S · Depends: none
- Description: `geography.html` and `ownership.html` are still built but are not in the top navigation; they are linked only from Methods and Prediction (v2 phone review, finding 18). Either add them to the navigation, fold what they hold into Places and Protected lands, or stop building them.
- Acceptance: an owner decision, and the navigation and build match it.
- Key files: `scripts/site_v2.py` (`NAV`), `scripts/build_site.py`

### [S-7.10] Commit the site's small data files
- Status: In Review · `.gitignore` anchored to `/data/` and `site/data/` committed except the point files, with the deploy set (`deploy/`, `scripts/deploy.py`) and the first site's source (`legacy/wildfire-poc/`) in the same PR
- Issue: #74
- Priority: P2 · Size: S · Depends: none
- Description: `.gitignore`'s `data/` rule also matches `site/data/`, so none of the site's data files are in git, not only the map's point files (v2 phone review, finding 19). A git-linked Netlify deploy would fail on every chart page. The site is deployed from a local build, and `docs/SITE.md` now says why. Anchor the rule (`/data/`), keep `site/data/points_*.bin` ignored, and commit the small `site/data/*.js` and `.json` files so a checkout renders.
- Acceptance: a fresh clone serves every page except the map from `site/`; CI checks that the build leaves the tree clean.
- Key files: `.gitignore`, `site/data/`, `docs/SITE.md`

### [S-7.11] Phone follow-ups after launch
- Status: Open
- Issue: #75
- Priority: P2 · Size: S · Depends: none
- Description: from the v2 phone review, findings 10 and 15. Recheck tap targets on a real phone after the launch fix (inline numbers now get a taller hit area on touch screens), and decide whether to expand source abbreviations in incident names ("Billy Ck", "Winter Traill" are as recorded; acronyms such as "NW" are now kept upper case).
- Acceptance: inline numbers and dense-row links are at least 24 px tall to the touch on a phone; a recorded decision on name abbreviations.
- Key files: `scripts/build_site.py` (`name_case`, `button.q`)
