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
