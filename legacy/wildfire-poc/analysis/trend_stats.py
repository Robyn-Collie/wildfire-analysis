"""The variance thesis, quantified — plus the fire-climate correlation base.

Claims produced here are ORIGINAL ANALYSIS (r3 guardrail: the literature supports
'highs higher'; 'lows higher'/variance-widening is ours to own and defend).
Outputs analysis/trend_stats.json; every number the site quotes traces here.
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
nifc = pd.read_csv(ROOT / "data" / "raw" / "nifc_annual.csv").sort_values("year")
fires = pd.read_parquet(ROOT / "data" / "fires.parquet", columns=["FIRE_YEAR", "FIRE_SIZE", "STATE"])
climate = pd.read_parquet(ROOT / "data" / "climate.parquet")

out = {"_meta": {"built": time.strftime("%Y-%m-%dT%H:%M:%S"), "script": "analysis/trend_stats.py",
                 "framing": "Original analysis on NIFC (1983-2025) and FPA-FOD (1992-2020); "
                            "literature context: EPA/NCA5 support rising large-year acreage; "
                            "the floor/variance findings are this project's own."}}

acres_m = nifc.set_index("year").acres / 1e6

# ── 1. Era comparison: 1983-1999 vs 2000-2025 (NIFC official series) ──────────
def era_stats(s):
    return {"years": f"{s.index.min()}-{s.index.max()}", "n": int(s.size),
            "min": round(s.min(), 2), "p25": round(s.quantile(.25), 2),
            "median": round(s.median(), 2), "p75": round(s.quantile(.75), 2),
            "max": round(s.max(), 2), "iqr": round(s.quantile(.75) - s.quantile(.25), 2)}

era1, era2 = acres_m.loc[:1999], acres_m.loc[2000:]
out["era_comparison_nifc_macres"] = {
    "1983-1999": era_stats(era1), "2000-2025": era_stats(era2),
    "floor_shift": {"pre2000_min": round(era1.min(), 2), "post2000_min": round(era2.min(), 2),
                    "ratio": round(era2.min() / era1.min(), 2)},
    "ceiling_shift": {"pre2000_max": round(era1.max(), 2), "post2000_max": round(era2.max(), 2),
                      "ratio": round(era2.max() / era1.max(), 2)},
    "mannwhitney_p": round(float(stats.mannwhitneyu(era1, era2, alternative="less").pvalue), 5),
    "note_lowest_years": "All 5 lowest-acre years in the official record are 1983-1998 (R2).",
}

# ── 2. Rolling 11-yr percentile band (the chart's data) ───────────────────────
roll = acres_m.rolling(11, center=True)
band = pd.DataFrame({"p10": roll.quantile(.10), "p50": roll.quantile(.50),
                     "p90": roll.quantile(.90)}).dropna().round(2)
out["rolling_band_nifc_macres"] = {
    "window": 11,
    "rows": [[int(y), float(r.p10), float(r.p50), float(r.p90)] for y, r in band.iterrows()],
    "first_vs_last": {
        "first_center_year": int(band.index[0]),
        "last_center_year": int(band.index[-1]),
        "p10_change": f"{band.p10.iloc[0]} -> {band.p10.iloc[-1]} M acres",
        "p90_change": f"{band.p90.iloc[0]} -> {band.p90.iloc[-1]} M acres",
    },
}

# ── 3. Trend tests on the official series ─────────────────────────────────────
yrs = acres_m.index.values.astype(float)
theil = stats.theilslopes(acres_m.values, yrs)
mk_tau, mk_p = stats.kendalltau(yrs, acres_m.values)
out["trend_nifc"] = {
    "theil_sen_slope_macres_per_decade": round(theil.slope * 10, 3),
    "theil_sen_ci95_per_decade": [round(theil.low_slope * 10, 3), round(theil.high_slope * 10, 3)],
    "kendall_tau": round(float(mk_tau), 3), "kendall_p": round(float(mk_p), 6),
}

# ── 4. The 10M-acre ceiling framing (post-R2 correction) ──────────────────────
big = acres_m[acres_m >= 10]
out["ten_million_club"] = {
    "years": [int(y) for y in big.index], "note":
    "Never reached before 2015 in the official record; reached three times 2015-2020. "
    "No new record 2021-2025 — the story is a rising floor plus a ceiling first touched in 2015."}

# ── 5. Fire-climate correlation (FOD state-year acres vs May-Oct PDSI) ────────
season = climate[(climate.month >= 5) & (climate.month <= 10)]
cs = season.groupby(["state_postal", "year"]).agg(pdsi=("pdsi", "mean")).reset_index()
sy = (fires.groupby(["STATE", "FIRE_YEAR"]).FIRE_SIZE.sum().reset_index()
      .rename(columns={"STATE": "state_postal", "FIRE_YEAR": "year", "FIRE_SIZE": "acres"}))
panel = sy.merge(cs, on=["state_postal", "year"]).dropna()
corrs = []
for st, g in panel.groupby("state_postal"):
    if len(g) >= 25 and g.acres.sum() > 50000:  # full coverage + meaningful fire activity
        r, p = stats.spearmanr(g.pdsi, np.log10(g.acres + 1))
        corrs.append({"state": st, "spearman_r": round(float(r), 3),
                      "p": round(float(p), 4), "years": len(g)})
corrs.sort(key=lambda d: d["spearman_r"])
strong = [c for c in corrs if c["spearman_r"] <= -0.5 and c["p"] < 0.05]
out["fire_climate_correlation"] = {
    "spec": "Spearman rank corr: state May-Oct mean PDSI vs log10 annual FOD acres, 1992-2020; "
            "states with >=25 yrs and >50k total acres. Negative = drier -> more burned.",
    "n_states": len(corrs),
    "strongest_negative_10": corrs[:10],
    "n_strong_negative": len(strong),
    "median_r": round(float(np.median([c["spearman_r"] for c in corrs])), 3),
    "west_11": [c for c in corrs if c["state"] in
                ("WA", "OR", "CA", "ID", "NV", "MT", "WY", "UT", "CO", "AZ", "NM")],
}

path = ROOT / "analysis" / "trend_stats.json"
path.write_text(json.dumps(out, indent=1))
print(json.dumps({k: v for k, v in out.items() if k != "rolling_band_nifc_macres"}, indent=1)[:3500])
print("rolling band rows:", len(out["rolling_band_nifc_macres"]["rows"]))
print("->", path)
