# Descriptive findings: what the code says about README Part 1

**Produced by:** `python -m analysis.descriptive --out outputs/` (package in `analysis/`; runs in about 20 seconds from `data/fires.parquet`).
**Outputs:** `outputs/claims.json` (95 claims, each with value, unit, definition, n, computed_at, source), `outputs/cells_1deg.csv`, and nine figures in `outputs/figures/`.
**Data:** FPA FOD 6th edition (Short 2022), 2,303,566 records, 1992 to 2020. Every number below is a claim id in `claims.json`; the README and the site should be generated from that file, not from this text.

Verdict scale: **Supported** (the code finds the claim as stated), **Weakened** (the direction holds but the wording overstates it), **Refuted** (the code finds the opposite or nothing), **Reframed** (the finding is real but the README describes it the wrong way).

## 1. Verdicts on the README Part 1 claims

| # | README claim | What the code finds | Claim ids | Verdict |
|---|---|---|---|---|
| 1 | 2,303,566 fire records, 1992 to 2020 | 2,303,566 rows, FIRE_YEAR 1992 to 2020 | `overview.n_rows`, `overview.years` | Supported |
| 2 | Fire sizes from near zero to 662,700 acres | min 0.00001, max 662,700 acres | `overview.smallest_fire_acres`, `overview.largest_fire_acres` | Supported |
| 3 | Containment date missing for 894,813, discovery time for 789,095 | 894,813 (38.8%) and 789,095 (34.3%); also CONT_TIME missing 989,902 (43.0%), owner not specified 1,068,424 (46.4%), general cause missing 597,933 (26.0%) | `overview.missing_counts`, `overview.missing_shares` | Supported, and understated: ownership and cause are the biggest gaps |
| 4 | Class G acres trend upward, "higher highs and higher lows" | Kendall tau 0.43 (p 0.0007), Theil-Sen +177,560 acres/yr (95% CI 69k to 288k). Without Alaska: tau 0.35 (p 0.007), +141,973 acres/yr. "Higher lows" fails: 2010 (2.14M) is the 5th lowest of 29 years | `class_g.acres_trend`, `class_g.acres_trend_excl_alaska`, `class_g.five_lowest_years` | Weakened: the upward trend is Supported, "higher lows" is not |
| 5 | Human-caused fires far outnumber natural; natural causes burn most acres, about 105.6M | Human 1,782,906 fires (77.4%) vs Natural 327,319 (14.2%), ratio 5.4 to 1. Natural acres 105,636,947 (58.7% of 180.0M) | `cause.by_classification`, `cause.natural_acres`, `cause.human_to_natural_fire_ratio` | Supported |
| 6 | Classes B and C are most often debris and open burning | B: debris 30.0%, missing 24.2%, arson 15.5%. C: debris 25.6%, arson 24.4%, missing 21.8% | `cause.top_general_cause_by_size_class` | Reframed: a plurality, not a majority, and in Class C arson is within 1.2 points |
| 7 | Large fires start in the South in winter and shift to the West by summer | Class G fires: South leads November to April, West leads May to October. Alaska adds 443 of the 1,030 June Class G fires | `season.class_g_leading_region_by_month`, `season.class_g_fires_by_region_month` | Supported |
| 8 | Western fires last the longest, peaking in August | Mean day-level duration: Alaska 13.1 days, West 1.6, Northeast 0.5, Other 0.3, South 0.2. Median is 0 days everywhere except Alaska (1). West mean by month peaks in August (2.5 days) | `season.duration_days_by_region`, `season.west_mean_duration_days_by_month` | Reframed: true only if Alaska is not "the West"; Alaska fires last eight times longer |
| 9 | June spike in Class G acreage in Arkansas | Arkansas has 2 Class G fires in 29 years (March and April 2006), none in June. June is Arkansas's second quietest month (1,422 fires). Arizona (100 fires, 2.83M acres) and Alaska (443 fires, 22.68M acres) both peak in June | `anom.arkansas_class_g`, `anom.june_class_g_by_state_top10`, `anom.verdict_arkansas_june` | Refuted: almost certainly an AR/AZ/AK label mix-up |
| 10 | December fires in Texas | December ranks 10th of 12 Texas months by fires (10,742) and by acres (325,737). One December stands out: 2005, 94,523 acres, 2.7 times the next largest December (2007) | `anom.texas_by_month`, `anom.texas_december_top_year`, `anom.verdict_texas_december` | Refuted as a pattern; Reframed as a single event period (December 2005) |
| 11 | 2010 outlier in the Northeast | With Northeast = CT ME MA NH RI VT NY NJ PA, 2010 has z = 0.98 on fires (rank 7 of 29) and z = 0.48 on acres (rank 10). The series is shaped by reporting: count jumps of +5,407 (2020), +4,782 (2005), +4,304 (2015); Rhode Island has 0 records in 13 years; Massachusetts goes from 6 fires (2014) to 2,170 (2015) | `anom.northeast_2010`, `anom.northeast_largest_yoy_count_jumps`, `anom.northeast_zero_report_years`, `anom.verdict_northeast_2010` | Refuted with this definition; Reframed as reporting-regime shifts |
| 12 | USFS, BLM and private landowners account for the most acres | USFS 38.36M (21.3%), BLM 37.17M (20.6%), Private 25.64M (14.2%). Fourth is MISSING/NOT SPECIFIED at 22.88M (12.7%), and that category holds 46.4% of all fires | `owner.top4_acres`, `owner.missing_share_fires` | Supported, with a caveat the README omits: unknown ownership is nearly as large as private |
| 13 | Control Efficiency Score = 1 / (mean acres per hour) can compare agencies, once terrain etc. are added | With the mean, USFS ranks 11th of 14 owners; with the median it ranks 1st. BLM moves 6th to 2nd, Private 3rd to 13th. Spearman correlation between the two rankings is 0.09. Median acres per hour rises from 0.08 (Class A) to 49.5 (Class G), so the score is mostly final fire size | `ces.by_owner`, `ces.rank_shift`, `ces.spearman_mean_vs_median`, `ces.median_aph_by_size_class` | Refuted as a measure of response: the ranking is an artefact of the aggregation choice, not of terrain |
| 14 | "Use the seasonal pattern to pre-position resources" | Not a data claim. The seasonal pattern (7) is supported; whether pre-positioning follows is outside this dataset | | Not testable here |

### Notes on individual verdicts

**Claim 4, trend.** The Class G series is the right one to test "getting worse" because 5,000-acre fires are recorded by every reporting system, whereas the total fire count depends on which agencies reported in each year (the count of all fires has no trend: tau 0.10, p 0.47, `year.fires_trend`). Class G fires are 0.21% of records and 75.1% of all acres (`year.fires_share_by_size_class`, `year.acres_share_by_size_class`). The first-half mean is 3.53M acres a year (1992 to 2005), the second-half mean 5.71M (2006 to 2020); without Alaska, 2.16M and 4.66M (`class_g.half_period_means`). Alaska holds 25.9% of Class G acres and its own series has no trend (tau 0.12, p 0.36), so the national trend is driven by the lower 48. The number of Class G fires also trends up (tau 0.35, p 0.007, +4.2 fires a year, `class_g.fires_trend`). Figure: `class_g_acres_trend.png`.

**Claim 8, duration.** The day-level duration is CONT_DATE minus DISCOVERY_DATE for the 1,408,753 records with a containment date, all years. Because 84% of those fires are contained on the day of discovery, the mean is driven by the tail and the median is 0 in every region but Alaska. The wording "last the longest" describes Alaska far better than the West.

**Claim 13, CES.** The score was recomputed on all 1,142,942 records with a positive hour-level duration (any year), for the 14 owner categories with at least 1,000 such records. Full table:

| Owner | n | Mean acres/hr | Median acres/hr | Rank (mean-based) | Rank (median-based) |
|---|---|---|---|---|---|
| PRIVATE | 331,278 | 4.92 | 0.83 | 3 | 13 |
| MISSING/NOT SPECIFIED | 293,511 | 6.46 | 0.90 | 8 | 14 |
| USFS | 201,382 | 8.64 | 0.045 | 11 | 1 |
| BIA | 119,040 | 5.08 | 0.43 | 4 | 11 |
| BLM | 70,049 | 5.85 | 0.069 | 6 | 2 |
| STATE | 33,056 | 6.34 | 0.35 | 7 | 7 |
| STATE OR PRIVATE | 31,283 | 7.85 | 0.43 | 9 | 10 |
| NPS | 16,434 | 1.80 | 0.086 | 1 | 3 |
| MUNICIPAL/LOCAL | 12,174 | 2.23 | 0.115 | 2 | 4 |
| FWS | 10,507 | 10.17 | 0.57 | 12 | 12 |
| TRIBAL | 10,514 | 5.25 | 0.32 | 5 | 6 |
| OTHER FEDERAL | 5,754 | 26.15 | 0.30 | 14 | 5 |
| UNDEFINED FEDERAL | 4,784 | 8.06 | 0.375 | 10 | 8 |
| COUNTY | 2,729 | 13.78 | 0.38 | 13 | 9 |

Rank 1 is the "most efficient" (fewest acres per hour). The mean is set by a handful of enormous fires per owner; the median is set by the typical fire, and the typical USFS or BLM fire spreads very slowly per hour because those agencies record long containment times even for small fires (see section 2.6). Neither version measures response quality.

## 2. New findings the Tableau story did not have

### 2.1 Where the acres are (`year.acres_share_by_size_class`, `geo.*`)

| Size class | Share of fires | Share of acres |
|---|---|---|
| A (<0.26 ac) | 38.0% | 0.06% |
| B (0.26 to 9.9) | 47.9% | 1.3% |
| C (10 to 99.9) | 11.2% | 4.1% |
| D (100 to 299) | 1.5% | 3.1% |
| E (300 to 999) | 0.7% | 4.9% |
| F (1,000 to 4,999) | 0.4% | 11.5% |
| G (5,000+) | 0.2% | 75.1% |

Top states by acres: Alaska 36.65M, California 20.93M, Idaho 15.95M, Texas 11.91M, Nevada 11.84M. Top states by fires: California 251,881, Georgia 185,040, Texas 180,087, North Carolina 130,165, Arizona 104,956 (`geo.top5_states_acres`, `geo.top5_states_fires`). Total acres 1992 to 2020: 180.05M; total acres per year trend up (tau 0.40, p 0.002, +200,671 acres a year, `year.acres_trend`), and 2020 is the peak year at 10.50M acres. The most fires in one year was 2006 (117,943), which is a reporting peak, not a fire peak. Figure: `fires_and_acres_by_year.png`.

### 2.2 The 1-degree grid (`geo.cells_1deg_file`, `geo.cells_1deg_summary`, `outputs/cells_1deg.csv`)

1,239 one-degree cells contain fires; 1,051 have at least 20. The 50 busiest cells hold 27.9% of all fires; the 50 largest by acreage hold 30.3% of all acres, and they are different cells. The busiest cell is 34N 80W (South Carolina Piedmont): 20,710 fires, 98% human among known causes. The largest-acreage cell is 42N 116W (south-west Idaho and northern Nevada rangeland): 2.43M acres from 893 fires, 54% human. Human share among known causes is above 90% across the South and East and drops to 20 to 50% in the interior West and Alaska. The CSV has columns cell_lat, cell_lon (south-west corner), n_fires, acres, n_human, n_natural, n_missing_cause, human_share_known, human_share_all, lat_centroid, lon_centroid. Figure: `cells_1deg_map.png`.

### 2.3 Cause by size (`cause.human_share_known_by_size_class`, `cause.classification_acre_share_by_size_class`)

Among fires with a known cause classification, the human share falls with size: A 78%, B 90%, C 88%, D 78%, E 67%, F 52%, G 35%. Natural causes are a majority of fires only in Class G (61.8% of Class G fires, 67.1% of Class G acres). Natural fires average 323 acres, debris burning 15 acres (`cause.by_general_cause`). Figure: `cause_share_fires_vs_acres.png`.

### 2.4 Seasonality by region (`season.*`)

| Region | Fires | Acres | Peak month, fires | Peak month, acres |
|---|---|---|---|---|
| West | 752,490 | 102.47M | Jul | Aug |
| South | 1,082,568 | 32.93M | Mar | Mar |
| Northeast | 180,427 | 0.43M | Apr | Apr |
| Alaska | 15,195 | 36.65M | Jun | Jun |
| Hawaii/PR | 32,172 | 0.47M | Mar | Aug |
| Other | 240,714 | 7.09M | Apr | Apr |

The South has the most fires and the West the most acres; Alaska has 0.7% of fires and 20.4% of acres. July is the national peak for both fires (297,770) and acres (43.6M). Figures: `seasonality_by_region.png`, `monthly_class_g_by_region.png`.

### 2.5 Ownership (`owner.fires_and_acres`)

Ownership is not recorded for 46.4% of fires (12.7% of acres). Among fires with a known cause, the human share by owner is BLM 33%, USFS 42%, NPS 52%, FWS 65%, BIA 84%, State 81%, Private 91%, Missing 95%. The federal land agencies burn the most acres with the fewest human ignitions; private and unrecorded land burn less area from mostly human ignitions. Figure: `ownership_acres.png`.

### 2.6 Containment records (`cont.*`)

61.2% of all records have a containment date. The share moves with reporting, not with fire behaviour: 37.5% in 1999, 84.0% in 2015 (`cont.share_with_cont_date_by_year`). By owner it is 99.7% for BLM, 99.2% BIA, 96.0% USFS and 39.9% for unrecorded ownership; by region 75.4% West, 48.8% South, 1.8% Hawaii/PR. Any model trained on fires with a containment date is trained on federal and Western fires.

For the 577,956 fires from 2010 on with both a discovery and a containment date-time, the median time to containment is 1.15 hours (75th percentile 3.2 hours, 90th 26 hours, 99th 554 hours); 4.0% are recorded as 0 hours. Median hours by size class and owner:

| Class | USFS | BLM | BIA | STATE | PRIVATE | Not specified |
|---|---|---|---|---|---|---|
| A | 4.2 | 3.4 | 0.9 | 0.8 | 0.7 | 0.4 |
| B | 21.5 | 5.5 | 1.6 | 1.4 | 1.2 | 0.9 |
| C | 30.0 | 23.2 | 5.4 | 4.1 | 2.8 | 2.4 |
| D | 97.6 | 42.4 | 25.3 | 21.4 | 7.5 | 4.7 |
| E | 185.0 | 64.7 | 73.7 | 45.1 | 24.1 | 8.8 |
| F | 644.8 | 100.3 | 141.6 | 117.6 | 54.0 | 28.5 |
| G | 1,149.8 | 292.0 | 374.1 | 793.9 | 193.3 | 93.4 |

Within every size class the USFS records containment times five to twenty times longer than private or unrecorded owners. Since a Class A fire is under a quarter acre in all cases, a 4.2-hour versus 0.4-hour median is a difference in what "contained" means to the reporting system, not in the fire. This is the same artefact that makes the Control Efficiency Score unstable. Figure: `containment_hours_by_class_owner.png`.

### 2.7 The Northeast series is a reporting series (`anom.northeast_*`)

New York is 54.9% of Northeast records. Rhode Island reports 0 fires in 1992 to 2004 (except 1994) and in 2010; Connecticut 0 in 2013 and 2014; Massachusetts 6 fires in 2014 and 2,170 in 2015. The three largest year-over-year jumps in the regional count (2005, 2015, 2020) coincide with states joining or changing systems. Northeast year-to-year comparisons should not be presented as fire trends.

## 3. Definitions and judgment calls

- **Regions.** West = AZ CA CO ID MT NV NM OR UT WA WY; South = AL AR FL GA KY LA MS NC OK SC TN TX VA WV; Northeast = CT ME MA NH RI VT NY NJ PA; Alaska = AK; Hawaii/PR = HI PR (one group, kept apart from "Other" because neither is contiguous); Other = everything else (Midwest, Plains, DC, DE, MD). These match `scripts/reproduce.py`. The Tableau workbook's region definition is unknown, so verdicts 8 and 11 are conditional on this one (`overview.region_definition`).
- **GACC grouping.** A state-level approximation of the ten NWCG Geographic Area Coordination Centers, in `analysis/common.py` (`GACC_STATES`). Verified from pages fetched on 2026-09-25: the ten names (https://gacc.nifc.gov/), Northwest = OR and WA (https://gacc.nifc.gov/nwcc/), Southwest dispatch centres in AZ and NM (https://gacc.nifc.gov/swcc/), Great Basin dispatch centres in ID NV UT WY (https://gacc.nifc.gov/gbcc/), Rocky Mountain dispatch centres in WY CO and the Great Plains (https://gacc.nifc.gov/rmcc/), Eastern Area described as twenty states (https://gacc.nifc.gov/eacc/). The Southern and Eastern state lists and the assignment of split states (ID, WY, TX, CA North/South) are **unverified**: real GACC boundaries do not follow state lines, so the grouping is labelled "(approx)" in every output and should not be presented as official.
- **Size classes.** FIRE_SIZE_CLASS as coded: A < 0.26 acres, B 0.26 to 9.9, C 10 to 99.9, D 100 to 299, E 300 to 999, F 1,000 to 4,999, G 5,000 and up.
- **Missing cause and owner.** The explicit categories "Missing data/not specified/undetermined" and "MISSING/NOT SPECIFIED" are counted as missing; there are no nulls in those fields. Human share is always "share of fires with a known cause classification that are Human", so the denominator excludes missing.
- **Owner labels.** OWNER_DESCR is upper-cased so that the two "Private" rows merge into "PRIVATE".
- **Month.** DISCOVERY_MONTH is the month of DISCOVERY_DATE, so a fire is counted in the month it was found, not the months it burned.
- **Trend tests.** Kendall tau and Theil-Sen on 29 annual points, with years that have no Class G fires counted as 0 (none occur). No serial-correlation adjustment; the p-values are the plain Kendall ones.
- **Hour-level duration.** DURATION_HOURS from the parquet cache: CONT_DATETIME minus DISCOVERY_DATETIME, defined only when both date and a valid HHMM time exist. The containment tables use fires from 2010 on with this field non-null and include 0-hour records; the Control Efficiency Score uses all years and requires DURATION_HOURS > 0, matching the Phase 0 recomputation.
- **Owner thresholds.** The CES table keeps owners with at least 1,000 positive-duration records; the ownership figure keeps owners with at least 5,000 fires; the containment figure shows the four most frequent owners in the 2010+ sample.
- **1-degree cells.** Cell = floor(LATITUDE), floor(LONGITUDE); the map draws cells with at least 20 fires. No coordinates are null.
- **Z-scores.** Against the 29-year mean and sample standard deviation of the same series; the "outlier" bar used is |z| above 2.

## 4. Figures

All in `outputs/figures/`, 150 dpi PNG, one palette, "n =" in every footer.

| File | Shows | Claim ids |
|---|---|---|
| `fires_and_acres_by_year.png` | fires and acres per year, two panels | `year.fires_and_acres` |
| `class_g_acres_trend.png` | Class G acres with and without Alaska, Theil-Sen line | `class_g.*` |
| `cause_share_fires_vs_acres.png` | share of fires vs share of acres by general cause | `cause.by_general_cause` |
| `seasonality_by_region.png` | month profile of fires and acres per region | `season.fires_by_region_month`, `season.acres_by_region_month` |
| `monthly_class_g_by_region.png` | Class G counts by month, stacked by region | `season.class_g_fires_by_region_month` |
| `ownership_acres.png` | acres by owner with human share | `owner.fires_and_acres` |
| `containment_hours_by_class_owner.png` | median hours to containment by size class and owner | `cont.median_hours_by_size_class_and_owner_2010_plus` |
| `cells_1deg_map.png` | 1-degree cells sized by count, coloured by human share | `geo.cells_1deg_file` |
| `june_class_g_states.png` | June Class G acres by state, the Arkansas check | `anom.june_class_g_by_state_top10` |

## 5. Proposed changes to other files

- **README.md Part 1:** replace the Tableau paragraph with the verdict table above (generated from `claims.json`). Drop the Arkansas, Texas December and Northeast 2010 "anomalies" or restate them as in rows 9 to 11. Restate "higher highs and higher lows" as "the trend is upward (Kendall tau 0.43, p 0.0007) but low years still occur". Add the unrecorded-ownership caveat to the ownership sentence. Retire the Control Efficiency Score, or present it only as an example of an unstable metric.
- **docs/review/REPRODUCTION.md:** no change needed; every Phase 0 number is reproduced here. The CES table here has 14 owners (threshold 1,000 records) rather than the top 12, so USFS ranks 11th rather than 10th under the mean.
- **scripts/reproduce.py:** could import `region_of` and the trend helper from `analysis.common` instead of carrying its own copies.
