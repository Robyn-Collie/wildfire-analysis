# NIFC national totals and drought drivers: replication and stress test

**Produced by:** `python -m analysis.nifc --out outputs/` (about 3 seconds) and `python -m analysis.drivers --out outputs/` (about 17 seconds).
**Outputs:** `outputs/claims_nifc.json` (17 claims), `outputs/claims_drivers.json` (16 claims), plus the raw and parsed source data listed under Sources below.
**Verdict scale:** same as the other findings docs. Supported (the recomputed number matches v1), Weakened (the direction holds but is smaller or noisier than claimed), Refuted (the opposite or nothing), Reframed (real but described the wrong way).

## Part 1: NIFC "Wildfires and Acres" national annual totals

### What was fetched

The NIFC statistics page (`https://www.nifc.gov/fire-information/statistics/wildfires`) was fetched fresh on 2026-09-26 and parsed with `pandas.read_html`. It is a single Year/Fires/Acres table, 1983 to 2025 (43 rows), with one footnote: 2004 acres exclude North Carolina state lands. The raw HTML and parsed CSV were cross-checked row by row against the v1 site's own cached copy at `https://us-wildfires.netlify.app/data/national_annual.json` (key `nifc`). Result: **0 differences across all 43 years**, so the page has not changed since v1 built its site, and the two 2025 and 2024 rows that v1 highlighted (77,850 fires / 5,131,474 acres and 64,897 fires / 8,924,884 acres) are exactly what is on NIFC's page today.

### Replication: every v1 NIFC number

All 20 checked items matched (see `nifc.v1_replication` for the full item-by-item table). None needed a variant or a different definition; the v1 methodology reproduces exactly from a fresh fetch.

| v1 claim | v1 value | Recomputed | Match |
|---|---|---|---|
| Era table 1983-1999 (n=17) | min 1.15, p25 1.83, median 2.72, p75 4.07, max 6.07 | identical to 2 dp | Yes |
| Era table 2000-2025 (n=26) | min 2.69, p25 4.78, median 7.29, p75 8.89, max 10.13 | identical to 2 dp | Yes |
| Floor / median / ceiling shift | x2.35 / x2.68 / x1.67 | x2.34 / x2.68 / x1.67 | Yes |
| Mann-Whitney early vs modern | p = 1e-5 | p = 1.04e-5 | Yes |
| Theil-Sen slope | +1.41M acres/decade, CI 0.81-2.13 | +1.41M acres/decade, CI 0.81-2.12 | Yes |
| Kendall tau | 0.44, p 2.7e-5 | 0.444, p 2.71e-5 | Yes |
| Rolling p10, centre 1988 -> 2020 | 1.32 -> 4.66M | 1.32 -> 4.66M | Yes |
| Rolling p90, centre 1988 -> 2020 | 4.62 -> 10.12M | 4.62 -> 10.12M | Yes |
| Years over 10M acres | 2015 10.13M, 2017 10.03M, 2020 10.12M | same three years, same values | Yes |
| 2023 | 2.69M acres | 2.69M acres | Yes |
| 2025 | 77,850 fires, 5,131,474 acres | identical | Yes |
| 2024 | 64,897 fires, 8,924,884 acres | identical | Yes |
| 1983 / 1984 fire counts | 18,229 / 20,493 | identical | Yes |

### Stricter tests of "the lows rose too"

v1's version of this claim rested on two numbers: the era-table floor (min 1.15M vs min 2.69M) and the two rolling-p10 endpoints (1.32M at the 1988-centred window, 4.66M at the 2020-centred window). Both are real, but they are two-point comparisons. Four stricter checks:

1. **Five lowest years.** 1984 (1.15M), 1983 (1.32M), 1998 (1.33M), 1993 (1.80M), 1989 (1.83M). All five of the lowest years are in the 1983-1999 half; the most recent low (1998) is still 27 years old. No year since 1999 has come close to the old floor.
2. **Trend test on the rolling minimum and rolling p10, not just two windows.** Kendall tau of the 11-year rolling minimum against its window's centre year is 0.51 (p = 0.0001); for the rolling p10 it is 0.73 (p = 1.8e-8). Both are clearly positive and significant, so the floor is rising as a trend, not just at the two centre years v1 quoted.
3. **Sensitivity: drop 1983-1985.** These are the three earliest Situation-Report-era years and include the two anomalously low fire-count years (1983, 1984) that v1 itself flags as separately suspect. Recomputing the 1983-1999 era on 1986-1999 only raises its floor from 1.15M to 1.33M acres, which **weakens** the floor shift from x2.34 to x2.02 (median shift from x2.68 to x2.61). The claim survives, but part of the original x2.34 headline number was carried by exactly the two years v1 flagged as possibly unreliable.
4. **Cross-check against FPA FOD, 1992-2020 overlap.** NIFC and FPA FOD annual acres correlate at Pearson r = 0.99, Spearman rho = 0.98 over the 29 overlapping years (FPA FOD acres run 66% to 106% of NIFC's total, median ratio about 0.97), so FPA FOD is not an independent check, it is the same national total measured through a different, less complete reporting system. Even so, FPA FOD shows the same floor rise: min acres 2.02M (1992-1999) vs 3.53M (2000-2020), a x1.75 shift.

**Verdict (`nifc.lows_verdict`):** "The lows rose too" is Supported as a trend (Kendall tau positive and significant on both the rolling minimum and rolling p10) but Weakened as a two-point headline: about 13% of the original x2.34 floor shift depends on the 1983-85 window, and NIFC's own reporting-agency footnote (2004 excludes North Carolina) is a reminder that even this "clean" national series has had at least one known accounting change.

## Part 2: State-level drought/climate drivers of FPA FOD acres

### Data and verification

State-level May-Oct mean PDSI, average temperature and precipitation come from NOAA nClimDiv (doi:10.7289/V5M32STR), fetched fresh from `https://www.ncei.noaa.gov/pub/data/cirs/climdiv/` by listing the directory for the current filenames (`climdiv-pdsist-v1.0.0-20260904`, `climdiv-tmpcst-v1.0.0-20260904`, `climdiv-pcpnst-v1.0.0-20260904`). The NCEI state-code table (codes 001-048 alphabetical Alabama through Wyoming, 049 Hawaii, 050 Alaska) was checked against the STATE CODE TABLE in the freshly fetched `state-readme.txt`: all 50 codes used in this project matched with 0 mismatches. FPA FOD annual acres are the sum of FIRE_SIZE by state and year, 1992-2020, with zero-fire state-years set to 0 acres. Alaska and Hawaii climate divisions are not present in these particular statewide files, so those two states drop out of the analysis on their own (all-missing PDSI). That leaves the 48 contiguous states, matching v1's population.

### Replication: every v1 drivers number

All 45 checked items matched (`drivers.v1_replication`). The exact methodology that reproduces v1's numbers:

- log10(acres + 1), not log10(acres).
- Per-state z-scoring of each climate predictor (subtract that state's own mean, divide by its own sample standard deviation, ddof = 1), not a pooled z-score across all state-years. A pooled z-score gives very different coefficients (temperature dominates at +0.47 instead of +0.09); the per-state version is what v1 used.
- For the reported model coefficients, the per-state z-score is computed once over the full 29-year window.
- For the leave-one-year-out (LOYO) cross-validation, the per-state z-score is recomputed from the training years only in each fold (no leakage from the held-out year into its own standardization). This is what reproduces the exact per-state OOS R2 numbers and the exact worst-misses list; using the full-sample z-score inside CV gives close but not exact numbers (for example CA 0.483 instead of 0.480, and NJ instead of WA at rank 10).
- The 17.1% "skill vs climatology" figure is **1 minus MSE_model / MSE_climatology on the log10 scale**. The RMSE-based version of the same idea gives about 9%, so MSE is the metric v1 used.

| v1 claim | v1 value | Recomputed | Match |
|---|---|---|---|
| Qualifying states (>=25 yrs, >50k acres) | 38 | 38 | Yes |
| Median per-state Spearman rho | -0.45 (-0.446) | -0.446 | Yes |
| States with rho <= -0.5 | 15 | 15 | Yes |
| CO / SD / GA / TN / ND / FL | -0.724 / -0.655 / -0.654 / -0.645 / -0.608 / -0.599 | identical to 3 dp | Yes |
| NJ / AR / NC / LA / CA / NM | -0.559 / -0.553 / -0.548 / -0.530 / -0.51 / -0.52 | identical | Yes |
| WY / ID / UT / AZ (p 0.36) / NV (p 0.50) | -0.46 / -0.33 / -0.28 / -0.177 / +0.13 | identical, p = 0.357 / 0.501 | Yes |
| LOYO OOS R2 | 0.711 | 0.711 | Yes |
| Skill vs climatology (MSE) | +17.1% | +17.1% | Yes |
| z-coefficients (PDSI, temp, precip) | -0.1013, +0.0915, -0.0617 | -0.1013, +0.0915, -0.0617 | Yes |
| Top-10 per-state OOS R2 | CA .480, CO .386, SD .379, MT .313, WY .282, TX .247, GA .216, OR .213, TN .204, WA .203 | identical to 3 dp | Yes |
| Bottom-5 per-state OOS R2 | OK -.098, NV -.163, SC -.302, MO -.324, MS -.625 | identical to 3 dp | Yes |
| Worst misses (actual vs predicted acres) | KS 1992 251 vs 16,116; NE 1993 173 vs 6,262; PA 1995 51 vs 1,721; PA 1993 40 vs 1,320; KY 1993 843 vs 26,393 | 251.6 vs 16,117; 173.5 vs 6,262; 51.2 vs 1,722; 40.8 vs 1,321; 843.1 vs 26,394 | Yes |

### Stricter test 1: Spearman restricted to usable (non-break) state-years

Using only state-years inside each state's reporting-coverage usable window (analysis.coverage) and requiring at least 15 usable years drops the qualifying set from 38 to 36 states (some states such as LA, PA, TX, NE lose their earliest 1990s years to reporting breaks and fall below the 15-year threshold; a few others such as IL, OH gain entry because their whole usable window is inside 1992-2020). Median rho moves from -0.446 to -0.475, slightly stronger, not weaker. Colorado moves from -0.724 (all years) to -0.615 (usable years only), still clearly the strongest drought signal in the panel. Arizona and Nevada are unchanged: AZ -0.177 in both versions, NV +0.13 in both versions; neither crosses into significance.

Two states change status between the all-years and usable-only tables:

| State | rho, all years | p, all years | rho, usable only | p, usable only | What changed |
|---|---|---|---|---|---|
| SC | -0.404 | 0.030 | -0.366 | 0.135 | loses significance |
| VA | -0.302 | 0.111 | -0.583 | 0.011 | gains significance |

No state flips sign. The Colorado/drought and Arizona-Nevada/fuel-limited stories both survive coverage restriction; South Carolina's significant-looking rho in the all-years table appears to be partly a reporting-window artifact.

### Stricter test 2: forward-in-time (expanding window) test instead of LOYO

LOYO lets the model see 28 of 29 years, including years both before and after the held-out year, when it fits each state's climatology and standardization. A genuine forecast only has the past. Fitting on all years before Y and predicting Y, for each Y from 2005 to 2020:

- **Overall:** OOS R2 0.690, skill vs climatology (MSE) 14.7%, a relative drop of about 14% from LOYO's 17.1%.
- **By year**, skill ranges from -41.6% (2009, a year the model does markedly worse than same-state climatology) to +37.4% (2020). Eleven of the sixteen years have positive skill; five years (2008, 2009, 2010, 2014, 2015) are net negative. (Corrected in review: an earlier draft of this file said nine and four.)

| Year | Skill (MSE) | OOS R2 |
|---|---|---|
| 2005 | 29.2% | 0.568 |
| 2006 | 21.6% | 0.385 |
| 2007 | 36.0% | 0.731 |
| 2008 | -8.3% | 0.563 |
| 2009 | -41.6% | 0.242 |
| 2010 | -9.8% | 0.561 |
| 2011 | 33.3% | 0.741 |
| 2012 | 36.8% | 0.722 |
| 2013 | 9.7% | 0.834 |
| 2014 | -19.1% | 0.535 |
| 2015 | -4.0% | 0.627 |
| 2016 | 11.7% | 0.742 |
| 2017 | 12.4% | 0.762 |
| 2018 | 16.8% | 0.792 |
| 2019 | 12.5% | 0.750 |
| 2020 | 37.4% | 0.832 |

LOYO's 17.1% headline overstates how well this model would have done as a real forecasting tool in real time; some of that number comes from a held-out year sharing its state-level climatology baseline with 28 other years, including future ones, which a genuine forecast never has.

### Stricter test 3: LOYO and forward tests repeated on the coverage-masked panel

Dropping unusable (reporting-break) state-years before fitting, instead of after, changes the picture:

| Test | Rows | OOS R2 | Skill (MSE) |
|---|---|---|---|
| LOYO, unmasked | 1,102 | 0.711 | 17.1% |
| LOYO, coverage-masked | 883 | 0.788 | 21.9% |
| Forward, unmasked | 608 | 0.690 | 14.7% |
| Forward, coverage-masked | 513 | 0.730 | 9.8% |

LOYO improves on the masked panel: once known reporting-break years are removed, the remaining, more reliable state-years are easier to predict from their own climate (OOS R2 rises from 0.711 to 0.788). The forward test's OOS R2 also rises (0.690 to 0.730) but its MSE-based skill number falls (14.7% to 9.8%), because the climatology baseline's own MSE shrinks even more than the model's once unreliable years are removed. Both readings say the same underlying thing: unreliable reporting years, not the climate model, are responsible for a real share of the "error" in the unmasked numbers.

### Stricter test 4: do the worst misses cluster in reporting breaks?

Of v1's five named worst misses, three (KS 1992, NE 1993, KY 1993) fall in state-years outside that state's reporting-coverage usable window; two (PA 1995, PA 1993) are inside the usable window (Pennsylvania's whole 1992-2020 series is thin and hard to predict for other reasons). Across the fuller top-20 miss list from this run's LOYO fit, **55% of the worst 20 misses are unusable state-years**, versus **19.9% of all 1,102 rows** in the panel, a 2.8x over-representation.

**Verdict (`drivers.verdict`):** the core drought story and the model's headline skill number both replicate exactly and mostly survive stricter testing. What is weaker than the v1 write-up implies: the LOYO cross-validation flatters the model relative to a genuine forward-in-time forecast (17.1% vs 14.7% skill, and negative skill in 5 of 16 forward-test years), and a meaningful share of the model's apparent error, especially its very worst misses, is reporting-coverage noise rather than a climate-model failure.

## Sources

- National Interagency Coordination Center, "Wildfires and Acres", `https://www.nifc.gov/fire-information/statistics/wildfires`, accessed 2026-09-26. Raw HTML saved to `data/external/nifc/wildfires_2026-09-26.html` (sha256 `91d1baa33c1c227624dbcd2d2cad1b4b80ff75e08805c7720f9ed36ad97f5533`). Parsed table: `data/external/nifc/nifc_annual.csv`. Public domain (U.S. government work).
- v1 cross-check snapshot: `https://us-wildfires.netlify.app/data/national_annual.json` (key `nifc`), fetched 2026-09-26; 0 differences against the freshly fetched NIFC table.
- NOAA nClimDiv, statewide monthly PDSI/temperature/precipitation, doi:10.7289/V5M32STR, `https://www.ncei.noaa.gov/pub/data/cirs/climdiv/`, fetched 2026-09-26:
  - `climdiv-pdsist-v1.0.0-20260904` (sha256 `f182d76631c6fa35e637cc4bd6597ffbb07cb14b9f749469527f23b1ccaed802`)
  - `climdiv-tmpcst-v1.0.0-20260904` (sha256 `eba0699e448cb01a531462dbdb81a46015b44ae05d473b4e6124c5a5d6c50d28`)
  - `climdiv-pcpnst-v1.0.0-20260904` (sha256 `56b67e12075a65213d7a2cbaf39ef3ba0cee25dd84f562cd767e27bdcd39c60b`)
  - `state-readme.txt` (format spec and STATE CODE TABLE, used to verify the state-code mapping)
- FPA FOD 6th edition (Short 2022), `V2/data/fires.parquet`, read via `analysis.common.load_fires`.
- Reporting-coverage mask: `outputs/coverage.json` and `outputs/coverage_state_year.csv` (analysis.coverage).

## Files produced by this work

- `analysis/nifc.py`, `analysis/drivers.py`
- `data/external/nifc/wildfires_2026-09-26.html`, `data/external/nifc/nifc_annual.csv`
- `data/external/nclimdiv/climdiv-pdsist-v1.0.0-20260904`, `climdiv-tmpcst-v1.0.0-20260904`, `climdiv-pcpnst-v1.0.0-20260904`, `state-readme.txt`
- `outputs/claims_nifc.json` (17 claims), `outputs/claims_drivers.json` (16 claims)
- `docs/findings/nifc_and_drivers.md` (this file)
