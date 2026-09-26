# Adversarial panel report

**Date:** 2026-09-25. **Reviewed commit:** `b52aff2` on `review/phase0-reproduction` (README as of `849e3b0`).
**Inputs:** `REPRODUCTION.md` (Phase 0) and the five persona reviews in this directory: `panel-ml.md`, `panel-fire.md`, `panel-repro.md`, `panel-rai.md`, `panel-conservation.md`. Each review ran its own code against `data/fires.parquet` (SHA-256 of the source database `04f5ab8b…51a965a8`) and fetched every source it cites. The rebuttal pass below challenged every Critical and Major finding once; the ones that survive are listed in section 3.

## 1. Executive summary

Every number in the README reproduces to four decimal places. Most of the sentences around them do not survive review.

The dataset is a compilation of federal, state and local reports whose coverage changes by state and year; its own metadata says counts "may underrepresent actual wildfire activity in certain areas and time periods." Fire counts therefore carry no interpretable national trend, and two of the three "anomalies" the README flags (Texas in December, the Northeast in 2010) are reporting changes. The third (Arkansas in June) does not exist; Arizona and Alaska peak in June.

The one descriptive claim that survives is the large-fire area trend, and it is stronger than the README makes it: acres burned in fires of 5,000+ acres in the 11 Western states roughly doubled between 1992-2005 and 2006-2020 (Kendall tau 0.34, p = 0.009), while the number of recorded fires shows no trend. "Higher lows" is false.

The Control Efficiency Score measures each owner's size mix, cause mix and containment-reporting convention, not response; its ranking flips when the mean is replaced by the median. It is retired.

The duration model should not survive as a regressor. Its 9% RMSE gain is a random-split artefact: forward in time the gain is 3% and absent in 2018. On the typical fire it is 26% worse than predicting zero. Latitude and longitude alone give 83% of its skill. Its training sample silently omits 26% of 2010+ fires, including 88% of Texas. It is replaced by a calibrated probability that a new fire reaches 300 acres, evaluated forward in time against a cell-by-month climatology, with weather covariates as the first experiment.

Land ownership is unrecorded for 46% of fires. Every ownership comparison must show that row.

## 2. Claims ledger

The full sentence-by-sentence ledger (60 sentences: 21 supported, 24 weakened, 7 refuted, 8 unverifiable) is in `panel-rai.md` section (b); the Part 1 ledger with domain reasoning is in `panel-fire.md` section (c). This table consolidates the sentences that carry the README's argument. "R" = `REPRODUCTION.md`, "D" = `docs/findings/descriptive.md`.

| README claim | Verdict | Evidence |
|---|---|---|
| "the US Forest Service's national record of wildfires" | **Refuted** | A compilation of dozens of reporting systems; 66-83% of records per year are non-federal. Metadata and Short (2014) quoted in panel-fire F1. |
| 2,303,566 records, 38 fields, 1992-2020 | Supported (definitional) | 39 columns including OBJECTID and geometry (R). |
| Containment date missing for 894,813; discovery time for 789,095 | Supported, incomplete | Reproduces. Missingness is structured: state/local reporters 31%, Texas 88%, Virginia 94% (panel-fire F2). |
| "I filtered around the gaps rather than filling them in" | Weakened | The filter removes 26.3% of 2010+ fires, non-randomly (R; panel-rai CRIT-3). |
| Class G acres trend upward "with higher highs and higher lows" | Weakened | Trend holds: tau 0.43, p 0.0007, +178k acres/yr; without Alaska tau 0.35, p 0.007; West tau 0.34, p 0.009. "Higher lows" refuted: 2010 is the fifth-lowest year (R, D, panel-fire F4). |
| Human-caused fires far outnumber natural ones | Supported nationally; region-specific | 77% vs 14% nationally; West 58% human, 32% natural, 10% undetermined; West acres are 62% natural (panel-fire F5). |
| Natural causes account for most acreage, about 105.6M acres | Supported | 105.64M acres, 58.7% of the total. Mostly a Western and Alaskan figure (panel-fire F5). |
| Classes B and C most often debris and open burning | Weakened | Plurality: 30% and 26%; general cause is missing or undetermined for 22-24% of each (R, D). |
| Large fires start in the South in winter and shift West by summer | Supported | Class G counts: South leads Jan-Apr, West May-Oct (R). "Especially Texas" is coverage-dependent: Texas has 1,040 records in 2004 and 15,019 in 2006 (panel-fire F6). |
| Western fires last the longest, peaking in August | Weakened | Alaska leads (mean 13.1 days vs West 1.6); the field is a containment declaration, not burn duration (R, panel-fire F2). |
| June spike in Class G acreage in Arkansas | **Refuted** | Arkansas has two Class G fires in 29 years, none in June. Arizona (2.8M acres) and Alaska (22.7M) peak in June (R, D). |
| December fires in Texas | **Refuted** as a pattern | December ranks 10th of 12 months for Texas; one event in December 2005, the first year of Texas A&M's compiled reporting (R, D, panel-fire F6). |
| A 2010 outlier in the Northeast | **Refuted** | z = 0.98 on counts; the series is reporting shifts in 2000-2005, 2015 and 2020 (R, D, panel-fire F1). |
| USFS, BLM and private landowners account for the most acres burned | Supported, incomplete | USFS 38.4M, BLM 37.2M, private 25.6M; unrecorded ownership is fourth at 22.9M and covers 46.4% of records (R, D, panel-conservation C2). |
| Control Efficiency Score compares how quickly fires are brought under control | **Refuted** as a measure | USFS ranks last by mean and first by median; the top 1% of USFS fires carry 97% of the sum; within every size class the gap between owners is a reporting convention (panel-fire F3, D). |
| "Use the seasonal pattern to pre-position … resources" | Refuted as a use | Pre-positioning runs on 7-day fire-weather outlooks, not a 29-year monthly climatology (panel-fire F8). Prevention messaging by cause and month is supported. |
| "An early warning that a fire is likely to run long would give crews time" | **Refuted** for this model | At any flag threshold the model misses 43-63% of fires that burn 30+ days, or flags a third of all fires at 2% precision (panel-rai CRIT-1). |
| CV RMSE 6.33 (± 0.13); test RMSE 6.60; test MAE 1.38 | Supported as numbers; Weakened as evidence | Reproduce exactly (R). "± 0.13" is the std of five fold RMSEs; the bootstrap 95% interval on test RMSE is 6.25 to 7.08 (panel-rai MAJ-1). Random-split numbers; forward in time RMSE is 8.02 (panel-ml 1). |
| Baseline 7.05 days; "≈6% better than always predicting the average" | Weakened | 7.05 is the full-sample std; like for like the gain is 9.0% on the random split and 3.0% on the temporal split (R, panel-ml 1). |
| "MAE is low … the model does well on the many short fires" | **Refuted** | On the 84% of fires contained on day 0 the model predicts 0.55 days; predict-zero MAE 1.09 beats the model's 1.38 on every split (R, panel-ml 2). |
| Most important features: latitude, longitude, cos(DOY), natural cause | Weakened | Order holds under MDI; permutation importance demotes natural cause to fifth, and lat/lon alone recover 83% of the model's skill (E-003, panel-ml 5). |
| "It is most useful for flagging fires that are likely to be short" | **Refuted** as a safe framing | A short label is a stand-down signal; the prior already says every fire is short; the "under 0.5 day" bucket still contains 7.6% of month-long fires (panel-rai C-5). |
| "The train/test split is random … a time-based split is the honest test" | Supported, and now measured | 3.0% RMSE gain forward in time; loses to both constants in 2018 (panel-ml 1). |
| "Serve predictions through a small API for field use" | **Refuted** as a next step | No calibration, no intervals, no coverage disclosure, 26% of fires unrepresented (panel-rai N-5). |

## 3. Surviving findings, ranked

The rebuttal pass challenged each Critical and Major finding. Three were downgraded: `panel-repro` D2 (the venv had no `pip`) is an artefact of how this session built the venv, not a repo defect; `panel-repro` C2 (`fillna(0)` on coordinates) is a latent defect with zero affected rows today and is Major, not Critical; `panel-ml` 6 (spatial block CV) was already rated Minor by its author because the temporal attack is stronger. Two apparent contradictions were resolved: the Control Efficiency Score rank of USFS is "10th of 12" (R, all years), "11th of 14" (D, 1,000-record threshold) and "16th of 16" (panel-fire, 2010+ with both times) because the samples differ, and the score is unstable in every variant; "missing cause" is 8-9% of records when measured on `NWCG_CAUSE_CLASSIFICATION` and 26% when measured on `NWCG_GENERAL_CAUSE` (which folds undetermined human causes into "Missing data/not specified/undetermined"), and both figures are correct for their field.

| Rank | Finding | Severity | Source | Fix (owner: backlog story) |
|---|---|---|---|---|
| 1 | The duration model's skill is a random-split artefact and it loses to a constant on the typical fire. Forward in time: RMSE gain 3.0%, loses in 2018; MAE 26% worse than predict-zero on every split; 83% of squared error from 1% of fires. | Critical | panel-ml 1-3; R | Retire the regressor; keep as a documented negative result. Replace with P(fire ≥ 300 acres) under the locked protocol (`EXPERIMENTS.md`). |
| 2 | The dataset is a compilation with state-year coverage breaks, and the README reads count changes as fire changes. 30 of 48 states have a >3x year-over-year jump; Texas 1,040 to 15,019 records in two years; national counts have no trend. | Critical | panel-fire F1; panel-conservation M1 | Coverage mask and coverage map as first-class artifacts; count trends only inside usable windows or for federal reporters. |
| 3 | The README proposes operational use (early warning, field API) for a model that cannot do the job, with no out-of-scope statement. | Critical | panel-rai CRIT-1, N-5 | Delete both sentences; publish the recall/precision table and the out-of-scope list in a model card. |
| 4 | The model sample silently omits 26% of 2010+ fires, concentrated in Texas (12% kept), Virginia, Hawaii, Puerto Rico, interagency reporters and unrecorded ownership; missingness correlates with the outcome. | Critical | R; panel-rai CRIT-3; panel-ml 4 | Coverage table in README and model card; the replacement target uses `FIRE_SIZE`, which is never missing. |
| 5 | Land ownership is unrecorded for 46.4% of fires (41.5% in 2010-2020), almost entirely among non-federal reporters, so every federal-vs-private comparison compares complete data to an unknown subset. | Critical | panel-conservation C2; D | Always show the Missing row; assign ownership spatially with PAD-US and publish the agreement table. |
| 6 | `CONT_DATE` is a containment declaration whose convention differs by reporting system; within every size class USFS median hours to containment are 5 to 20 times private owners'. Neither "duration" nor the efficiency score measures what the README says. | Critical | panel-fire F2, F3; D | Retire the Control Efficiency Score. Any containment-timing view is descriptive, stratified by size class and reporting system, and labelled as a declaration. |
| 7 | Three published anomalies were never checked; two do not exist and one names the wrong state. | Major | R; D; panel-rai MAJ-2 | Remove; add an errata section stating what was claimed and what the check found. |
| 8 | Uncertainty is misreported: "± 0.13" is a fold std; the bootstrap 95% interval on test RMSE is 6.25 to 7.08, three times wider. No metric carries an interval. | Major | panel-rai MAJ-1 | Bootstrap intervals on every reported metric; the site rules in panel-rai (e). |
| 9 | The model is a geography lookup: lat/lon alone recover 83% of its skill; cause dummies reduce accuracy; DOY+cause without geography is worse than a constant. | Major | panel-ml 5, 12; E-006 | Every replacement is benchmarked against cell-by-month climatology; grouped permutation importance, no MDI. |
| 10 | `src/features.py` has three silent-corruption paths: one-hot columns change with the input (a model cannot score a batch with a different cause mix), `fillna(0)` would place a fire with no coordinates at 0N 0E, and DOY/365 maps 31 December of a leap year onto 1 January (140 rows). | Major | panel-repro C1, C2, C4; tests `_DEFECT` | Fixed category list, explicit null validation, leap-aware angle; the tests in PR #2 pin the current behaviour and the expected fix. |
| 11 | The committed figures come from an unrecorded, out-of-order notebook run (byte-identical to the notebook's exec-5 images); the notebook ran on Python 3.14.2. | Major | panel-repro N1-N3; R | Regenerate figures from `reproduce.py`; delete or strip and re-execute the notebook. |
| 12 | The download script cannot verify what it fetches (no checksum, no resume, truncated zips reused) and `load_data` calls `sys.exit` inside a library. | Major | panel-repro P1-P2, C7 | Checksum against `data.sha256`, `.part` downloads, raise instead of exit. |
| 13 | Human vs natural is region-specific and the undetermined class is large enough to move the answer (West: 58% human with it, 72% without). Hawaii and Puerto Rico are 97-99% missing cause. | Major | panel-fire F5 | Three categories always shown; report by region; exclude HI and PR from cause analyses. |
| 14 | "Large fire" has no single definition in the project (Class G for trends, ≥300 acres for the reframe, MTBS thresholds 1,000 West / 500 East). | Major | panel-conservation M3 | One glossary entry used everywhere. |
| 15 | The cause feature is "Missing data" for 26.7% of the model sample and cause is often determined after investigation, so "only what is known at discovery" is not established. | Major (unverifiable) | panel-rai MAJ-3 | Test the replacement with cause removed; state the leakage caveat in the model card. |
| 16 | The environment files do not describe the environment (`pyarrow`, `duckdb` unpinned; lock out of date); the split depends on SQLite physical row order; parallelism is hard-coded. | Major | panel-repro D1, D4, D5 | Regenerate the lock; `ORDER BY FOD_ID`; one `n_jobs` setting. |
| 17 | The site will redistribute derived aggregates; the data terms permit this without fee but the site must carry the citation, state that aggregates are project-derived, and carry the USFS liability disclaimer. | Major | panel-repro L1 | `docs/DATA_TERMS.md` and a footer on every page. |

Minor findings (wording, definitions, the LA anecdote, region membership, "38 fields", leap-year docstring) are listed in the individual reviews and carried into the backlog under the README rewrite.

## 4. The defensible headline

**Large wildfires in the West burn about twice the area they did in the 1990s; the number of recorded fires has not grown, and much of what looks like change in this record is change in who reports.**

Supporting sentence: in the 11 Western states, area burned in fires of 5,000+ acres rose from 1.9M to 3.8M acres per year between 1992-2005 and 2006-2020 (Kendall tau 0.34, p = 0.009), carried by extreme years and absent in Alaska; this record cannot say why.

What the project can now honestly claim about prediction: location and calendar month alone give a usable ranking of which new fires will reach 300 acres (about half of them fall in the top decile of scores, 5x the base rate), and the earlier duration model added nothing to that. Whether weather at discovery adds skill is the open experiment.

## 5. Decision on the prediction target

Adopted, per `panel-ml` (c) and (d), `panel-fire` F7 and `panel-conservation` question 10:

- **Primary:** P(final size ≥ 300 acres) at discovery, on all 854,880 fires discovered 2010-2020 (no containment-date selection). Base rate 1.4%.
- **Secondary:** P(containment declared ≥ 7 days after discovery) on the containment-date sample, with its coverage caveat.
- **Retired:** the whole-day duration regressor, kept in `EXPERIMENTS.md` as E-001 to E-007.
- **Protocol:** the locked 2019-2020 holdout and expanding-window temporal CV defined in `EXPERIMENTS.md`; every table includes base rate, cell-by-month climatology, logistic regression and a geography-only learner; PR-AUC, Brier skill, reliability and top-decile lift; grouped permutation importance.
- **First experiment:** weather at discovery (ERC, burning index, wind, VPD, fuel moisture) via gridMET or the FPA FOD-Attributes dataset, with an ablation showing what it adds over climatology. If it adds little, that is the published result.

## 6. What each review contributed beyond the findings

- `panel-conservation`: the join keys are already populated (MTBS_ID on 94% of Class G fires; ICS-209-PLUS id on 80% of fires ≥ 300 acres), the external tables are small and openly licensed, and human-caused large fires cluster in eastern Oklahoma and the Cumberland Plateau where cause is recorded. Dashboard rules in its section (f).
- `panel-fire`: the prevention calendar (South Feb-Apr debris burning; West Jun-Aug; Alaska May-Jul), the coverage-map recommendation, and the ranked practitioner questions.
- `panel-rai`: the model card and datasheet skeletons, the ten uncertainty-communication rules, and the errata-section recommendation.
- `panel-repro`: the test plan (implemented in PR #2), the repo layout, and the data-terms text for the site.
- `panel-ml`: the evaluation protocol and the exploratory reframe numbers (E-008).
