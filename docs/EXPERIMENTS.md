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

## E-009 · 2026-09-25 · Same model after the src/ fixes (leap-aware DOY angle, ORDER BY FOD_ID)
- Branch/commit: `fix/src-defects` (`6d71dc9` features, `16b7dd9` loader); `python scripts/reproduce.py --part model --skip-cv --out outputs_fix/`, `WILDFIRE_N_JOBS` unset (n_jobs=1), `OMP_NUM_THREADS=1`. Python 3.12.3, pandas 3.0.6, numpy 2.5.3, scikit-learn 1.9.1. Data hash matches `data.sha256`.
- Config: identical to E-001 (RF 100 trees, depth 10, seed 42; random 80/20 split, seed 42; same 17 feature names; n = 630,053, 504,042 train / 126,011 test; 0 negative durations). CV skipped. Two inputs changed: (1) the day-of-year angle is now `2*pi*(DOY-1)/days_in_year` from `DISCOVERY_DATE` with 366 days in leap years (E-001 used `DOY/365`), which moves the SIN/COS features of the 173,141 rows (27%) discovered in 2012, 2016 and 2020 by up to one day step (about 1 degree) and puts the 140 DOY-366 rows at Dec 31 instead of Jan 1; (2) the loader orders rows by `FOD_ID` instead of SQLite's physical order, which moves 523 rows (positions 125,578 to 327,351) and swaps 92 of the 126,011 test rows.

| Run | Row order | DOY angle | Test RMSE | Test MAE | Predict-zero MAE | Predict-mean RMSE |
|---|---|---|---|---|---|---|
| E-001 | rowid | DOY/365 | 6.5957 | 1.3768 | 1.0941 | 7.2506 |
| E-009a (isolation, scratch script) | rowid | leap-aware | 6.6433 | 1.3794 | 1.0941 | 7.2506 |
| **E-009** | FOD_ID | leap-aware | **6.6437** | **1.3793** | 1.0941 | 7.2506 |

- Metrics (E-009): Test RMSE 6.6437 (+0.0480 vs E-001, +0.73%), MAE 1.3793 (+0.0025). Versus baselines on the same test rows: 8.4% better RMSE than predict-mean (E-001: 9.0%), 26.1% worse MAE than predict-zero (unchanged). Error share by true duration: fires >= 30 days (0.8% of test rows) carry 84.8% of squared error. MDI top 5: lat .352, lon .320, cos DOY .140, natural .092, sin DOY .076. Permutation (MAE increase, days, 50,000 test rows): lat .635, lon .524, cos DOY .395, sin DOY .112, natural .047.
- Reason for the difference: almost all of it is the leap-year fix (E-009a differs from E-001 by 0.0476 RMSE; the reordering then adds 0.0004). The baselines are unchanged to 4 d.p. because the target and the test rows are (essentially) the same; only the season features moved, by at most one day step for a quarter of the rows. A random forest with depth-10 trees picks up that shift through its split thresholds on SIN/COS and gives a slightly worse test RMSE. The "third or fourth decimal" expectation was wrong: the change is in the second decimal, which says the reported RMSE is sensitive at the 0.05 level to a sub-1-degree rotation of the season encoding, consistent with the bootstrap 95% interval of 6.25 to 7.08 on the E-001 test RMSE (`panel-rai`). The fix is a correctness change, not an improvement, and it does not change any conclusion in E-002 or the panel report.
- Conclusion: E-001's numbers are no longer what `scripts/reproduce.py` regenerates on this branch; README Part 2 numbers should be regenerated (or retired per the panel decision) from this code. The CV numbers were not re-run (CV is 14 min single core); expect them to move by a similar amount.
