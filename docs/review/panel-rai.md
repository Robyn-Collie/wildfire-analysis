# Panel review: responsible-AI and communication (panel-rai)

**Reviewer role:** responsible-AI and communication reviewer on the adversarial panel. Brief: argue against how the project communicates and against its fitness for the stated use, as hard as the evidence allows.
**Inputs read in full:** `README.md`, `docs/review/REPRODUCTION.md`, `docs/EXPERIMENTS.md`, `docs/DATA_VERSION.md`, `src/*.py`, `run_pipeline.py`, `scripts/reproduce.py` (skimmed), `notebooks/wildfire_duration_model.ipynb`, `docs/img/*.png`.
**My own computations:** scripts and raw outputs in `/tmp/claude-0/-home-user-wildfire-analysis/a4df9529-3e52-5fbc-b7e0-fb427368a57f/scratchpad/panel-rai/` (`representation.py`, `misuse.py`, `bootstrap.py` and their `.txt` outputs). All data numbers below come from those runs on `data/fires.parquet` (2010+ = `FIRE_YEAR >= 2010`; "kept" = `CONT_DATE` not null, which is exactly the `load_data` filter) or from `REPRODUCTION.md`. Model checks use the reported RF configuration (100 trees, depth 10, seed 42) fitted on a 150,000-row random subsample of the original training split (seed 42, `n_jobs=1`) and scored on the original 126,011-row test split; that subsampled model scores test RMSE 6.64 and MAE 1.41 against the full model's 6.60 and 1.38, so its numbers are indicative, not identical.
**References fetched this session:** Mitchell et al., "Model Cards for Model Reporting", https://arxiv.org/abs/1810.03993 (PDF https://arxiv.org/pdf/1810.03993, sections 4.1 to 4.9 extracted); Gebru et al., "Datasheets for Datasets", https://arxiv.org/abs/1803.09010 (PDF https://arxiv.org/pdf/1803.09010, sections 3.1 to 3.7 extracted).

---

## (a) Verdict (150 words)

The numbers in the README are honest; the sentences around them are not yet. Every metric reproduces, but the README's reading of them is wrong in the one place that matters: it says the model "does well on the many short fires", when on the 84% of fires that are contained the same day it predicts 0.55 days and loses to a constant zero by 26% on MAE. It then proposes an early-warning use and an API "for field use" for a model that, at any threshold a dispatcher could act on, misses 43% to 63% of fires that go on to burn 30 days or more. The training sample silently omits 26% of 2010+ fires, including 88% of Texas, 95% of Virginia and 96% of Hawaii, and this is disclosed nowhere. Two of three flagged anomalies do not exist. Uncertainty is reported as a fold standard deviation dressed as an interval. Fixable, and worth fixing, because the descriptive finding underneath (large fires burn more acres; fire counts do not rise) is solid and reproducible.

---

## (b) Claims ledger

Classification key: **Supported** (holds as written), **Weakened** (true in part or with a caveat the README omits), **Refuted** (does not hold), **Unverifiable** (no artifact or data to check). "R" = `docs/review/REPRODUCTION.md`; "own" = my runs in the panel-rai scratch dir.

### Introduction and Data

| # | README sentence | Class | Reason (one line) |
|---|---|---|---|
| I-1 | "I lived in Los Angeles for ten years, and over that time it felt like the fires kept getting worse." | Unverifiable | Personal impression; not a data claim. See finding MIN-6 on whether it belongs. |
| I-2 | "I wanted to find out whether that impression holds up against the data" | Weakened | The README never answers it for Los Angeles or California; the answer given is national Class G acreage. CA is also 51% missing containment dates in 2010+ (own). |
| I-3 | "a descriptive story in Tableau, then a model in Python that estimates how long a fire will burn from what is known when it is first reported." | Weakened | Tableau is being deprecated and no link exists; "what is known when first reported" is contestable for cause (P2-9). |
| D-1 | "2,303,566 fire records × 38 fields, 1992–2020, distributed as a SQLite database." | Weakened | Row count reproduces; table has 39 columns (37 attributes + OBJECTID + Shape). Definitional (R). |
| D-2 | "Fire sizes range from near zero to 662,700 acres." | Supported | 0.00001 to 662,700 acres (R). |
| D-3 | "the containment date is missing for 894,813 records and the discovery time for 789,095." | Supported | Both reproduce (R). |
| D-4 | "I filtered around the gaps rather than filling them in." | Weakened | Accurate as method, but framed as neutral; the filter removes 26.3% of 2010+ fires non-randomly (R; own, section (c) MAJ-3). |

### Part 1: descriptive analysis

| # | README sentence | Class | Reason |
|---|---|---|---|
| P1-1 | "Interactive dashboards: [Tableau Public link coming]" | Unverifiable | No artifact. Every Part 1 claim is therefore unverifiable against its stated source; R re-derived them from the database. |
| P1-2 | "For the largest fires (Class G, 5,000 acres and up), acres burned trend upward over the period, with higher highs and higher lows." | Weakened | Trend holds (Kendall tau 0.43, p = 0.0007; Theil-Sen +178k acres/yr, R). "Higher lows" is false as stated: 2010 (2.1M) is below 1996 and 1999 (R). |
| P1-3 | "Human-caused fires far outnumber natural ones" | Supported | 77.4% human vs 14.2% natural of fires (R). |
| P1-4 | "natural causes (mostly lightning) account for most of the acreage burned, about 105.6 million acres." | Supported | 105.64M acres = 58.7% of 180.0M (R). |
| P1-5 | "Smaller fires (Classes B and C) are most often debris and open burning." | Weakened | Plurality, not majority: B 30%, C 26%; "missing" cause is 24% and 22% (R). |
| P1-6 | "An animated seasonal map shows large fires starting in the South, especially Texas, in winter and shifting to the West and Northwest by summer." | Weakened | South leads Class G counts Jan to Apr, West May to Oct (R). "Especially Texas" was not checked by R or me: Unverifiable. "Northwest" is not defined. |
| P1-7 | "Western fires last the longest, peaking in August." | Weakened | Alaska mean duration 13.1 days vs West 1.6; only true if Alaska is not "West" (R). West-by-month August peak holds. |
| P1-8 | "a June spike in Class G acreage in Arkansas" | Refuted | Arkansas has 2 Class G fires in 29 years, none in June. Arizona and Alaska peak in June (R). Likely AR/AZ/AK label error. |
| P1-9 | "December fires in Texas" | Refuted | December is among Texas's quietest months; one Dec 2005 event (R). |
| P1-10 | "a 2010 outlier in the Northeast" | Refuted | 2010 count z = 0.98, acres z = 0.48 for a 9-state Northeast; series is dominated by reporting-regime shifts (R). Region definition Unverifiable. |
| P1-11 | "The US Forest Service, the Bureau of Land Management and private landowners account for the most acres burned." | Weakened | USFS 38.4M, BLM 37.2M, Private 25.6M reproduce, but the 4th category is "MISSING/NOT SPECIFIED" at 22.9M, omitted (R). |
| P1-12 | "I built a Control Efficiency Score: 1 ÷ (average acres burned per hour until control)." | Supported (as definition) | Recomputable (R). |
| P1-13 | "It is not fair to rank agencies with that score as it stands." | Supported, understated | True, but the reason given (terrain, weather) is not the demonstrated defect: swapping mean for median moves USFS from 10th to 1st of 12 (R). The score is unstable before any confounder is considered. |
| P1-14 | "It ignores terrain, elevation, weather and the resources each agency has." | Supported | True by construction. |
| P1-15 | "a lower score may reflect steep, remote country rather than a slower response." | Unverifiable | Plausible; no terrain data joined. |
| P1-16 | "Before drawing conclusions from it, I would add terrain, elevation, historical weather and fire perimeter data." | Weakened | The first fix is statistical (robust summary, n per group), not more covariates. |
| P1-17 | "Use the seasonal pattern to pre-position federal and state firefighting resources, and time public awareness campaigns to the months and regions where human-caused fires peak." | Weakened | Seasonal pattern reproduces, but the sentence implies the analysis adds something to agency practice. No evidence that it does; Unverifiable as a utility claim. |

### Part 2: duration model

| # | README sentence | Class | Reason |
|---|---|---|---|
| P2-1 | "when a fire is first reported, can we estimate how long it will burn?" | Supported (as question) | Answered below by the evidence: barely, and not for long fires. |
| P2-2 | "An early warning that a fire is likely to run long would give crews time to move resources before it grows." | Refuted (as applied to this model) | At a 5-day flag threshold the subsampled model flags 4.2% of fires and misses 43% of 30+ day fires (213 of 500) and 56% of 7+ day fires; at 10 days it misses 63% of 30+ day fires (own, `misuse.txt`). |
| P2-3 | "630,053 fires discovered from 2010 onward that have a recorded containment date." | Supported | Reproduces (R). Omits that this is 73.7% of 854,880 2010+ fires (own). |
| P2-4 | "Duration is containment date minus discovery date, in days." | Weakened | Day-level target: 17.5% of "1-day" fires lasted under 12 hours; two 3-hour fires can land in different classes (R). |
| P2-5 | "Records with a negative duration (contained before discovered) are dropped as data errors." | Supported (no-op) | Filter removes 0 rows (R). |
| P2-6 | "Features (only what is known at discovery):" | Weakened | See P2-9. |
| P2-7 | "latitude and longitude" | Supported | |
| P2-8 | "general cause (one-hot encoded; 13 categories)" | Weakened | One of the 13 is "Missing data/not specified/undetermined", which is 26.7% of the model sample and the third-largest feature category (own). The README does not say the model has a "cause unknown" input. |
| P2-9 | (implied) cause is known at discovery | Unverifiable, likely false for a share of fires | NWCG general cause is frequently assigned after investigation. No field in FPA FOD records when cause was determined. This is a leakage risk the README does not name. |
| P2-10 | "day of year, encoded as sine and cosine so that December 31 sits next to January 1" | Supported | `features.py` lines 43-44. Divides by 365; leap-day 366 wraps to day 1 (harmless). |
| P2-11 | "Fire size class is left out on purpose. It records the fire's final size, which isn't known at discovery, so using it would leak the answer into the inputs." | Supported | Correct reasoning; `features.py` drops it. |
| P2-12 | "Random Forest regressor (100 trees, max depth 10), an 80/20 train/test split, and 5-fold cross-validation on the training set." | Supported | `train_model.py`; reproduces to 4 d.p. (R, E-001). |
| P2-13 | "Cross-validation RMSE (5-fold, training set): 6.33 days (± 0.13)" | Weakened | Number reproduces. "±0.13" is the standard deviation of five fold RMSEs, not a confidence interval. Bootstrap 95% CI on test RMSE is 6.25 to 7.08, three times wider (own, `bootstrap.txt`). |
| P2-14 | "Test RMSE: 6.60 days" | Supported | 6.5957 (R). No interval given; see P2-13. |
| P2-15 | "Test MAE: 1.38 days" | Weakened | 1.3768 reproduces, but predict-zero scores 1.094 on the same rows (R, E-002); bootstrap ratio model/zero = 1.27 to 1.31 (own). |
| P2-16 | "Baseline: standard deviation of duration (always predicting the mean): 7.05 days" | Weakened | 7.05 is the full-sample std; the like-for-like predict-training-mean RMSE on the test rows is 7.25 (R). The baseline that matters for a zero-inflated target (predict 0) is absent. |
| P2-17 | "The target is zero-inflated." | Supported | 83.7% zeros (R). |
| P2-18 | "The median duration is 0 days, since most fires are contained the day they are found, and a small number burn for months." | Supported | 91.5% within 1 day; 99th pct 24 days; max 364 (R). |
| P2-19 | "That's why MAE is low while RMSE stays close to the baseline: the model does well on the many short fires and misses the long ones." | Refuted (first half) | On 0-day fires the model predicts 0.55 days on average and does worse than predicting 0 (R). MAE is low because the truth is mostly 0, not because the model is good. The "misses the long ones" half is Supported: fires of 30+ days are 0.8% of test rows and carry 85% of squared error (R). |
| P2-20 | "The most important features are latitude, longitude, cos(day of year) and a natural cause." | Weakened | MDI order reproduces; permutation importance ranks sin(DOY) above natural cause and puts natural cause at 0.035 days MAE increase (E-003). |
| P2-21 | "Where and when a fire starts, and whether lightning started it, carry most of the signal." | Weakened | "Where and when" holds; "whether lightning started it" is small by permutation (E-003). |
| P2-22 | Figures `docs/img/feature_importance.png`, `docs/img/residuals.png` presented as from the reported run | Unverifiable | Notebook cells executed out of order (display cell 5, training cell 6) (R). |

### "What this model can't do"

| # | README sentence | Class | Reason |
|---|---|---|---|
| C-1 | "In the residual plot, fires that burned for 100+ days are mostly predicted to last only a few days." | Supported | Mean prediction for 100+ day fires is 15.9 days, n = 122 (R); plot confirms the mass near 0 to 20. |
| C-2 | "Without wind, humidity, temperature and fuel conditions, the model has no way to tell a fire that will run for months from one that will go out overnight." | Unverifiable | Reasonable hypothesis; no weather join has been tried, so it is a conjecture presented as an explanation. |
| C-3 | "Test RMSE is about 6% better than always predicting the average." | Weakened | 6.4% against the full-sample std, 9.0% against predict-mean on the same rows (R); bootstrap 95% CI for the improvement is 6.8% to 10.3% (own). Understated, but the wrong comparison. |
| C-4 | "The signal is real but modest." | Weakened | Real on RMSE (CI excludes 0). On MAE the model is reliably worse than a constant. "Modest" hides that. |
| C-5 | "It is most useful for flagging fires that are likely to be short, not for sizing up the dangerous ones." | Refuted (as a safe framing) | 66% of fires are predicted under 0.5 days; the prior "every fire is short" already achieves lower MAE. Flagging short fires is not an operational need, and the "short" bucket still contains 7.6% of all 30+ day fires (own). See section (d). |
| C-6 | "The train/test split is random, so fires from the same season and area appear on both sides. A time-based split is the honest test for a model meant to be used on future fires." | Supported | Correct, and it means every Part 2 number is an upper bound on deployable performance. |

### "Next steps"

| # | README sentence | Class | Reason |
|---|---|---|---|
| N-1 | "Switch to a time-based train/test split ... to remove leakage between neighboring fires." | Supported | Right first step. |
| N-2 | "Join NOAA weather observations at the time and place of discovery." | Unverifiable | Sensible; untested. |
| N-3 | "Compare against a plain linear model as a control, so the Random Forest's gain is measured rather than assumed." | Weakened | The control that matters (predict 0, predict median) has now been run and the RF lost on MAE (E-002). A linear model is the wrong control for a zero-inflated target. |
| N-4 | "Tune hyperparameters." | Weakened | Premature until the model beats a constant on the metric that matches the use. |
| N-5 | "Serve predictions through a small API for field use." | Refuted (as a responsible step) | Field use is exactly the out-of-scope use in section (d). No calibration, no intervals, no coverage disclosure, 26% of fires unrepresented. |

### Other sections

| # | README sentence | Class | Reason |
|---|---|---|---|
| O-1 | "Stack: Tableau, Python, SQLite, pandas, NumPy, scikit-learn, Matplotlib, Seaborn, Jupyter." | Weakened | Tableau is being deprecated; SQLite is being supplanted by the Parquet cache. |
| O-2 | "docs/img/ # plots from the run reported above" | Unverifiable | See P2-22. |
| O-3 | "The wildfire data belongs to the USDA Forest Service and is subject to its own terms; please cite it as shown above." | Supported | Citation matches `DATA_VERSION.md` and the DOI. |

**Tally:** 60 classified sentences. Supported 21, Weakened 24, Refuted 7, Unverifiable 8 (some rows carry two classes; counted by the primary class).

---

## (c) Findings

### Critical

**CRIT-1. The README proposes an operational use (early warning, "API for field use") for a model that cannot do the job, and says so nowhere near the proposal.**
Evidence (own, `misuse.txt`, subsampled RF on 60,000 test rows; base rate of 30+ day fires 0.83%, of 7+ day fires 3.2%):

| Flag if predicted ≥ | Share of fires flagged | Recall of 30+ day fires | Precision for 30+ day | 30+ day fires missed (of 500) | Recall of 7+ day fires |
|---|---|---|---|---|---|
| 0.5 d | 34.0% | 92% | 2.3% | 38 | 92% |
| 1 d | 19.5% | 84% | 3.6% | 80 | 82% |
| 2 d | 13.6% | 78% | 4.8% | 109 | 71% |
| 5 d | 4.2% | 57% | 11.4% | 213 | 44% |
| 10 d | 1.4% | 37% | 22.4% | 313 | 21% |

There is no threshold that a dispatcher could act on: to catch 9 in 10 long fires the model must flag a third of all fires (precision 2%); to keep the flag rare (1.4%) it misses two thirds of the fires that will burn a month or more. The README's P2-2 sentence and N-5 present the opposite picture.
Fix: delete N-5; rewrite P2-2 as a hypothesis the results reject; add the table above (regenerated with the full model) under a heading "Could this be used as an early warning? No." Add the out-of-scope section in (d) to the README and to a model card.

**CRIT-2. The README's interpretation of MAE is wrong, and it is the interpretation on which the model's claimed usefulness rests.**
Evidence: P2-19. On 0-day fires (83.7% of test) the model predicts 0.55 days on average (R). Predict-zero MAE 1.094 vs model 1.377 (E-002); bootstrap 95% CI for model/zero MAE ratio 1.27 to 1.31 (own), so the loss is not noise. The model is well calibrated in the mean within prediction bins (own reliability table in (d)), which is exactly why it cannot win on a median-type metric for a zero-inflated target.
Fix: replace P2-19 with "MAE is 1.38 days, which is worse than the 1.09 days from predicting 0 for every fire. The model wins on RMSE only, and RMSE is 85% driven by the 0.8% of fires that burn 30 days or more." Add the E-002 table to the README results.

**CRIT-3. The model is silently not about a quarter of recent US fires, and the quarter is not random.**
Evidence (own, `representation.txt`; 2010+ fires by `FIRE_YEAR >= 2010`, "kept" = `CONT_DATE` not null):

| Slice | Fires 2010+ | In model sample | Share kept | Share of 2010+ fires | Share of model sample |
|---|---|---|---|---|---|
| All | 854,880 | 630,053 | 73.7% | 100% | 100% |
| Texas | 101,070 | 12,568 | 12.4% | 11.8% | 2.0% |
| California | 90,191 | 46,169 | 51.2% | 10.6% | 7.3% |
| Virginia | 7,231 | 408 | 5.6% | 0.8% | 0.06% |
| Hawaii | 2,441 | 106 | 4.3% | 0.3% | 0.02% |
| Puerto Rico | 4,472 | 231 | 5.2% | 0.5% | 0.04% |
| Louisiana | 9,655 | 3,907 | 40.5% | 1.1% | 0.6% |
| Arkansas | 15,918 | 9,210 | 57.9% | 1.9% | 1.5% |
| South Dakota | 13,293 | 7,169 | 53.9% | 1.6% | 1.1% |
| Owner: MISSING/NOT SPECIFIED | 354,471 | 204,757 | 57.8% | 41.5% | 32.5% |
| Owner: STATE OR PRIVATE | 35,525 | 9,823 | 27.7% | 4.2% | 1.6% |
| Owner: MUNICIPAL/LOCAL | 15,673 | 11,498 | 73.4% | 1.8% | 1.8% |
| Owner: PRIVATE | 269,676 | 238,822 | 88.6% | 31.6% | 37.9% |
| Owner: USFS | 62,944 | 54,667 | 86.9% | 7.4% | 8.7% |
| Owner: BLM | 24,244 | 24,050 | 99.2% | 2.8% | 3.8% |
| Owner: BIA | 37,327 | 36,812 | 98.6% | 4.4% | 5.8% |
| Reporting agency: ST/C&L (state, county, local) | 678,743 | 469,194 | 69.1% | 79.4% | 74.5% |
| Reporting agency: IA (interagency) | 4,235 | 11 | 0.3% | 0.5% | 0.00% |
| Reporting agency: DOD | 118 | 30 | 25.4% | 0.01% | 0.00% |
| Reporting agency: FS | 73,571 | 64,209 | 87.3% | 8.6% | 10.2% |
| Reporting agency: BLM | 38,257 | 37,986 | 99.3% | 4.5% | 6.0% |
| Source system: NONFED | 667,557 | 462,297 | 69.3% | 78.1% | 73.4% |
| Source system: FED | 158,032 | 148,776 | 94.1% | 18.5% | 23.6% |
| General cause = Missing | 274,394 | 168,503 | 61.4% | 32.1% | 26.7% |

States with 97%+ of fires kept: GA, PA, WV, WI, SC, NV, FL, RI, MA, NC, DE, KS, NE, MN, OK, TN. So the model has effectively learned the reporting practices of state and federal systems that record containment dates, and has barely seen the largest fire-count state in the country (Texas is 11.8% of 2010+ fires and 2.0% of the sample). Who is silently excluded: fires on unspecified or state-or-private land reported by state, county and local systems in Texas, Virginia, Louisiana, Hawaii and Puerto Rico, plus every interagency-system fire. The dropped fires also skew toward Class B and away from Class A and G, so the exclusion is not simply "small fires nobody logged".
Fix: a "Coverage" subsection in the README and in the model card (section (e)), with the table above, and a per-state coverage map on the public site. Every predicted number on the site should carry the line "Trained on fires with a recorded containment date (74% of 2010+ records; Texas 12%, California 51%)."

### Major

**MAJ-1. Uncertainty is misreported.** "± 0.13" is the standard deviation of five fold RMSEs (E-001 folds 6.37, 6.55, 6.37, 6.21, 6.17). Nothing on the test set carries an interval. Bootstrap (1,000 resamples of the 126,011 test rows, subsampled model): RMSE 6.64 [6.25, 7.08]; MAE 1.41 [1.38, 1.44]; predict-zero MAE 1.09 [1.06, 1.13]; RMSE improvement over predict-mean 6.8% to 10.3%. The RMSE interval is ±0.4 days, three times the reported ±0.13, because 1% of fires carry 85% of squared error. Across-tree spread of the forest (mean std 0.79 days) is about half the mean absolute error (1.43), so tree disagreement would also understate uncertainty if anyone tried to use it as an interval. Fix: report bootstrap 95% CIs for every test metric; label the CV figure "std of 5 fold RMSEs"; see (e) for site rules.

**MAJ-2. Three "flagged for follow-up" anomalies were published without a check, and two do not exist (P1-8, P1-9, P1-10).** In a portfolio for responsible-AI roles, "I flagged this rather than explained it" reads well only if the flag is real. The Arkansas one is almost certainly a state-label mix-up (Arizona and Alaska both peak in June). Fix: remove all three from the README; add an "Errata" section stating what was claimed, what the check found, and what the mistake probably was. That paragraph is worth more to a hiring manager than the anomalies were.

**MAJ-3. The cause feature contains "missing" as its third-largest category and may not be known at discovery.** 26.7% of the model sample has general cause "Missing data/not specified/undetermined" (own), and the model uses that as a feature. Fires with missing cause have lower MAE (1.03 vs 1.55) and shorter true durations (mean 0.78 vs 1.21 days) than fires with known cause (own, `bootstrap.txt`), which means "cause not recorded" is itself predictive of the reporting regime, not of fire behaviour. Separately, cause determination often follows investigation, so "only what is known at discovery" (P2-6) is not established. Fix: state both facts in the README; test the model with cause removed; in the model card list cause as a feature with a leakage caveat.

**MAJ-4. The baseline in the results table is not comparable (P2-16), and the relevant baseline is missing.** 7.05 is the full-sample std; the same-split predict-mean RMSE is 7.25; predict-zero is absent even though it is the natural baseline for a target that is 0 for 84% of rows. Fix: replace the results table with the E-002 table (RF, predict-mean, predict-zero, per-cause median), all on the same test rows, with CIs.

**MAJ-5. Figures of unverifiable provenance are presented as results (P2-22).** Fix: regenerate from `scripts/reproduce.py`, commit to `docs/img/` with the run date and data hash in the caption.

**MAJ-6. The Control Efficiency Score is presented as a measure that needs more covariates, when it is a measure that does not measure response (P1-13, P1-16).** Median vs mean flips USFS from 10th to 1st (R). Fix: either drop the score or present the flip as the finding ("a ratio of means is dominated by the largest fires; here is what happens when you use the median; neither is a response metric without controls").

**MAJ-7. "Most useful for flagging fires that are likely to be short" (C-5) is not a safe framing.** See section (d). Fix: delete; replace with what the model does and does not separate, with base rates.

### Minor

**MIN-1.** "38 fields" (D-1): say "37 attribute fields plus an ID and a geometry column".
**MIN-2.** "Higher lows" (P1-2): replace with the Kendall tau, the Theil-Sen slope and the two-period means from R; add "the number of fires shows no trend (tau 0.10, p = 0.47)", which is the more interesting sentence.
**MIN-3.** "Most often debris and open burning" (P1-5): "the most common recorded cause (30% of Class B, 26% of Class C); cause is missing for about a quarter of each."
**MIN-4.** "Western fires last the longest" (P1-7): define West; say Alaska separately.
**MIN-5.** Day-granularity target (P2-4): disclose that 91.7% of kept fires have times and that an hours-level target is available; either use it or say why not.
**MIN-6. The Los Angeles anecdote (I-1).** It is one sentence, it discloses a past city of residence and a ten-year span, and it is Robyn's own text; only she decides. My assessment for the responsible-AI reader: it helps as motivation and hurts as framing, because the README then never returns to it (I-2). If kept, close the loop with one sentence in the findings ("For California specifically the record cannot answer my question: half of California's 2010+ fires have no containment date, and Class G acreage is a national trend"). If she prefers less personal detail on a public site, "Having lived in a fire-prone region" carries the same motivation with no location or time span.
**MIN-7.** Placeholder link and Tableau in the stack (P1-1, O-1): remove once the static site exists.
**MIN-8.** "Fourth-largest owner category is unknown" (P1-11): add it; leaving it out makes the ownership story look cleaner than the data is.

---

## (d) Misuse and harm analysis, and the out-of-scope section

### What happens if a dispatcher acts on this model

The model's outputs, as they would appear to a user, look like this (own reliability table, subsampled model, 60,000 test rows):

| Predicted duration bin (days) | n | Mean predicted | Mean actual | Median actual | Actual 0 days | Actual 7+ days | Actual 30+ days |
|---|---|---|---|---|---|---|---|
| 0 to 0.25 | 28,216 | 0.13 | 0.14 | 0 | 95.7% | 0.3% | 0.1% |
| 0.25 to 0.5 | 11,383 | 0.36 | 0.34 | 0 | 92.2% | 0.7% | 0.2% |
| 0.5 to 1 | 8,677 | 0.76 | 0.85 | 0 | 81.8% | 2.2% | 0.5% |
| 1 to 2 | 3,575 | 1.27 | 1.70 | 0 | 68.9% | 5.6% | 0.8% |
| 2 to 5 | 5,629 | 3.12 | 3.07 | 1 | 45.6% | 9.6% | 1.8% |
| 5 to 10 | 1,686 | 7.44 | 7.28 | 2 | 25.9% | 26.2% | 5.9% |
| 10 to 20 | 572 | 13.1 | 13.4 | 5 | 23.4% | 42.0% | 15.6% |
| 20+ | 262 | 33.1 | 29.9 | 15 | 11.8% | 61.5% | 37.4% |

Two things follow. First, the model is calibrated in the mean: bin means match. A reader who sees "predicted 13 days" and takes it as a typical outcome is wrong; the median fire in that bin lasted 5 days and 23% went out the same day. A point prediction of a right-skewed quantity is a mean of a distribution the user never sees. Second, every bin below 5 days, which is 96% of fires, still contains 30+ day fires. Predicting "under half a day" for 66% of fires leaves 38 month-long fires (7.6% of all 30+ day fires) in the bucket a dispatcher was told is safe.

**Who bears the cost of false negatives.** A false negative here is a fire predicted short that runs long. The dispatcher who deferred resources is not the one who pays; the people downwind and the crews sent late are. Because coverage is worst for Texas (12% of fires in sample), Virginia, Louisiana, Hawaii, Puerto Rico and fires on land of unspecified ownership reported by local systems, the model is least informed exactly where a local dispatcher would be. The false-negative burden is therefore not uniform: it lands on the populations whose fires never made it into the training set, and the model gives no signal that it is out of its depth there.

**Is "most useful for flagging fires that are likely to be short" a safe framing?** No, for three reasons. (1) The prior already says every fire is short: 84% are contained the day they are found. A "short" flag adds nothing a dispatcher did not already assume, and the constant "0" beats the model on MAE. (2) A "short" label is an instruction to stand down, so the harmful error mode of the model is placed on the label the README says it is good at. (3) The label is wrong about 1 in 250 times for 7+ day fires and 1 in 1,000 times for 30+ day fires in the "under 0.5 day" bucket, and there are 40,000 such fires in a fifth of one decade's data; those are hundreds of long fires labelled short over the period. The safe framing is the reverse: "The model can say which fires are more likely than average to run long, at low precision. It cannot say that any fire is safe."

### Out-of-scope uses (for the model card and README)

The fire-duration model in this repository is a research artifact trained on historical records. It is **not** for:

1. **Dispatch, resource allocation, staffing, evacuation or any real-time decision about an active fire.** At any threshold, it misses between 43% and 63% of fires that will burn 30 days or more, and it predicts under half a day for two thirds of fires, including 1 in 1,000 fires that go on to burn a month.
2. **Declaring any fire "likely to be short" or "low risk".** The model's short predictions have lower MAE than its long ones only because most fires are short; a constant prediction of 0 days does better.
3. **Fires in states or reporting systems with low coverage**, including Texas (12% of 2010+ fires in the training sample), Hawaii (4%), Puerto Rico (5%), Virginia (6%), Louisiana (41%), California (51%), any fire recorded through an interagency system (0.3%), and fires on land of unspecified or "state or private" ownership (58% and 28%). The model has not seen these fires and its outputs there carry no evidence.
4. **Any fire after 2020, or any year the model was not evaluated on.** The evaluation split is random, not temporal, so reported numbers are upper bounds on forward performance.
5. **Ranking agencies, landowners or jurisdictions by response quality.** Duration is a reporting outcome as much as a physical one; containment date recording differs by agency (BLM 99% recorded, state/local 69%).
6. **Point predictions shown without a distribution.** A predicted "13 days" is a mean over fires whose median was 5 days and a quarter of which went out the same day.
7. **Any product that shows a number without the coverage note, the base rate, and the calibration table beside it.**
8. **Input beyond the training feature space**, including fires outside the United States, fires with fabricated or estimated coordinates, or causes not in the 13 NWCG general-cause categories.

Related tools that are designed for the operational need: the National Interagency Fire Center's Predictive Services outlooks and the National Fire Danger Rating System (unverified in this session; cite from their sites before publishing).

---

## (e) Uncertainty communication and documentation skeletons

### What a public site must show next to any predicted quantity

Rules, each with a wording pattern:

1. **Never a bare number.** Pattern: "Fires like this one (same region, month and cause; n = 8,677 in the test set) were contained within a day 82% of the time, ran 7 days or more 2% of the time, and 30 days or more 0.5% of the time."
2. **Base rate beside every lift.** Pattern: "Predicted 5 to 10 days: 26% ran 7+ days, against 3% of all fires (8× the base rate, from n = 1,686)." Never show the 8× without the 3% and the 26%.
3. **n = everywhere.** Every percentage, bin, map cell and table row carries its n. Cells with n < 100 are greyed and labelled "too few fires to say".
4. **Intervals, not ±.** Pattern: "Test RMSE 6.60 days (95% bootstrap interval 6.25 to 7.08; 1,000 resamples of 126,011 test fires)." Replace "6.33 (±0.13)" with "6.33; five fold values 6.17 to 6.55".
5. **Reliability diagram, not a scatter.** Replace `residuals.png` with (a) a reliability diagram of mean predicted vs mean actual per prediction bin with bin n, and (b) a per-bin stacked bar of actual outcome classes (0 d, 1 d, 2 to 6 d, 7 to 29 d, 30+ d). The scatter hides that 84% of points sit at x = 0.
6. **Coverage note on every model view.** Pattern: "Trained on 630,053 fires from 2010 to 2020 that have a recorded containment date (74% of records). Coverage is 12% for Texas and 51% for California; see the coverage map."
7. **Baseline row always visible.** Any metric table shows predict-zero and predict-mean in the same table, same rows, same interval method.
8. **Version and hash.** Footer on every page: model version, data file SHA-256 prefix, date of run, link to `docs/EXPERIMENTS.md` entry.
9. **Colour and language conventions.** No red/green for predicted duration (it reads as safe/unsafe). Use a single-hue sequential scale for magnitude and neutral wording ("expected", "typical", "range"), never "risk", "danger", "safe" or "low".
10. **A one-line disclaimer that is specific.** Not "for informational purposes only" but "This model loses to 'predict 0 days' on mean absolute error and misses most month-long fires; it is a study of what location and date can and cannot tell you."

### Appendix E1: `docs/MODEL_CARD.md` skeleton

Sections follow Mitchell et al. 2019, section 4 (https://arxiv.org/pdf/1810.03993). Filled fields come from `REPRODUCTION.md`, `EXPERIMENTS.md`, `DATA_VERSION.md` and this review; `[TODO]` marks fields Robyn must supply or that a later phase must produce.

```markdown
# Model card: FPA FOD fire-duration Random Forest

## Model details
- Developer: Robyn Collie (individual, portfolio project). [TODO: contact]
- Model date: original run 2026-01-08 (notebook timestamps); reproduction 2026-09-25.
- Model version: v0 (E-001). Differs from nothing; first version.
- Model type: scikit-learn RandomForestRegressor, 100 trees, max_depth 10,
  random_state 42, default min_samples_leaf. 17 input columns.
- Training: 504,042 rows (80% random split, seed 42). Test: 126,011 rows.
- Resources: README.md, docs/EXPERIMENTS.md (E-001..E-003),
  docs/review/REPRODUCTION.md, scripts/reproduce.py.
- Citation: [TODO]. License: MIT (code); data under USFS terms.
- Feedback: [TODO: GitHub issues on Robyn-Collie/wildfire-analysis]

## Intended use
- Primary intended use: a study of how much fire duration can be predicted
  from location, day of year and recorded cause alone, and a demonstration
  of evaluating a zero-inflated regression target against naive baselines.
- Primary intended users: readers of the portfolio; data analysts
  reproducing the result.
- Out-of-scope uses: see the eight items in docs/review/panel-rai.md section (d).
  Summary: not for dispatch, staffing, evacuation or any live decision;
  not for "likely short" labels; not for low-coverage states or reporting
  systems; not for years after 2020; not for ranking agencies.

## Factors
- Relevant factors: state; reporting agency (NWCG_REPORTING_AGENCY);
  land owner (OWNER_DESCR); source system type (FED/NONFED/INTERAGCY);
  cause known vs missing; fire size class (post hoc only); year.
  Determined from the coverage analysis (26.3% of 2010+ fires lack a
  containment date, concentrated in Texas, the South, non-federal reporters).
- Evaluation factors reported so far: cause missing vs known (MAE 1.03 vs
  1.55; mean actual 0.78 vs 1.21 days). [TODO: per-state, per-agency,
  per-owner metrics with bootstrap CIs; per-year.]

## Metrics
- Model performance measures: RMSE and MAE in days on the test split.
  RMSE was the original selection criterion; this card reports both because
  they disagree about whether the model beats a constant.
- Decision thresholds: none in the model. If a threshold on predicted days
  is used to flag fires, see the recall/precision table (section (d) of the
  review) [TODO: regenerate with the full model].
- Uncertainty: 5-fold CV std of fold RMSE 0.13 (not an interval);
  bootstrap 95% CI on test metrics (1,000 resamples) [TODO: regenerate with
  the full model; subsampled values: RMSE 6.25 to 7.08, MAE 1.38 to 1.44].

## Evaluation data
- Dataset: FPA FOD 6th ed. (Short 2022, doi:10.2737/RDS-2013-0009.6),
  SHA-256 04f5ab8b...51a965a8; test split = 20% random of the 630,053-row
  sample (seed 42).
- Motivation: same distribution as training; no separate challenging set.
  [TODO: temporal hold-out (train <= 2017, test 2018-2020); low-coverage
  state hold-out.]
- Preprocessing: FIRE_YEAR >= 2010; CONT_DATE not null; duration in whole
  days; negative durations dropped (0 rows); cause one-hot (13 incl.
  "Missing"); DOY as sin/cos.

## Training data
- 504,042 fires, 2010-2020, with a recorded containment date. Coverage by
  state, owner and agency: see docs/DATASHEET.md, "Composition".
- Target distribution: 83.7% zero days; 91.5% <= 1 day; 99th pct 24 days;
  max 364.

## Quantitative analyses
- Unitary results (test split, same rows):
  | Predictor | RMSE | MAE |
  | Random Forest | 6.596 | 1.377 |
  | Predict training mean (1.08) | 7.251 | 1.830 |
  | Predict 0 (median) | 7.333 | 1.094 |
  | Per-cause median | 7.333 | 1.094 |
  | Per-cause mean | 7.162 | 1.739 |
- Error concentration: fires >= 30 days (0.8% of test) carry 85% of squared
  error. On 0-day fires the mean prediction is 0.55 days.
- Reliability table: [TODO: regenerate section (d) table with full model.]
- Intersectional results: [TODO: state x cause-known; agency x year.]

## Ethical considerations
- Data: no personal data; locations are fire points, some on private land.
- Human life: yes, the domain is safety-critical. The model is therefore
  explicitly not for operational use (see Intended use).
- Mitigations: naive-baseline comparison published; coverage disclosed;
  no API or field-use path.
- Risks and harms: a "short" prediction acted on as a stand-down signal;
  outputs for low-coverage regions mistaken for evidence; duration
  differences between agencies read as response quality.
- Use cases: no identified beneficial operational use at this performance.

## Caveats and recommendations
- Random split; forward performance is unknown and expected to be worse.
- Duration is measured in whole days from date fields; 17.5% of "1-day"
  fires lasted under 12 hours.
- Cause may be assigned after discovery; "Missing" cause is a feature.
- Recommendation: treat this as a negative result about location-and-date
  features; do not tune before beating predict-zero on MAE or defining a
  metric that matches a use.
```

### Appendix E2: `docs/DATASHEET.md` skeleton

Questions follow Gebru et al. 2021, section 3 (https://arxiv.org/pdf/1803.09010). This datasheet covers **the derived model sample and Parquet cache**, not the upstream FPA FOD, whose own documentation is the Forest Service's; where an answer belongs to the upstream dataset it says so.

```markdown
# Datasheet: wildfire-analysis derived dataset (fires.parquet and the model sample)

## Motivation
- Purpose: a typed cache of the FPA FOD "Fires" table for analysis and a
  filtered sample for the fire-duration model; created to make every
  README number reproducible from one hashed file.
- Created by: Robyn Collie. Funded by: nobody (personal project).
- Upstream: Short, K. C. 2022. Spatial wildfire occurrence data for the
  United States, 1992-2020 [FPA_FOD_20221014], 6th ed.
  doi:10.2737/RDS-2013-0009.6. Created by the USDA Forest Service for the
  Fire Program Analysis system. [Upstream funding: see the USFS record.]

## Composition
- Instances: one row per reported wildfire (2,303,566), 1992-2020, from
  federal, state and local reporting systems. 37 attribute fields plus
  OBJECTID and Shape in SQLite; the Parquet cache adds DISCOVERY_DATETIME,
  CONT_DATETIME, DURATION_DAYS, DURATION_HOURS, DISCOVERY_MONTH.
- Sample or complete: the upstream is itself a compilation, not a census
  (reporting is voluntary and uneven across systems). The model sample is
  630,053 rows = 2010+ AND CONT_DATE not null = 73.7% of 854,880 2010+
  fires. Not representative: coverage by state ranges from 4.3% (HI) to
  99.9% (GA); Texas 12.4%, California 51.2%; owner "STATE OR PRIVATE"
  27.7%, "MISSING/NOT SPECIFIED" 57.8%, BLM 99.2%; reporting agency
  ST/C&L 69.1%, IA 0.3%, BLM 99.3%. Full table: docs/review/panel-rai.md (c) CRIT-3.
- Data per instance: dates, times, coordinates, cause (NWCG), size,
  ownership, reporting unit, state/county.
- Label/target: DURATION_DAYS (whole days, CONT_DATE minus DISCOVERY_DATE);
  83.7% of model-sample values are 0.
- Missing information: CONT_DATE missing in 894,813 rows (38.8%);
  DISCOVERY_TIME in 789,095 (34.3%); NWCG_GENERAL_CAUSE "Missing" in
  32.1% of 2010+ rows (26.7% of the model sample). Missingness is
  concentrated in non-federal reporters and the South.
- Relationships: ICS_209_PLUS and MTBS join IDs link some fires to
  incident reports and burn-severity records (not used here).
- Recommended splits: the original random 80/20 (seed 42) is recorded for
  reproduction only. [TODO: locked temporal test set, per EXPERIMENTS.md.]
- Errors and noise: day-level target coarseness (17.5% of 1-day fires
  under 12 h); no negative durations; max 364 days; known reporting-regime
  shifts (Northeast 2001, 2005; CT and RI zero years). A likely
  duplicate-reporting risk across systems is documented upstream. [TODO:
  quantify duplicates via FPA_ID / ICS join IDs.]
- Self-contained: yes for analysis; upstream archived at the DOI.
- Confidential or sensitive: no personal data. Fire locations on private
  land could in principle be linked to an owner; not done here.
- Subpopulations: by state, owner, agency (see above). No people.

## Collection process
- Acquisition: reported by agency personnel into fire-reporting systems,
  compiled by the USFS; not directly observable; validation described in
  the upstream documentation. [Cite USFS metadata; unverified here.]
- Mechanisms: download of the SQLite archive by scripts/download_data.py
  on 2026-09-25; SHA-256 checked; Parquet built by scripts/build_cache.py.
- Sampling strategy for the model sample: deterministic filter
  (FIRE_YEAR >= 2010 AND CONT_DATE IS NOT NULL).
- Who collected: agency staff (upstream); Robyn Collie (derived).
- Timeframe: fires 1992-2020; upstream compiled 2022; derived 2026-09-25.
- Ethical review: none required (no human subjects).

## Preprocessing, cleaning, labeling
- Done: date parsing (MM/DD/YYYY), HHMM time validation, duration
  derivation, categorical typing, 2010+ filter, containment-date filter,
  one-hot cause, sin/cos DOY, drop of FIRE_SIZE_CLASS and FIRE_YEAR from
  features.
- Raw data saved: yes, the SQLite file is retained and hashed
  (docs/DATA_VERSION.md, data.sha256).
- Software: src/data_loader.py, src/features.py, scripts/build_cache.py,
  scripts/reproduce.py (this repo, MIT).

## Uses
- Used for: the descriptive analysis (Part 1) and the duration model (Part 2).
- Repository of uses: this repo; docs/EXPERIMENTS.md.
- Other tasks: seasonal and cause analyses; coverage/reporting studies;
  joins to weather and terrain.
- Impact of composition on future uses: the containment-date filter
  removes a quarter of recent fires non-randomly; any duration model or
  agency comparison inherits that. Mitigation: report coverage per group;
  never compare agencies on duration without noting recording rates.
- Should not be used for: operational prediction; agency ranking; any
  claim about Texas, Virginia, Hawaii, Puerto Rico, Louisiana or
  interagency-reported fires from the model sample.

## Distribution
- Third parties: the derived Parquet is not distributed (built locally);
  the upstream is public at the DOI.
- How: GitHub (private repo) for code; data via download script.
- License: code MIT; data subject to USFS terms (cite as above).
- Third-party restrictions, export controls: none known. [TODO: confirm
  from the USFS record.]

## Maintenance
- Maintainer: Robyn Collie. [TODO: contact]
- Erratum: docs/review/REPRODUCTION.md and the README "Errata" section
  [TODO: create].
- Updates: rebuild when a new FPA FOD edition is released; record the new
  hash in docs/DATA_VERSION.md.
- Older versions: previous hashes kept in docs/DATA_VERSION.md history.
- Contributions: [TODO: GitHub issues/PRs].
```

---

## (f) Headline proposals and the portfolio narrative

Ranked by defensibility (most defensible first).

1. **"Large US wildfires burn more acres than they did in the 1990s, and the number of fires has not grown: 2.3 million records, 1992 to 2020, with every number reproducible from one hashed file."**
   Defensible now: Kendall tau 0.43 (p = 0.0007) for Class G acres; tau 0.10 (p = 0.47) for counts (R). It leads with the one finding that survived review and with the reproducibility work, which is the actual differentiator.

2. **"What a fire's location and start date can and cannot tell you about how long it will burn: a duration model tested against 'predict zero', and what it lost."**
   Defensible as a negative result. Honest and unusual in a portfolio. Requires the README to be rewritten around E-002 and the coverage table before it is true.

3. **"Predicting wildfire duration at discovery from public fire records."**
   The current implied headline. Least defensible: the model does not predict duration in any operational sense, and "at discovery" is unproven for the cause feature. Only usable if paired with headline 2's framing.

**Recommended:** headline 1 for the repo and site; headline 2 as the Part 2 section title.

### The "what I found and what I got wrong" paragraph

> I set out to test whether US wildfires are getting worse and whether a fire's location, date and recorded cause can predict how long it will burn. The first question has a clear answer in the Forest Service record: acres burned by the largest fires (5,000+ acres) trend upward from 1992 to 2020 (Kendall tau 0.43, p = 0.0007), while the number of fires shows no trend. The second question mostly does not. My Random Forest reproduces exactly, and it beats predicting the mean on RMSE by about 9%, but I originally wrote that it "does well on short fires", and that was wrong: on the 84% of fires contained the same day it predicts half a day, and a constant zero beats it on mean absolute error by 26%. I also proposed it as an early-warning tool; at any usable threshold it misses roughly half of month-long fires, so it is not one. I had also not noticed that my sample dropped a quarter of recent fires, including 88% of Texas, because they lack a containment date, and that two of three anomalies I flagged in the descriptive work were label errors, not anomalies. The repo now records each of those corrections next to the original claim, with the script that checks it.

---

## (g) Proposed changes to other files

I did not edit any of these. Owners: the lead.

**README.md**
- Delete N-5 ("Serve predictions through a small API for field use") and P1-1 placeholder link.
- Rewrite P2-2 as a hypothesis and add a "Could this be an early warning? No." subsection with the recall/precision table regenerated from the full model.
- Replace P2-19 with the sentence in CRIT-2; replace the results table with the E-002 table plus bootstrap CIs; relabel "± 0.13" as the std of five fold RMSEs.
- Add a "Coverage" subsection with the CRIT-3 table (at least the state, owner and agency rows) and the sentence "Trained on 74% of 2010+ fires; Texas 12%, California 51%."
- Add "Errata" listing P1-8, P1-9, P1-10 with what the check found, and P2-19.
- Delete C-5 and replace with the reverse framing in section (d).
- Add the out-of-scope list (section (d)) verbatim under "What this model can't do" or link to `docs/MODEL_CARD.md`.
- P2-8: state that "Missing" is one of the 13 cause categories (26.7% of the sample) and that cause may be assigned after discovery.
- Minor fixes MIN-1 to MIN-5, MIN-7, MIN-8. MIN-6 is Robyn's call.
- P1-11: add "MISSING/NOT SPECIFIED" as the fourth category (22.9M acres).
- P1-13/P1-16: present the mean-to-median flip of the Control Efficiency Score as the finding, or remove the score.

**docs/MODEL_CARD.md and docs/DATASHEET.md (new)**
- Create from Appendix E1 and E2; fill `[TODO]` fields after the temporal split and per-group evaluation exist.

**docs/EXPERIMENTS.md**
- Add an entry for the bootstrap CI and flag-threshold analysis once run with the full model (my subsampled runs are review evidence, not a logged experiment). Config to log: 1,000 bootstrap resamples of the 126,011 test rows, seed 42; thresholds 0.5, 1, 2, 3, 5, 10 days; long-fire definitions 7 and 30 days.

**scripts/reproduce.py**
- Add: bootstrap CIs for every test metric; the reliability table (prediction bins as in section (d)); per-state, per-owner, per-agency coverage table for the 2010+ filter; per-group test metrics (cause missing vs known, state, agency). Replace the scatter with a reliability diagram plus a per-bin outcome-class bar.

**src/train_model.py**
- Log predict-zero and predict-mean baselines alongside the RF metrics so the pipeline output itself carries the comparison.
- `plot_residuals`: replace or supplement with the reliability diagram.

**src/features.py**
- Document (docstring) that the "Missing" cause becomes a feature column and that `FIRE_YEAR` is dropped, so a temporal split must be done before this function or by index.

**docs/img/**
- Regenerate both figures from `scripts/reproduce.py` and caption with run date and data hash.

**Public site (Netlify, not yet built)**
- Apply the ten rules in section (e) to every model view; coverage map as a first-class page; no red/green scale for duration.

---

## Summary (10 lines)

1. Wrote `docs/review/panel-rai.md`: verdict, 62-row claims ledger, findings (3 Critical, 7 Major, 8 Minor), misuse analysis with out-of-scope list, model card and datasheet skeletons, three headlines, proposed changes.
2. Scratch scripts and outputs in `/tmp/claude-0/-home-user-wildfire-analysis/a4df9529-3e52-5fbc-b7e0-fb427368a57f/scratchpad/panel-rai/`.
3. Finding 1 (Critical): the "early warning" and "API for field use" framing is refuted; at a 5-day flag the model misses 43% of 30+ day fires and at 10 days 63%; 66% of fires are predicted under 0.5 days and that bucket holds 7.6% of all month-long fires.
4. Finding 2 (Critical): the README's reading of MAE is wrong; model 1.38 vs predict-zero 1.09 (bootstrap ratio 1.27 to 1.31); on 0-day fires it predicts 0.55 days.
5. Finding 3 (Critical): the sample silently drops 26.3% of 2010+ fires; Texas 12.4% kept (11.8% of fires, 2.0% of sample), Hawaii 4.3%, Puerto Rico 5.2%, Virginia 5.6%, California 51.2%; owner "STATE OR PRIVATE" 27.7%; interagency reporters 0.3%.
6. "± 0.13" is a fold std; bootstrap 95% CI on test RMSE is 6.25 to 7.08.
7. "Missing" cause is a feature and 26.7% of the sample; cause-missing fires are shorter and easier, a reporting-regime signal.
8. Two of three flagged anomalies do not exist; recommend an Errata section rather than deletion.
9. Recommended headline: large fires burn more acres, fire counts do not rise, everything reproducible; Part 2 reframed as a negative result.
10. The LA anecdote is Robyn's call; if kept, close the loop with the California coverage fact.
