# Findings: can the record predict which new fires become large?

**Produced by:** `python -m analysis.large_fire --stage all --out outputs/` (48 minutes on 4 CPUs). Re-registering claims and figures from the saved results takes a minute: `--stage claims`. Experiment log: E-010 to E-015. Model card: `docs/MODEL_CARD.md`. Claims: `outputs/claims_model.json` (28).

## The answer

**Knowing where a new fire starts (its fuels, terrain and land status) lets a model rank which fires will become large about twice as well as a location-and-month lookup. Its scores are not usable as probabilities from one year to the next, and weather on the discovery day adds nothing measurable.**

This replaces the first version's duration model, which lost to predicting zero days. The question changed from "how long will it burn?" to "is this one of the roughly 1 in 80 fires that reaches 300 acres?". Practitioners ask that question at initial attack (`docs/review/panel-fire.md`, F7). It can also use every fire in the record, not the three quarters that have a containment date.

## What was tested, and how

- **Sample:** all 842,239 fires discovered 2010-2020 in the conterminous US, all sizes. 11,517 of them (1.37%) reached 300 acres.
- **Inputs:** 96 features known on the discovery day, from the FPA FOD itself and the FPA FOD-Attributes dataset, joined on `FOD_ID` (E-010).
- **Protocol, fixed before development:**
  - Develop on 2010-2018 with four forward-in-time folds.
  - Choose the configuration by mean PR-AUC, and decide calibration by a written rule on the 2018 fold.
  - Then evaluate once on 2019-2020.
  - Every table carries four baselines: the base rate, a lookup of each 1-degree cell's rate by month, logistic regression, and a location-and-season-only model.

## Results on the 2019-2020 holdout (135,685 fires, 1,710 large)

| Model | PR-AUC [95%] | Top 10% of scores capture | Brier skill vs base rate |
|---|---|---|---|
| Lookup: cell x month | 0.075 [0.067, 0.085] | 45% | +0.025 |
| Location + season model | 0.088 [0.079, 0.099] | 51% | +0.039 |
| Logistic regression | 0.107 [0.098, 0.117] | 65% | -0.527 |
| **Gradient boosting, all inputs** | **0.139 [0.127, 0.151]** | **74%** | **-0.262** |

### What held up

1. **The ranking is real and it generalizes.** The model roughly doubles the lookup's PR-AUC with non-overlapping intervals. Its top 10% of scores holds 74% of the fires that became large, against 45% for the lookup. It also works on places it never saw: holding out whole 1-degree cells, PR-AUC was 0.19 to 0.23 on the development years (E-014).
2. **It beat the lookup in every development year and both holdout years** (`model_per_year.png`).
3. **Place carries the signal: fuels, terrain, land status.** Shuffling fuels, terrain and ecoregion costs 0.100 of holdout PR-AUC. Protection status and social context cost 0.061, and owner and agency 0.026. The ablation tells the same story: adding fuels and terrain lifts the fold-mean PR-AUC from 0.139 to 0.185 (E-011).
4. **A second label agrees.** For "became an MTBS-mapped fire", PR-AUC is 0.076 [0.067, 0.089] against a lookup of 0.032.

### What made it look worse

1. **The scores are not calibrated forward in time.**
   - For the top tenth of scores the model said 16.5% and 9.4% happened.
   - Read as probabilities, the scores do worse than one constant rate: Brier skill -0.26 [-0.30, -0.22].
   - The failure is 2019: Brier skill -0.85. 2019 was a quiet year (1.06% of fires became large) after the two large seasons at the end of the training period. In 2020, when 1.43% became large, Brier skill was +0.12.
   - The calibration rule, decided on 2018, applied an isotonic map. The map looked right one year ahead inside development and did not rescue 2019 (E-013).
   - The model has no input that says what kind of year it is.
2. **It loses to the lookup in the South.**
   - PR-AUC 0.111 against 0.121, on 497 large fires, with Brier skill -1.20.
   - In Texas it wins (0.240 against 0.123), so the loss sits in the other Southern states.
   - These are the states whose records come most from local reporting systems (`docs/review/panel-conservation.md`, M1).
3. **Same-day weather adds nothing measurable.**
   - Adding the 15 gridMET variables for the discovery day lowered the fold-mean PR-AUC slightly (0.144 to 0.137). Shuffling them on the holdout changes PR-AUC by -0.003, within noise.
   - Shuffling the weather normals and percentiles *raises* holdout PR-AUC by 0.019, which suggests they encode the development years' regime.
   - The literature says fire weather drives large-fire growth (`docs/research/LITERATURE.md`). The difference is timing: growth depends on the days after discovery, and this model only knows the discovery day.
4. **Much of the signal is reporting and jurisdiction.**
   - Owner and agency, and protection status, rank high. They say where fires are fought, reported and allowed to burn, as well as how they behave.
   - A reader should not read a place's score as a statement about its land or its managers.
5. **At the very top, the simple models win.** In the top 1% of scores, the location-and-season model captures 12.8% of large fires and the lookup 12.3%. This model captures 10.8%. Its advantage is in the next nine percent.
6. **Correction.** An earlier summary of this run said 78% of large fires fall in the top decile. Tied calibrated scores had pushed that "decile" to 12% of fires. The exact figure at 10% is 74% (E-015 correction note).

## What this means for the project

- The site and README present the model as a ranking: rank or percentile of score, the capture table, and the reliability diagram. They show no probabilities.
- The duration model stays retired. This model is the prediction piece, with its failures stated first.
- Next:
  - A leading indicator of the year's regime, to fix calibration (backlog S-2.9). Candidates: a seasonal outlook, drought index, or season-to-date count of large fires.
  - Preparedness counts lagged by a day, to remove a mild leak.
  - A look at the Southern states outside Texas.

## Proposed changes to other files

- **README.md, Prediction section:** the answer above, the holdout table, the three failures, and a link to the model card.
- **BACKLOG.md:**
  - Mark S-4.1 to S-4.3, S-2.5, S-2.6, S-3.1 and S-3.2 done.
  - Add S-2.9 (forward calibration with a regime indicator) and S-4.7 (why the model loses in the South).
  - Close S-4.6 (the probability widget) as not planned until S-2.9 succeeds.
- **Site:** the Prediction page renders `model.capture_at_top` and `model.calibration_failure` above the metrics table.
