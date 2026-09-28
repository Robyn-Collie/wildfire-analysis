"""Act 3 monsters blob: every class-G fire (no sampling), with real names.

monsters.bin: 16 bytes/fire LE — f32 lon, f32 lat, f32 acres, uint16 meta (year5<<6|cause2<<4|region2<<2), uint16 nameIdx
monsters-names.json: display names (MTBS_FIRE_NAME preferred, else FIRE_NAME, title-cased; else 'Unnamed fire')
top100.json: gallery source (rank, name, year, state, acres, cause) — STAT source for /monsters page.
Spec: design-spec-v2.md §2.
"""
import json
import struct
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site-v2" / "public" / "data"
OUT.mkdir(parents=True, exist_ok=True)
CAUSE2 = {"Human": 0, "Natural": 1, "Missing data/not specified/undetermined": 2}
REGIONS = [(-125.0, -66.0, 24.0, 50.0), (-170.0, -129.0, 54.0, 72.0), (-161.0, -154.0, 18.5, 22.8)]

def region_of(lon, lat):
    for i, (x0, x1, y0, y1) in enumerate(REGIONS):
        if x0 <= lon <= x1 and y0 <= lat <= y1:
            return i
    return -1

def display_name(r):
    for v in (r.MTBS_FIRE_NAME, r.FIRE_NAME):
        if isinstance(v, str) and v.strip():
            return v.strip().title()
    return "Unnamed fire"

df = pd.read_parquet(ROOT / "data" / "fires.parquet",
                     columns=["LATITUDE", "LONGITUDE", "FIRE_SIZE", "FIRE_SIZE_CLASS", "FIRE_YEAR",
                              "NWCG_CAUSE_CLASSIFICATION", "STATE", "FIRE_NAME", "MTBS_FIRE_NAME"])
g = df[df.FIRE_SIZE_CLASS == "G"].copy()
g["region"] = [region_of(lo, la) for lo, la in zip(g.LONGITUDE, g.LATITUDE)]
dropped = int((g.region < 0).sum())
g = g[g.region >= 0].sort_values("FIRE_SIZE", ascending=False).reset_index(drop=True)
g["name"] = [display_name(r) for r in g.itertuples()]

names = []
nidx = {}
def idx_of(n):
    if n not in nidx:
        nidx[n] = len(names)
        names.append(n)
    return nidx[n]

buf = bytearray()
for r in g.itertuples():
    meta = ((int(r.FIRE_YEAR) - 1992) << 6) | (CAUSE2[r.NWCG_CAUSE_CLASSIFICATION] << 4) | (int(r.region) << 2)
    buf += struct.pack("<fffHH", r.LONGITUDE, r.LATITUDE, r.FIRE_SIZE, meta, idx_of(r.name))
(OUT / "monsters.bin").write_bytes(bytes(buf))
(OUT / "monsters-names.json").write_text(json.dumps(names))

top100 = [{"rank": i + 1, "name": r.name, "year": int(r.FIRE_YEAR), "state": r.STATE,
           "acres": int(r.FIRE_SIZE), "cause": r.NWCG_CAUSE_CLASSIFICATION}
          for i, r in enumerate(g.head(100).itertuples())]
(OUT / "top100.json").write_text(json.dumps({
    "_meta": {"built": time.strftime("%Y-%m-%dT%H:%M:%S"), "script": "pipeline/build_monsters.py",
              "source": "FPA-FOD 6th ed. class G (>=5,000 acres), regions CONUS/AK/HI",
              "note": f"{dropped} class-G records outside region bounds dropped (offshore/PR)",
              "name_rule": "MTBS_FIRE_NAME preferred, else FIRE_NAME, title-cased"},
    "rows": top100}, indent=1))
print(f"monsters: {len(g):,} fires, {len(names):,} names, blob {(OUT/'monsters.bin').stat().st_size/1024:.0f} KB; top: {top100[0]['name']} {top100[0]['acres']:,} ac")
