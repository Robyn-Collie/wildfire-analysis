"""explore-cause13 sidecar: one uint8 per point, aligned 1:1 with points-v2.bin row order.

Maps each selected fire's NWCG_GENERAL_CAUSE to an index into the sorted list of unique
values read from data/fires.parquet (13 categories, incl. Missing). Loaded lazily only on
the Explore page to power the general-cause multiselect (design-spec-v2.md §5).

Selection logic is factor-copied VERBATIM from pipeline/build_points_v2.py: same seed 20260712,
same region filter, same C-G complete + A/B seeded 700k sample, same permutation. This GUARANTEES
row alignment with points-v2.bin. Any divergence here silently corrupts every filter on the page,
so the selection block below must stay byte-identical to build_points_v2.py.

Outputs: site-v2/public/data/explore-cause13.bin + explore-cause13.json.
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site-v2" / "public" / "data"
OUT.mkdir(parents=True, exist_ok=True)

# ---- VERBATIM from build_points_v2.py (selection contract) ------------------
REGIONS = [  # (lon_min, lon_max, lat_min, lat_max)
    (-125.0, -66.0, 24.0, 50.0),    # 0 CONUS
    (-170.0, -129.0, 54.0, 72.0),   # 1 AK
    (-161.0, -154.0, 18.5, 22.8),   # 2 HI
]
AB_TARGET = 700_000
SEED = 20260712

# We need NWCG_GENERAL_CAUSE for the sidecar, but every column that participates in
# selection (LATITUDE, LONGITUDE, FIRE_SIZE_CLASS) must be read identically so the
# region filter, big/small split, sample, and permutation reproduce exactly.
df = pd.read_parquet(ROOT / "data" / "fires.parquet",
                     columns=["LATITUDE", "LONGITUDE", "DISCOVERY_DOY", "FIRE_SIZE_CLASS",
                              "FIRE_YEAR", "NWCG_CAUSE_CLASSIFICATION", "STATE",
                              "NWCG_GENERAL_CAUSE"])


def region_of(lon, lat):
    for i, (x0, x1, y0, y1) in enumerate(REGIONS):
        if x0 <= lon <= x1 and y0 <= lat <= y1:
            return i
    return -1


df["region"] = [region_of(lo, la) for lo, la in zip(df.LONGITUDE, df.LATITUDE)]
inb = df[df.region >= 0].copy()

big = inb[inb.FIRE_SIZE_CLASS >= "C"]
small = inb[inb.FIRE_SIZE_CLASS < "C"]
rng = np.random.default_rng(SEED)
take = min(AB_TARGET, len(small))
small = small.iloc[rng.choice(len(small), size=take, replace=False)]
pts = pd.concat([big, small]).iloc[rng.permutation(len(big) + take)].reset_index(drop=True)
# ---- end VERBATIM block -----------------------------------------------------

# Category index over the ACTUAL unique general-cause values (sorted for a stable order).
categories = sorted(df["NWCG_GENERAL_CAUSE"].dropna().unique().tolist())
print(f"general-cause categories ({len(categories)}):")
for i, c in enumerate(categories):
    print(f"  {i:2d}  {c}")
assert len(categories) <= 255, f"cause13 index overflow: {len(categories)}"
assert pts["NWCG_GENERAL_CAUSE"].notna().all(), "unexpected null general cause in selection"

cidx = {c: i for i, c in enumerate(categories)}
codes = pts["NWCG_GENERAL_CAUSE"].map(cidx).to_numpy(np.uint8)

# ---- asserts ---------------------------------------------------------------
# 1. Row count must equal points-v2.json .points (proves 1:1 alignment length).
header_pts = json.loads((OUT / "points-v2.json").read_text())["points"]
assert len(codes) == header_pts, f"row count {len(codes)} != points-v2.json .points {header_pts}"
count_assert = f"len(codes)=={len(codes)} == points-v2.json .points=={header_pts}"

# 2. Spot-assert 5 random rows decode to matching (x,y) when re-quantized against
#    points-v2.bin. This proves the ORDER matches, not just the length.
blob = np.frombuffer((OUT / "points-v2.bin").read_bytes(), dtype="<u2").reshape(-1, 4)
assert blob.shape[0] == len(codes), f"blob rows {blob.shape[0]} != codes {len(codes)}"
regions_arr = np.array(REGIONS)
reg = pts.region.to_numpy()
b = regions_arr[reg]
x_expect = np.round((pts.LONGITUDE.to_numpy() - b[:, 0]) / (b[:, 1] - b[:, 0]) * 65535).astype(np.uint16)
y_expect = np.round((pts.LATITUDE.to_numpy() - b[:, 2]) / (b[:, 3] - b[:, 2]) * 65535).astype(np.uint16)

spot_rng = np.random.default_rng(SEED + 1)
spot = sorted(spot_rng.choice(len(codes), size=5, replace=False).tolist())
spot_lines = []
for r in spot:
    bx, by = int(blob[r, 0]), int(blob[r, 1])
    ex, ey = int(x_expect[r]), int(y_expect[r])
    ok = (bx == ex) and (by == ey)
    line = (f"row {r}: blob(x,y)=({bx},{by}) vs re-quantized=({ex},{ey}) "
            f"cause='{pts.NWCG_GENERAL_CAUSE.iloc[r]}' idx={int(codes[r])} -> {'OK' if ok else 'MISMATCH'}")
    spot_lines.append(line)
    print("  " + line)
    assert ok, f"spot-assert failed at row {r}: {line}"

(OUT / "explore-cause13.bin").write_bytes(codes.tobytes())

header = {
    "built": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "script": "pipeline/build_explore_cause13.py",
    "source": "FPA-FOD 6th ed. (Short 2022, doi:10.2737/RDS-2013-0009.6), 1992-2020",
    "record": "1x uint8 LE per point; index into 'categories'; aligned 1:1 with points-v2.bin row order",
    "aligns_with": "points-v2.bin (same seed, region filter, sample, permutation as build_points_v2.py)",
    "categories": categories,
    "count": int(len(codes)),
    "seed": SEED,
    "category_counts": {c: int((codes == i).sum()) for i, c in enumerate(categories)},
    "asserts": {
        "row_count": count_assert,
        "spot_requantize": spot_lines,
    },
}
(OUT / "explore-cause13.json").write_text(json.dumps(header, indent=1))
print(f"\n{len(codes):,} codes x 1B = {(OUT/'explore-cause13.bin').stat().st_size/1e6:.3f} MB; "
      f"{len(categories)} categories")
print("ALL ASSERTS PASSED")
