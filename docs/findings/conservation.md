# Conservation lens: coverage mask, ICS-209-PLUS outcomes, PAD-US protected areas

**Produced by:** `python -m analysis.conservation --out outputs/` (about 4 minutes on 4 CPUs the first time, including
the 190 s spatial join; 50 s afterwards from the cached join). External inputs come from
`python scripts/download_external.py` and are documented, with hashes, in `docs/DATA_JOINS.md`.
**Outputs:** `outputs/claims_conservation.json` (77 claims, same schema as `outputs/claims.json`, claim ids prefixed
`coverage.`, `ics.`, `padus.`), `outputs/coverage.json`, `outputs/coverage_state_year.csv`,
`outputs/ics209_fires_joined.csv`, `data/external/padus/fires_padus.parquet`, and five figures in `outputs/figures/`.
**Data:** FPA FOD 6th edition (Short 2022), 2,303,566 records, 1992-2020; ICS-209-PLUS 2.0 (St. Denis et al. 2023),
34,622 wildfire incidents 1999-2020; PAD-US 4.1 Vector Analysis file (USGS GAP 2024), 324,733 polygons over CONUS,
Alaska and Hawaii. Every number below is a claim id in `claims_conservation.json`; the site should render from that
file, not from this text.

Definitions used throughout: **large fire** = `FIRE_SIZE >= 300` acres (classes E, F, G; `conservation.large_fire_definition`).
**Owner classes** (`conservation.owner_class_definition`): Federal = USFS BLM NPS FWS BOR OTHER FEDERAL UNDEFINED FEDERAL;
Tribal/BIA = BIA TRIBAL; State; Private; State or private (kept separate, it is a Texas/California reporting artefact);
County/local = COUNTY MUNICIPAL/LOCAL; Missing. **Human share of known cause** = Human / (Human + Natural).
**Regions** as in `analysis/common.py`. **GAP status** (PAD-US metadata, quoted in `docs/DATA_JOINS.md`): 1 managed for
biodiversity with natural disturbance, 2 managed for biodiversity with disturbance suppressed, 3 multiple use with
extraction allowed, 4 no known biodiversity mandate; **none** = the "Non-PAD-US Area" fill polygons of the Vector
Analysis file (mostly private land); **unmatched** = points in no polygon (Puerto Rico and 25 stray coordinates).

## 1. Coverage mask: which state-years can carry a count trend

Module `analysis/coverage.py` (also runs standalone: `python -m analysis.coverage --out outputs/`, 5 s).

**Rule** (`coverage.rule`). For each state, the yearly record count is compared with the most recent earlier year that
had records. A year is a **break** when the ratio is above 3 or below 1/3 and the larger of the two counts is at least
30 (the floor keeps DC, DE and RI from tripping on single-digit counts). Zero-count years are flagged separately and are
never usable. A break year starts a new reporting regime, so runs are cut before every break year and at every zero
year; the **usable window** is the longest run (ties go to the most recent one), and `coverage_ok(state, year)` is true
inside it. The function `coverage_ok` in the module looks the rule up on the CSV.

| Claim | Value |
|---|---|
| `coverage.n_states` / `coverage.n_states_ge_1000_records` | 52 STATE values; 48 with at least 1,000 records |
| `coverage.n_states_with_break` / `coverage.n_states_ge_1000_with_break` | 33 states have at least one break; 30 of the 48 with 1,000+ records (the same 30 the fire panel found with its unfloored rule) |
| `coverage.n_break_state_years` | 96 state-years flagged |
| `coverage.states_with_interior_zero_years` | CT (2013, 2014), DC, DE, MA (2011), PR (1995, 1999-2001), RI (13 years), VT |
| `coverage.share_records_in_usable_window` / `coverage.share_acres_in_usable_window` | 86.4% of records and 94.4% of acres lie inside a usable window |
| `coverage.window_length_years` | median window 24 years; 18 states have the full 29 years (CA GA NC AZ FL OK OR WA AK and others); 5 states have fewer than 10 |
| `coverage.federal_agency_break_years_1992_2019` | no break in the national series of FS, BLM, BIA, NPS or FWS, 1992-2019 |

Windows that matter (`coverage.usable_window_by_state`, `coverage.break_years_by_state`): TX 2008-2020 (breaks 1997 x0.27,
2001 x0.29, 2005 x6.6, 2008 x3.3: the Texas A&M compilation ramps in over 2005-2008); NY 1997-2020; KS 1994-2012 then
breaks in 2013, 2014, 2015 (x100), 2016, 2019 (x0.03), 2020 (x8); LA 2012-2020 after eight breaks; TN 2005-2020; MA
1992-2001 (2015 is a x362 jump); HI 2001-2012 (coverage ends 2013); AL 1994-2016; CO 1992-2011 (2012 x0.15, 2013 x3.5).

**The 2020 source switch** (`coverage.ia_irwin_switch_2020`). In 2020 `SOURCE_SYSTEM_TYPE` goes from FED 12,630 /
INTERAGCY 63 (2019) to FED 921 / INTERAGCY 19,413, because FS-FIRESTAT and DOI-WFMI were replaced by IA-IRWIN as the
source. `NWCG_REPORTING_AGENCY` is preserved: FS has 5,425 records in 2019 and 6,677 in 2020, and the IA code has only
11 records in 2020 (21,842 in earlier years). Any series by source-system type breaks at 2020; series by reporting
agency do not.

**What the masked national series looks like** (`coverage.national_fires_by_year_all_vs_masked`). The all-states count
peaks at 117,943 in 2006; inside usable windows the same year has 95,770 records from 43 states, and 2019 has 51,931
of 63,557 from 37 states. The masked series is still not a national series, because the set of contributing states changes by year;
the honest uses of the mask are per-state trends and "which states to drop" for a pooled analysis.

Figure `coverage_state_year.png`: state x year heatmap of log counts, breaks marked with x, usable window outlined,
grouped by region.

## 2. ICS-209-PLUS outcomes: structures, personnel, cost, evacuations

**Join** (`ics.*`). FPA FOD `ICS_209_PLUS_INCIDENT_JOIN_ID` matched to `INCIDENT_ID` in the ICS-209-PLUS 2.0 wildfire
incident summary table: 33,494 FPA FOD rows carry the key, 33,476 match, 29,921 distinct incidents (complexes join many
FPA FOD fires to one incident, up to 57). Match rate 2010-2020 by size class (`ics.match_rate_by_size_class_2010_2020`):
A 0.2%, B 0.3%, C 1.3%, D 33.7%, E 71.1%, F 84.6%, G 95.5%. By year, the share of fires >= 300 acres with a matched
incident is 42% in 1999, 64% in 2005, 71% in 2010, 82% in 2015 and 84% in 2020 (`ics.match_rate_by_year`), so
outcome coverage improves through the window and early years are thinner. Two
consistency checks: the largest joined FPA FOD fire is the one ICS-209-PLUS names in `LRGST_FOD_ID` for 99.97% of
incidents (`ics.largest_fod_id_agreement`); ICS `FINAL_ACRES` is within 25% of the summed FPA FOD size for 88.6% of
incidents, median ratio 1.00 (`ics.final_acres_vs_fod_acres`). Cause agrees where both sources record one: 98.5% of
23,144 incidents (`ics.cause_agreement_share`); but ICS-209-PLUS records "Unknown" for 3,825 incidents the FPA FOD
calls Human and 773 it calls Natural (`ics.cause_agreement_all_matched`), so the FPA FOD cause is the better field.

**Sample** (`ics.sample_definition`): one row per incident, FPA FOD attributes from the largest joined fire, FIRE_YEAR
2010-2020, FIRE_SIZE >= 300 acres: **n = 9,609** incidents, 70.8M FPA FOD acres. Field fill in the sample
(`ics.field_fill_rates_sample`): structures destroyed and fatalities 100% (zeros included, so a missing report cannot be
told from a true zero), projected cost 88%, peak personnel 87%, structures threatened 47%, evacuation flag 41%, peak
evacuations 14%.

### Table 1. Outcomes by cause classification, 2010-2020, fires >= 300 acres (`ics.outcomes_by_cause`)

| Cause (FPA FOD) | Incidents | M acres | Structures destroyed | Share of incidents with any loss | Structures per 1,000 acres | Peak personnel, median | Projected cost, $bn (n) | Fatalities |
|---|---|---|---|---|---|---|---|---|
| Human | 4,904 | 23.5 | 45,784 | 17.1% | 1.95 | 30 | 8.46 (4,258) | 200 |
| Natural | 4,172 | 41.4 | 10,459 | 7.7% | 0.25 | 47.5 | 9.24 (3,760) | 55 |
| Cause missing | 533 | 5.8 | 10,163 | 27.4% | 1.74 | 76 | 1.77 (484) | 28 |
| All (`ics.outcomes_total`) | 9,609 | 70.8 | 66,406 | 13.6% | 0.94 | 39 | 19.46 (8,502) | 283 |

Human-caused large fires burn a third of the acres but destroy 69% of the structures and account for 71% of the
fatalities; per acre burned they destroy structures at eight times the rate of lightning fires. The 533 incidents with
no cause classification carry 15% of the losses, which is the prevention-relevant gap M2 of the panel review in its
sharpest form.

### Table 2. Outcomes by owner class and by region (`ics.outcomes_by_owner_class`, `ics.outcomes_by_region`)

| Group | Incidents | M acres | Structures destroyed | Share with any loss | Structures per 1,000 acres | Projected cost, $bn | Fatalities |
|---|---|---|---|---|---|---|---|
| Federal | 3,988 | 39.7 | 38,891 | 9.9% | 0.98 | 12.27 | 171 |
| Private | 2,165 | 10.7 | 12,435 | 17.8% | 1.16 | 2.98 | 35 |
| Missing | 1,325 | 5.1 | 3,164 | 13.7% | 0.62 | 0.95 | 45 |
| State | 813 | 6.0 | 2,954 | 11.6% | 0.50 | 1.06 | 8 |
| Tribal/BIA | 703 | 5.4 | 2,229 | 14.4% | 0.41 | 1.45 | 5 |
| State or private | 455 | 3.0 | 5,678 | 22.4% | 1.87 | 0.57 | 9 |
| County/local | 160 | 0.8 | 1,055 | 26.9% | 1.25 | 0.19 | 10 |
| West | 5,055 | 46.2 | 57,787 | 17.3% | 1.25 | 18.15 | 247 |
| South | 3,097 | 10.4 | 7,517 | 9.4% | 0.72 | 0.55 | 31 |
| Alaska | 786 | 12.5 | 284 | 3.9% | 0.02 | 0.64 | 0 |
| Other | 589 | 1.5 | 779 | 17.3% | 0.51 | 0.11 | 5 |
| Northeast | 58 | 0.07 | 20 | 5.2% | 0.31 | 0.005 | 0 |
| Hawaii/PR | 24 | 0.07 | 19 | 12.5% | 0.27 | 0.004 | 0 |

"Owner" is the owner at the ignition point of the largest joined fire, not where the structures stood: 58% of
structures destroyed sit on incidents whose ignition point is federal land (the Camp Fire's origin is coded USFS), which
says where large destructive fires start, not who lost the buildings. The West holds 87% of structures destroyed and
87% of fatalities; the South has a third of the incidents and 11% of the structure loss. Structures destroyed by
region and cause: West Human 38,441, Natural 9,774, missing 9,572; South Human 6,568 (`ics.structures_destroyed_by_region_cause`).

**Distribution** (`ics.structures_destroyed_distribution`): 86.4% of sample incidents destroyed no structure; 3.8%
destroyed 10 or more, 0.8% 100 or more, 0.12% (12 incidents) 1,000 or more. Percentiles: p90 = 1, p95 = 6, p99 = 68,
p99.9 = 1,384, max 18,804 (Camp Fire). The top 10 incidents hold 52% of all structures destroyed and the top 25 hold 68%.
Loss is a tail phenomenon: a mean per incident is meaningless, and any model of "structures at risk" is a model of
a few dozen events.

**Top 25 by structures destroyed** (`ics.top25_structures_destroyed`, `ics.top25_composition`): 15 of 25 are in
California, 3 in Oregon, 3 in Colorado; 14 Human, 5 Natural, 6 cause missing; 14 have a federal ignition owner.
Camp 2018 (18,804; power lines; Human; 85 fatalities), Chimney Tops 2  2016 TN (2,066; misuse of fire by a minor),
North Complex 2020 (2,342; Natural), Valley 2015 (1,958), Bastrop County Complex 2011 TX (1,709; power lines),
Woolsey 2018 (1,643), Carr 2018 (1,604; equipment), Glass 2020 (1,520; equipment), CZU August Lightning 2020 (1,490;
cause missing in FPA FOD), LNU Lightning Complex 2020 (1,479), Beachie Creek 2020 OR (1,323), Thomas 2017 (1,063),
Almeda Drive 2020 OR (700 structures on 3,200 acres; arson; municipal land). Power lines cause 309 sample incidents
but 22,781 structures destroyed, 12.5 per 1,000 acres, thirteen times the sample rate (`ics.outcomes_by_general_cause`).

**Evacuations** (`ics.evacuations_by_form_era`): the ICS-209 form changed in 2014. For 2010-2013 there is a yes/no
flag on every incident: 436 of 3,422 (12.7%) reported evacuations. For 2014-2020 there is a peak count, present only
when reported: 561 of 6,187 incidents (9.1%) have a positive count, summing to 1.66M person-evacuations (peak per
incident, so repeated evacuations of the same people are not de-duplicated). The two eras must not be pooled.

Figure `ics_structures_by_year_cause.png`: structures destroyed per year by cause (2018 = 24,091; 2020 = 17,632).

## 3. PAD-US protected areas: where ignitions land

**What was joined and how** (`padus.source`, `padus.join_definition`). The PAD-US 4.1 national geodatabase and the
state downloads are behind a ScienceBase login (details in `docs/DATA_JOINS.md`), so the join uses the PAD-US 4.1
**Vector Analysis file**, which USGS built from the same Combined Fee/Designation/Easement feature class by resolving
overlaps with the GAP-priority rule the brief asked for. The ignition point of every record was projected to the
layer's Albers CRS and joined with `sjoin(predicate='within')` in 250k-point chunks. Because the layer is a flat
partition, each point falls in exactly one polygon and `n_overlaps` is 1 everywhere (`padus.match_summary`): 2,281,339
of 2,303,566 points matched, 638,049 inside a PAD-US unit, 1,643,290 in Non-PAD-US Area, 22,227 unmatched (22,202 of
them Puerto Rico, which the file does not cover).

### Table 3. Ignitions and acres by GAP status at the ignition point (`padus.by_gap_all_years`, `padus.by_gap_2010_2020`)

| GAP status | Fires 1992-2020 | Share | Acres | Share | Human share of known cause | Fires >= 300 | Share of fires >= 300 | Fires 2010-2020 | Share | Acres 2010-2020 share | Human share 2010-2020 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 43,762 | 1.9% | 27.8M | 15.4% | 33.8% | 2,698 | 8.5% | 12,070 | 1.4% | 15.5% | 35.4% |
| 2 | 63,304 | 2.7% | 12.8M | 7.1% | 70.7% | 2,330 | 7.4% | 19,965 | 2.3% | 6.7% | 73.5% |
| 3 | 297,578 | 12.9% | 57.4M | 31.9% | 48.0% | 7,945 | 25.1% | 93,673 | 11.0% | 29.7% | 53.2% |
| 4 | 233,405 | 10.1% | 24.5M | 13.6% | 85.8% | 5,093 | 16.1% | 77,461 | 9.1% | 13.5% | 87.2% |
| none (not in PAD-US) | 1,643,290 | 71.3% | 57.4M | 31.9% | 93.4% | 13,543 | 42.8% | 647,227 | 75.7% | 34.6% | 93.5% |
| unmatched | 22,227 | 1.0% | 0.14M | 0.1% | 99.4% | 57 | 0.2% | 4,484 | 0.5% | 0.0% | 99.6% |

Reading. GAP 1 and 2 land, the land managed for biodiversity, receives 4.6% of ignitions but 22.5% of acres burned;
GAP 1 alone has 1.9% of ignitions and 15.4% of acres, and the share of its ignitions that become large is 6.2%
(8.1% in 2010-2020), against 0.8% on land outside PAD-US (`share_ge_300_within_gap`). The human share of known-cause
ignitions rises monotonically from GAP 1 (34%) through GAP 3 (48%) and GAP 4 (86%) to non-PAD-US land (93%); GAP 2 is
the exception at 71%, because GAP 2 includes small refuges, state wildlife areas and recreation areas near people.
Over 5-year blocks (`padus.share_fires_by_block_gap`, `padus.share_acres_by_block_gap`) the ignition share outside
PAD-US rises from 65% (1992-1996) to 77% (2017-2020), which is the non-federal reporting growth of section 1, not a
shift in fire; the acre shares are flat within noise (GAP 1: 10%, 15%, 18%, 16%, 15%, 16%).

Human-caused ignitions on GAP 1-2 land in 2010-2020 (`padus.general_cause_share_gap12_2010_2020`, n = 32,035 all
causes): Natural 39.5%, cause missing 17.0%, recreation and ceremony 11.8%, arson 9.3%, equipment 8.0%, debris 6.9%.
Among the 1,780 large fires on GAP 1-2 land, Natural is 65.9% and cause missing 15.0%.

### Table 4. Top units by human-caused ignitions, 2010-2020 (`padus.top25_units_human_ignitions_2010_2020`)

n = 130,810 human-caused ignitions inside PAD-US units 2010-2020, in 12,268 distinct unit names; the top 25 hold 30.4%.
**39.2% of them fall in tribal reservations and Oklahoma Tribal Statistical Areas** (`Des_Tp` TRIBL, GAP 4), which
PAD-US carries from the Census and which include private land inside the boundary; they are jurisdictions, not
conservation units. The table below is the all-units ranking; `padus.top25_nontribal_units_human_ignitions_2010_2020`
and `padus.top25_gap12_units_human_ignitions_2010_2020` give the non-tribal and the GAP 1-2 rankings.

| Rank | Unit (Mang_Name, state) | GAP | Human ignitions | Human >= 300 ac | Peak month (share) | Top general cause |
|---|---|---|---|---|---|---|
| 1 | Choctaw Oklahoma Tribal Statistical Area (TRIB, OK) | 4 | 5,375 | 277 | Mar (23%) | Arson |
| 2 | Red Lake Reservation (TRIB, MN) | 4 | 4,143 | 15 | Apr (46%) | Arson |
| 3 | Cherokee Oklahoma Tribal Statistical Area (TRIB, OK) | 4 | 3,751 | 112 | Mar (24%) | Arson |
| 4 | Pine Ridge Reservation (TRIB, SD) | 4 | 2,371 | 17 | Jul (26%) | Missing |
| 5 | Spirit Lake Reservation (TRIB, ND) | 4 | 1,958 | 1 | Apr (31%) | Arson |
| 6 | Morley Nelson Snake River Birds of Prey NCA (BLM, ID) | 2 | 1,769 | 25 | Jul (33%) | Equipment and vehicle use |
| 7 | San Carlos Reservation (TRIB, AZ) | 4 | 1,514 | 8 | May (26%) | Missing |
| 8 | Hoopa Valley Reservation (TRIB, CA) | 4 | 1,421 | 1 | Jul (23%) | Arson |
| 9 | State Trust Land (SDOL, AZ NM) | 4 | 1,381 | 49 | May (18%) | Missing |
| 10 | White Earth Reservation (TRIB, MN) | 4 | 1,298 | 4 | Apr (52%) | Arson |
| 11 | Navajo Nation Reservation (TRIB, AZ NM) | 4 | 1,233 | 6 | Jun (23%) | Debris and open burning |
| 12 | Crow Reservation (TRIB, MT) | 4 | 1,091 | 10 | Jul (27%) | Missing |
| 13 | Yakama Nation Reservation (TRIB, WA) | 4 | 1,083 | 19 | Jul (39%) | Debris and open burning |
| 14 | Osage Reservation (TRIB, OK) | 4 | 1,081 | 181 | Mar (28%) | Debris and open burning |
| 15 | Standing Rock Reservation (TRIB, ND SD) | 4 | 1,062 | 8 | Jul (31%) | Missing |
| 16 | Tonto National Forest (USFS, AZ) | 3 | 1,005 | 15 | May (22%) | Missing |
| 17 | Blackfeet Indian Reservation (TRIB, MT) | 4 | 993 | 4 | Jul (35%) | Fireworks |
| 18 | Creek Oklahoma Tribal Statistical Area (TRIB, OK) | 4 | 970 | 159 | Mar (29%) | Missing |
| 19 | Coconino National Forest (USFS, AZ) | 3 | 961 | 7 | Jun (20%) | Recreation and ceremony |
| 20 | Cheyenne River Reservation (TRIB, SD) | 4 | 928 | 7 | Jul (30%) | Equipment and vehicle use |
| 21 | Deschutes National Forest (USFS, OR) | 3 | 926 | 2 | Jul (25%) | Recreation and ceremony |
| 22 | Rosebud Indian Reservation (TRIB, SD) | 4 | 901 | 6 | Jul (30%) | Arson |
| 23 | Turtle Mountain Reservation (TRIB, ND) | 4 | 879 | 0 | Apr (36%) | Debris and open burning |
| 24 | Wind River Reservation (TRIB, WY) | 4 | 844 | 3 | Jul (30%) | Debris and open burning |
| 25 | Washington State Department of Natural Resources (SDNR, WA) | 3 | 835 | 4 | Jul (28%) | Recreation and ceremony |

Non-tribal ranking, top 10: Morley Nelson Snake River Birds of Prey NCA (1,769, GAP 2, July, equipment), State Trust
Land AZ/NM (1,381), Tonto NF (1,005), Coconino NF (961), Deschutes NF (926), Washington DNR (835), Mark Twain NF MO
(801, March, arson), Sitgreaves NF (705), San Bernardino NF (616), Kisatchie NF LA (491, March, arson). The national
forests of the interior West peak in May-August on recreation; the southern and Ozark forests peak in March on arson.
GAP 1-2 ranking, top 5: Morley Nelson (1,769), Gateway NRA NY/NJ (205), Benson County Waterfowl Production Area ND
(162), Honobia Creek WMA OK (161), Lake Mead NRA (120). By manager (`padus.human_ignitions_by_manager_2010_2020`):
TRIB 51,325, USFS 31,277, BLM 11,970, state DNRs 4,285, SFW 3,525, NPS 3,170, FWS 2,848.

### Table 5. Validation: FPA FOD owner at origin against PAD-US manager type at the point (`padus.owner_vs_mang_type_row_shares`)

n = 1,234,700 ignitions with a recorded OWNER_DESCR that fell in a polygon. Percent of row.

| OWNER_DESCR class (n) | FED | TRIB | STAT | LOC | DIST | NGO | PVT | JNT | UNK | Not in PAD-US | Consistent (`padus.owner_agreement_by_class`) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Federal (348,120) | 85.1 | 1.0 | 1.5 | 0.2 | 0.1 | 0.2 | 0.0 | 0.1 | 0.2 | 11.7 | 85.1% |
| Tribal/BIA (134,988) | 2.9 | 93.1 | 0.4 | 0.2 | 0.0 | 0.0 | 0.0 | 0.0 | 0.1 | 3.2 | 93.1% |
| State (56,453) | 5.4 | 3.4 | 33.4 | 1.2 | 1.4 | 0.5 | 0.2 | 0.1 | 2.3 | 52.1 | 33.4% |
| Private (597,619) | 2.4 | 4.5 | 1.8 | 0.4 | 0.1 | 0.6 | 0.1 | 0.1 | 0.2 | 89.7 | 90.4% |
| State or private (71,575) | 10.2 | 0.9 | 2.2 | 0.4 | 0.1 | 0.4 | 0.0 | 0.0 | 0.2 | 85.4 | 88.1% |
| County/local (25,945) | 3.9 | 4.3 | 3.6 | 11.0 | 0.4 | 0.3 | 0.0 | 0.0 | 0.7 | 75.6 | 11.5% |

Consistent = FED for Federal, TRIB for Tribal, STAT for State, LOC or DIST for County/local, PVT/NGO/Not in PAD-US for
Private; pooled agreement 84.8% (`padus.owner_agreement_overall`). At agency level
(`padus.agency_exact_agreement`, `padus.agency_vs_mang_name_counts`): USFS 90.6%, NPS 88.3%, BIA 93.7% (PAD-US codes
tribal land TRIB), BLM 83.8%, FWS 68.1% (2,790 of 13,620 FWS-owner ignitions fall outside any PAD-US polygon), BOR 27.7%.
Where the two disagree, the pattern is one-directional: 11.7% of federal-owner ignitions and 52% of state-owner ignitions
fall on land PAD-US does not inventory. Some of that is location precision (a section-precise point on a boundary), some is
PAD-US completeness for state land, and some is OWNER_DESCR meaning "protecting agency" rather than "landowner". A
site should present ownership from PAD-US and OWNER_DESCR side by side, never as a single merged field.

**What PAD-US assigns where OWNER_DESCR is missing** (`padus.missing_owner_assignment_all_years`,
`padus.missing_owner_assignment_2010_2020`). Of the 1,046,639 missing-owner records that fell in a polygon, 91.0% are
in Non-PAD-US Area (94.4% in 2010-2020), 2.6% on state-managed land, 2.4% tribal, 1.8% federal, 0.9% local, 0.5% NGO.
By acres: 75.7% not in PAD-US, 8.5% state, 7.8% federal, 4.3% tribal. By GAP status
(`padus.missing_owner_by_gap_all_years`): 952,244 none, 48,484 GAP 4, 28,231 GAP 3, 14,565 GAP 2, 3,115 GAP 1. The
missing block is filed almost entirely by state and local systems (ST/C&L 1,038,856 of 1,046,639,
`padus.missing_owner_by_reporting_agency_and_mang_type`). So the 46% ownership gap is resolvable in the aggregate: the
missing-owner records are overwhelmingly on land that PAD-US does not inventory, which in the United States is
predominantly private, and the 9% that fall in a PAD-US unit can be given the unit's manager. The fix should be
labelled "PAD-US manager at the ignition point", not "owner".

Figures: `padus_gap_by_block.png` (ignition and acre shares by GAP status per 5-year block), `padus_top_units.png`
(Table 4 as bars, coloured by GAP status), `padus_owner_agreement.png` (Table 5 as a row-normalised matrix).

## 4. Caveats

- **Point, not footprint.** Every PAD-US attribute is the polygon under the ignition point. A fire that starts on
  private land and burns into a wilderness is counted as "none". Acres "by GAP status" are the acres of fires that
  started there, not acres burned inside that status; only MTBS perimeters can give the latter.
- **Location precision.** The FPA FOD inclusion rule requires a point at least as precise as a PLSS section (1 square
  mile), and the metadata warns of "inaccuracies and imprecision inherent in the original datasets". A section-precise
  point near a unit boundary can land on either side. The panel found 1.2% of 2010-2020 records at 2 decimal places or
  coarser. For small units and for any per-unit count near a boundary, treat counts as approximate; a 1-2 km buffer
  analysis is the natural next step.
- **Flattened layer.** The Vector Analysis file resolves overlaps by GAP priority, then public access, then load order.
  A point in a wilderness inside a national forest is attributed to the wilderness (GAP 1), which is what the brief asked
  for; a point in an easement over private land is attributed to the easement. The original overlap multiplicity is not
  recoverable from this file, so `n_overlaps` is uninformative.
- **Tribal areas.** PAD-US includes reservations and Oklahoma Tribal Statistical Areas from the Proclamation feature
  class; they are large, contain private inholdings and non-trust land, and dominate any per-unit count. They are
  reported because they are in the data, with the non-tribal ranking alongside.
- **Coverage.** Puerto Rico and the territories are not in the Vector Analysis extents. Coverage of the FPA FOD itself
  varies by state-year (section 1); the 5-year-block ignition shares in Table 3 move with reporting, not with fire.
- **ICS-209-PLUS.** Incidents are reported when they are large or complex enough to warrant a 209, so the matched set is
  biased to large and long fires; 20% of 2010-2020 fires >= 300 acres have no incident. Complex-level totals are split
  evenly across member incidents (fractional counts). "Zero values included" for structures and fatalities means a
  non-report reads as zero. Structures threatened is a per-incident maximum, not a distinct count. Evacuation reporting
  changed in 2014. `PROJECTED_FINAL_IM_COST` is an estimate filed on the last report, not an audited cost. Owner and
  cause come from the largest joined FPA FOD fire, which is the ICS-209-PLUS convention (`LRGST_FOD_ID`) and matched it
  99.97% of the time.
- **Cause.** The FPA FOD cause of the largest fire is used everywhere; ICS-209-PLUS `CAUSE` is "Unknown" for 16% of
  incidents the FPA FOD classifies as Human or Natural. The 2020 cause-standard change flagged by the fire panel applies.
- **Nothing here is causal.** Higher human shares on GAP 4 land and higher losses on human-caused fires describe where
  people and fires meet; they do not say that protection status changes ignition risk.

## 5. Proposed changes to other files

- **README.md**: add a "What this data can now say" paragraph: ignitions can be placed in PAD-US units and GAP status
  (99% matched), large-fire outcomes exist for 80% of 2010-2020 fires >= 300 acres via ICS-209-PLUS, and the ownership
  gap is resolved in the aggregate (91% of missing-owner records are outside PAD-US). State the point-not-footprint
  caveat next to every PAD-US number. Add the coverage mask as the first artifact and link `outputs/coverage_state_year.csv`.
- **.gitignore**: add `data/external/` (about 1 GB after extraction) and keep `docs/DATA_JOINS.md` as the record of
  what is there. Alternatively commit `data/external/padus/fires_padus.parquet` (14.5 MB) so the site can be built without
  the 900 MB PAD-US download; if so, add its hash to `data.sha256`.
- **docs/DATA_VERSION.md**: add a "Join keys" section pointing to `docs/DATA_JOINS.md`, and record that
  `ICS_209_PLUS_INCIDENT_JOIN_ID` matches 33,476 of 33,494 rows against ICS-209-PLUS 2.0 v3.
- **analysis/common.py**: move `OWNER_CLASS`, `OWNER_CLASS_ORDER`, `LARGE_ACRES` and `BLOCKS` from
  `analysis/conservation.py` into common so the descriptive module and the site share them.
- **scripts/reproduce.py**: no change needed; the conservation numbers regenerate from `analysis.conservation`.
- **docs/review/panel-conservation.md** (not edited): its Table G numbers are confirmed here (33,494 rows with the ICS
  key; 79.5% of 2010-2020 fires >= 300 acres matched); its "2-3 days" estimate for PAD-US was pessimistic because the
  Vector Analysis file removes the dissolve step.
- **Site**: a conservation page should render from `claims_conservation.json` with these claim ids and figures:
  coverage (`coverage.*`, `coverage_state_year.png`), outcomes (`ics.outcomes_by_cause`, `ics.outcomes_by_owner_class`,
  `ics.outcomes_by_region`, `ics.structures_destroyed_distribution`, `ics.top25_structures_destroyed`,
  `ics_structures_by_year_cause.png`), protected areas (`padus.by_gap_all_years`, `padus.by_gap_2010_2020`,
  `padus.top25_units_human_ignitions_2010_2020` and the two alternative rankings, `padus.owner_vs_mang_type_row_shares`,
  `padus.missing_owner_assignment_all_years`, `padus_gap_by_block.png`, `padus_top_units.png`,
  `padus_owner_agreement.png`). Every PAD-US chart needs the "ignition point, not footprint" note and every ICS chart
  the "ICS-209 incidents only" note in its footer.
