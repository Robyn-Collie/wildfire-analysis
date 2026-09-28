"""v2 point blob: one 8-byte record per fire drives Acts 0/1/2/4 + Explore.

Record (4x uint16 LE): x, y, w3 = doy<<3 | class, w4 = year5<<11 | cause2<<9 | region2<<7 | state6<<1
x/y quantized within the point's REGION bounds (0 CONUS, 1 AK inset, 2 HI inset).
Sampling: classes C-G complete; A/B seeded sample (700k) across all regions.
Outputs: site-v2/public/data/points-v2.bin + points-v2.json (spec: design-spec-v2.md §2).
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site-v2" / "public" / "data"
OUT.mkdir(parents=True, exist_ok=True)

REGIONS = [  # (lon_min, lon_max, lat_min, lat_max)
    (-125.0, -66.0, 24.0, 50.0),    # 0 CONUS
    (-170.0, -129.0, 54.0, 72.0),   # 1 AK
    (-161.0, -154.0, 18.5, 22.8),   # 2 HI
]
AB_TARGET = 700_000
SEED = 20260712
CAUSE2 = {"Human": 0, "Natural": 1, "Missing data/not specified/undetermined": 2}

df = pd.read_parquet(ROOT / "data" / "fires.parquet",
                     columns=["LATITUDE", "LONGITUDE", "DISCOVERY_DOY", "FIRE_SIZE_CLASS",
                              "FIRE_YEAR", "NWCG_CAUSE_CLASSIFICATION", "STATE"])

def region_of(lon, lat):
    for i, (x0, x1, y0, y1) in enumerate(REGIONS):
        if x0 <= lon <= x1 and y0 <= lat <= y1:
            return i
    return -1

df["region"] = [region_of(lo, la) for lo, la in zip(df.LONGITUDE, df.LATITUDE)]
inb = df[df.region >= 0].copy()
print(f"in-region: {len(inb):,} of {len(df):,} (dropped {len(df)-len(inb):,}: PR/offshore/odd coords)")

big = inb[inb.FIRE_SIZE_CLASS >= "C"]
small = inb[inb.FIRE_SIZE_CLASS < "C"]
rng = np.random.default_rng(SEED)
take = min(AB_TARGET, len(small))
small = small.iloc[rng.choice(len(small), size=take, replace=False)]
pts = pd.concat([big, small]).iloc[rng.permutation(len(big) + take)].reset_index(drop=True)

states = sorted(pts.STATE.unique())
assert len(states) <= 64, f"state6 overflow: {len(states)}"
sidx = {s: i for i, s in enumerate(states)}

reg = pts.region.to_numpy()
b = np.array(REGIONS)[reg]  # per-point bounds
x = np.round((pts.LONGITUDE.to_numpy() - b[:, 0]) / (b[:, 1] - b[:, 0]) * 65535).astype(np.uint16)
y = np.round((pts.LATITUDE.to_numpy() - b[:, 2]) / (b[:, 3] - b[:, 2]) * 65535).astype(np.uint16)
doy = pts.DISCOVERY_DOY.clip(1, 366).to_numpy(np.uint32)
cls = pts.FIRE_SIZE_CLASS.map({c: i for i, c in enumerate("ABCDEFG")}).to_numpy(np.uint32)
year5 = (pts.FIRE_YEAR.to_numpy(np.uint32) - 1992)
cause2 = pts.NWCG_CAUSE_CLASSIFICATION.map(CAUSE2).to_numpy(np.uint32)
state6 = pts.STATE.map(sidx).to_numpy(np.uint32)
w3 = ((doy << 3) | cls).astype(np.uint16)
w4 = ((year5 << 11) | (cause2 << 9) | (reg.astype(np.uint32) << 7) | (state6 << 1)).astype(np.uint16)

blob = np.empty(len(pts) * 4, dtype=np.uint16)
blob[0::4], blob[1::4], blob[2::4], blob[3::4] = x, y, w3, w4
(OUT / "points-v2.bin").write_bytes(blob.tobytes())

header = {
    "built": time.strftime("%Y-%m-%dT%H:%M:%S"), "script": "pipeline/build_points_v2.py",
    "source": "FPA-FOD 6th ed. (Short 2022, doi:10.2737/RDS-2013-0009.6), 1992-2020",
    "record": "4x uint16 LE: x, y, doy<<3|class, year5<<11|cause2<<9|region2<<7|state6<<1",
    "regions": [{"name": n, "bounds": list(bb)} for n, bb in zip(["CONUS", "AK", "HI"], REGIONS)],
    "states": states, "cause2": {v: k for k, v in CAUSE2.items()},
    "points": int(len(pts)),
    "sampling": {"C_to_G": "complete", "A_B": f"seeded sample {take:,} (seed {SEED})",
                 "dropped_out_of_region": int(len(df) - len(inb))},
    "class_counts": {k: int(v) for k, v in pts.FIRE_SIZE_CLASS.value_counts().sort_index().items()},
    "seed": SEED,
}
(OUT / "points-v2.json").write_text(json.dumps(header, indent=1))
print(f"{len(pts):,} pts x 8B = {(OUT/'points-v2.bin').stat().st_size/1e6:.1f} MB; states={len(states)}")
