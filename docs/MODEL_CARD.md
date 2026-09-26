# Model card: large-fire ranking model

Structure after Mitchell et al., "Model Cards for Model Reporting" (2019, https://arxiv.org/abs/1810.03993). Every number here is a claim in `outputs/claims_model.json` or an entry in `docs/EXPERIMENTS.md` (E-010 to E-015).

**In one paragraph.** This model ranks newly discovered US wildfires by how likely they are to reach 300 acres, using what is known on the discovery day. On fires from 2019 and 2020 that it never saw, its top 10% of scores held 74% of the fires that became large, against 45% for a lookup of each place's historical rate. Its scores are **not probabilities**: in 2019 they overstated the chance for the highest-ranked fires by about 75% (16.5% scored against 9.4% observed), and read as probabilities they do worse than a single constant rate. It is a research artifact about what the fire record can and cannot predict, not a tool for decisions about any fire.

## Model details

- **Developer:** Robyn Collie (portfolio project), with an AI-assisted review and build. Contact: GitHub issues on `Robyn-Collie/wildfire-analysis`.
- **Version and date:** 1.0, evaluated 2026-09-25 (E-015).
- **Type:** scikit-learn `HistGradientBoostingClassifier` (learning rate 0.05, 63 leaves, at least 50 fires per leaf, L2 1.0, early stopping), followed by an isotonic map fitted on the 2018 development fold. Native categorical splits for 12 categorical inputs.
- **Inputs:** 96 features known on the discovery day, in nine groups: location; season (leap-aware day-of-year angle); cause classification (Human, Natural, Missing); owner class and reporting agency; same-day gridMET weather (15 variables); 1990-2020 weather normals and percentile bins; terrain, fuels, vegetation and ecoregion at the point and within 1 km (LANDFIRE, NLCD, MODIS); protection status (PAD-US 3.0) and social context (CDC SVI, population, human modification); suppression context (fire stations, road distances, suppression difficulty, national and GACC preparedness levels, and counts of fires in the same reporting unit and 1-degree cell in the previous 7 days). Full list: claim `model.card`, `outputs/model/features.csv`.
- **Output:** a score between 0 and 1. Higher means more likely to become large. Only its order is supported by the evaluation.
- **Code and data:** `analysis/large_fire.py`; FPA FOD 6th edition (Short 2022) joined to FPA FOD-Attributes (Pourmohamad et al. 2024) on `FOD_ID`. Citations and licenses in `docs/DATA_TERMS.md`.
- **License:** code MIT; data under the terms in `docs/DATA_TERMS.md`.

## Intended use

- **Primary use:** to show, with a locked forward-in-time test, how much the circumstances of an ignition (where it is, what it is burning in, whose land it is on, who reported it, what the weather was that day) tell you about whether it will become a large fire, and which of those things matter.
- **Intended users:** readers of this project; analysts studying large-fire risk who want a documented baseline with its failures written down.
- **What it can support:** statements about relative ranking on held-out years ("fires in the top tenth of scores were about seven times as likely to become large as the average fire"), about which input groups carry the ranking, and about where the ranking fails.

## Out of scope

1. **Reading scores as probabilities.** The scores did not stay calibrated from the development years to 2019. Do not show a score as "x% chance". Show a rank or a percentile, and show the base rate next to it.
2. **Any decision about an active fire:** dispatch, staffing, pre-positioning, evacuation, or deciding a fire needs less attention. A low score is not evidence that a fire will stay small: 12% of large fires sit outside the top 20% of scores.
3. **Alaska, Hawaii, Puerto Rico.** Excluded because the attributes cover the conterminous US only. Alaska holds 19% of 2010-2020 acres in fires of 5,000+ acres.
4. **The South without a check.** On the holdout the model ranked Southern fires worse than the place-and-month lookup (PR-AUC 0.111 against 0.121) and was worst calibrated there (Brier skill -1.20). It did better in Texas than the lookup, so the weakness sits in the other Southern states.
5. **Years after 2020.** It has been tested on two years. The 2019 result shows its behaviour changes with the year's fire regime, which none of its inputs measures.
6. **Ranking agencies, landowners or places by "risk".** Owner, agency and protection status carry much of the signal because they encode where fires are fought, reported and allowed to burn, not only how fires behave.
7. **Explaining why a fire became large.** Importance is associational, and groups overlap.
8. **States where cause is mostly unrecorded.** The cause input there says which reporting system filed the record, not what started the fire.

## Factors

- **Region and state:** evaluated for four regions and the ten states with the most fires (claims `model.holdout_per_region`, `model.holdout_per_state`). New York had no large fire in the holdout and Georgia two, so their metrics carry no information.
- **Year:** 2019 and 2020 separately (`model.holdout_per_year`). The model behaves differently in a quiet year.
- **Reporting system:** records come from dozens of federal, state and local systems with different conventions (`docs/review/panel-fire.md`, F1-F2). The owner and agency inputs let the model learn those conventions. That helps the ranking and limits what it means.

## Metrics

- **Primary:** precision-recall AUC, because 1.3% of fires become large.
- **Also reported:** ROC-AUC; Brier score and Brier skill against the training base rate and against the lookup; share of large fires captured in the top 1, 5, 10 and 20% of scores; precision at 50% recall; a 10-bin reliability table.
- **Uncertainty:** 95% percentile intervals from 1,000 bootstrap resamples of the holdout fires. Development folds are reported as the range over folds, not as an interval.
- **Baselines, always in the same table:** base rate; lookup of the training rate by 1-degree cell and month; logistic regression on all features; gradient boosting on location and season only.

## Evaluation data

- **Holdout:** all 135,685 CONUS fires discovered in 2019 and 2020 (1,710 large). Defined in `docs/EXPERIMENTS.md` before any of this model's development. One earlier exploratory look at these years with default settings and no selection (E-008) is disclosed there.
- **Development:** 2010-2018 with expanding-window folds (test years 2015 to 2018) and a spatial check that holds out whole 1-degree cells (E-011 to E-014).

## Training data

- 706,554 CONUS fires discovered 2010-2018, all sizes, no filter on containment date. 1.39% became large.
- The attributes join to 100% of these fires. In 2019, 1,071 fires (1.7%) have no attribute row and enter the holdout with missing inputs.

## Quantitative analyses

Holdout, 2019-2020 (E-015):

| Model | PR-AUC [95%] | ROC-AUC | Brier skill vs base rate [95%] | Top 5% / 10% / 20% of scores capture |
|---|---|---|---|---|
| Base rate | 0.013 | 0.500 | 0 | 5% / 10% / 20% |
| Lookup: cell x month | 0.075 [0.067, 0.085] | 0.808 | +0.025 [0.018, 0.032] | 31% / 45% / 64% |
| Location + season model | 0.088 [0.079, 0.099] | 0.844 | +0.039 [0.032, 0.046] | 37% / 51% / 70% |
| Logistic regression | 0.107 [0.098, 0.117] | 0.889 | -0.527 [-0.582, -0.478] | 47% / 65% / 82% |
| **This model** | **0.139 [0.127, 0.151]** | **0.916** | **-0.262 [-0.302, -0.224]** | **57% / 74% / 88%** |

By region, PR-AUC of this model against the lookup: West 0.231 against 0.061 (1,072 large fires); Plains-Midwest 0.209 against 0.042 (135); South 0.111 against 0.121 (497); Northeast 0.100 against 0.004 (6 large fires, not informative).

By year: PR-AUC 0.111 (2019) and 0.218 (2020); Brier skill -0.85 and +0.12.

Which inputs carry the ranking (drop in holdout PR-AUC when a group is shuffled): fuels, terrain and ecoregion 0.100; protection status and social context 0.061; owner and agency 0.026; suppression context 0.009; cause 0.002; season and location about 0; same-day weather -0.003; weather normals and percentiles -0.019.

Figures: `outputs/figures/model_reliability.png`, `model_pr_curves.png`, `model_ablation.png`, `model_importance.png`, `model_per_year.png`.

## Ethical considerations

- **Misreading a ranking as a forecast.** A score shown without its base rate and its calibration record invites exactly the misuse listed first above. The site shows ranks and capture rates, and shows the reliability diagram next to them.
- **Who a false low score harms.** The people near a fire the model ranked low that became large, and the crews sent late. The model is weakest in the South, where the record's reporting is least uniform, so that burden is not evenly spread.
- **Reporting systems, not only fire behaviour.** Owner and agency inputs raise the score of fires reported by systems that record large fires completely. A reader should not take a place's score as a statement about its land or its managers.
- **Personal data:** none. Inputs are public, aggregated or place-based.

## Caveats and recommendations

- The **preparedness inputs** (national and GACC preparedness level, new and uncontrolled large fires in the GACC that day) are daily situation-report counts. A fire that is large on its discovery day can already appear in its GACC's count, a mild leak. They sit in the suppression-context group, which adds 0.009 to holdout PR-AUC, so removing them would not change the conclusions. The next version should lag them by a day.
- **Calibration needs a signal of the year's regime.** A seasonal outlook, drought index or the season-to-date large-fire count, known at discovery, is the obvious candidate (backlog story S-2.9).
- **Weather:** the null result is for weather on the discovery day at gridMET's 4 km grid. It does not say weather is irrelevant to fire growth. It says that day's weather adds little to ranking once place, fuels and land status are known. Weather over the following days, which is what drives growth, is not available at discovery.
- The model was tuned by mean PR-AUC over the development folds. It was not tuned for calibration, and the pre-registered calibration step did not rescue it.
