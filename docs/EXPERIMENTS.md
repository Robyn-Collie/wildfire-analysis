# Experiment log

Every model run, including failed and unflattering ones. Data hash is the SHA-256 of `data/FPA_FOD_20221014.sqlite`; all runs so far use `04f5ab8b…51a965a8` (`data.sha256`).

## Held-out data policy

- **Phase 0 (reproduction)** re-scores the original random 80/20 split. That split is the original author's; nothing was tuned on it.
- **From Phase 4 on**, a locked test set is defined once and not used until final evaluation (see the entry that defines it).

---

## E-001 · 2026-09-25 · Reproduce the reported model
- Branch/commit: `review/phase0-reproduction`
- Config: RF(n_estimators=100, max_depth=10, random_state=42); random 80/20 split (seed 42); 5-fold shuffled KFold (seed 42) on train. Features: lat, lon, sin/cos DOY, 13 cause dummies. n = 630,053 (2010+, `CONT_DATE` present). Python 3.12.10, scikit-learn 1.9.1.
- Metrics: CV RMSE 6.3322 ± 0.1338 (folds 6.37, 6.55, 6.37, 6.21, 6.17). Test RMSE 6.5957, MAE 1.3768.
- Conclusion: identical to the notebook to 4 d.p.

## E-002 · 2026-09-25 · Naive baselines on the same test rows
- Branch/commit: `review/phase0-reproduction`
- Config: statistics fitted on the 504,042 training rows, scored on the 126,011 test rows.

| Predictor | RMSE | MAE |
|---|---|---|
| Random Forest (E-001) | 6.596 | 1.377 |
| Predict training mean (1.08) | 7.251 | 1.830 |
| Predict 0 (= training median) | 7.333 | **1.094** |
| Per-cause median (all 0) | 7.333 | 1.094 |
| Per-cause mean | 7.162 | 1.739 |

- Conclusion: the RF beats mean-type baselines on both metrics (RMSE −9.0% vs predict-mean), but **loses to predict-zero on MAE by 26%**. On 0-day fires (83.7% of the test set) the RF predicts 0.55 days on average. Fires ≥ 30 days (0.8% of test rows) carry 85% of the squared error; the RF's mean prediction for 100+ day fires is 15.9 days.

## E-003 · 2026-09-25 · Importance check
- Branch/commit: `review/phase0-reproduction`
- Config: MDI from E-001; permutation importance (neg. MAE, 5 repeats, 50,000 random test rows, seed 42).
- Metrics: MDI top 5: lat .357, lon .323, cos DOY .127, natural .093, sin DOY .082. Permutation (MAE increase, days): lat .630, lon .526, cos DOY .253, sin DOY .159, natural .035.
- Conclusion: geography and season dominate under both methods. Cause matters much less by permutation than MDI suggested.

## E-004 · 2026-09-25 · Forward-in-time split of the reported model (panel-ml, run1)
- Branch/commit: `review/panel`
- Config: same features and RF config as E-001. Train 2010-2017 (150,000-row random subsample, seed 42; full fit skipped for time), test all 158,784 fires discovered 2018-2020. `n_jobs=1`.
- Metrics: RF RMSE 8.023 vs predict-train-mean 8.269 (gain 3.0%) vs predict-zero 8.357. MAE: RF 1.540 vs predict-zero 1.223 (26% worse). By year: 2018 RF 7.771 vs mean 7.661 (RF loses); 2019 RF 9.577 vs mean 10.215; 2020 RF 6.584 vs mean 6.807. Same-size random split for comparison: RF 6.326 vs mean 7.031 (gain 10.0%).
- Conclusion: the README's 9% RMSE gain is a random-split artefact. Forward in time the gain is 3% and not present in every year.

## E-005 · 2026-09-25 · Spatial block CV (panel-ml, run2)
- Config: GroupKFold(3) by 1-degree cell on a 150,000-row subsample (1,089 cells); random KFold(3) on the same rows for comparison.
- Metrics: blocked RF RMSE 6.781 vs mean 7.186 (gain 5.6%), fold range 6.53 to 7.08; random 6.694 vs 7.187 (gain 6.9%). MAE blocked: RF 1.481 vs predict-zero 1.088.
- Conclusion: geography transfers at 1 degree; the spatial-leakage attack is weaker than the temporal one.

## E-006 · 2026-09-25 · Geography-only ablation (panel-ml, run3)
- Config: random 80/20 on a 150,000-row subsample; RMSE gain over predict-mean.
- Metrics: full 17 features 5.66%; lat+lon only 4.72% (83% of the full gain); lat+lon+sin/cos DOY 6.19% (beats the full model); DOY+cause with no geography -1.03% (worse than a constant); per-cell mean lookup 2.71%.
- Conclusion: the model is a spatial smoother of the training mean plus season. The cause dummies reduce accuracy.

## E-007 · 2026-09-25 · Model alternatives on the temporal split (panel-ml, run6)
- Config: as E-004. RMSE gain over predict-mean.
- Metrics: RF depth 10 (README) 3.0%; RF depth 20, min_samples_leaf 50: 6.0%; HistGradientBoosting squared loss, defaults: 5.5%; HGB Poisson 1.0%; RF on log1p target 3.9% with MAE 1.217 (ties predict-zero 1.223). Error attribution: fires >= 30 days are 0.97% of test rows and carry 83.1% of squared error; 100+ day fires predicted at 9.4 days on average.
- Conclusion: the untuned depth-10 config is the weakest obvious choice, and no regressor on whole days predicts the tail.

## E-008 · 2026-09-25 · Exploratory classification reframe (panel-ml, run4). SPENT LOOK AT 2019-2020.
- Config: train 2010-2018 (400,000-row subsample), test all fires 2019-2020. Features as E-001. HistGradientBoostingClassifier and LogisticRegression at scikit-learn defaults, no tuning. Climatology = Laplace-smoothed rate by 1-degree cell x month from training years, backing off to cell then global. Brier skill = 1 - Brier / Brier(base rate).
- Metrics (all 2010+ fires, n_test 136,819, base rate 1.38%), target LARGE = FIRE_SIZE >= 300 acres: climatology PR-AUC 0.081 / ROC 0.806 / Brier skill 0.031; HGB 17 features 0.103 / 0.848 / 0.033; HGB lat+lon only 0.108 / 0.838 / 0.045; logistic 0.060 / 0.754 / 0.026. Top decile of HGB scores holds 52.6% of large fires (5.3x lift; climatology 46.4%, 4.6x).
- Metrics (CONT_DATE sample, n_test 96,682): P(duration > 0): HGB PR-AUC 0.593 vs climatology 0.514, base 0.165, Brier skill 0.295. P(duration >= 7 days): HGB 0.313 vs climatology 0.222, base 0.035, Brier skill 0.171.
- Conclusion: real but modest skill; the signal is mostly climatology; lat+lon alone matches or beats the full feature set for LARGE. This run touched the 2019-2020 years once, with default parameters and no selection among configurations.

---

## Locked holdout (defined 2026-09-25, before any Phase D modelling)

- **Holdout:** every fire with `FIRE_YEAR` in {2019, 2020} in `data/fires.parquet` (all 2010+ rows are eligible for the large-fire target; the `CONT_DATE` sample applies only to duration targets). Row identity is `FOD_ID`.
- **Spent looks:** exactly one, E-008, at default parameters with no tuning or model selection. It is disclosed here and in the model card. 2020 alone was rejected as the holdout because the 2020 reporting-system switch (IA-IRWIN) and the August 2020 cause-standard change make it unrepresentative on its own.
- **Development:** 2010-2018 only. Expanding-window temporal CV (train through 2014/2015/2016/2017, test the next year) for every model choice; GroupKFold by 1-degree cell as a secondary check. All tuning is logged here, including losing configurations.
- **Final evaluation:** one run on 2019-2020 per model family after development is frozen, reported with bootstrap intervals, per-year values, and every baseline (base rate, cell x month climatology, logistic regression, geography-only learner) in the same table.

## E-010 · 2026-09-25 · Build the large-fire sample and the FPA FOD-Attributes join
- Branch: `model/large-fire`. Code: `scripts/download_attributes.py`, `analysis/large_fire.py --stage build`.
- Data: FPA FOD-Attributes v1.0 (Pourmohamad et al. 2024, Zenodo 10.5281/zenodo.8381129, CC BY 4.0), annual files 2010-2020, SHA-256 of each in `docs/DATA_JOINS.md`. About 80 of 308 columns kept; every `*_5D_*` column excluded because the five-day window is centred on discovery and includes two later days. `tmmn_Percentile` and `tmmx_Percentile` excluded because they are `>90%` for every CONUS row in these files (a source defect).
- Sample: all FPA FOD fires discovered 2010-2020 outside AK, HI and PR (the attributes are CONUS-only; 12,641 fires dropped). n = 842,239, of which 11,517 (1.37%) reached 300 acres and 5,033 carry an `MTBS_ID`. No containment-date selection.
- Join: 100% on `FOD_ID` for 2010-2018; 98.3% in 2019 (1,071 FPA FOD rows have no attribute row) and 99.9% in 2020. Rows without attributes stay in the sample with missing features.
- Features: 96 (lat/lon, leap-aware sin/cos of day of year, cause as Human/Natural/Missing, owner class, reporting agency, 15 same-day gridMET variables, normals and percentile bins, terrain, 1 km fuels and vegetation, ecoregion, PAD-US 3.0 protection, social vulnerability and population, fire-station and road distances, suppression difficulty, national and GACC preparedness levels, and two drawdown counts: fires in the same reporting unit and the same 1-degree cell in the 7 days before discovery, strictly before).

## E-011 · 2026-09-25 · Baselines and cumulative feature-group ablation on the temporal folds
- Protocol: expanding-window folds on 2010-2018 only (train through 2014/15/16/17, test 2015/16/17/18). HistGradientBoosting at default settings; label LARGE = `FIRE_SIZE >= 300`.
- Fold-mean PR-AUC (range over folds): G0 geography + season 0.089; G1 + cause, owner, agency 0.144; G2 + same-day weather 0.137; G3 + normals and percentiles 0.139; G4 + fuels, terrain, vegetation, ecoregion 0.185; G5 + protection and social 0.202; G6 + suppression context, preparedness, drawdown 0.213. Cell x month lookup 0.083; logistic regression on all features 0.167.
- Conclusion: **same-day weather does not improve the ranking once owner and agency are known**; fuels, terrain and land status do. Geography + season alone is barely better than the lookup and, as a gradient-boosted model, is poorly calibrated (Brier skill -0.96 on the 2015 fold).

## E-012 · 2026-09-25 · Tuning grid on the full feature set
- 16 HistGradientBoosting configurations (learning rate {0.05, 0.1} x max leaf nodes {31, 63} x min samples per leaf {50, 200} x L2 {0, 1}), each scored on all four temporal folds, chosen by mean PR-AUC.
- Result: mean PR-AUC ranged 0.205 to 0.237; every learning-rate-0.05 configuration beat every 0.1 configuration. Chosen: learning rate 0.05, 63 leaves, 50 per leaf, L2 1.0 (mean 0.237, worst fold 0.193). All 16 rows are in `outputs/model/develop_grid.csv` and claim `model.tuning_grid`.

## E-013 · 2026-09-25 · Calibration decision (pre-registered rule, decided on 2018)
- Rule, fixed before the holdout: apply isotonic calibration if any of the 10 quantile bins with at least 20 large fires is off by more than 20% relative on the 2018 fold.
- 2018 fold, chosen configuration: largest relative bin error 31% (PR-AUC 0.320, Brier skill +0.18), so isotonic calibration was applied. An isotonic map fitted on the 2017 fold and applied to 2018 kept PR-AUC at 0.300 and Brier skill at +0.18.
- Conclusion: calibration looked fine forward by one year inside development. E-015 shows it did not hold for 2019.

## E-014 · 2026-09-25 · Spatial block check and the MTBS label on the development years
- GroupKFold(3) by 1-degree cell on 2010-2018 (about 300 held-out cells per fold): PR-AUC lookup 0.013 to 0.016 (a lookup cannot see unseen cells), geography + season model 0.057 to 0.094, full model 0.189 to 0.226. The full model's skill transfers to places it did not train on.
- Secondary label MTBS (fire mapped by MTBS, about 1,000+ acres West / 500+ East), chosen configuration, temporal folds: full model PR-AUC 0.125 to 0.215 against a lookup of 0.030 to 0.071.

## E-015 · 2026-09-25 · Final evaluation on the locked 2019-2020 holdout (the one look)
- Config: chosen configuration (E-012) with isotonic calibration (E-013), fitted on all 2010-2018 fires (706,554); evaluated once on all 2019-2020 CONUS fires (135,685; 1,710 or 1.26% reached 300 acres). Every baseline fitted on 2010-2018 only. 95% intervals: 1,000 bootstrap resamples of the holdout, seed 42. Nothing was refitted or tuned after this run; later commits only re-register claims and redraw figures from the saved results (`--stage claims`).

| Model | PR-AUC [95%] | ROC-AUC | Brier skill vs base rate [95%] | Share of large fires in top 10% of scores |
|---|---|---|---|---|
| Base rate | 0.013 | 0.500 | 0 | 10% |
| Cell x month lookup | 0.075 [0.067, 0.085] | 0.808 | +0.025 [0.018, 0.032] | 44.6% |
| Gradient boosting, geography + season | 0.088 [0.079, 0.099] | 0.844 | +0.039 [0.032, 0.046] | 50.8% |
| Logistic regression, all features | 0.107 [0.098, 0.117] | 0.889 | -0.527 [-0.582, -0.478] | 64.5% |
| Gradient boosting, all features, uncalibrated | 0.145 [0.133, 0.158] | 0.917 | -0.209 [-0.243, -0.175] | 74.2% |
| **Gradient boosting, all features, isotonic (final)** | **0.139 [0.127, 0.151]** | **0.916** | **-0.262 [-0.302, -0.224]** | **74.1%** |

- Ranking: the final model captures 57% of large fires in the top 5% of scores and 88% in the top 20%, against 31% and 64% for the lookup (`model.capture_at_top`).
- **Calibration failed.** Top-decile mean score 0.165 against an observed rate of 0.094. Brier skill -0.85 in 2019 (base rate 1.06%, a quiet year after 2017-2018) and +0.12 in 2020 (1.43%). By region: South -1.20, West +0.13, Plains-Midwest +0.09.
- **Region:** the model loses to the lookup in the South (PR-AUC 0.111 against 0.121, 497 large fires) and wins in the West (0.231 against 0.061) and the Plains-Midwest (0.209 against 0.042). In Texas it wins (0.240 against 0.123), so the Southern loss sits in the other Southern states.
- **Importance** (grouped permutation, uncalibrated model, 10 repeats): fuels/terrain/ecoregion 0.100, protection/social 0.061, owner/agency 0.026, suppression context 0.009, cause 0.002, season 0.001, geography 0.000, same-day weather -0.003, climate normals/percentiles -0.019 (shuffling them helps on 2019-2020, a sign they encode the development years' regime).
- MTBS label: PR-AUC 0.076 [0.067, 0.089] against a lookup of 0.032 [0.026, 0.039].
- **Correction (same day).** The first write-up of this run said 78% of large fires fall in the top decile. With tied isotonic scores the "top decile" flagged 12.0% of fires; the exact share at 10% is 74.1%. `score()` and `bootstrap()` now take exactly the top 10% by rank whenever ties move the share by more than half a point.
- Conclusion: **usable as a ranking, not as a probability.** Where a fire starts carries the signal; weather on the discovery day adds nothing measurable. The prediction headline changes accordingly (see `docs/findings/large_fire_model.md`).
