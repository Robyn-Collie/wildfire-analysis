"""The bounded prediction model (tier 2 of the tiered-prediction decision).

Spec: log10(state annual FOD acres + 1) ~ within-state z-scores of May-Oct
mean PDSI, mean temp, total precip + state fixed effects (pooled OLS).
Validation: leave-one-YEAR-out (all states of a held-out year predicted by a
model trained on the other 28 years) — the honest test for "could we have
anticipated this season."
Skill baseline: state climatology (median log-acres over training years).
Honesty ceiling from prior art: Riley et al. 2013 report PDSI-area R^2 ~ 0.25
(r3) — we expect modest skill and SAY SO.
Output: analysis/model_results.json.
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
fires = pd.read_parquet(ROOT / "data" / "fires.parquet", columns=["FIRE_YEAR", "FIRE_SIZE", "STATE"])
climate = pd.read_parquet(ROOT / "data" / "climate.parquet")

# panel: state-year acres + May-Oct climate
sy = (fires.groupby(["STATE", "FIRE_YEAR"]).FIRE_SIZE.sum().reset_index()
      .rename(columns={"STATE": "state", "FIRE_YEAR": "year", "FIRE_SIZE": "acres"}))
season = climate[(climate.month >= 5) & (climate.month <= 10)]
cs = (season.groupby(["state_postal", "year"])
      .agg(pdsi=("pdsi", "mean"), tavg=("tavg_f", "mean"), precip=("precip_in", "sum"))
      .reset_index().rename(columns={"state_postal": "state"}))
panel = sy.merge(cs, on=["state", "year"]).dropna()
# restrict to states with all 29 years and meaningful fire activity (same bar as trend_stats)
keep = [s for s, g in panel.groupby("state") if len(g) == 29 and g.acres.sum() > 50_000]
panel = panel[panel.state.isin(keep)].sort_values(["state", "year"]).reset_index(drop=True)
panel["y"] = np.log10(panel.acres + 1)

# within-state z-scores (computed on TRAINING years inside the CV loop below)
STATES = sorted(panel.state.unique())
YEARS = sorted(panel.year.unique())
S_IDX = {s: i for i, s in enumerate(STATES)}

def design(df, zstats):
    Z = np.zeros((len(df), 3 + len(STATES)))
    for j, var in enumerate(["pdsi", "tavg", "precip"]):
        mu, sd = zstats[var]
        Z[:, j] = (df[var].values - mu[df.state.map(S_IDX)]) / sd[df.state.map(S_IDX)]
    for i, s in enumerate(df.state):
        Z[i, 3 + S_IDX[s]] = 1.0
    return Z

def zfit(train):
    zstats = {}
    for var in ["pdsi", "tavg", "precip"]:
        mu = train.groupby("state")[var].mean().reindex(STATES).values
        sd = train.groupby("state")[var].std().reindex(STATES).values
        sd[sd == 0] = 1.0
        zstats[var] = (mu, sd)
    return zstats

# ── leave-one-year-out CV ──────────────────────────────────────────────────────
rows = []
for held in YEARS:
    train, test = panel[panel.year != held], panel[panel.year == held]
    zs = zfit(train)
    Xtr, Xte = design(train, zs), design(test, zs)
    beta, *_ = np.linalg.lstsq(Xtr, train.y.values, rcond=None)
    pred = Xte @ beta
    base = train.groupby("state").y.median().reindex(test.state).values  # climatology
    for st, yt, yp, yb in zip(test.state, test.y, pred, base):
        rows.append((held, st, yt, yp, yb))
cv = pd.DataFrame(rows, columns=["year", "state", "y", "yhat", "ybase"])

sse_m = ((cv.y - cv.yhat) ** 2).sum()
sse_b = ((cv.y - cv.ybase) ** 2).sum()
sst = ((cv.y - cv.y.mean()) ** 2).sum()
oos_r2 = 1 - sse_m / sst
skill_vs_clim = 1 - sse_m / sse_b   # >0 means beats climatology

per_state = []
for st, g in cv.groupby("state"):
    r2 = 1 - ((g.y - g.yhat) ** 2).sum() / max(((g.y - g.y.mean()) ** 2).sum(), 1e-9)
    per_state.append({"state": st, "oos_r2": round(float(r2), 3)})
per_state.sort(key=lambda d: -d["oos_r2"])

# full-sample coefficients for the explainer (signs/magnitudes; z-scored so comparable)
zs_all = zfit(panel)
beta_all, *_ = np.linalg.lstsq(design(panel, zs_all), panel.y.values, rcond=None)
coefs = {"pdsi_z": round(float(beta_all[0]), 4), "tavg_z": round(float(beta_all[1]), 4),
         "precip_z": round(float(beta_all[2]), 4)}

# a worst-miss table — honesty exhibit for the model page
cv["abs_err"] = (cv.y - cv.yhat).abs()
worst = cv.nlargest(5, "abs_err")
misses = [{"state": r.state, "year": int(r.year),
           "actual_acres": int(10 ** r.y - 1), "predicted_acres": int(10 ** r.yhat - 1)}
          for r in worst.itertuples()]

out = {
    "_meta": {"built": time.strftime("%Y-%m-%dT%H:%M:%S"), "script": "analysis/model.py",
              "spec": "pooled OLS, log10(acres+1) ~ z(PDSI)+z(temp)+z(precip) May-Oct + state FE; "
                      "leave-one-year-out CV; baseline = state climatology (train-years median)",
              "honesty": "Prior art ceiling: Riley et al. 2013 PDSI-area R^2 ~ 0.25. "
                         "This model explains state identity (FE) + a modest climate signal; "
                         "it is a seasonal risk indicator, not a forecast of individual fires."},
    "panel": {"states": len(STATES), "years": f"{YEARS[0]}-{YEARS[-1]}", "rows": len(panel)},
    "oos_r2_overall": round(float(oos_r2), 3),
    "skill_vs_climatology": round(float(skill_vs_clim), 3),
    "coefficients_z": coefs,
    "per_state_oos_r2_top10": per_state[:10],
    "per_state_oos_r2_bottom5": per_state[-5:],
    "worst_misses": misses,
    # full held-out predictions so the site's scatter is the real validation,
    # not a 5-point excerpt (gap found by the build wave's w5, which refused
    # to fabricate a denser plot)
    "cv_predictions": {
        "columns": ["state", "year", "actual_acres", "predicted_acres"],
        "rows": [[r.state, int(r.year), int(round(10 ** r.y - 1)),
                  int(round(10 ** r.yhat - 1))] for r in cv.itertuples()],
    },
}
(ROOT / "analysis" / "model_results.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1)[:2600])
