# Findings: state briefs and the prevention calendar

**Produced by:** `python -m analysis.places --out outputs/` (about one minute). This needs `outputs/coverage_state_year.csv`; the PAD-US join and ICS-209-PLUS are optional.

**Claims:** `outputs/claims_places.json`:

- one `places.state.XX` per state, 52 in all;
- `calendar.*`;
- `places.acres_trend_summary`;
- `places.window_lengths`.

**Tables** (`outputs/tables/`):

- `places_summary.csv`;
- `state_year.csv`;
- `calendar_regions.csv`;
- `calendar/XX.csv`: month x general cause for each state, usable window.

**Site:** `places.html`, `place-XX.html` and the calendar section of `causes.html`.

## Rule used throughout

Counts are taken only inside each state's usable reporting window, from `analysis/coverage.py`. That window is the longest run of years with no reporting break. Outside it, a change in the count of fires can mean a reporting system joined or left.

Shares and rates are computed inside the same window, because a new system usually adds many small fires and dilutes them. Acres are shown for every year. Years outside the window are drawn in grey and left out of the trend test.

## Prevention calendar (usable state-years)

- **People start most fires, but not most of the area in large ones.**
  - Human causes are 80% of fires with a known cause.
  - They are 47% of fires that reached 300 acres.
  - They are 23% of the acres in those fires (`calendar.human_share`).
- **Debris and open burning** is the most common known human cause in every month except July, when equipment and vehicle use leads (`calendar.top_human_cause_by_month`).
  - Its season differs by region (`calendar.debris_peak`).
  - In the Northeast and the Midwest/Plains ("Other"), about half of debris fires start in March and April.
  - In the South the peak is March, then February, then April.
  - In the West and Alaska it is May to June.
- **4 July.** A typical day between 24 June and 15 July (4-5 July excluded) brings 269 new fires nationally; 4 July brings 625 (2.3x) and 5 July 416 (1.5x).
  - 4 July was the single busiest day of the year in 11 of the 29 years.
  - Only 16% of 4-5 July fires are coded as fireworks, and 34% have no recorded cause (`calendar.july4`).
  - So the size of the spike measures fireworks-season ignitions better than the cause code does.
- **4 July by state.** The ratio to a normal day is highest in Hawaii (8.4x), Wyoming (5.2x), North Dakota (5.0x) and Texas (3.9x).
  - Texas codes almost none of them as fireworks (1%).
  - Hawaii records a cause for almost no fires.
  - In both, the spike is visible only through the calendar (`calendar.july4_by_state`).
- **New Year.** 31 December and 1 January together run 1.5x the surrounding days.

## Trends by state

38 states have a usable window of 15 years or more (`places.acres_trend_summary`). At p < 0.05 (Kendall):

- annual acres burned trend upward in California, Oregon, Arizona, Washington, Oklahoma and Illinois;
- they trend downward in Mississippi, Minnesota, Tennessee, Maryland and Maine.

About 2 such results would appear by chance among 38 tests, so treat a single state's result as a lead, not a finding. The per-state sentences on the briefs say this.

## Limits

- **Cause coverage varies by state** (`calendar.cause_missing_by_state`). Where the general cause is mostly missing, the brief says so beside the cause list.
- **Losses** count only incidents with an ICS-209 report, 1999-2020. Each incident is matched to its largest FPA FOD fire, which assigns the state and cause.
- **Protection shares** use the PAD-US 4.1 point join from `analysis/conservation.py`. "Not in PAD-US" is mostly private land.
- **The GACC label** on each brief is the state-level approximation in `analysis/common.py`, not the official boundary.
