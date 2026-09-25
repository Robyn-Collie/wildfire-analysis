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
