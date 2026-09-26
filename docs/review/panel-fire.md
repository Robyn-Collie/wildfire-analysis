# Panel review: fire-science domain expert (panel-fire)

Reviewer role: wildland fire researcher who works with the FPA FOD and with incident management.
Brief: argue against the project's domain framing and the Part 1 descriptive claims.
Data: `data/fires.parquet` (FPA FOD 6th ed., 2,303,566 rows, SHA-256 `04f5ab8b…51a965a8`).
Scratch scripts (all run from the repo root with `.venv/bin/python`):

| Script | What it computes |
|---|---|
| `/tmp/claude-0/-home-user-wildfire-analysis/a4df9529-3e52-5fbc-b7e0-fb427368a57f/scratchpad/panel-fire/01_reporting_coverage.py` | fires and acres per year by SOURCE_SYSTEM_TYPE and NWCG_REPORTING_AGENCY; distinct source systems per year; state-year reporting breaks; CONT_DATE / CONT_TIME / DISCOVERY_TIME missingness by agency |
| `.../panel-fire/01b_cont_missing.py` | CONT_DATE missingness by year, size class, owner, state; FS by year |
| `.../panel-fire/02_control_efficiency.py` | Control Efficiency Score by mean and median; stratified median hours to containment by owner and size class; size mix and natural-cause share by owner |
| `.../panel-fire/03_classG_cause.py` | Class G acres by year with and without Alaska, West only, minus top-3 years (Kendall tau, Theil-Sen); cause shares by region and decade; day-resolution check; P(size >= 300 acres) |
| `.../panel-fire/04_misc.py` | residual cross-agency duplicates; West Class G by state; human-caused fires by month and top causes by region; P(>= 300) by region x cause, region x month, discovery hour; MTBS/ICS-209 linkage of Class G fires |

Outputs are in `01_out.txt`, `01b_out.txt`, `02_out.txt`, `03_out.txt`, `04_out.txt` in the same directory.
Region definitions used throughout (same 11-state West, 14-state South and 9-state Northeast as `scripts/reproduce.py`):
West = AZ CA CO ID MT NV NM OR UT WA WY; South = AL AR FL GA KY LA MS NC OK SC TN TX VA WV; Northeast = CT ME MA NH RI VT NY NJ PA; Plains/Midwest = ND SD NE KS MN IA MO WI IL IN MI OH; Alaska, Hawaii and Puerto Rico separately; everything else "Other".

---

## (a) Verdict (150 words)

The README treats the FPA FOD as a census of US wildfires and reads every year-to-year change as a change in fire. It is not a census. It is a compilation of dozens of reporting systems whose coverage changes by state and year, and its own metadata says counts "may underrepresent actual wildfire activity in certain areas and time periods." Fire counts, "worse", Texas, the Northeast and anything built on CONT_DATE inherit those breaks. The one Part 1 claim that survives is the large-fire area trend, and it survives with caveats: it is significant with and without Alaska, weaker once the top three years are removed, and says nothing about cause (weather, fuels, ignition density, policy). The Control Efficiency Score is not a response metric; it measures the size mix, cause mix and reporting conventions of each owner. The duration model rests on a field that means different things in different systems. Rebuild around large-fire probability, ignition timing by cause, and explicit coverage masks.

---

## (b) Findings

Ratings: Critical (a claim or method is wrong in a way that changes the story), Major (a claim is weakened or a method needs replacing), Minor (wording, definitions, presentation).

### F1. Critical: the FPA FOD is a compilation of reporting systems, not a census, and the README never says so

**What the dataset says about itself.** Fetched from the 6th-edition FGDC metadata, https://www.fs.usda.gov/rds/archive/products/RDS-2013-0009.6/_metadata_RDS-2013-0009.6.html (linked from https://www.fs.usda.gov/rds/archive/Catalog/RDS-2013-0009.6, which is where https://doi.org/10.2737/RDS-2013-0009.6 redirects):

> "Viable state and local (i.e., nonfederal) records were not available from all states for all years. Estimates of wildfire numbers and area burned from the FPA FOD may therefore underrepresent actual wildfire activity in certain areas and time periods."

> "Estimates of area burned tend to be less compromised than wildfire numbers by missing nonfederal records, because very large fires tend to account for the majority of area burned and are commonly responded to and reported by multiple agencies."

> "The following core data elements were required for records to be included in this data publication: discovery date, final fire size, and a point location at least as precise as a Public Land Survey System (PLSS) section (1-square mile grid)."

> Attribute accuracy: "These data were acquired from federal, state, and local wildfire reporting systems and are subject to inaccuracies and imprecision inherent in the original datasets."

And from Short (2014), the paper that defines the database, https://essd.copernicus.org/articles/6/1/2014/essd-6-1-2014.pdf (text extracted from the PDF in this session; saved as `.../panel-fire/short2014.txt`):

> "For Texas and other states in which local entities bear responsibility for initial attack on non-federal wildlands, no data set purporting to represent all lands can be deemed complete, particularly with regard to wildfire numbers, without viable local wildfire records. In general, non-federal fire reporting has been on the rise over the past several decades, and users of national data sets like the FPA FOD must beware of local reporting biases in addition to those of state entities in order to avoid drawing spurious conclusions when analyzing the data. Apparent trends in the numbers and area burned by wildfires, for example, may be the result of multiple factors, including changes in climate, fuels, demographics (e.g., population density), fire-management policies (Johnston and Klick, 2012), and, as we underscore here, levels of reporting."

> "scores for the states of Iowa, Illinois, Kansas, New York, and Texas are not indicated in Fig. 5, because they are misleading due to reporting biases evident in the FPA FOD and the reference sources"

> On New York: "Estimates from all sources agree well for the period 1992–1999, but are based only on federal records and records from fires responded to by the state's forest ranger force. Beginning in 2000, numbers from the AWSR and the FPA FOD increase with increased reporting from local fire departments"

> On sources: "the Texas A&M Forest Service (TFS) provided a compiled data set of state and local wildfires reported to the TFS since 2005."

The README calls the data "the US Forest Service's national record of wildfires." It is hosted by the Forest Service Research Data Archive, but 75% of the records come from state and local systems (NONFED share of fire count, 1992 to 2019: 66% to 83%, script 01 section E).

**What the data show (script 01).**

Fires per year by source-system type (counts):

| Year | FED | INTERAGCY | NONFED | Total | Distinct SOURCE_SYSTEM values |
|---|---|---|---|---|---|
| 1992 | 20,760 | 334 | 46,867 | 67,961 | 27 |
| 1997 | 15,753 | 0 | 45,689 | 61,442 | 30 |
| 2000 | 25,116 | 130 | 71,150 | 96,396 | 27 |
| 2005 | 21,134 | 5,566 | 66,221 | 92,921 | 15 |
| 2006 | 27,257 | 3,547 | 87,139 | 117,943 | 14 |
| 2011 | 17,408 | 3,479 | 78,016 | 98,903 | 13 |
| 2015 | 15,925 | 438 | 60,912 | 77,275 | 9 |
| 2019 | 12,630 | 63 | 50,864 | 63,557 | 5 |
| 2020 | 921 | 19,413 | 52,928 | 73,262 | 5 |

In 2020 the federal systems (FS-FIRESTAT: 0 records; DOI-WFMI: 467) were replaced by IA-IRWIN (19,406 records). Federal fires did not disappear; they moved to the INTERAGCY type. Any analysis by SOURCE_SYSTEM_TYPE breaks at 2020 (NWCG_REPORTING_AGENCY is preserved and is the field to use).

State-year reporting breaks. Among the 48 states/territories with at least 1,000 records, 30 have at least one year-over-year count change larger than 3x or smaller than 1/3, and three (CT, MA, PR) have zero-count years (CT 2013 and 2014, MA 2011, PR 1995 and 1999 to 2001). Examples that matter for the README's story:

| State | Series (fires per year) | Reading |
|---|---|---|
| TX | 2004: 1,040; 2005: 6,901; 2006: 15,019; 2007: 5,477; 2008: 18,068 | TFS compilation starts 2005 (Short 2014). "Texas in winter" is a 2005+ artifact of coverage, not a 1992 to 2020 pattern. Texas 2010+ records lack CONT_DATE 87.6% of the time. |
| NY | 1994: 129; 2000: 1,756; 2003: 4,933; 2005: 7,700 | Local fire departments start reporting in 2000 (Short 2014). Any Northeast series is a reporting series. |
| KS | 2014: 59; 2015: 5,885; 2016: 1,781; 2019: 123; 2020: 980 | Coverage switches on and off. |
| LA | 2000: 4,234; 2001: 976; 2003: 94; 2005: 3,384; 2007: 63; 2008: 1,438; 2011: 217 | Alternating years of coverage. |
| TN | 2002: 1,485; 2003: 31; 2005: 2,041 | Same. |
| MA | 2014: 6; 2015: 2,170 | 361x jump. |
| HI | 2012: 715; 2013: 60; 2014: 2 | Coverage ends. |
| AL | 1993: 137; 1994: 3,452 | Coverage begins. |

National fire counts therefore have no interpretable trend: 1992 to 2004 average about 75,000 per year, 2005 to 2011 about 95,000, 2012 to 2020 about 74,000, tracking the entry and exit of state systems rather than fire.

Residual duplication (script 04 section A) is small: 365 cross-agency groups with the same discovery date, same final size and location within 0.01 degree (390 excess records), and zero pairs of fires of 1,000+ acres reported by two agencies with the same date and size within 0.05 degree. Short's deduplication holds for large fires; this is a point in the data's favour and should be stated.

**Fix.** Add a "What this data is" section: compilation, inclusion rule, coverage varies by state and year, counts are not comparable across years without a coverage mask, area is more robust than counts. Publish a coverage table (state x year record counts with flagged breaks) as a first-class artifact of the site. Restrict any count-based trend to (a) federal reporting agencies (FS, BLM, BIA, NPS, FWS), whose coverage is stable 1992 to 2019 (script 01 section B: FS 5,400 to 14,500 per year with no step changes), or (b) states whose series pass the break test. Never show a national count-per-year line without the mask.

### F2. Critical: CONT_DATE is not "when the fire stopped burning", and its missingness is structured by reporting agency

**Definition (fetched, metadata URL above):** CONT_DATE is the "Date on which the fire was declared contained or otherwise controlled (mm/dd/yyyy where mm=month, dd=day, and yyyy=year)." CONT_TIME: "Time of day that the fire was declared contained or otherwise controlled." CONT_DOY: "Day of year on which the fire was declared contained or otherwise controlled." The field mixes two different operational milestones.

**Operational meaning.** NWCG glossary entries (PMS 205). Fetched directly: "out (fire)", https://www.nwcg.gov/publications/pms205/nwcg-glossary-of-wildland-fire-pms-205/out-fire: "All observable combustion has ceased and there is no risk of the fire again becoming active and requiring additional control or management actions." The "containment (wildfire)" and "controlled" pages (https://www.nwcg.gov/publications/pms205/nwcg-glossary-of-wildland-fire-pms-205/containment-wildfire-5 and .../controlled-5) returned 404/403 to every fetch attempt in this session (the NWCG site is mid-reorganisation); the text below is what the search engine returned as the snippet for those two URLs and is therefore only partly verified:

> containment (wildfire): "The status of a wildfire suppression action signifying that a control line has been completed around the fire, and any associated spot fires, which can reasonably be expected to stop the fire's spread."
> controlled: "The completion of control line around a fire, any spot fires therefrom, and any interior islands to be saved; burned out any unburned area adjacent to the fire side of the control lines; and cool down all hotspots that are immediate threats to the control line, until the lines can reasonably be expected to hold under the foreseeable conditions."

So: contained means the line is around it and expected to hold; controlled means mop-up along the line is done; out means combustion has ceased. A fire can burn inside the line for weeks after "contained". The README's Part 2 question ("how long it will burn") and Part 1's "Western fires last the longest" are about burn duration; the field is about a suppression-status declaration. The declaration convention differs by system: state and local reports often record the time the engine cleared; federal reports on multi-day incidents record containment after mop-up. This is visible in the data (F3 below): for fires of 300+ acres, the median hours to containment is 24 h when a state/county/local unit wrote the report and 387 h when the Forest Service wrote it (script 02 section C). A 300-acre fire is not contained in 24 hours in any physical sense; that is a reporting convention.

**Missingness is structured (scripts 01 and 01b).** CONT_DATE missing, 2010 to 2020, by reporting agency:

| NWCG_REPORTING_AGENCY | n (2010+) | CONT_DATE missing % | CONT_TIME missing % | DISCOVERY_TIME missing % |
|---|---|---|---|---|
| ST/C&L | 678,743 | 30.9 | 35.7 | 22.8 |
| FS | 73,571 | 12.7 | 19.6 | 6.8 |
| BIA | 44,961 | 1.4 | 6.2 | 6.0 |
| BLM | 38,257 | 0.7 | 4.4 | 4.2 |
| NPS | 6,694 | 4.1 | 7.7 | 6.1 |
| FWS | 5,909 | 6.8 | 18.3 | 14.5 |
| IA | 4,235 | 99.7 | 99.8 | 99.8 |
| DOD | 118 | 74.6 | 75.4 | 13.6 |

By source type 2010+: FED 5.9%, INTERAGCY 35.2%, NONFED 30.7%. By year, NONFED missingness ranges from 84.6% (1998) to 17.1% (2015); the FS series jumps from 0.2 to 1.4% (2010 to 2014) to 24 to 30% (2015 to 2019), a FIRESTAT-era reporting change, not a change in fire behaviour. By owner, "STATE OR PRIVATE" records lack CONT_DATE 72.3% of the time; USFS-owned records lack it for 13.1% of fires but 28.1% of USFS acres. By state, Texas 87.6%, Virginia 94.4%, Puerto Rico 94.8%, Hawaii 95.7%, Louisiana 59.5%, California 48.8%.

**Day resolution (script 03 section C, 2010+ fires with both timestamps).** Share contained the same calendar day: class A 84.5%, B 87.5%, C 76.3%, D 48.7%, E 30.3%, F 12.8%, G 2.9%. Of all 2010+ fires with both timestamps, 45.1% were "contained" in under 1 hour and 73.6% in under 3 hours; 4.03% have CONT_TIME identical to DISCOVERY_TIME (5.0% of NONFED records), which is a placeholder, not a measurement. For fires of 300+ acres the hours-to-containment distribution is median 77 h, 90th percentile 1,274 h (53 days), 99th percentile 2,880 h (120 days). A whole-day target puts 84% of the sample at zero and treats a 20-minute grass fire and a 23-hour fire as identical while splitting two 3-hour fires across midnight into 0 and 1 (REPRODUCTION.md agrees).

**Fix.** Stop calling this "burn duration". If a suppression-timing analysis is kept, (1) use hours, (2) restrict to a single reporting system with a stable convention (federal agencies, or one state system), (3) stratify by size class, (4) say explicitly that it measures time to a containment declaration under that system's convention. Report missingness by agency and state next to every containment-based number.

### F3. Critical: the Control Efficiency Score is not a response metric

Definition in README: 1 / (mean acres burned per hour until control), by owner. Script 02, 2010+ fires with both timestamps and positive hours (n = 554,677).

**It is dominated by a handful of fires.** For USFS-owned land the top 1% of fires by acres-per-hour carry 97.3% of the sum of acres-per-hour, and the top 10 fires alone carry 77.8%. The mean is a statistic of the ten largest wind-driven runs, not of "response". Ranking by 1/mean puts USFS 16th of 16 owners; ranking by 1/median puts USFS 1st (REPRODUCTION.md found 10th to 1st on the all-years sample; same instability).

**It is confounded by what each owner's fires are.**

| Owner (2010+, both times) | n | Class A share % | Class E+ share % | Natural-cause share % | Fires >= 14 days % |
|---|---|---|---|---|---|
| USFS | 50,310 | 68.9 | 2.4 | 53.0 | 4.5 |
| BLM | 22,353 | 54.6 | 6.4 | 59.7 | 3.7 |
| NPS | 5,190 | 62.8 | 5.1 | 44.8 | 12.4 |
| FWS | 3,539 | 30.5 | 11.6 | 31.0 | 9.4 |
| PRIVATE | 213,109 | 29.9 | 1.1 | 8.4 | 1.3 |
| STATE | 23,422 | 49.7 | 2.9 | 16.2 | 3.9 |
| MISSING/NOT SPECIFIED | 170,529 | 52.0 | 0.6 | 4.8 | 0.2 |

Federal owners have lightning-dominated ignitions in remote terrain, the only owners with a policy option of managing natural ignitions for resource benefit (which by design produces long "durations" and large final sizes), the only fires with multi-day mop-up before containment is declared, and a different detection regime (lookouts, aircraft, satellite) from a private landowner who calls 911 about a debris pile. None of that is "response". The README already says the score is unfair; the problem is that it is presented at all, with a name that implies efficiency.

**Stratified alternative (script 02 section B): median hours to containment by owner within size class, 2010+, cells with n >= 200.**

| Owner | A | B | C | D | E+ |
|---|---|---|---|---|---|
| MISSING/NOT SPECIFIED | 0.4 | 0.9 | 2.6 | 5.0 | 21.2 |
| PRIVATE | 0.8 | 1.2 | 2.9 | 8.1 | 42.0 |
| STATE OR PRIVATE | 1.0 | 1.7 | 3.5 | 7.8 | 28.5 |
| STATE | 0.8 | 1.4 | 4.4 | 21.7 | 108.7 |
| BIA | 1.0 | 1.8 | 5.5 | 25.5 | 124.8 |
| FWS | 1.0 | 3.5 | 16.0 | 22.2 | 218.5 |
| BLM | 3.5 | 6.2 | 23.6 | 42.6 | 103.0 |
| USFS | 4.2 | 21.5 | 30.0 | 97.6 | 457.5 |
| NPS | 3.0 | 20.5 | 77.8 | (n<200) | 712.6 |

Does the ordering survive stratification? Yes, and that is the problem: within every size class, non-federal owners are "faster" and USFS/NPS are "slowest", by 5x to 20x. A 0.1-acre fire on USFS land takes a median 4.2 h to a containment declaration versus 0.8 h on private land; a 300+ acre fire 458 h versus 42 h. Nobody who has worked an incident believes a 300-acre fire on private land is contained in 42 hours at the median while the same fire on Forest Service land takes 19 days; the gap is reporting convention (containment after mop-up versus engine cleared), detection lag, access, and managed natural ignitions. The same table by NWCG_REPORTING_AGENCY (who wrote the report, not who owns the land) shows the same split: E+ median 24.3 h for ST/C&L versus 387 h for FS. The stratified score therefore ranks reporting systems, and the README's mean-based ranking, which happened to put USFS last, was right for the wrong reason.

**What a fair comparison needs.** Same reporting system (or a calibrated crosswalk of containment conventions), same size class, same cause, same fuel type (LANDFIRE FBFM), same terrain class (slope, distance to road), same weather at discovery (ERC, wind), same detection method and reported discovery-to-first-response interval (which the FPA FOD does not carry; it is in ICS-209-PLUS for large fires and in some state systems), and exclusion of fires under a non-full-suppression strategy (ICS-209-PLUS carries strategy fields for 209-reported incidents; the FPA FOD row carries `ICS_209_PLUS_INCIDENT_JOIN_ID` for the join). Without at least the first three, no owner comparison should be published.

**Fix.** Remove the Control Efficiency Score. Replace with a descriptive "time to containment declaration by reporting system and size class" table with the caveats above, or drop the response question entirely.

### F4. Major: the Class G trend is real but narrower than "fires are getting worse"

Script 03 section A. Kendall tau on annual Class G acres, 1992 to 2020, Theil-Sen slope, and the change in mean between 1992 to 2005 and 2006 to 2020:

| Series | tau | p | Theil-Sen (M acres/yr) | Mean 1992-2005 (M) | Mean 2006-2020 (M) |
|---|---|---|---|---|---|
| All states | 0.43 | 0.0007 | 0.178 | 3.53 | 5.71 |
| Excluding Alaska | 0.35 | 0.0073 | 0.142 | 2.16 | 4.66 |
| West (11 states) | 0.34 | 0.0093 | 0.102 | 1.88 | 3.76 |
| South (14 states) | 0.27 | 0.0401 | 0.012 | 0.18 | 0.79 |
| Alaska only | 0.12 | 0.36 | 0.007 | 1.37 | 1.05 |
| All, minus top-3 years (2020, 2015, 2017) | 0.33 | 0.018 | 0.118 | 3.53 | 4.97 |
| Excl. Alaska, minus top-3 (2020, 2017, 2012) | 0.24 | 0.094 | 0.077 | 2.16 | 3.82 |
| West, minus top-3 (2020, 2012, 2007) | 0.29 | 0.042 | 0.068 | 1.88 | 2.91 |

Alaska is 25.9% of all Class G acres and has no trend of its own; it contributes the noise (0.89 of the 2004 total, 0.79 of 1997, 0.66 of 2019), not the signal. The signal is the conterminous West: Class G acres by 5-year block are 7.6, 9.4, 14.4, 13.5, 16.8, 21.0 million. Every one of the 11 Western states has higher Class G acreage in 2006 to 2020 than in 1992 to 2005 (ratios: WA 3.4, CA 3.2, CO 3.2, OR 2.7, WY 2.4, MT 2.2, ID 1.9, NM 1.8, AZ 1.6, UT 1.5, NV 1.2); California is 23.3% of Western Class G acres in the later period, so this is not a California-only story. The count of Class G fires also trends up (tau 0.35 all, 0.29 excluding Alaska, 0.28 West), which is safer than the national count of all fires because 92.5% of Class G records carry an MTBS_ID (satellite-mapped perimeter), so they are not reporting artifacts. Class G fires are 75.1% of all acres in the database.

But: dropping three years takes the non-Alaska series to p = 0.09. The trend is carried by the upper tail of the distribution of years, which is exactly what one expects from a fire regime driven by a few extreme fire-weather seasons; that is a property of the phenomenon, not a flaw, but "higher highs and higher lows" is not accurate (2010: 2.1M, lower than 1996 or 1999; REPRODUCTION.md agrees).

**What the data cannot say.** The FPA FOD has no weather, no fuels, no ignition-density denominator (no exposure: acres of burnable land, person-days, lightning strikes), and no suppression strategy. "Worse" in the README means "more area in fires over 5,000 acres in the West". It cannot separate warmer and drier fire seasons (the literature's leading explanation) from fuel accumulation, from more human ignitions in the wildland-urban interface, from changed suppression policy (managed fire), or from the reporting effects on the smaller size classes. It also cannot say anything about severity, structures lost, smoke, or deaths, which is what a Los Angeles resident means by "worse".

**Fix.** Rewrite the claim as: "Area burned in fires of 5,000+ acres in the 11 Western states roughly doubled between 1992-2005 and 2006-2020 (1.9M to 3.8M acres per year; Kendall tau 0.34, p = 0.009). The trend is carried by extreme years and is not present in Alaska. This dataset cannot attribute it." Show the Alaska and non-Alaska series separately. Drop "higher lows".

### F5. Major: human vs natural is region-specific, and "Missing" cause is large enough to move the answer

Script 03 sections B and B3; script 04 section C.

Share of fires and of acres by cause class, 1992 to 2020:

| Region | Fires (n) | Human % of fires | Natural % | Missing % | Acres (M) | Human % of acres | Natural % of acres | Missing % |
|---|---|---|---|---|---|---|---|---|
| West | 752,490 | 57.6 | 32.1 | 10.3 | 102.5 | 32.8 | 61.8 | 5.4 |
| South | 1,082,568 | 87.9 | 5.4 | 6.7 | 32.9 | 68.9 | 19.5 | 11.6 |
| Alaska | 15,195 | 63.5 | 33.5 | 3.0 | 36.7 | 4.9 | 93.9 | 1.2 |
| Plains/Midwest | 236,276 | 91.9 | 5.5 | 2.6 | 7.0 | 68.6 | 21.5 | 9.9 |
| Northeast | 180,427 | 92.5 | 4.9 | 2.5 | 0.4 | 90.1 | 4.6 | 5.3 |
| Hawaii | 9,970 | 2.0 | 0.4 | 97.5 | 0.3 | 29.6 | 5.5 | 64.9 |
| Puerto Rico | 22,202 | 1.3 | 0.0 | 98.6 | 0.1 | 7.0 | 0.0 | 93.0 |

By decade (all regions): human share of fires 75.8, 77.2, 78.7%; natural 16.0, 15.2, 12.0%; missing 8.3, 7.6, 9.3%. Natural share of acres 55.2, 64.1, 55.0%. Missing cause by year swings between 0.8% (2000) and 16.0% (2011), and is 59.1% for INTERAGCY records (so 2020, which is 27% INTERAGCY, is not comparable on cause). In the West 2010 to 2020, missing cause is 17.7% of records: the human share of fires is 58.9% including missing in the denominator and 71.7% excluding it. The README's "human-caused fires far outnumber natural" is true nationally and in the East; in the West and Alaska it is 58% and 64%, and in the West the acres story is the reverse (62% natural). The README's national 105.6M natural acres is about 34.5M Alaska (93.9% of 36.7M) plus 63.3M West (61.8% of 102.5M) plus a residue of about 7.8M; it is a Western and Alaskan number.

Among human-caused fires, "Missing data/not specified/undetermined" is the largest general cause in the West (42.4%), Alaska (42.7%) and the Plains/Midwest and Northeast (32.9%); only in the South is a real cause on top (debris and open burning, 44.6%). Any "what causes them" chart that hides this category overstates what is known.

**Fix.** Always show three bars (human, natural, undetermined) and report shares both with and without the undetermined class. Report by region, never only nationally. Exclude HI and PR from cause analyses (97 to 99% missing). Note the 2020 INTERAGCY break.

### F6. Major: the seasonal and "where" claims mix real seasonality with coverage artifacts

"Large fires starting in the South, especially Texas, in winter" reproduces on Class G counts (REPRODUCTION.md), but Texas contributes 1,040 records in 2004 and 15,019 in 2006. The Texas winter pattern is real (dormant grass, frontal winds) but the map's Texas density is a 2005+ coverage effect. "December fires in Texas" does not reproduce and the 2005 spike coincides with the first year of the TFS compilation. "2010 outlier in the Northeast": the Northeast series is a reporting series (NY 2000 to 2005 ramp; CT zero years). "Arkansas June spike" is a label error (Arizona and Alaska peak in June). The "animated seasonal map" should be restricted to size classes and years where coverage is stable, or built on Class D+ fires only.

### F7. Major: "duration" is the wrong target; the reframed target P(size >= 300 acres) is meaningful but needs covariates to be more than climatology

Script 03 section D, script 04 section D. Among 854,880 fires discovered 2010 to 2020, 12,459 (1.46%) reached 300 acres (class E+) and they hold 93.4% of the acres. Fires of this size are what triggers an ICS-209, extended attack, a Type 3 or higher organisation and, at 5,000 acres, MTBS mapping; "will this ignition escape initial attack and become an extended-attack fire" is a question every duty officer asks. So the target is meaningful to practitioners. The climatology is strong:

| Slice (2010+) | P(>= 300 ac) % |
|---|---|
| Natural cause, West | 4.63 |
| Human cause, West | 1.35 |
| Natural cause, South | 4.03 |
| Human cause, South | 1.04 |
| Alaska, natural | 34.24 |
| Northeast, all | 0.08 |
| West, August discovery | 3.34 (vs 0.50 in January) |
| West, natural, discovered 14:00 hour | 2.65 (vs about 1.0 overnight) |
| Owner BLM / FWS / USFS / PRIVATE | 6.29 / 9.88 / 3.13 / 1.08 |

A model on lat, lon, day of year, cause, owner and discovery hour will reproduce this lookup table and no more. To be useful for a duty officer it must add, at the time and place of discovery: energy release component (ERC) percentile and burning index from gridMET or the nearest RAWS; wind speed and gusts; vapour pressure deficit or relative humidity; 100-h and 1000-h fuel moisture; fuel model (LANDFIRE FBFM40) and canopy cover; slope and aspect; distance to road and to the nearest station (initial-attack access); WUI class (SILVIS) and population density; and days since last rain. Anything with lead time (7-day fire-weather outlook) is a bonus. Agency or suppression capacity can be proxied by reporting agency and by the number of fires already burning in the dispatch zone that day (a count computable from the FPA FOD itself: fires discovered in the same NWCG_REPORTING_UNIT_ID in the prior 7 days is a defensible "resource drawdown" proxy).

Two cautions specific to this target. Final size is not known at discovery for the target definition either: it is the label, which is fine, but the evaluation must be time-split and must report precision at the top of the ranking (fires flagged per real escape), because at a 1.5% base rate an AUC of 0.85 can still mean 20 false alarms per escape. And the label depends on reporting: 300 acres on a Texas ranch reported to NFIRS by a volunteer department is not the same 300 acres as a FIRESTAT record, so the coverage mask from F1 applies to the training set as well.

### F8. Minor: framing and wording

- "the US Forest Service's national record of wildfires": say "a Forest Service compilation of federal, state and local fire reports".
- "38 fields": 37 attributes plus OBJECTID and Shape (REPRODUCTION.md).
- "I filtered around the gaps rather than filling them in": filtering on CONT_DATE removed 26% of 2010+ fires and 88% of Texas; that is not neutral and should be stated as a selection.
- "Fire sizes range from near zero to 662,700 acres": the largest record is the 2017 Starbuck fire in Oklahoma; worth naming because readers assume California.
- "Use the seasonal pattern to pre-position federal and state firefighting resources": pre-positioning is done on 7-day fire-weather outlooks and current ERC, not on a 29-year monthly climatology. Prevention messaging by cause and month is the realistic use (F5, section (d)).

---

## (c) Claims ledger for Part 1 (and the framing sentences that support it)

Verdicts: Supported, Weakened, Refuted, Unverifiable. "Weakened" means the sentence is true under some reading but the README's reading overreaches.

| # | README sentence (Part 1 and framing) | Verdict | Why |
|---|---|---|---|
| 1 | "it felt like the fires kept getting worse. I wanted to find out whether that impression holds up" | Weakened | The data can test "large-fire area in the West is increasing" (yes, F4). It cannot test "worse" as an Angeleno means it (structures, smoke, deaths, severity), and it cannot attribute. Say which question is being answered. |
| 2 | "the US Forest Service's national record of wildfires" | Refuted | It is a compilation of dozens of federal, state and local systems (F1); 75% of records are non-federal. Hosted by the FS, not the FS's record. |
| 3 | "2,303,566 fire records x 38 fields, 1992-2020" | Supported (38 is definitional) | Reproduced; 39 columns including geometry. |
| 4 | "Fire sizes range from near zero to 662,700 acres" | Supported | 0.00001 to 662,700 (Starbuck, OK, 2017). |
| 5 | "the containment date is missing for 894,813 records and the discovery time for 789,095" | Supported, incomplete | Numbers reproduce. Missingness is structured by agency and state (F2): ST/C&L 49.5%, TX 88%, VA 94%; this must be said. |
| 6 | "I filtered around the gaps rather than filling them in" | Weakened | The filter removes a quarter of 2010+ fires, non-randomly (F2). It is a selection, not a neutral filter. |
| 7 | "Are wildfires getting worse?" (Question 1) | Weakened | Answerable only as "is large-fire area increasing", only for area (not counts), and only descriptively. |
| 8 | "What causes them, and where and when do they happen?" (Question 2) | Supported in part | Cause and season are answerable by region with the undetermined class shown (F5). "Where" at the national count level is a coverage map (F1). |
| 9 | "How are landowners responding, and can that response be measured?" (Question 3) | Refuted | Not with this data (F3). CONT_DATE conventions, size mix, cause mix and strategy differ by owner and system. |
| 10 | "For the largest fires (Class G, 5,000 acres and up), acres burned trend upward over the period" | Supported with caveats | tau 0.43 (p 0.0007) all; 0.35 (p 0.007) without Alaska; 0.34 (p 0.009) West. Carried by extreme years (p 0.09 without top 3, non-Alaska). Class G is real (92.5% MTBS-linked). |
| 11 | "with higher highs and higher lows" | Refuted | 2010 (2.14M) is below 1996 (4.28M), 1999 (4.36M), 2000 (5.57M). Highs are higher; lows are not. |
| 12 | "Human-caused fires far outnumber natural ones" | Supported nationally; Weakened by region | 77% vs 14% nationally; West 58% vs 32% with 10% undetermined; Alaska 64% vs 34%. |
| 13 | "natural causes (mostly lightning) account for most of the acreage burned, about 105.6 million acres" | Supported | 105.6M = 58.7% of acres. "Mostly lightning": the Natural class is lightning plus volcanic/other; the data has one Natural code, so "mostly lightning" is an inference, but a safe one. |
| 14 | "Smaller fires (Classes B and C) are most often debris and open burning" | Weakened | Plurality (B 30%, C 26%), with "missing" at 22 to 24% and arson at 15 to 24%. True in the South; in the West the top human cause is undetermined (42%). |
| 15 | "An animated seasonal map shows large fires starting in the South, especially Texas, in winter and shifting to the West and Northwest by summer" | Weakened | Class G seasonality reproduces (South Jan to Apr, West May to Oct). "Especially Texas" is coverage-dependent (1,040 records in 2004; 15,019 in 2006). |
| 16 | "Western fires last the longest, peaking in August" | Weakened | True for the containment-declaration field on the 74% of records that have it; Alaska (13.1 days) beats the West (1.6) if separated; the field is not burn duration (F2). |
| 17 | "a June spike in Class G acreage in Arkansas" | Refuted | Arkansas has 2 Class G fires in 29 years, none in June. Arizona (2.8M acres) and Alaska (22.7M) peak in June. |
| 18 | "December fires in Texas" | Refuted as a pattern | December is among Texas's quietest months; one 2005 event, which is also the first TFS coverage year. |
| 19 | "a 2010 outlier in the Northeast" | Refuted | Not an outlier on counts or acres (z under 1). The Northeast series is a reporting series (NY 2000 to 2005; CT zeros). |
| 20 | "The US Forest Service, the Bureau of Land Management and private landowners account for the most acres burned" | Supported, incomplete | USFS 38.4M, BLM 37.2M, Private 25.6M; fourth is unknown ownership at 22.9M, which should be shown. |
| 21 | "To compare how quickly fires are brought under control, I built a Control Efficiency Score: 1 / (average acres burned per hour until control)" | Refuted as a measure of control | Measures size and cause mix and reporting convention (F3); USFS top 1% of fires carry 97% of the sum; rank flips 16th to 1st on mean vs median. |
| 22 | "It is not fair to rank agencies with that score as it stands. It ignores terrain, elevation, weather and the resources each agency has" | Supported, incomplete | Correct, but the larger omissions are containment-declaration convention, size class, cause, detection lag and managed-fire strategy, none of which terrain data would fix. |
| 23 | "The Forest Service and the BLM manage very different land, so a lower score may reflect steep, remote country rather than a slower response" | Supported in spirit | Also: 53 to 60% of their fires are lightning-caused, 55 to 69% are class A, and they are the only owners with managed natural ignitions. |
| 24 | "Before drawing conclusions from it, I would add terrain, elevation, historical weather and fire perimeter data" | Weakened | Necessary but not sufficient; without a common containment convention and strategy field the comparison cannot be made (F3). |
| 25 | "Use the seasonal pattern to pre-position federal and state firefighting resources" | Refuted as a use | Pre-positioning is driven by short-range fire-weather outlooks and current fuel moisture, which the climatology cannot substitute for. |
| 26 | "time public awareness campaigns to the months and regions where human-caused fires peak" | Supported | The data supports this well: South human ignitions peak in March (17% of the year's human fires) with debris burning at 45%; West peaks in July (19%); Alaska in May (37%). |

---

## (d) Practitioner questions the rebuilt project should answer, ranked

Ranked by (usefulness to a fire manager or conservation planner) x (how well the FPA FOD alone, or with cheap public joins, can support it).

1. **When and where do human ignitions peak, by cause, for prevention messaging?** Fully supported. Human-caused fire counts by region, month and NWCG_GENERAL_CAUSE, 2010 to 2020, on states with stable coverage; show the undetermined share. Deliverable: a prevention calendar (South: debris burning in Feb to Apr; West: equipment and recreation in Jun to Aug; Fourth of July fireworks spike is directly checkable from DISCOVERY_DOY 185 to 186).
2. **What is the probability that a new ignition reaches 300 acres (extended attack), given what is known at discovery?** Supported as climatology now; useful with weather and fuels joins (F7). Deliverable: a calibrated, time-split model with precision-at-top-k, plus a plain lookup table by region x cause x month that a duty officer can read.
3. **Is large-fire area increasing, where, and in which season?** Supported for area, Class D+ or G, by region, with Alaska separate and with an explicit statement that attribution is out of scope. Add MTBS linkage rate as a validity check.
4. **Which weeks of the year carry the most large-fire risk in each region (for planning prescribed-burn windows and staffing)?** Supported: Class E+ discoveries by week and region, with the caveat that it is climatology.
5. **How many ignitions occur on and within 1 km of protected areas, by cause?** Supported with a PAD-US join (lat/lon are section-precise or better for most records; PLSS-section precision means about 1 mile, so use a 2 km buffer and say so). This is the conservation-planner question.
6. **What share of ignitions and of area burned is human-caused near roads and settlements (WUI)?** Supported with a SILVIS WUI join. Useful for planners; state the location precision.
7. **Where does coverage in the FPA FOD itself fail, and which state-years should be excluded?** Supported entirely from the data (F1). Not glamorous, but a coverage map is the single most useful artifact for any downstream user of this dataset, and nobody publishes one.
8. **Which human general causes are growing or shrinking over time?** Partly supported: only within federal reporting agencies or stable-coverage states, and only with the 2020 cause-standard change flagged (the metadata says the cause standard was updated in August 2020; older records were recoded).
9. **How long from discovery to a containment declaration, by reporting system and size class?** Supported only as a descriptive table with the F2 caveats; do not model it and do not call it duration.
10. **How quickly are fires being suppressed, and is it changing?** Not supported. Requires initial-attack response times, strategy and resource data the FPA FOD does not have (ICS-209-PLUS for large fires only).
11. **Are fires getting worse for people (structures, smoke, evacuations, deaths)?** Not supported by this dataset. Say so up front; point to ICS-209-PLUS for structures threatened and destroyed on 209-reported incidents.
12. **Why is large-fire area increasing?** Not supported. Needs weather, fuels, ignition density and policy covariates; out of scope for a descriptive site unless the weather join is done and the claim is kept correlational.

---

## (e) Proposed changes to other files

**README.md**
- Replace "the US Forest Service's national record of wildfires" with "a Forest Service compilation of federal, state and local wildfire reports (the FPA FOD)". Add a "What this data is and is not" paragraph quoting the completeness statement from the metadata (F1) and stating that fire counts are not comparable across years without a coverage mask.
- Rewrite Question 1 as "Is large-fire area increasing, and where?" and Question 3 as a descriptive question about containment reporting, or drop it.
- Replace the Class G sentence with the F4 wording; drop "higher lows"; show Alaska and non-Alaska separately.
- Report cause shares by region with the undetermined class visible (F5 table); state that the national natural-acres figure is a West-plus-Alaska figure.
- Delete the three flagged anomalies (AR June, TX December, NE 2010) and replace with the reporting-break explanation.
- Delete the Control Efficiency Score. If a replacement table is kept, use the F3 stratified table with the reporting-convention caveat.
- Replace "pre-position resources" with prevention messaging by cause and month; keep the awareness-campaign sentence.
- Part 2: stop describing the target as "how long it will burn"; describe CONT_DATE as a containment declaration and note the F2 missingness structure. If the E+ target is adopted, state the base rate (1.46%) and the covariates required (F7).

**scripts/reproduce.py**
- Add a coverage section: state x year counts, break flags (ratio > 3 or < 1/3, zero years), and SOURCE_SYSTEM counts per year, written to `outputs/coverage.json`. Add the Alaska/non-Alaska/West Class G series and the top-3-years sensitivity. Use NWCG_REPORTING_AGENCY, not SOURCE_SYSTEM_TYPE, for any federal/non-federal split (2020 IRWIN break).

**src/data_loader.py and src/features.py**
- If a containment-time analysis survives: load hours, not days; add NWCG_REPORTING_AGENCY and SOURCE_SYSTEM as features or stratifiers; add a `coverage_ok` mask from the reproduce.py coverage table. If the target becomes P(size >= 300), add FIRE_SIZE >= 300 as label, keep FIRE_SIZE_CLASS out of features, and add a "fires in same NWCG_REPORTING_UNIT_ID in prior 7 days" feature.

**docs/review/REPRODUCTION.md**
- Add a line under the "Western fires last longest" row that the field is a containment declaration and that Alaska is not in the 11-state West definition. Add the FS 2015 to 2019 CONT_DATE missingness jump (0.2 to 1.4% then 24 to 30%) to the sample checks.

**docs/EXPERIMENTS.md**
- Record the F3 stratified table as an experiment entry (E-004 candidate) so the score's retirement is on the log. Add a held-out policy note that any time split must also be a coverage-masked split.

**docs/DATA_VERSION.md**
- Note the 2020 SOURCE_SYSTEM change (FS-FIRESTAT and DOI-WFMI replaced by IA-IRWIN) and the August 2020 cause-standard update, both of which affect comparability of the last year.

**Site (new)**
- First page after the headline should be the coverage map (F1, question 7 in section (d)). Every count chart should carry the mask; every cause chart three categories; every containment chart the agency caveat.

---

## Sources fetched in this session

- FPA FOD 6th edition catalog page (DOI target): https://www.fs.usda.gov/rds/archive/Catalog/RDS-2013-0009.6 (https://doi.org/10.2737/RDS-2013-0009.6 redirects here).
- FPA FOD 6th edition FGDC metadata (definitions, completeness, supplemental information): https://www.fs.usda.gov/rds/archive/products/RDS-2013-0009.6/_metadata_RDS-2013-0009.6.html
- File index: https://www.fs.usda.gov/rds/archive/products/RDS-2013-0009.6/_fileindex_RDS-2013-0009.6.html (lists `FPA_FOD_source_list.pdf` and `_variable_descriptions.csv`; direct fetches of both returned 404 in this session, so they are unverified).
- Short, K. C. (2014), A spatial database of wildfires in the United States, 1992-2011, Earth Syst. Sci. Data 6, 1-27: https://essd.copernicus.org/articles/6/1/2014/essd-6-1-2014.pdf (PDF text extracted; quotes above are verbatim from the extracted text, with ligatures normalised).
- Short, K. C. (2015), Sources and implications of bias and uncertainty in a century of US wildfire activity data, Int. J. Wildland Fire: https://connectsci.au/wf/article-lookup/doi/10.1071/WF14190 (abstract page only; the summary returned was paraphrased, so no verbatim quote is used from it).
- NWCG Glossary of Wildland Fire, PMS 205, "out (fire)": https://www.nwcg.gov/publications/pms205/nwcg-glossary-of-wildland-fire-pms-205/out-fire (fetched, verbatim). "containment (wildfire)" and "controlled" entries: URLs listed in F2 returned 404/403; the text used is the search-engine snippet for those URLs and is marked as partly unverified.
