"""Hero-prototype point blob: every fire as a 6-byte record for WebGL2.

Record layout (little-endian, 6 bytes):
  uint16 x   — longitude quantized to [0,65535] across CONUS bounds
  uint16 y   — latitude  quantized likewise
  uint16 dc  — (discovery day-of-year << 3) | size_class(0..6)   [doy 1..366 needs 9 bits]

Sampling: ALL fires of class C+ (>=10 acres) are kept; classes A/B are randomly
sampled (seeded) down to a target so the blob stays light. The hero shows
ignition timing/geography, and A/B dots are visually tiny — the sample keeps
density honest while the big fires stay complete.

CONUS only for the prototype (AK/HI/PR excluded — noted in the header JSON).
Outputs: site/hero-data/points.bin + points.json (header/provenance).
"""
import json
import struct
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "hero-data"
OUT.mkdir(parents=True, exist_ok=True)

LON_MIN, LON_MAX = -125.0, -66.0
LAT_MIN, LAT_MAX = 24.0, 50.0
AB_TARGET = 700_000
SEED = 20260712

df = pd.read_parquet(ROOT / "data" / "fires.parquet",
                     columns=["LATITUDE", "LONGITUDE", "DISCOVERY_DOY", "FIRE_SIZE_CLASS"])
n_total = len(df)
conus = df[(df.LONGITUDE >= LON_MIN) & (df.LONGITUDE <= LON_MAX) &
           (df.LATITUDE >= LAT_MIN) & (df.LATITUDE <= LAT_MAX)].copy()
n_conus = len(conus)

big = conus[conus.FIRE_SIZE_CLASS >= "C"]
small = conus[conus.FIRE_SIZE_CLASS < "C"]
rng = np.random.default_rng(SEED)
take = min(AB_TARGET, len(small))
small = small.iloc[rng.choice(len(small), size=take, replace=False)]
pts = pd.concat([big, small])
pts = pts.iloc[rng.permutation(len(pts))].reset_index(drop=True)  # shuffle for even loading

x = np.round((pts.LONGITUDE - LON_MIN) / (LON_MAX - LON_MIN) * 65535).astype(np.uint16)
y = np.round((pts.LATITUDE - LAT_MIN) / (LAT_MAX - LAT_MIN) * 65535).astype(np.uint16)
doy = pts.DISCOVERY_DOY.clip(1, 366).to_numpy(dtype=np.uint16)
cls = pts.FIRE_SIZE_CLASS.map({c: i for i, c in enumerate("ABCDEFG")}).to_numpy(dtype=np.uint16)
dc = ((doy.astype(np.uint32) << 3) | cls).astype(np.uint16)

blob = np.empty(len(pts) * 3, dtype=np.uint16)
blob[0::3], blob[1::3], blob[2::3] = x, y, dc
(OUT / "points.bin").write_bytes(blob.tobytes())

class_counts = pts.FIRE_SIZE_CLASS.value_counts().sort_index()
header = {
    "built": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "script": "pipeline/build_hero_points.py",
    "source": "FPA-FOD 6th ed. (Short 2022, doi:10.2737/RDS-2013-0009.6), 1992-2020",
    "record": "3x uint16 LE per fire: x, y, (doy<<3|class)",
    "bounds": {"lon": [LON_MIN, LON_MAX], "lat": [LAT_MIN, LAT_MAX]},
    "points": int(len(pts)),
    "sampling": {
        "total_records": int(n_total),
        "conus_records": int(n_conus),
        "classes_C_to_G": "complete",
        "classes_A_B": f"random sample of {take:,} (seed {SEED}) from {len(conus)-len(big):,}",
        "excluded": "AK/HI/PR (prototype is CONUS-only; noted on page)",
    },
    "class_counts": {k: int(v) for k, v in class_counts.items()},
    "seed": SEED,
}
(OUT / "points.json").write_text(json.dumps(header, indent=1))
mb = (OUT / "points.bin").stat().st_size / 1e6
print(f"{len(pts):,} points -> points.bin {mb:.1f} MB ({dict(class_counts)})")
