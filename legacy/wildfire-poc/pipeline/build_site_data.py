"""Build the static JSON aggregates the site consumes.

Inputs:  data/fires.parquet (FPA-FOD 1992-2020), data/climate.parquet (nClimDiv),
         data/raw/nifc_annual.csv (NIFC 1983-2025).
Outputs: site-data/*.json, each carrying a _meta block (source, script, built, counts).
Guardrails honored (research/r3-provenance-lit.md Part C): FOD and NIFC kept as
separate series everywhere; NIFC fire-count series annotated for 1983-84 undercount;
official size-class thresholds used verbatim.
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site-data"
OUT.mkdir(exist_ok=True)

META_BASE = {
    "built": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "script": "pipeline/build_site_data.py",
    "fod_source": "Short 2022, FPA-FOD 6th ed., doi:10.2737/RDS-2013-0009.6 (1992-2020)",
    "nifc_source": "NIFC annual wildfire statistics, accessed 2026-07-12 (1983-2025)",
    "climate_source": "NOAA nClimDiv v1.0.0-20260707, doi:10.7289/V5M32STR",
}

SIZE_CLASS_ACRES = {  # official FPA-FOD thresholds (r3, verbatim)
    "A": "0-0.25", "B": "0.26-9.9", "C": "10-99.9", "D": "100-299",
    "E": "300-999", "F": "1000-4999", "G": "5000+",
}

def write(name: str, payload: dict) -> None:
    p = OUT / name
    p.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"  {name:<28} {p.stat().st_size/1024:,.0f} KB")

print("loading inputs...")
fires = pd.read_parquet(ROOT / "data" / "fires.parquet",
    columns=["FIRE_YEAR", "DISCOVERY_DATE", "CONT_DATE", "FIRE_SIZE", "FIRE_SIZE_CLASS",
             "NWCG_CAUSE_CLASSIFICATION", "NWCG_GENERAL_CAUSE", "STATE",
             "LATITUDE", "LONGITUDE", "OWNER_DESCR"])
fires["month"] = fires.DISCOVERY_DATE.dt.month
nifc = pd.read_csv(ROOT / "data" / "raw" / "nifc_annual.csv")
climate = pd.read_parquet(ROOT / "data" / "climate.parquet")

# ── 1. national annual: FOD + NIFC as SEPARATE series ─────────────────────────
fod_annual = fires.groupby("FIRE_YEAR").agg(
    fires=("FIRE_SIZE", "size"), acres=("FIRE_SIZE", "sum")).reset_index()
write("national_annual.json", {
    "_meta": {**META_BASE,
              "note": "Two series, different scopes (NIFC broader: all SitReps incl. AK); "
                      "differences are small and sign-flipping where they overlap. "
                      "NIFC fire COUNTS 1983-84 are undercounted per early SitRep coverage; "
                      "acres for those years are fine."},
    "fod": [{"year": int(r.FIRE_YEAR), "fires": int(r.fires), "acres": round(float(r.acres))}
            for r in fod_annual.itertuples()],
    "nifc": [{"year": int(r.year), "fires": int(r.fires), "acres": int(r.acres),
              "count_flag": bool(r.year in (1983, 1984))}
             for r in nifc.itertuples()],
})

# ── 2. state × year ────────────────────────────────────────────────────────────
sy = fires.groupby(["STATE", "FIRE_YEAR"]).agg(
    fires=("FIRE_SIZE", "size"), acres=("FIRE_SIZE", "sum")).reset_index()
write("state_year.json", {
    "_meta": {**META_BASE, "rows": len(sy)},
    "rows": [[r.STATE, int(r.FIRE_YEAR), int(r.fires), round(float(r.acres))]
             for r in sy.itertuples()],
    "columns": ["state", "year", "fires", "acres"],
})

# ── 3. seasonality: month × state and month × cause (national) ────────────────
ms = fires.groupby(["STATE", "month"]).agg(
    fires=("FIRE_SIZE", "size"), acres=("FIRE_SIZE", "sum")).reset_index()
mc = fires.groupby(["NWCG_CAUSE_CLASSIFICATION", "month"]).agg(
    fires=("FIRE_SIZE", "size"), acres=("FIRE_SIZE", "sum")).reset_index()
write("seasonality.json", {
    "_meta": {**META_BASE, "note": "FOD 1992-2020; month = discovery month"},
    "by_state_month": [[r.STATE, int(r.month), int(r.fires), round(float(r.acres))]
                       for r in ms.itertuples()],
    "by_cause_month": [[r.NWCG_CAUSE_CLASSIFICATION, int(r.month), int(r.fires),
                        round(float(r.acres))] for r in mc.itertuples()],
    "columns": ["key", "month", "fires", "acres"],
})

# ── 4. map grid: 0.5-degree bins, per 5-year era ──────────────────────────────
fires["lat_bin"] = (fires.LATITUDE * 2).round() / 2
fires["lon_bin"] = (fires.LONGITUDE * 2).round() / 2
fires["era"] = pd.cut(fires.FIRE_YEAR, bins=[1991, 1996, 2001, 2006, 2011, 2016, 2020],
                      labels=["1992-96", "1997-01", "2002-06", "2007-11", "2012-16", "2017-20"])
grid = fires.groupby(["era", "lat_bin", "lon_bin"], observed=True).agg(
    fires=("FIRE_SIZE", "size"), acres=("FIRE_SIZE", "sum")).reset_index()
grid = grid[grid.fires > 0]
write("map_grid.json", {
    "_meta": {**META_BASE, "cells": len(grid),
              "note": "0.5-degree bins by 5-yr era (last era 4 yrs); includes AK/HI/PR"},
    "rows": [[str(r.era), float(r.lat_bin), float(r.lon_bin), int(r.fires),
              round(float(r.acres))] for r in grid.itertuples()],
    "columns": ["era", "lat", "lon", "fires", "acres"],
})

# ── 5. causes and classes ──────────────────────────────────────────────────────
cause_detail = fires.groupby("NWCG_GENERAL_CAUSE").agg(
    fires=("FIRE_SIZE", "size"), acres=("FIRE_SIZE", "sum")).reset_index()
cls = fires.groupby("FIRE_SIZE_CLASS").agg(
    fires=("FIRE_SIZE", "size"), acres=("FIRE_SIZE", "sum")).reset_index()
write("causes_classes.json", {
    "_meta": {**META_BASE,
              "note": "Missing/undetermined cause is a native NWCG category (8%), not a cleaning artifact. "
                      "Class thresholds are official FPA-FOD definitions."},
    "cause_classification": [
        {"cause": str(k), "fires": int(v.fires), "acres": round(float(v.acres))}
        for k, v in fires.groupby("NWCG_CAUSE_CLASSIFICATION").agg(
            fires=("FIRE_SIZE", "size"), acres=("FIRE_SIZE", "sum")).iterrows()],
    "general_cause": [{"cause": r.NWCG_GENERAL_CAUSE, "fires": int(r.fires),
                       "acres": round(float(r.acres))} for r in cause_detail.itertuples()],
    "size_class": [{"class": r.FIRE_SIZE_CLASS, "acres_range": SIZE_CLASS_ACRES[r.FIRE_SIZE_CLASS],
                    "fires": int(r.fires), "acres": round(float(r.acres))}
                   for r in cls.itertuples()],
})

# ── 6. fire-climate panel: state-year acres + fire-season climate ──────────────
season = climate[(climate.month >= 5) & (climate.month <= 10)]  # May-Oct fire season
cs = season.groupby(["state_postal", "year"]).agg(
    pdsi_szn=("pdsi", "mean"), tavg_szn=("tavg_f", "mean"),
    precip_szn=("precip_in", "sum")).reset_index()
panel = sy.rename(columns={"STATE": "state_postal", "FIRE_YEAR": "year"}).merge(
    cs, on=["state_postal", "year"], how="left")
missing_climate = panel.pdsi_szn.isna().sum()
write("fire_climate_panel.json", {
    "_meta": {**META_BASE, "rows": len(panel),
              "season_def": "climate aggregated May-Oct (PDSI/temp mean, precip sum)",
              "rows_missing_climate": int(missing_climate),
              "note": "PR and other non-state FOD entries have no nClimDiv climate."},
    "rows": [[r.state_postal, int(r.year), int(r.fires), round(float(r.acres)),
              None if pd.isna(r.pdsi_szn) else round(float(r.pdsi_szn), 2),
              None if pd.isna(r.tavg_szn) else round(float(r.tavg_szn), 1),
              None if pd.isna(r.precip_szn) else round(float(r.precip_szn), 1)]
             for r in panel.itertuples()],
    "columns": ["state", "year", "fires", "acres", "pdsi_szn", "tavg_szn", "precip_szn"],
})

print("done")
