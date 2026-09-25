# Literature review for the wildfire-analysis rebuild

## Verification note

Every entry below was verified on 2026-09-25. "Page fetched" means the article page or PDF was read with WebFetch or curl. Where a publisher blocked the fetcher (PNAS, MDPI, Wiley, Elsevier, Springer and nature.com returned 403 or a login redirect), the citation (authors, title, journal, volume, pages, year) was verified through the Crossref API (https://api.crossref.org/works/<DOI>) and the abstract was read through the Europe PMC API, the Semantic Scholar API, or a PubMed Central copy; each entry says which. Summaries are written from the abstract or page that was actually read; where no abstract could be retrieved the entry says so and the summary is limited to what the verified title and page metadata support. Nothing here is cited from memory.

Fetch failures: nature.com article pages (login redirect; PMC or Crossref used), Springer page for Plucinski 2019 (login redirect; Crossref only, no abstract), Wiley pages for Roberts 2017, Cattau 2020, Meyer and Pebesma 2021 (403; Crossref and Semantic Scholar used), ScienceDirect page for Wadoux 2021 (403; Crossref only, no abstract), MDPI page for Nagy 2018 (403; Crossref and Semantic Scholar used), PNAS pages (403; Crossref and Europe PMC used). The Ploton 2020 PMC ID I guessed first (PMC7486385) was a different paper; the entry below relies on the Crossref record and the Europe PMC abstract for DOI 10.1038/s41467-020-18321-y.

Raw API responses are saved in the research scratch dir as `citations.json` (Crossref and Europe PMC) and `s2.json` (Semantic Scholar).

---

## A. The FPA FOD itself: completeness and bias

### 1. Short 2014, the database paper
Short, K. C. (2014). A spatial database of wildfires in the United States, 1992-2011. Earth System Science Data 6: 1-27. https://doi.org/10.5194/essd-6-1-2014 (page fetched: https://essd.copernicus.org/articles/6/1/2014/).
Describes the compilation of about 1.6 million records from federal, state and local systems, requiring discovery date, final size and a PLSS-section location. The author states the database is "necessarily incomplete in some aspects" because there is no single national record-keeping system, that users must "check for and purge redundant records" when combining sources, and that source systems have "inconsistent information content".
What it changes: every count-based trend in Part 1 needs a completeness caveat and, ideally, a completeness-adjusted comparison (federal-only, or MTBS area burned). The 26% of 2010+ records lacking CONT_DATE (REPRODUCTION.md) is a symptom of the same "inconsistent information content".

### 2. Short 2015, bias and uncertainty in a century of data
Short, K. C. (2015). Sources and implications of bias and uncertainty in a century of US wildfire activity data. International Journal of Wildland Fire 24(7): 883-891. https://doi.org/10.1071/WF14190 (page fetched via redirect to connectsci.au).
Reviews the three families of US fire data (archival summaries, incident-level reports, remote sensing) and documents reporting biases and inconsistencies in all of them. A key point is that "use of national fire reporting systems by state and local fire organisations has been rising", which creates discontinuities: apparent growth in fire counts can be growth in reporting.
What it changes: this is the published critique of using FPA FOD counts as trends. The README's "are fires getting worse" answer should be built on area burned of large fires (which Short's metadata says is "less compromised") and on MTBS, not on record counts; the Northeast reporting-regime jumps found in Phase 0 are exactly the artefact this paper predicts.

### 3. Short 2022, the 6th edition metadata
Short, K. C. (2022). Spatial wildfire occurrence data for the United States, 1992-2020 [FPA_FOD_20221014]. 6th Edition. Forest Service Research Data Archive. https://doi.org/10.2737/RDS-2013-0009.6 (catalog page and HTML metadata fetched; see DATA_SOURCES.md).
The metadata states that "viable state and local (i.e., nonfederal) records were not available from all states for all years", that states were scored for completeness with the Great Lakes, Southeast and West scoring highest, and that "estimates of area burned tend to be less compromised than wildfire numbers by missing nonfederal records". It defines CONT_DATE as the date the fire was "declared contained or otherwise controlled" and documents the MTBS_ID and ICS-209-PLUS join fields.
What it changes: gives the exact wording to cite for the two biggest caveats (nonfederal gaps; counts worse than area), and confirms that "duration" in this project is a containment-declaration interval, not a burn duration.

---

## B. Enriched FPA FOD and cause inference

### 4. Pourmohamad et al. 2024, FPA FOD-Attributes
Pourmohamad, Y., Abatzoglou, J. T., Belval, E. J., Fleishman, E., Short, K., Reeves, M. C., Nauslar, N., Higuera, P. E., Henderson, E., Ball, S., AghaKouchak, A., Prestemon, J. P., Olszewski, J., and Sadegh, M. (2024). Physical, social, and biological attributes for improved understanding and prediction of wildfires: FPA FOD-Attributes dataset. Earth System Science Data 16: 3045-3060. https://doi.org/10.5194/essd-16-3045-2024 (page and PDF fetched; data at https://doi.org/10.5281/zenodo.8381129, verified).
Augments FPA FOD v6 with 267 attributes at the date and point of ignition from 24 sources: gridMET daily weather and fire danger with 5-day windows, normals and percentiles; LANDFIRE topography and vegetation; NLCD; MODIS and AVHRR NDVI; PAD-US GAP status; SVI and CEJST; WorldPop; fire stations; road distances; suppression difficulty; national and GACC preparedness levels. The authors state the attributes are CONUS-only, that location precision is limited to a PLSS section, that duplicates may remain, that the dataset "does not provide details about large fire growth days", and that variables "have substantial overlap and correlation".
What it changes: it becomes data source 1 (see DATA_SOURCES.md, join tested at 100% on FOD_ID). The README's "join NOAA weather observations" next step is done. The at-discovery model must exclude the 5-day-window fields (they include two days after discovery).

### 5. Pourmohamad et al. 2025, inferring unknown causes
Pourmohamad, Y., Abatzoglou, J. T., Fleishman, E., Short, K. C., Shuman, J., AghaKouchak, A., Williamson, M., Seydi, S. T., and Sadegh, M. (2025). Inference of wildfire causes from their physical, biological, social and management attributes. Earth's Future, article 10.1029/2024EF005187 (PDF fetched from https://www.fs.usda.gov/rm/pubs_journals/2025/rmrs_2025_pourmohamad_y001.pdf; the DOI is taken from the PDF header and was not separately resolved).
Trains a classifier on 1992-2020 western US fires with 12 known causes using the FPA FOD-Attributes fields, reaching over 70% overall accuracy on held-out data, 93% for natural versus human, and 55% among the 11 human classes; the top attributes were global human modification, elevation, discovery day of year, fire year and temperature. The key points state that unknown-cause reports rose five-fold from 1992 to 2020 and exceed 50% in recent years.
What it changes: the "human vs natural" claims in Part 1 rest on a cause field that is increasingly missing (22% missing among the dropped 2010+ records in Phase 0). The rebuild should report cause shares with and without the missing class and should not treat "Missing" as random. It also shows a published, validated use of exactly the feature set this project will adopt.

---

## C. Containment, duration and initial attack

### 6. Finney, Grenfell and McHugh 2009, containment probability of large fires
Finney, M., Grenfell, I. C., and McHugh, C. W. (2009). Modeling containment of large wildfires using generalized linear mixed-model analysis. Forest Science 55(3): 249-255. https://doi.org/10.1093/forestscience/55.3.249 (OUP page fetched; abstract also via Europe PMC).
Fits a GLMM to daily size changes of 306 large fires (2001-2005), tested on 140 fires from 2006. Containment probability rose with the number of consecutive low-growth days and fell with the length of high-spread intervals and with timber fuel types; fire size itself "was not a significant predictor".
What it changes: containment is driven by what the fire does after discovery, which the FPA FOD does not record. A discovery-time model of days-to-containment is structurally limited, and the honest framing is a hurdle: probability of escaping initial attack, then growth-dependent containment which needs ICS-209-PLUS daily data.

### 7. Plucinski 2019, suppression effectiveness review
Plucinski, M. P. (2019). Contain and control: wildfire suppression effectiveness at incidents and across landscapes. Current Forestry Reports 5: 20-40. https://doi.org/10.1007/s40725-019-00085-4 (Crossref verified; Springer page blocked; no abstract retrieved, so the summary is limited).
A review of the suppression-effectiveness literature at incident and landscape scales, including initial-attack success metrics. Search results (not the paper itself) indicate the review covers logistic-regression and tree-based models of initial-attack success using weather, response time, slope and road distance.
What it changes: provides the framing that "initial attack success" (fire held small) is the standard, well-studied binary outcome; it is the natural replacement for the README's duration regression.

### 8. Xu, Cheng and Dong 2026, a national initial-attack-failure benchmark on FPA FOD
Xu, R., Cheng, X., and Dong, Y. (2026). A nationwide benchmark for wildfire initial attack failure prediction with public environmental data. arXiv:2606.15529 (abstract page fetched: https://arxiv.org/abs/2606.15529; preprint, not peer reviewed).
Builds WildfireIA from 38,128 naturally caused FPA FOD fires aligned with VIIRS detections, with gridMET, LANDFIRE, OpenStreetMap and WorldPop features; defines initial-attack failure with a size-based rule; uses chronological splits; excludes final size and post-discovery satellite data from inputs; reports AUPRC as the primary metric, with XGBoost best at 53.3% AUPRC, and finds fuel the strongest static predictor. The search snippet for the same paper states that containment duration "is only weakly explained by discovery-time inputs".
What it changes: this is the closest published analogue of the rebuild's model and sets the bar: a size-based escape label, chronological validation, AUPRC not RMSE, and leakage rules stated up front. Its natural-cause-only scope leaves the human-caused majority open for this project.

### 9. Bhardwaj 2025, containment time regression for California
Bhardwaj, S. (2025). Predicting the containment time of California wildfires using machine learning. arXiv:2512.09835 (abstract page fetched: https://arxiv.org/abs/2512.09835; preprint, not peer reviewed).
Treats days-to-containment as a regression task on CAL FIRE FRAP data; XGBoost slightly beats random forest and an LSTM underperforms because the data have no temporal features. The abstract reports no error metric and no validation design.
What it changes: a cautionary comparator only. It shows the same regression framing the README used, without a baseline or spatial/temporal validation; the rebuild should be explicit about beating predict-zero and predict-median, which this preprint does not report.

---

## D. Large-fire probability and its drivers

### 10. Preisler et al. 2004, the probability framework
Preisler, H. K., Brillinger, D. R., Burgan, R. E., and Benoit, J. W. (2004). Probability based models for estimation of wildfire risk. International Journal of Wildland Fire 13(2): 133-142. https://doi.org/10.1071/WF02061 (page fetched via connectsci.au).
Decomposes fire risk into the probability of ignition, the conditional probability of a large fire given ignition, and the unconditional large-fire probability, fitted with non-parametric logistic regression on 1 km2-day grouped data for Oregon using weather and danger indices; notes that "standard errors are large".
What it changes: gives the canonical decomposition for this project. The rebuild's model is the middle term, P(large | ignition), and should be described that way, with ERC-type indices as the first predictors to test.

### 11. Riley et al. 2013, which indices matter and at what time scale
Riley, K. L., Abatzoglou, J. T., Grenfell, I. C., Klene, A. E., and Heinsch, F. A. (2013). The relationship of large fire occurrence with drought and fire danger indices in the western USA, 1984-2008: the role of temporal scale. International Journal of Wildland Fire 22(7): 894-909. https://doi.org/10.1071/WF12149 (page fetched via connectsci.au).
Short-term indices (ERC and monthly precipitation percentile) explained area burned and fire counts strongly (R2 0.89-0.94), whereas long-term drought indices (PDSI, 24-month SPI) were weak (R2 0.25 and below), because short-term moisture reflects dead-fuel availability.
What it changes: prioritise `erc`, `erc_Percentile`, `fm100`, `fm1000`, `vpd`, `vs` from FPA FOD-Attributes; the US Drought Monitor and long-window SPEI are lower priority.

### 12. Abatzoglou and Kolden 2013, climate and area burned by region
Abatzoglou, J. T. and Kolden, C. A. (2013). Relationships between climate and macroscale area burned in the western United States. International Journal of Wildland Fire 22(7): 1003-1020. https://doi.org/10.1071/WF13019 (Crossref verified; abstract read from the Crossref record).
Using MTBS area burned 1984-2010 for eight western GACCs, biophysical variables tied to fuel and soil moisture depletion and prolonged high fire danger correlated more strongly with area burned than standard monthly climate, especially in forests; relationships differed between forested and non-forested land.
What it changes: supports stratifying the model and the descriptive story by region and by forest versus non-forest (available via `EVT`/`Land_Cover` and `Ecoregion_*` in Attributes) rather than fitting one national relationship.

### 13. Abatzoglou and Williams 2016, anthropogenic climate change and forest fire area
Abatzoglou, J. T. and Williams, A. P. (2016). Impact of anthropogenic climate change on wildfire across western US forests. PNAS 113(42): 11770-11775. https://doi.org/10.1073/pnas.1607171113 (Crossref verified; abstract read via Europe PMC).
Anthropogenic warming and VPD increases accounted for about 55% of the observed rise in fuel aridity 1979-2015 in western US forests and an estimated additional 4.2 million ha of forest fire area 1984-2015, roughly doubling what would have burned otherwise.
What it changes: the README's "are fires getting worse" question has a published, quantified answer for western forests; the rebuild can cite it as context and use VPD/fuel-aridity fields as predictors, but should not claim to test attribution itself.

### 14. Dennison et al. 2014, large-fire trends from MTBS
Dennison, P. E., Brewer, S. C., Arnold, J. D., and Moritz, M. A. (2014). Large wildfire trends in the western United States, 1984-2011. Geophysical Research Letters 41: 2928-2933. https://doi.org/10.1002/2014GL059576 (Crossref verified; abstract read from the Crossref record).
Using a database of fires over 405 ha, finds significant increasing trends in the number of large fires and/or total large-fire area in most western ecoregions, at about seven additional fires and 355 km2 per year overall, coinciding with increasing drought severity.
What it changes: the Phase 0 finding (Class G acres trend up, Kendall tau 0.43; counts flat) is consistent with this, and a large-fire-only trend from MTBS-linked records is the defensible version of "getting worse". Note the period and region differ (western US, 1984-2011).

### 15. Coop et al. 2022, extreme single-day spread events
Coop, J. D., Parks, S. A., Stevens-Rumann, C. S., Ritter, S. M., and Hoffman, C. M. (2022). Extreme fire spread events and area burned under recent and future climate in the western USA. Global Ecology and Biogeography 31(10): 1949-1959. https://doi.org/10.1111/geb.13496 (Crossref verified; abstract read via Semantic Scholar).
Relates satellite-derived daily fire-spread events (2002-2020) to annual area burned and fire-season climate, and projects change under +2 C.
What it changes: area burned is dominated by a few extreme growth days, which supports a hurdle/extreme-value view of fire outcomes and explains why a day-level duration target is so heavy-tailed (Phase 0: 0.8% of fires carry 85% of squared error).

---

## E. Human ignitions and the fire season

### 16. Balch et al. 2017, human-started fires expand the fire niche
Balch, J. K., Bradley, B. A., Abatzoglou, J. T., Nagy, R. C., Fusco, E. J., and Mahood, A. L. (2017). Human-started wildfires expand the fire niche across the United States. PNAS 114(11): 2946-2951. https://doi.org/10.1073/pnas.1617394114 (Crossref verified; abstract read via Europe PMC).
From 1.5 million FPA FOD records 1992-2012: humans started 84% of wildfires and 44% of area burned; the human-caused fire season was three times longer than the lightning season and added about 40,000 fires per year; human ignitions dominated in over 5.1 million km2 and occurred at higher fuel moisture than lightning fires.
What it changes: the Part 1 claim "human-caused fires far outnumber natural ones, but natural causes account for most acreage" is consistent with this paper (Phase 0: 77.4% of fires and 35.3% of acres are human, 1992-2020); the rebuild can cite the season-length result and should show the seasonal cause split by region, which the Attributes ecoregion fields make easy.

### 17. Nagy et al. 2018, human ignitions and large fires by ecoregion
Nagy, R. C., Fusco, E., Bradley, B., Abatzoglou, J. T., and Balch, J. (2018). Human-related ignitions increase the number of large wildfires across U.S. ecoregions. Fire 1(1): 4. https://doi.org/10.3390/fire1010004 (Crossref verified; abstract read via Semantic Scholar).
Defines "large" as the largest 10% of fires within each ecoregion (175,222 fires, 1992-2015) rather than a fixed threshold; mean large-fire size spans three orders of magnitude (1-10 ha in the Northeast to over 1,000 ha in the West); humans ignited four times as many large fires as lightning (92% of large fires in the East, 65% in the West), and human large fires occurred at higher fuel moisture and wind speed.
What it changes: gives a defensible, region-relative definition of "large fire" for the model label as an alternative to Class F/G or the MTBS threshold, and predicts that cause will interact with region and weather in the model.

### 18. Cattau et al. 2020, fires larger, more frequent, longer season
Cattau, M. E., Wessman, C., Mahood, A., and Balch, J. K. (2020). Anthropogenic and lightning-started fires are becoming larger and more frequent over a longer season length in the U.S.A. Global Ecology and Biogeography 29(4): 668-681. https://doi.org/10.1111/geb.13058 (Crossref verified; abstract read via Semantic Scholar).
Aggregating over 1.8 million government records and satellite fire radiative power at 50 km resolution for 1984-2016: fire seasons lengthened 17%, fires became 78% larger and 12% more frequent but not more intense, and the proportion of human ignitions rose 9%.
What it changes: supports the "longer season" narrative with numbers, but note that the frequency result rests on the same records whose reporting coverage grew (entries 1-3); the rebuild should present count trends alongside a completeness caveat.

### 19. Radeloff et al. 2018, WUI growth
Radeloff, V. C., Helmers, D. P., Kramer, H. A., Mockrin, M. H., Alexandre, P. M., Bar-Massada, A., Butsic, V., Hawbaker, T. J., Martinuzzi, S., Syphard, A. D., and Stewart, S. I. (2018). Rapid growth of the US wildland-urban interface raises wildfire risk. PNAS 115(13): 3314-3319. https://doi.org/10.1073/pnas.1718850115 (Crossref verified; abstract read via Europe PMC).
The WUI grew from 30.8 to 43.4 million houses (41%) and from 581,000 to 770,000 km2 (33%) between 1990 and 2010, 97% of it from new housing; houses inside recent fire perimeters rose from 177,000 to 286,000; WUI growth "often results in more wildfire ignitions".
What it changes: motivates the SILVIS WUI join for both the human-ignition story and exposure in the conservation lens, and provides context for why human ignitions rise even where weather does not change.

### 20. St. Denis et al. 2023, ICS-209-PLUS
St. Denis, L. A., Short, K. C., McConnell, K., Cook, M. C., Mietkiewicz, N. P., Buckland, M., and Balch, J. K. (2023). All-hazards dataset mined from the US National Incident Management System 1999-2020. Scientific Data 10: 112. https://doi.org/10.1038/s41597-023-01955-0 (PMC copy fetched: https://pmc.ncbi.nlm.nih.gov/articles/PMC9958120/).
187,160 situation reports for 35,170 incidents, 34,478 of them wildland fires, with daily structures destroyed, personnel, cost, evacuations and spread rate; about 86% of incidents link to FPA FOD via the incident ID, which also connects to MTBS.
What it changes: the only source for a daily containment trajectory and for a "structures destroyed" outcome; see DATA_SOURCES.md. It also lets the README's Control Efficiency Score be replaced by personnel-normalised containment progression on the subset with 209s.

---

## F. Validation for spatial and imbalanced prediction

### 21. Roberts et al. 2017, blocked cross-validation
Roberts, D. R., Bahn, V., Ciuti, S., Boyce, M. S., Elith, J., Guillera-Arroita, G., Hauenstein, S., Lahoz-Monfort, J. J., Schroeder, B., Thuiller, W., Warton, D. I., Wintle, B. A., Hartig, F., and Dormann, C. F. (2017). Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure. Ecography 40(8): 913-929. https://doi.org/10.1111/ecog.02881 (Crossref verified; abstract read from the Crossref record).
Random cross-validation on structured data seriously underestimates predictive error and, worse, lets models overfit non-causal predictors; block cross-validation in space, time or groups addresses this, but the blocking scale must match the intended prediction task.
What it changes: the README's random 80/20 split and 5-fold CV are the case this paper warns about. The rebuild should report at least a year-forward split and a spatial block split (for example by ecoregion or by 1 degree cells), and state which prediction task each split mimics.

### 22. Ploton et al. 2020, spatial validation exposes near-zero skill
Ploton, P., Mortier, F., Rejou-Mechain, M., Barbier, N., Picard, N., Rossi, V., Dormann, C., Cornu, G., Viennois, G., Bayol, N., Lyapustin, A., Gourlet-Fleury, S., and Pelissier, R. (2020). Spatial validation reveals poor predictive performance of large-scale ecological mapping models. Nature Communications 11: 4540. https://doi.org/10.1038/s41467-020-18321-y (Crossref verified; abstract read via Europe PMC).
A random forest on 11.8 million trees explained over half of biomass variation under non-spatial validation but had "quasi-null predictive power" under spatial validation accounting for autocorrelation.
What it changes: the current model's top features are latitude and longitude, which is precisely the pattern that collapses under spatial validation. Any reported skill must be shown under a spatial hold-out before it is claimed.

### 23. Meyer and Pebesma 2021, area of applicability
Meyer, H. and Pebesma, E. (2021). Predicting into unknown space? Estimating the area of applicability of spatial prediction models. Methods in Ecology and Evolution 12(9): 1620-1633. https://doi.org/10.1111/2041-210X.13650 (Crossref verified; abstract read via Semantic Scholar).
Proposes a dissimilarity index (distance in importance-weighted predictor space to the training data) and derives the area of applicability as the region where cross-validation performance can be expected to hold.
What it changes: with 26% of 2010+ records (heavily Texas and the South) missing from the training sample, the rebuild should compute an applicability map and say plainly where the model should not be used. (The companion paper, Meyer and Pebesma 2022, Nature Communications 13, https://doi.org/10.1038/s41467-022-29838-9, Crossref verified, page blocked, extends the argument to global maps.)

### 24. Wadoux et al. 2021, the counter-argument
Wadoux, A. M. J.-C., Heuvelink, G. B. M., de Bruin, S., and Brus, D. J. (2021). Spatial cross-validation is not the right way to evaluate map accuracy. Ecological Modelling 457: 109692. https://doi.org/10.1016/j.ecolmodel.2021.109692 (Crossref verified; page blocked; no abstract retrieved, so the summary is limited to the verified title and the position it states).
Argues, per its title, that spatial cross-validation is not the right estimator of map accuracy; the correct estimator depends on the sampling design of the validation data.
What it changes: the rebuild should not present spatial CV as the single truth. State the target of inference (new fires in the same places in later years versus fires in unseen places) and choose the split to match; report both and explain the difference.

### 25. Saito and Rehmsmeier 2015, precision-recall for rare events
Saito, T. and Rehmsmeier, M. (2015). The precision-recall plot is more informative than the ROC plot when evaluating binary classifiers on imbalanced datasets. PLOS ONE 10(3): e0118432. https://doi.org/10.1371/journal.pone.0118432 (page fetched).
ROC curves look the same on balanced and imbalanced data and can hide poor performance; precision-recall curves change with class balance and show directly the fraction of flagged cases that are real.
What it changes: with large fires at a few percent of ignitions (Class F+G are a small minority; exact share to be computed by the modelling agent), report PR-AUC and precision at operational recall levels, and give ROC-AUC only as a secondary number.

### 26. Van Calster et al. 2019, calibration
Van Calster, B., McLernon, D. J., van Smeden, M., Wynants, L., Steyerberg, E. W., on behalf of Topic Group "Evaluating diagnostic tests and prediction models" of the STRATOS initiative (2019). Calibration: the Achilles heel of predictive analytics. BMC Medicine 17: 230. https://doi.org/10.1186/s12916-019-1466-7 (Crossref verified; abstract read via Europe PMC).
Argues that calibration of risk models is neglected and that miscalibrated probabilities are misleading and potentially harmful; recommends calibration curves at validation with adequate sample sizes and updating when needed.
What it changes: a "probability of becoming a large fire" is only useful for pre-positioning resources if it is calibrated; the rebuild should show reliability diagrams on the held-out years and regions, not just ranking metrics.

### 27. Zeileis, Kleiber and Jackman 2008, hurdle and zero-inflated models
Zeileis, A., Kleiber, C., and Jackman, S. (2008). Regression models for count data in R. Journal of Statistical Software 27(8). https://doi.org/10.18637/jss.v027.i08 (page fetched).
Reviews Poisson and negative binomial regression and introduces hurdle and zero-inflated implementations for data with over-dispersion and "an excess of zeros".
What it changes: 83.7% of durations are zero days (Phase 0). If any duration model survives, it should be a hurdle: a classifier for "contained same day" and a separate positive-duration model, each evaluated against its own baseline; a single regressor on the mixed target cannot beat predict-zero on MAE.

### 28. Jain et al. 2020, ML in wildfire science review
Jain, P., Coogan, S. C. P., Subramanian, S. G., Crowley, M., Taylor, S., and Flannigan, M. D. (2020). A review of machine learning applications in wildfire science and management. Environmental Reviews 28(4): 478-505. https://doi.org/10.1139/er-2020-0019 (Crossref verified; abstract read via Semantic Scholar).
Scoping review across six problem domains (fuels and detection; fire weather and climate; occurrence, susceptibility and risk; behaviour; effects; management) discussing data size, computation, generalisability and interpretability of ML approaches.
What it changes: places the rebuild in the "occurrence, susceptibility and risk" domain and gives a citable basis for choosing interpretable gradient-boosted trees with permutation importance over a black-box model, consistent with the owner's glass-box standard.

---

## Implications for the rebuild

1. Adopt FPA FOD-Attributes as the feature source (entry 4); the weather-join work in the README's next steps is already done, but exclude the `*_5D_*` fields from an at-discovery model because they include two post-discovery days.
2. Reframe the prediction task from "days to containment" to P(large fire | ignition) in Preisler's decomposition (entry 10), with a stated label: MTBS-mapped (via MTBS_ID), Class F+G, or Nagy's per-ecoregion top decile (entry 17). Report results for at least two labels.
3. If duration is kept at all, use a hurdle structure (entry 27) and only on the ICS-209-PLUS subset where daily containment exists (entries 6, 20); the FPA FOD interval is a containment-declaration date, not fire behaviour (entry 3).
4. Validate with a year-forward split and a spatial block split, report both, and explain which real-world use each mimics (entries 21, 22, 24). The current lat/lon-dominated random forest is the textbook failure case.
5. Use PR-AUC and precision at fixed recall as the headline metrics and show calibration curves on held-out years (entries 25, 26). Do not lead with RMSE.
6. Publish an area-of-applicability statement (entry 23): the training sample under-represents Texas, the South and nonfederal reporters, so say where the model does not apply.
7. Lead the feature set with ERC, fuel moisture, VPD and wind, and their percentiles relative to local climatology (entries 11, 12); treat long-term drought indices and modelled burn-probability products as secondary or descriptive.
8. For "are fires getting worse", use large-fire area (MTBS or Class G acres) and cite the attribution literature (entries 13, 14); present count trends only with the reporting-coverage caveat (entries 1, 2, 18), and treat the Northeast series as a reporting artefact until checked.
9. Report human versus natural cause shares with and without the missing class, note the five-fold rise in unknown causes (entry 5), and show the season-length contrast by region (entries 16, 17).
10. Replace the Control Efficiency Score with outcomes that condition on fire behaviour and resources from ICS-209-PLUS (entries 6, 20); acres per hour to containment measures fire size distribution, not response (Phase 0 finding).
