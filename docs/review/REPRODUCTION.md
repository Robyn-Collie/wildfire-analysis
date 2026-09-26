# Reproduction of README claims

**Run:** 2026-09-25, branch `review/phase0-reproduction`, `python scripts/reproduce.py --part model` and `--part descriptive`.
**Data:** `FPA_FOD_20221014.sqlite`, SHA-256 `04f5ab8b…51a965a8` (see `docs/DATA_VERSION.md`); hash checked by the script.
**Environment:** Python 3.12.10, pandas 3.0.6, NumPy 2.5.3, scikit-learn 1.9.1 (the original notebook ran on Python 3.14.2 with unrecorded package versions).
**Raw output:** `outputs/reproduction_model.json`, `outputs/reproduction_descriptive.json` (regenerated, not committed).

Verdicts: **Reproduced** (matches to the stated precision), **Differs** (the number or the claim built on it doesn't hold as stated), **Can't reproduce** (no reading of the data I tried gives the claim; the Tableau definition may differ).

## Part 2: duration model

| Claim | README value | Reproduced value | Verdict | Note |
|---|---|---|---|---|
| Sample size | 630,053 | 630,053 | Reproduced | 2010+ with `CONT_DATE`. |
| Negative durations dropped | "dropped as data errors" | 0 rows | Reproduced (no-op) | The filter exists but removes nothing in this sample. |
| Features | lat, lon, 13 causes, sin/cos DOY | 17 columns, as described | Reproduced | |
| CV RMSE | 6.33 (± 0.13) | 6.3322 (± 0.1338) | Reproduced | Identical to 4 d.p.; the RF is deterministic with `random_state=42`. |
| Test RMSE | 6.60 | 6.5957 | Reproduced | |
| Test MAE | 1.38 | 1.3768 | Reproduced | |
| Std of duration ("baseline") | 7.05 | 7.052 (full sample); 7.251 (test split) | Reproduced | 7.05 is the full-sample std. On the same test rows, predict-the-training-mean scores RMSE 7.251. |
| Median duration | 0 days | 0 days | Reproduced | 83.7% of fires have duration 0; 91.5% ≤ 1 day; 99th pct 24 days; max 364. |
| "≈6% better than always predicting the average" | ≈6% | 6.4% vs 7.05; **9.0%** vs predict-mean on the same test rows | Differs (understated) | The like-for-like RMSE comparison is 6.60 vs 7.25. |
| Model beats naive baselines (implied) | — | **MAE: model 1.377 vs predict-zero 1.094** | **Differs** | On MAE the model is **26% worse** than predicting 0 days for every fire. Predict-median and per-cause median are also 0 for every cause, so they tie predict-zero. The model only beats mean-type baselines (MAE 1.83 predict-mean, 1.74 per-cause mean). |
| "MAE is low … the model does well on the many short fires" | — | On 0-day fires (83.7% of test) the model predicts 0.55 days on average | **Differs** | The model does *worse* than predict-zero on short fires. Its MAE looks low because most true values are 0, not because it is good on them. |
| "fires that burned 100+ days are mostly predicted to last a few days" | — | Mean prediction for 100+ day fires: 15.9 days (n = 122) | Reproduced (direction) | Fires ≥ 30 days are 0.8% of the test set but carry **85%** of the squared error. |
| Top features: lat, lon, cos(DOY), natural cause | as stated | MDI: lat 0.357, lon 0.323, cos 0.127, natural 0.093, sin 0.082 | Reproduced | Permutation importance (MAE, 50k test rows) agrees on the order of the top 4 but ranks sin(DOY) above natural cause. |
| Figures in `docs/img/` come from the reported run | implied | Can't confirm | Can't reproduce | Notebook cells ran out of order (display cell exec 5, training cell exec 6). The reproduced figures are in `outputs/`; `docs/img/` is left unchanged until the README is rewritten. |

### Target and sample checks (not claimed, but needed to judge the claims)

- **The sample drops 26.3% of 2010+ fires** (224,827 of 854,880) for a missing `CONT_DATE`, and not at random:
  - The dropped fires are 91% non-federal records vs 73% of the kept ones.
  - They are 52% in the South vs 38% of the kept ones.
  - Their cause is missing 22% of the time vs 5% for the kept ones.
  - Natural causes are 6% of the dropped fires vs 14% of the kept ones.
  - Missing-containment share by state: Virginia 94%, **Texas 88%**, California 49%, Louisiana 60%. The model has barely seen Texas.
- **Day granularity:**
  - 91.7% of kept fires have both times recorded.
  - Among "0-day" fires, the median is 0.9 hours and the 99th percentile 9.1 hours.
  - Among "1-day" fires the median is 20 hours, and 17.5% lasted under 12 hours (they crossed midnight).
  - The day-level target mixes a 20-minute fire and a 23-hour fire into the same class, and splits two 3-hour fires into 0 and 1.
- No duration exceeds 365 days (max 364). No negative hour-level durations.

## Part 1: descriptive claims

| Claim | README value | Reproduced value | Verdict | Note |
|---|---|---|---|---|
| Records | 2,303,566 | 2,303,566 | Reproduced | |
| Fields | 38 | 39 columns in `Fires` (37 attributes + `OBJECTID` + `Shape`) | Differs (definitional) | 38 likely excludes the geometry column. |
| Missing containment date | 894,813 | 894,813 | Reproduced | |
| Missing discovery time | 789,095 | 789,095 | Reproduced | |
| Largest fire | 662,700 acres | 662,700 (Starbuck, OK, 2017) | Reproduced | |
| Smallest fire | "near zero" | 0.00001 acres | Reproduced | |
| Natural causes ≈105.6M acres, most acreage | 105.6M | 105.64M acres = 58.7% of 180.0M total, from 14.2% of fires | Reproduced | Human-caused fires are 77.4% of fires and 35.3% of acres. |
| Classes B and C mostly debris/open burning | as stated | B: debris 30%, missing 24%, arson 15%. C: debris 26%, arson 24%, missing 22% | Reproduced (plurality) | "Most often" is a plurality, not a majority. |
| Class G acres trend upward | "higher highs and higher lows" | Kendall τ = 0.43, p = 0.0007; Theil–Sen +178k acres/yr; mean 3.5M (1992–2005) vs 5.7M (2006–2020) | Reproduced | The number of fires shows no trend (τ = 0.10, p = 0.47). "Worse" is about large-fire area, not fire counts. "Higher lows" is loose: 2010 (2.1M) is lower than 1996 or 1999. |
| USFS, BLM, private lead acres burned | as stated | USFS 38.4M, BLM 37.2M, Private 25.6M; next is "MISSING/NOT SPECIFIED" 22.9M | Reproduced | The 4th category is unknown ownership, nearly as large as private. |
| Large fires start in South in winter, shift West by summer | as stated | Class G counts: South leads Jan–Apr; West leads May–Oct (peak Aug, 1,062); Alaska peaks June | Reproduced | |
| Western fires last longest, peaking in August | as stated | Mean day-level duration: Alaska 13.1, West 1.6, others ≤ 0.5; West by month peaks August (2.5 days) | Reproduced | Depends on whether Alaska counts as "West". |
| June spike in Class G acreage in **Arkansas** | as stated | Arkansas has **2** Class G fires in 29 years (March, April); **none in June**. June is AR's 2nd-quietest month overall | **Can't reproduce** | **Arizona** (100 Class G fires, 2.8M acres in June) and **Alaska** (443 fires, 22.7M acres in June) both peak in June. Likely an AR/AZ/AK label mix-up in Tableau. Needs Robyn to check the workbook. |
| December fires in Texas | flagged anomaly | December is one of Texas's *quietest* months (10,742 fires; 326k acres, 3rd lowest). One outlier: Dec 2005 (94.5k acres, largest December by 2.6×) | Can't reproduce as a general pattern | Texas's big-fire season is Jan–Apr. The Dec 2005 spike is a single event period. Also, 88% of 2010+ Texas records lack a containment date. |
| 2010 outlier in the Northeast | flagged anomaly | Northeast (CT, ME, MA, NH, RI, VT, NY, NJ, PA): 2010 count z = 0.98, acres z = 0.48. Not an outlier | Can't reproduce | The Tableau region definition is unknown. The Northeast series shows **reporting-regime shifts** instead: counts jump 2001 and 2005 (NY dominates), CT and RI report 0 fires in some years. Treat Northeast trends as reporting artifacts until checked. |
| Control Efficiency Score (1 ÷ mean acres/hour to containment) | defined; README says unfair to rank | Recomputed for 1.14M fires with both times and positive duration | Reproduced, and **unstable** | Switching mean → median acres/hour moves **USFS from 10th to 1st** of 12 owner categories (BLM 6th → 2nd). The mean is dominated by a few huge fires. The score measures fire size distribution more than response. |

## What this changes

1. The "≈6% better" RMSE claim is a slight *under*statement (9% against the same-split mean baseline), but RMSE is driven by 1% of fires.
2. On the typical fire, the model is worse than a constant zero on MAE. The README's reading of the low MAE is wrong.
3. The model sample excludes about a quarter of 2010+ fires, heavily from Texas, the South and non-federal reporters. Results don't generalize to them.
4. Two of the three flagged Part 1 anomalies don't reproduce with the obvious definitions, and the third (Arkansas June) probably names the wrong state.
