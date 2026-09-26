# Panel review: conservation stakeholder

**Reviewer role:** data lead at a land trust or state natural-resources agency, i.e. the person who would actually be handed this analysis and asked "so what do we do differently?"
**Date:** 2026-09-25. **Data:** `data/fires.parquet` (2,303,566 rows, 1992-2020, same rows as `FPA_FOD_20221014.sqlite`, hash in `docs/DATA_VERSION.md`). Every number below comes from DuckDB or pandas queries run in this session; the query definitions are stated next to each table. Every dataset claim comes from a URL fetched in this session (section e). Scratch figures and CSVs are in `/tmp/claude-0/-home-user-wildfire-analysis/a4df9529-3e52-5fbc-b7e0-fb427368a57f/scratchpad/panel-conservation/`.

---

## (a) Verdict

As it stands, the project does not answer a single question a conservation or land-management user would ask. It is an ignition-point catalogue with a duration model bolted on. Nothing in it links a fire to a protected area, a habitat, a community, a fuel type, or an outcome (severity, structures lost), so nothing in it can change a decision about where to spend prevention money, where to thin, or which easements are exposed. Worse, the two outputs that look decision-shaped (the Control Efficiency Score and the duration model) are the two that must not reach a user: one flips its ranking when the mean is swapped for the median, the other is beaten by "predict zero". The raw data does support useful descriptive facts today, which I produce below with definitions and n. But 46% of records have no land owner, and ownership trends are confounded with reporting-regime changes. The rebuild must lead with joins (PAD-US, MTBS, ICS-209-PLUS, WUI), not with prediction.

---

## (b) Findings

### Critical

**C1. No conservation-relevant join exists, so no output is actionable.**
Evidence: the only spatial or land attributes in the pipeline are `LATITUDE`, `LONGITUDE`, `STATE`, `COUNTY`, `OWNER_DESCR` (owner at the point of origin only, per the RDS-2013-0009.6 metadata: "Name of primary owner or entity responsible for managing the land at the point of origin"). The README's three questions ("getting worse", "causes/where/when", "landowner response") are answered with national aggregates a land manager cannot act on. A manager needs: which of *my* units, which GAP status, which distance to the WUI, what severity, what was lost.
Fix: make the join layer the core deliverable (section e), and gate every published chart on "which decision does this inform?" (section f).

**C2. Ownership is missing for 46.4% of all records and for 41.5% of 2010-2020 records; the gap is not random.**
Evidence (all rows): `OWNER_DESCR = 'MISSING/NOT SPECIFIED'` on 1,068,424 of 2,303,566 (46.4%). By year: 54% in 1992, 27.5% in 2009 (best year), 55.9% in 2018, 41.5% in 2020. By reporter, 2010-2020: non-federal state/county/local systems (`SOURCE_SYSTEM_TYPE='NONFED'`, `NWCG_REPORTING_AGENCY='ST/C&L'`, n=667,295) are 51.7% missing; USFS 2.4%, BLM 0.1%, BIA 0.0%, NPS 0.2%, FWS 0.6%. Missing ownership carries 22.9M acres, the 4th largest "owner" (README lists USFS 38.4M, BLM 37.2M, Private 25.6M and stops). 
Consequence: any federal-vs-private comparison is really "complete federal records vs an unknown subset of non-federal records". The human-caused share of missing-owner fires (95.0% of known-cause) looks like private land (92.0%), so the missing block is mostly non-federal, but it cannot be assigned.
Fix: never present ownership shares without the Missing row. Spatially assign ownership with PAD-US (section e) and report agreement with `OWNER_DESCR` where both exist; that becomes a validation table, not a footnote.

**C3. The two decision-shaped outputs must not ship to a land manager.**
Evidence: REPRODUCTION.md shows the Control Efficiency Score moves USFS from 10th to 1st of 12 when mean is replaced by median, and the RF is 26% worse than "predict 0 days" on MAE and predicts 0.55 days on fires that lasted 0 days. From the user's chair: an agency ranking that depends on the summary statistic is a liability, and a duration predictor that is wrong on the 84% of fires that are out the same day has no field use. The README's "pre-position resources" and "serve predictions through a small API for field use" would be read by an agency as overclaims.
Fix: drop the score. Keep the model only if it is reframed as a classifier for a rare outcome (e.g. P(fire reaches >= 300 acres | discovery attributes)) with calibration and base rates shown, and evaluated on a time split. If it cannot beat a per-cell base rate, publish that as the finding.

### Major

**M1. Ownership categories carry reporting-regime artifacts that would be misread as land-management trends.**
Evidence: `OWNER_DESCR='STATE OR PRIVATE'` is 71,576 rows, of which Texas 42,026 and California 13,134; it totals 8,188 (1992-98), 7,599 (1999-05), 53,040 (2006-12), then 2,749 (2013-20), and its last Texas year is 2014. Texas A&M Forest Service fires >= 300 acres per year: 1 (1992), 45 (1996), 130 (2005), 388 (2006), 485 (2008), 581 (2011), 57 (2012). Private-land ignitions rise from 81,547 (1992-98) to 200,733 (2006-12) while the share >= 300 acres stays flat at 1.1%; that is more reporting, not more fire.
Fix: every ownership-by-time chart must be annotated with reporter entry/exit years, or restricted to reporters present for the whole window (the federal systems, which are stable).

**M2. General cause is missing for about a third of human-caused large fires, which is exactly where prevention targeting needs it.**
Evidence, 2010-2020, `FIRE_SIZE >= 300`, `NWCG_CAUSE_CLASSIFICATION='Human'`: on USFS/BLM/NPS/FWS land, 417 of 1,165 (35.8%) have `NWCG_GENERAL_CAUSE` = Missing; on private land 698 of 2,169 (32.2%). Of the top 20 one-degree cells for human-caused large fires, the modal cause is "Missing" in 9 (all Texas, Kansas, Washington and Missouri/Arkansas cells).
Fix: show "cause known" n on every cause chart; treat Texas/Kansas cause mixes as unknown rather than "debris".

**M3. "Large fire" has no single definition in the project.**
Evidence: README uses Class G (>= 5,000 acres) for the trend claim, REPRODUCTION uses Class G for South/West seasonality, MTBS eligibility is >= 1,000 acres West / >= 500 acres East (mtbs.gov/project-overview, fetched), and a state forester's "large" is often >= 100 or >= 300 acres. This review uses >= 300 acres (classes E, F, G) because that is where ICS-209 reporting becomes common (79.5% of 2010-2020 fires >= 300 acres carry an ICS-209-PLUS id; class D is 33.7%).
Fix: one glossary entry, used everywhere, with the MTBS thresholds noted so users know which "large" fires have severity data.

**M4. `NWCG_REPORTING_UNIT_NAME` is who filed the report, not who manages the land, and the README's "landowner response" framing conflates the two.**
Evidence: Alaska Fire Service (BLM) reports 498 fires >= 300 acres in 2010-2020 across all Alaska ownerships; Texas A&M Forest Service reports 1,481 with 44% missing ownership. Reporting unit is a fine key for "who to talk to about prevention messaging", a poor key for "whose land burned".
Fix: label it "reporting unit" in the UI and never use it as an ownership proxy.

### Minor

**m1. Region definitions are implicit.** REPRODUCTION.md notes "depends on whether Alaska counts as West". Definitions used here are stated under Table C.

**m2. Ignition point precision is good enough for polygon joins, but a point is not a footprint.** Only 1.2% of 2010-2020 records have lat/lon at 2 decimal places or coarser (0.0% at 1 dp). Joining the ignition point to PAD-US or WUI tells you where the fire *started*; only an MTBS perimeter tells you what burned.

**m3. Duplicate MTBS keys.** 13,870 rows carry an `MTBS_ID` but there are 13,292 distinct ids (578 rows share an id, mostly complexes). A one-to-one join will silently double count; join on id then aggregate.

---

## (c) Conservation facts the data supports today

Ownership classes used throughout: **Federal** = USFS, BLM, NPS, FWS, BOR, OTHER FEDERAL, UNDEFINED FEDERAL; **Tribal/BIA** = BIA, TRIBAL; **State**; **Private** (includes the 2 rows spelled "Private"); **State or private** (kept separate because of M1); **County/local** = COUNTY, MUNICIPAL/LOCAL; **Missing**. "Federal conservation lands" below = USFS + BLM + NPS + FWS only. "Large" = `FIRE_SIZE >= 300` acres. "Human share of known cause" = Human / (Human + Natural), excluding `NWCG_CAUSE_CLASSIFICATION` = Missing.

### Table A. Ignitions, acres and large fires by ownership class and period (all causes)

Query: group by class and 7-year period on all 2,303,566 rows.

| Class | Ignitions 1992-98 | 1999-05 | 2006-12 | 2013-20 | M acres 1992-98 | 1999-05 | 2006-12 | 2013-20 | Fires >= 300 ac 1992-98 | 1999-05 | 2006-12 | 2013-20 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Federal | 91,659 | 99,820 | 83,335 | 73,627 | 12.01 | 28.06 | 26.89 | 30.15 | 2,439 | 3,077 | 3,333 | 3,107 |
| Tribal/BIA | 31,742 | 39,494 | 34,454 | 29,302 | 1.12 | 3.76 | 2.61 | 4.57 | 320 | 549 | 570 | 605 |
| State | 5,423 | 12,498 | 20,270 | 18,296 | 0.97 | 4.86 | 4.31 | 4.97 | 228 | 430 | 745 | 660 |
| Private | 81,547 | 126,000 | 200,733 | 189,400 | 2.54 | 3.56 | 8.97 | 10.58 | 918 | 1,361 | 2,267 | 1,991 |
| State or private | 8,188 | 7,599 | 53,040 | 2,749 | 0.38 | 0.85 | 4.22 | 0.34 | 97 | 134 | 1,053 | 82 |
| County/local | 806 | 2,711 | 5,451 | 16,977 | 0.00 | 0.27 | 0.57 | 0.62 | 4 | 40 | 168 | 116 |
| Missing | 263,301 | 291,315 | 248,032 | 265,776 | 4.79 | 5.69 | 5.97 | 6.44 | 1,619 | 2,004 | 1,980 | 1,769 |

Reading: federal ignition counts fall by 20% across the periods while federal acres rise 2.5x. Private and County/local counts rise mostly through reporter entry (M1). Missing is the largest class in every period.

### Table B. Cause by owner, 2010-2020 (n = 854,880 records in the window)

| OWNER_DESCR | n | M acres | Human | Natural | Human % of known cause | Fires >= 300 | Human % of known-cause fires >= 300 | Top named human cause |
|---|---|---|---|---|---|---|---|---|
| MISSING/NOT SPECIFIED | 354,471 | 7.90 | 272,612 | 14,208 | 95.0 | 2,264 | 80.1 | Debris and open burning |
| PRIVATE | 269,676 | 13.72 | 244,674 | 21,173 | 92.0 | 2,923 | 77.5 | Debris and open burning |
| USFS | 62,944 | 19.45 | 29,695 | 32,838 | 47.5 | 1,972 | 32.2 | Recreation and ceremony |
| BIA | 37,327 | 4.06 | 31,804 | 5,249 | 85.8 | 700 | 71.7 | Arson/incendiarism |
| STATE | 28,617 | 6.41 | 23,231 | 4,701 | 83.2 | 937 | 51.9 | Debris and open burning |
| BLM | 24,244 | 13.37 | 10,201 | 13,887 | 42.3 | 1,524 | 27.3 | Equipment and vehicle use |
| TRIBAL | 5,996 | 1.80 | 4,757 | 1,181 | 80.1 | 172 | 35.7 | Arson/incendiarism |
| NPS | 5,886 | 2.05 | 3,275 | 2,574 | 56.0 | 294 | 16.3 | Recreation and ceremony |
| FWS | 4,504 | 5.12 | 2,357 | 1,321 | 64.1 | 445 | 21.6 | Recreation and ceremony |

Grouped: Federal (all federal codes) 49.1% human of known cause and 24.5% of known-cause acres human; Private 92.0% and 67.4%; Tribal/BIA 85.0%; State 83.2%. The conservation-relevant fact: on USFS/BLM land, human ignitions are a minority of starts and about 30% of large fires; on private, state and tribal land they are 3 of every 4 large fires. Prevention messaging has far more leverage off federal land.

Human-caused large fires (>= 300 ac, 2010-2020), general cause mix: federal conservation lands (n = 1,165): Missing 35.8%, Arson 17.0%, Equipment/vehicle 15.8%, Recreation 9.7%, Debris 6.8%, Firearms/explosives 5.9%, Power lines 5.3%. Private (n = 2,169): Missing 32.2%, Arson 21.9%, Debris 18.8%, Equipment/vehicle 15.4%, Power lines 5.2%.

### Table C. Seasonal timing of human-caused ignitions by region, 2010-2020 (counts)

Regions: **West** = WA OR CA ID NV MT WY UT CO AZ NM; **Alaska**; **South** = TX OK AR LA MS AL GA FL SC NC TN KY VA WV; **Midwest/Plains** = ND SD NE KS MN IA MO WI IL IN MI OH; **Northeast** = NY NJ PA CT RI MA VT NH ME MD DE DC. Filter: `NWCG_CAUSE_CLASSIFICATION='Human'`, discovery month.

| Region | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep | Oct | Nov | Dec | Total | Top 3 months (share) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| South | 28,518 | 36,958 | 53,561 | 35,438 | 19,254 | 16,638 | 19,544 | 18,606 | 20,645 | 24,817 | 26,175 | 15,556 | 315,710 | Mar, Feb, Apr (39.9%) |
| West | 4,777 | 5,517 | 10,559 | 14,074 | 18,501 | 25,988 | 33,491 | 23,842 | 17,514 | 11,104 | 6,075 | 3,449 | 174,891 | Jul, Jun, Aug (47.6%) |
| Midwest/Plains | 3,620 | 5,644 | 18,641 | 23,000 | 12,415 | 5,413 | 8,666 | 4,928 | 4,208 | 5,756 | 5,152 | 2,097 | 99,540 | Apr, Mar, May (54.3%) |
| Northeast | 1,362 | 2,173 | 8,557 | 18,908 | 12,380 | 6,867 | 8,069 | 5,490 | 4,930 | 3,303 | 5,670 | 1,533 | 79,242 | Apr, May, Mar (50.3%) |
| Alaska | 2 | 11 | 42 | 364 | 1,145 | 635 | 395 | 246 | 182 | 58 | 18 | 10 | 3,108 | May, Jun, Jul (70.0%) |

Human-caused *large* fires (>= 300 ac) by region: South 3,271 (peak Mar 771, Apr 514, Feb 421), West 2,368 (peak Jul 531, Aug 439, Jun 403), Midwest/Plains 962 (Mar 299, Apr 230), Northeast 69, Alaska 60. So the "campaign month" for human-caused large fires is February-April east of the Rockies and June-August in the West; the South also has a secondary November peak (310). Figure: `fig1_human_ignitions_by_region_month.png` in the scratch dir.

### Table D. Top 20 reporting units by fires >= 300 acres, 2010-2020

| Rank | NWCG_REPORTING_UNIT_NAME | Agency | Fires >= 300 | Human | Natural | M acres | % owner missing | States |
|---|---|---|---|---|---|---|---|---|
| 1 | Texas A & M Forest Service | ST/C&L | 1,481 | 1,071 | 356 | 4.98 | 44 | TX, OK |
| 2 | Alaska Fire Service | BLM | 498 | 46 | 452 | 6.19 | 0 | AK |
| 3 | Oklahoma Division of Forestry | ST/C&L | 483 | 418 | 15 | 1.85 | 16 | AR, OK |
| 4 | Florida Forest Service | ST/C&L | 353 | 218 | 131 | 0.65 | 6 | FL |
| 5 | Osage Agency | BIA | 189 | 181 | 7 | 0.37 | 0 | OK |
| 6 | Boise District | BLM | 171 | 85 | 86 | 0.98 | 0 | NV, ID |
| 7 | Nebraska Forest Service | ST/C&L | 160 | 124 | 34 | 0.36 | 61 | NE |
| 8 | Kentucky Division of Forestry | ST/C&L | 159 | 159 | 0 | 0.10 | 58 | KY |
| 9 | Okmulgee Field Office | BIA | 150 | 150 | 0 | 0.27 | 0 | OK |
| 10 | Twin Falls District | BLM | 146 | 44 | 102 | 1.72 | 0 | ID |
| 11 | Nez Perce - Clearwater National Forests | FS | 138 | 3 | 135 | 0.65 | 0 | ID |
| 12 | Idaho Falls District | BLM | 119 | 57 | 62 | 0.75 | 0 | ID, UT |
| 13 | Elko District Office | BLM | 114 | 23 | 91 | 1.37 | 0 | NV |
| 14 | Spokane District | BLM | 113 | 85 | 26 | 1.33 | 0 | WA |
| 15 | Miles City Field Office | BLM | 110 | 22 | 87 | 0.82 | 1 | WY, MT, SD |
| 16 | Winnemucca District Office | BLM | 109 | 31 | 78 | 1.48 | 0 | NV, OR |
| 17 | Prineville District | BLM | 108 | 56 | 52 | 0.97 | 1 | OR |
| 18 | Alaska State Office | BLM | 107 | 5 | 102 | 2.42 | 0 | AK |
| 19 | Kansas Forest Service | ST/C&L | 106 | 104 | 2 | 0.08 | 89 | NE, KS |
| 20 | Salt Lake Field Office | BLM | 101 | 51 | 50 | 0.42 | 0 | UT |

Note the split: the state units (TX, OK, FL, NE, KY, KS) are human-dominated with poor ownership data; the BLM/FS units are lightning-dominated with complete ownership data. These are two different prevention problems.

### Table E. Where human-caused large fires cluster: top 20 one-degree cells, 2010-2020

Filter: `NWCG_CAUSE_CLASSIFICATION='Human' AND FIRE_SIZE >= 300`, n = 6,761 fires in 720 cells (671 in CONUS). The top 20 cells hold 22.1% of these fires; four reporting units (Texas A&M, Oklahoma Forestry, Osage Agency, Okmulgee FO) file 26.9% of them. Cell = floor(lat), floor(lon), so "36, -97" is the cell 36-37 N, 97-96 W.

| Rank | Cell (lat, lon) | Fires | k acres | States | Modal general cause |
|---|---|---|---|---|---|
| 1 | 36, -97 | 211 | 420 | OK, KS | Debris and open burning |
| 2 | 34, -96 | 185 | 166 | OK | Arson/incendiarism |
| 3 | 35, -97 | 123 | 220 | OK | Debris and open burning |
| 4 | 35, -96 | 120 | 142 | OK | Arson/incendiarism |
| 5 | 37, -83 | 94 | 54 | KY, VA, WV | Debris and open burning |
| 6 | 35, -95 | 78 | 48 | OK, AR | Arson/incendiarism |
| 7 | 35, -102 | 76 | 290 | TX | Missing |
| 8 | 33, -99 | 71 | 97 | TX | Missing |
| 9 | 37, -97 | 56 | 91 | KS | Missing |
| 10 | 36, -84 | 51 | 35 | VA, KY, TN | Debris and open burning |
| 11 | 43, -117 | 50 | 75 | ID | Firearms and explosives use |
| 12 | 36, -85 | 48 | 42 | TN, KY | Arson/incendiarism |
| 13 | 27, -82 | 45 | 43 | FL | Debris and open burning |
| 14 | 37, -84 | 44 | 27 | KY | Debris and open burning |
| 15 | 46, -121 | 43 | 333 | WA | Missing |
| 16 | 33, -104 | 42 | 259 | TX, NM | Missing |
| 17 | 35, -101 | 40 | 288 | TX | Missing |
| 18 | 35, -103 | 40 | 93 | TX | Power generation/transmission/distribution |
| 19 | 36, -93 | 39 | 30 | MO, AR | Missing |
| 20 | 32, -101 | 39 | 135 | TX | Missing |

By state (same filter): TX 1,152 (17.0%), OK 945 (14.0%), CA 465 (6.9%), KS 325 (4.8%), FL 303 (4.5%), ID 269, NM 236, WA 225, MT 217, AZ 195, KY 178, OR 178, UT 164, CO 156, NE 141. Figure: `fig2_human_large_fires_1deg_cells.png`. The actionable reading: the eastern Oklahoma / Cross Timbers block (4 adjacent cells, 639 fires, arson and debris burning) and the Cumberland Plateau (KY/TN/VA, debris and arson, spring) are where human-caused large fires are most concentrated and where cause *is* recorded. The Texas Panhandle cells are as busy but the cause is unknown, so they need data before messaging.

### Table F. Are fires on federal conservation lands getting larger? (USFS + BLM + NPS + FWS, 1992-2020, all causes)

| Period | Ignitions | Fires >= 300 | Fires >= 5,000 | M acres | % >= 300 | % >= 5,000 |
|---|---|---|---|---|---|---|
| 1992-98 | 88,952 | 2,368 | 394 | 11.64 | 2.66 | 0.44 |
| 1999-05 | 90,562 | 2,931 | 707 | 27.26 | 3.24 | 0.78 |
| 2006-12 | 73,786 | 3,137 | 750 | 26.09 | 4.25 | 1.02 |
| 2013-20 | 68,841 | 2,963 | 825 | 28.88 | 4.30 | 1.20 |

Kendall tau on 29 annual values: ignition count -0.56 (p < 0.0001, falling); fires >= 300 +0.03 (p = 0.84, flat); fires >= 5,000 +0.23 (p = 0.08); acres +0.28 (p = 0.033); 90th percentile size +0.31 (p = 0.019); 99th percentile size +0.51 (p = 0.0001). Honest reading: the *number* of large fires on federal conservation land is flat; the *tail* is heavier (the 99th percentile fire grew from about 750-2,400 acres in the 1990s to 4,500-12,800 acres in 2015-2020) and the share of ignitions becoming large has risen from 2.7% to 4.3%, part of which is fewer small fires being recorded. For private land the same test gives ignitions +0.46, fires >= 300 +0.37, acres +0.46 (all p < 0.005) with the share >= 300 flat at 1.1%: that is a reporting story, not a fire story.

### Table G. Join-key coverage in FPA FOD (all 2,303,566 rows)

Definition: key present = not null and not empty string.

| Key | Rows with key | Years present | Coverage where it matters |
|---|---|---|---|
| `MTBS_ID` | 13,870 (13,292 distinct) | 1992-2020 | 2010-2020: 84.2% of fires >= 1,000 ac (5,041 of 5,988); by class F 79.0% (3,042/3,849), G 93.5% (1,999/2,139), E 8.1% (527/6,471), D 0.3%, A-C ~0% |
| `ICS_209_PLUS_INCIDENT_JOIN_ID` | 33,494 | 1999-2020 only (0 before 1999) | 2010-2020: 79.5% of fires >= 300 ac (9,901 of 12,459); class D 33.7% (4,132/12,243); class E 71.1%; F 84.6%; G 95.6% |
| `ICS_209_PLUS_COMPLEX_JOIN_ID` | 5,459 | 1999-2020 | complexes only |

96.6% of `MTBS_ID` values match the pattern `[A-Z]{2}[0-9]{19}` (state + lat + lon + YYYYMMDD, e.g. `CA3850212028020041006` for the 2004 Power fire), the same shape as MTBS Event IDs, so the join is a plain string match. Both keys are populated in the data we already have; the external tables are the only thing missing.

---

## (d) Ranked user questions and answerability

Ranked by how often a land-trust or state-agency data lead is actually asked them.

| # | Question | Status | What it takes |
|---|---|---|---|
| 1 | Which protected areas (or which of *our* units) have the most human-caused ignitions, and in which months? | Answerable with PAD-US | Point-in-polygon of ignition points into PAD-US 4.1 units (Unit_Name, Mang_Name, GAP_Sts); Table C gives the month profile once units are attached. |
| 2 | Are fires on conservation lands getting larger? | Partly answerable now (Table F, using OWNER_DESCR federal codes); properly with PAD-US + MTBS | Table F is by owner-at-origin. To say "on conservation land" you need PAD-US GAP 1-2 polygons and MTBS perimeters for area actually burned inside them. |
| 3 | What share of large fires start within N km of the WUI, and is that share rising? | Answerable with SILVIS WUI | Distance from ignition point to nearest WUI census block (1990/2000/2010/2020 vintages), by year. |
| 4 | Where do ignitions on private land threaten adjacent protected land? | Answerable with PAD-US + MTBS (for the "threaten" part) | Private-origin ignitions within N km of GAP 1-2 polygons; MTBS perimeters show which ones actually crossed. Point data alone cannot show spread. |
| 5 | Which human causes drive large fires on our land type, so what should prevention messaging say? | Answerable now for ~65% of human large fires (M2) | Table B and the cause mix under it; flag the Missing share every time. |
| 6 | How severely did fires burn in habitat we care about (critical habitat, GAP 1-2)? | Answerable with MTBS + USFWS critical habitat | MTBS thematic burn severity rasters clipped to critical habitat polygons; joined back to FPA FOD via MTBS_ID for cause/owner. |
| 7 | What did the fire cost in structures, evacuations and personnel? | Answerable with ICS-209-PLUS 2.0 | 33,494 FPA FOD rows carry the join id; ICS-209-PLUS 2.0 covers 1999-2020 and 34,478 wildfire incidents. |
| 8 | What fuels and vegetation are ignitions landing in, and has that shifted (e.g. cheatgrass conversion in the Great Basin)? | Answerable with LANDFIRE + NLCD | Sample 30 m rasters at ignition points by year; LANDFIRE fuel model and EVT, NLCD class. |
| 9 | Which reporting units should we partner with on prevention? | Answerable now | Table D (with the caveat in M4). |
| 10 | Will this specific new ignition become a large fire? | Not answerable from ignition records (needs weather, fuels, suppression) | The current RF should not be presented as this. A per-cell base rate (share of ignitions reaching 300 acres by cell, month, cause) is the honest floor and is answerable now. |
| 11 | Are prescribed burns or fuel treatments reducing wildfire on our land? | Not answerable from FPA FOD | FPA FOD excludes prescribed fire; needs agency treatment records (FACTS, NFPORS) and a causal design. |
| 12 | How fast do agencies respond and which is "best"? | Not answerable (C3) | The score must not ship. Containment time is confounded by terrain, fuel, access and reporting. |

---

## (e) External datasets for the conservation lens

"Verified" means the URL was fetched in this session and returned the content described. Sizes are as reported by the server or page. Effort assumes one analyst, the existing DuckDB/geopandas stack, and a 15 GB machine.

| Dataset | Landing page (verified) | What it gives | Format / size | License | Join method | Effort |
|---|---|---|---|---|---|---|
| PAD-US 4.1 (USGS GAP) | https://www.usgs.gov/programs/gap-analysis-project/science/pad-us-data-overview (fetched; a curl HEAD returned 403, WebFetch succeeded) and ScienceBase item https://www.sciencebase.gov/catalog/item/652d4fc5d34e44db0e2ee45e (fetched JSON) | Protection status, manager, GAP status 1-4 (1 = permanent natural-state mandate; 2 = permanent, some degrading uses; 3 = extractive uses allowed; 4 = no conversion mandate), easements | National file geodatabase `PADUS4_1Geodatabase.zip` 1,523.4 MB; state downloads also in shapefile, GeoPackage, GeoJSON, KMZ | USGS disclaimer, no fee; page warns it is not authoritative for regulatory use | Point-in-polygon on ignition lat/lon; keep Unit_Name, Mang_Name, Mang_Type, GAP_Sts, Own_Type; compare with OWNER_DESCR where present | 2-3 days (download, dissolve to GAP status, spatial join of 2.3M points in chunks) |
| SILVIS WUI change 1990-2020 (v4, Feb 2025) | https://silvis.forest.wisc.edu/data/wui-change/ (fetched) | WUI intermix ("housing and vegetation intermingle") and interface ("housing in the vicinity of contiguous wildland vegetation") by census block for 1990, 2000, 2010, 2020 | Shapefile by state, file geodatabase for US/CONUS; size not stated on page | Citation required per page; no fee stated | Nearest-WUI-block distance from ignition point, using the census vintage closest to FIRE_YEAR | 2 days (large block polygons; use a spatial index and state-by-state processing) |
| MTBS (burn severity and perimeters) | https://www.mtbs.gov/project-overview (fetched: "all fires 1,000 acres or greater in the western United States and 500 acres or greater in the eastern United States", 1984 to present, 30 m); products at https://www.mtbs.gov/product-descriptions (fetched); downloads moved to https://burnseverity.cr.usgs.gov/products/mtbs (fetched) | Burned area boundaries, thematic burn severity (unburned to high), dNBR/RdNBR rasters, fire occurrence points | Shapefile (perimeters), GeoTIFF (severity mosaics, one per year); sizes not stated on pages | Not stated on pages fetched; US government product | String match FPA FOD `MTBS_ID` to MTBS Event_ID (96.6% of ids match the MTBS pattern); then perimeter-level joins to PAD-US, WUI, critical habitat | 3-4 days (perimeters are fast; severity mosaics are large rasters, process by year) |
| ICS-209-PLUS 2.0 (1999-2020) | https://api.figshare.com/v2/articles/19858927 (fetched: v3, published 2023-01-10, CC BY 4.0, DOI 10.6084/m9.figshare.19858927.v3); older 1999-2014 edition at https://api.figshare.com/v2/articles/8048252 (fetched: v14, CC0, "124,411 reports for 25,083 incidents, including 24,608 wildfires"; the figshare HTML page for this DOI returned 403) | Daily situation reports and incident summaries: structures threatened/destroyed, personnel, evacuations, costs (fields confirmed on the 1999-2014 record; the 2.0 API description lists the sitrep, wildfire incident summary and complex tables plus county/tract/block-group linkage files) | `ics209plus-wildfire.zip` 46.5 MB, `ics209plus-allhazards.zip` 38.6 MB, source 407 MB (CSV inside) | CC BY 4.0 (2.0); CC0 (1.0) | `ICS_209_PLUS_INCIDENT_JOIN_ID` to the incident summary table; 33,494 FPA FOD rows carry the key vs 34,478 wildfire incidents reported for 2.0 by the search summary (unverified count, from search result text) | 1 day; the join is tabular |
| LANDFIRE (fuels, vegetation, disturbance) | https://landfire.gov/data (fetched: LF 2025 Update current, LF 2023/2024 available, 30 m, CONUS/AK/HI full downloads, LFPS REST API, WCS/WMS) | Surface and canopy fuel models, existing vegetation type, annual disturbance | GeoTIFF via full-extent downloads or LFPS area-of-interest; sizes not stated | Not stated on page; USFS/DOI product | Sample raster at ignition points (rasterio), using the LF version closest to FIRE_YEAR; page warns against single-pixel use, so sample a 3x3 or 5x5 window mode | 2 days plus download time (CONUS layers are multi-GB) |
| NLCD / Annual NLCD Collection 1.2 (1985-2025) | https://www.mrlc.gov/data (fetched: six products, 30 m, CONUS; SE Alaska, PR, USVI expected later in 2026) | Annual land cover, land cover change, impervious surface | GeoTIFF; size not stated | Not stated; USGS EROS product | Sample land cover at ignition point for FIRE_YEAR; annual vintages make this the cleanest time-matched layer | 1-2 days |
| USFWS critical habitat (ECOS) | https://ecos.fws.gov/docs/crithab/crithab_all/crithab_all_shapefiles.zip (HEAD 200, application/zip, Content-Range shows 417,703,162 bytes = 417.7 MB) and https://ecos.fws.gov/docs/crithab/crithab_all/crithab_all_layers.zip (HEAD 200); report page https://ecos.fws.gov/ecp/report/critical-habitat loads via JavaScript only; REST endpoint https://ecos.fws.gov/arcgis/rest/services/crithab/usfwsCriticalHabitat/MapServer returned HTTP 500 at fetch time | Final and proposed critical habitat polygons and lines per listed species | Shapefile zip 417.7 MB; geodatabase zip | Not stated on the pages reached; US government product | Point-in-polygon for ignitions; MTBS perimeter overlay for area burned inside critical habitat | 1 day |
| FPA FOD 6th ed. metadata | https://www.fs.usda.gov/rds/archive/products/RDS-2013-0009.6/_metadata_RDS-2013-0009.6.html (fetched) | Field definitions; use constraint "These data were collected using funding from the U.S. Government and can be used without additional permissions or fees." | already in repo | see quote | n/a | done |
| State datasets (optional) | not fetched | e.g. CAL FIRE FRAP perimeters, Texas A&M fire cause detail, state easement registries | varies | varies | varies | only if a state partner asks |

Order of build: ICS-209-PLUS (1 day, tabular, immediately gives outcomes), then PAD-US (the ownership fix for C2), then MTBS perimeters, then WUI, then rasters (LANDFIRE, NLCD, critical habitat) as a second phase.

---

## (f) Dashboard and site requirements from a user's chair

**Landing page must show, above the fold:**
1. One sentence on what the data is (ignition records, 1992-2020, from FPA FOD 6th edition) and one on what it is not (no perimeters, no prescribed fire, no severity, no losses unless the join layer says so).
2. A data-completeness strip that is always visible: records in view, % with known owner, % with known cause, % with MTBS severity, % with ICS-209 outcomes. If a filter drops any of these below a threshold (say 70%), the strip turns amber and says so.
3. The four descriptive facts that are solid today: human-caused share by ownership (Table B), seasonal timing by region (Table C), the human-caused large-fire cluster map (Table E), the federal tail-size trend (Table F), each with n and definition on hover.
4. A glossary link: "large fire" (>= 300 acres, with the MTBS threshold noted), region membership, ownership classes, and the "Missing" rules.

**Filters that matter (in this order):** state; ownership class (with Missing selectable and on by default); cause classification, then general cause; year range (with a note when a reporter enters or exits the window, per M1); size class (A-G, plus a ">= 300" and ">= MTBS threshold" shortcut); once joined, GAP status, WUI distance band, and "has MTBS severity / has ICS-209 outcome".

**Map aggregation that is honest:** hexagonal or square bins with the count and the underlying n shown on hover and in the legend (as in `fig2`), with a minimum-count rule (cells under 5 fires drawn hollow or grey, never colored). Bins should be selectable at two scales (1 degree and roughly 25 km). Ownership from PAD-US should be a separate layer, not blended into the ignition color. No kernel-density heat maps: they hide n, spread Oklahoma's 211-fire cell into neighbouring empty cells, and a manager cannot audit them.

**What must not be shown:**
- Any duration or size prediction without the base rate next to it (P(>= 300 ac) by cell, month and cause) and without a calibration plot on a time-split test set.
- Agency or owner rankings on response speed or "efficiency" (C3). If a containment-time view is kept, it must be stratified by size class and region and labelled descriptive.
- Ownership pie charts with Missing removed.
- Trend lines for state, county/local, private or "State or private" ownership that cross a reporter entry or exit year without the break marked.
- Cause shares for Texas, Kansas or any state where general cause is Missing for more than a third of human-caused large fires, unless "cause known n" is on the chart.
- The animated seasonal map unless each frame shows n; a frame with 12 fires and a frame with 1,200 must not look the same.

**Export:** every chart offers CSV of its aggregated rows with the definition string embedded in the header. A land-trust analyst will re-run it against their own boundaries; make that easy rather than making the map prettier.

---

## (g) Proposed changes to other files

- **README.md**: remove "How are landowners responding, and can that response be measured?" as a headline question, or reword to "What the ignition record can and cannot say about land ownership". Add the Missing ownership row (22.9M acres, 46.4% of records) wherever USFS/BLM/private acres are listed. Replace "USFS, BLM and private landowners account for the most acres burned" with the same statement plus "and unknown ownership is fourth". Delete "pre-position federal and state firefighting resources" and "serve predictions through a small API for field use". Add a glossary with the "large fire" definition and region membership.
- **scripts/reproduce.py**: add the Table A, B, C, F and G computations as named functions so the conservation facts regenerate with the README numbers; include the ownership-missing-by-year and reporter-entry checks (M1) as printed warnings.
- **src/data_loader.py**: expose a loader that does not filter on `CONT_DATE`, so descriptive work does not inherit the 26% model-sample drop; add an option to load `data/fires.parquet` instead of SQLite.
- **docs/EXPERIMENTS.md**: before any new model run, add an entry that records the per-cell, per-month, per-cause base rate of reaching 300 acres on a 2010-2016 train / 2017-2020 test split, so the next model has a floor to beat.
- **docs/DATA_VERSION.md**: add a "Join keys" section with the Table G coverage numbers and the MTBS Event ID pattern, so the next person knows the keys are populated before downloading anything.
- **New file (proposed, not written): `docs/DATA_JOINS.md`**: the dataset table in section (e) with the verified URLs, to be updated as each join lands.
- **scripts/download_data.py**: add optional fetchers for ICS-209-PLUS 2.0 (46.5 MB) and the ECOS critical habitat shapefile zip (417.7 MB), with SHA-256 recorded in `data.sha256`.
