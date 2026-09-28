"""Act 4 drought tint grid: state-month PDSI 1992-2020 as a uint8 texture blob.

pdsi-grid.bin: uint8[nStates][29*12] — PDSI linearly quantized -8..+8 -> 0..254; 255 = missing.
Row order MUST match points-v2.json's state list (asserted here).
Spec: design-spec-v2.md §2. Source: NOAA nClimDiv (Vose 2014, doi:10.7289/V5M32STR).
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site-v2" / "public" / "data"
states = json.loads((OUT / "points-v2.json").read_text())["states"]

cl = pd.read_parquet(ROOT / "data" / "climate.parquet")
cl = cl[(cl.year >= 1992) & (cl.year <= 2020)]

grid = np.full((len(states), 29 * 12), 255, dtype=np.uint8)
for i, st in enumerate(states):
    g = cl[cl.state_postal == st]
    for r in g.itertuples():
        col = (r.year - 1992) * 12 + (r.month - 1)
        if pd.notna(r.pdsi):
            grid[i, col] = int(round(np.clip((r.pdsi + 8) / 16, 0, 1) * 254))

missing = int((grid == 255).sum())
(OUT / "pdsi-grid.bin").write_bytes(grid.tobytes())
(OUT / "pdsi-grid.json").write_text(json.dumps({
    "built": time.strftime("%Y-%m-%dT%H:%M:%S"), "script": "pipeline/build_drought_grid.py",
    "source": "NOAA nClimDiv v1.0.0-20260707 (Vose et al. 2014, doi:10.7289/V5M32STR)",
    "layout": "uint8[nStates][348]; col = (year-1992)*12 + (month-1); rows match points-v2.json states",
    "scale": "PDSI -8..+8 -> 0..254 linear; 255 = missing",
    "states": states, "missing_cells": missing,
}, indent=1))
print(f"pdsi grid: {len(states)} states x 348 months = {grid.size/1024:.1f} KB; missing cells {missing} "
      f"({missing/grid.size*100:.1f}% — PR etc. have no nClimDiv)")
