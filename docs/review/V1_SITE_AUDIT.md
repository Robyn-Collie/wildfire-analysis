# Audit of the first public site (us-wildfires.netlify.app)

**Scope.** The first public version of this project is an Astro site deployed as the Netlify project `us-wildfires`. Its source is not in this repository, so it was audited from the published pages and the data files they load (`/data/national_annual.json`, `trend_stats.json`, `seasonality.json`, `points-v2.json`, the point binaries). Each analysis was then rebuilt here from the original sources, its published numbers were replicated, and the claims were tested more strictly. Version 2 of the site (`scripts/build_site.py`, `scripts/site_v2.py`) carries the result. The site's own summary of this document is `site/audit.html`.

**Standard.** A claim holds if it replicates and survives the stricter test. It is revised if it replicates but the stricter test changes the number or the wording it supports. It is corrected if it is wrong as published.

## Summary

| # | Claim on the first site | Verdict | Evidence |
|---|---|---|---|
| 1 | Era comparisons of fire counts on the Map page ("fewest fires of any era", national count "falls to ~300,000 in 2017-2020") | Corrected | Unequal eras; counts carry reporting breaks |
| 2 | "Fewer fires, not smaller ones" and other count trends | Corrected | `outputs/coverage.json`: 30 of 48 states with 1,000+ records have a reporting break |
| 3 | Drought model skill "+17.1% vs climatology" (leave-one-year-out) | Revised | Replicates exactly; forward-in-time test gives 14.7% (`drivers.forward_cv`) |
| 4 | Per-state drought correlations; Arizona and Nevada fuel-limited | Holds | Replicates exactly; survives the coverage mask (`drivers.spearman_usable_only`) |
| 5 | The 100 largest fires | Corrected | 100 rows are 92 incidents (`incidents.row_top100_duplicates`) |
| 6 | "The highs are higher. So are the lows." (NIFC 1983-2025) | Holds, with a caveat | Replicates exactly; floor shift 2.34x becomes 2.02x without 1983-1985 (`nifc.floor_shift_sensitivity_drop_1983_85`) |
| 7 | Home page "density / heat field" | Replaced | A smoothed surface hides n; v2 draws every point and counts on click |
| 8 | "Every number on this page is audited" | Replaced | Numbers now link to ledger entries, and `tests/test_site_claims.py` checks every one against the ledger |

## 1. Era comparisons of fire counts

The Map page compared eras of the FPA FOD by total fire count: California had its "fewest fires of any era" in 2017-2020, and the national count "falls to ~300,000" in that era. The last era has four years (2017-2020) and the others five, so its total is about a fifth lower for that reason alone. Counts are also exposed to reporting breaks (item 2).

**v2.** Counts are shown per year and only inside each state's usable reporting window (`analysis/coverage.py`). The state briefs report "fires a year" over that window.

## 2. Count trends

The FPA FOD compiles federal, state and local reporting systems. Systems joined and left in different years. The coverage mask flags a break when a state's count changes by more than 3x against its previous non-zero year. 30 of the 48 states with at least 1,000 records have at least one break: Texas goes from 1,040 records in 2004 to 15,019 in 2006, New York from 129 in 1994 to 7,700 in 2005. A national or state count trend across those years measures reporting.

**v2.** Count trends are tested only inside usable windows (`places.state.*`, `trend_fires`). National trends use acres (NIFC and FPA FOD) and fires of 5,000+ acres, which every system reports.

## 3. Drought model skill

The first site fitted pooled OLS of log10(acres + 1) on z-scored May-October PDSI, temperature and precipitation (NOAA nClimDiv, state level) with state fixed effects, for 38 states in 1992-2020, and reported leave-one-year-out (LOYO) out-of-sample R² 0.711 and a 17.1% "reduction in prediction error versus a same-state climatology baseline".

**Replication.** `analysis/drivers.py` rebuilt the panel from the NOAA files and the FPA FOD. All 45 published numbers match (`drivers.v1_replication`), including the coefficients (PDSI -0.1013, temperature +0.0915, precipitation -0.0617) and the per-state R² values. The 17.1% is a reduction in mean squared error on the log10 scale, with each state's median log acres from the training years as the baseline. An exact match needs the z-scores recomputed from the training fold inside each LOYO split.

**Stricter tests** (`docs/findings/nifc_and_drivers.md`):

| Test | State-years | Skill (MSE) | OOS R² |
|---|---|---|---|
| LOYO, all years (v1) | 1,102 | 17.1% | 0.711 |
| Forward in time, 2005-2020 | 608 | 14.7% | 0.690 |
| LOYO, usable years only | 883 | 21.9% | 0.788 |
| Forward in time, usable years only | 513 | 9.8% | 0.730 |

- LOYO trains on years after the test year. Fitting only on earlier years lowers skill to 14.7%, and 5 of 16 test years are worse than the baseline.
- 11 of the 20 largest LOYO misses (55%) fall in state-years outside the usable window, against 19.9% of all rows. Three of the five misses the first site featured (Kansas 1992, Nebraska 1993, Kentucky 1993) are reporting breaks. Pennsylvania 1993 and 1995 are inside Pennsylvania's window.

**Verdict: revised.** Seasonal climate explains a real but modest share of year-to-year burned area: 10-20% of the squared error left after knowing a state's usual year, depending on the test. The site shows all four numbers.

## 4. Per-state drought correlations

Spearman rho between May-October PDSI and log10 acres, 1992-2020, for 38 states with 25+ years and more than 50,000 acres. The median rho is -0.45 and 15 states are at or below -0.5. Colorado is -0.72, Arizona -0.18 (p 0.36) and Nevada +0.13 (p 0.50). All replicate. On usable years only (36 states with 15+ usable years), the median is -0.48 and Colorado -0.62. Arizona and Nevada are unchanged and still not significant. South Carolina loses significance and Virginia gains it.

**Verdict: holds.** The fuel-limited reading of the desert Southwest is kept: there, wet winters grow the fine fuel that carries the next fire.

## 5. The 100 largest fires

The first site listed the 100 largest FPA FOD records. A complex managed as one incident appears as several records, so the list repeats incidents:

- August Complex 2020: DOE (#3) and HOPKINS (#26)
- East Amarillo Complex 2006: HWY 152 (#10) and I-40 (#13)
- Rodeo-Chediski 2002: RODEO (#49) and CHEDISKI (#80)
- Taylor Complex 2004: #11, #27, #40
- Central Complex 2004: #58, #77, #86
- Solstice Complex 2004: #17, #25

100 rows are 92 incidents, and the list understates complexes: the August Complex is 1,031,896 acres as an incident against 589,368 for its largest record.

**v2.** `analysis/incidents.py` groups records sharing an ICS-209 complex id, an ICS-209 incident id, or a year, state and complex name. Membership is transitive. MTBS perimeter ids are deliberately not used: in the 2008 northern California lightning siege, chaining through MTBS_ID merged four complexes and 107 records. The East Amarillo Complex groups to 907,245 acres, the published figure for that incident. A rule to drop "the same fire reported twice" was tried and dropped, because it flagged the I-40 and HWY 152 fires, which are distinct. The `largest.html` page lists the component fires and the largest single record beside each sum.

## 6. "The highs are higher. So are the lows."

`analysis/nifc.py` re-fetched the NIFC Wildfires and Acres table (1983-2025) and matched all 20 published numbers, and the cached v1 data file differs from the fresh fetch in no year.

| Test | Result |
|---|---|
| Era floor, 1983-1999 vs 2000-2025 | 1.15M vs 2.69M acres, 2.34x |
| Rolling 11-year minimum, Kendall tau vs centre year | 0.51 (p = 0.0001) |
| Rolling 11-year 10th percentile | 0.73 (p = 2e-8) |
| Floor shift starting in 1986 (1983-1985 dropped) | 2.02x |
| FPA FOD annual acres, floor 1992-1999 vs 2000-2020 | 2.02M vs 3.53M, 1.75x (r = 0.99 with NIFC, so not independent) |

The two lowest years are the first two, 1983 and 1984, whose fire counts (18,229 and 20,493 against 70,000-90,000 later) suggest incomplete reporting.

**Verdict: holds, with the caveat stated.** This differs from the FPA FOD Class G series (fires of 5,000+ acres), where 2010 is the fifth-lowest of 29 years and the lows do not rise (`class_g.five_lowest_years`). The two statements are about different series and both appear on the Trend page.

## 7. Density heat field

A kernel-smoothed surface shows where fires are dense but not how many sit under each colour, and its bandwidth changes the picture. v2 draws every fire as a point with WebGL (`scripts/site_assets/console.js`, data from `scripts/build_points.py`), lists the count for the current filters, and gives the counts in a small square around any point on click.

## 8. "Every number on this page is audited"

The errors above passed an audit that a reader could not repeat. In v2:

- every number is a ledger claim with a definition, an n and a source, one click away;
- `tests/test_site_claims.py` checks every such number on every generated page against the ledger at the precision it is written;
- `tests/test_claims_ledger.py` does the same for the README.

## What carries over, with credit

- the NIFC national series and its era table;
- the drought analysis and the fuel-limited reading;
- a point map of every fire;
- the literature framing;
- the practice of featuring corrections.
