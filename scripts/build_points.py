"""Build the map console's point files and state outlines from data/fires.parquet.

Every FPA FOD fire becomes one 8-byte record, pre-projected so the browser only scales and draws:

    uint16 x, uint16 y      position in a 4096-unit square: USA Contiguous Albers (ESRI:102003) for the lower 48,
                            with Alaska (EPSG:3338, scaled 0.35), Hawaii (ESRI:102007) and Puerto Rico
                            (EPSG:32161) as insets, the usual "Albers USA" layout
    uint32 attrs            bits  0-4   year - 1992          (0-28)
                                  5-13  day of year - 1      (0-365)
                                 14-15  cause class          0 human, 1 natural, 2 missing
                                 16-18  size class           0 A ... 6 G
                                 19-20  protection           0 GAP 1-2, 1 GAP 3, 2 GAP 4, 3 not in PAD-US
                                 21-26  state index          into points_meta.json "states"
                                 27-30  general cause index  into points_meta.json "general_causes"

Two files, so the page can draw the fires that matter for burned area first:
    site/data/points_c_plus.bin   size classes C-G (10 acres and more)
    site/data/points_a_b.bin      size classes A-B (under 10 acres), fetched when the reader asks for them

Also writes site/data/points_meta.json (lookups, counts, projection frame) and site/data/outline.json (state
outlines as projected polylines in the same 4096 frame, from the Natural Earth 1:110m subunits already vendored
for Plotly).

Usage: python scripts/build_points.py [--site site]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd
from pyproj import Transformer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis.common import CAUSE_MISSING, load_fires  # noqa: E402
from analysis.conservation import PADUS_OUT  # noqa: E402

FRAME = 4096
GENERAL = ['Debris and open burning', 'Arson/incendiarism', 'Equipment and vehicle use', 'Recreation and ceremony',
           'Smoking', 'Misuse of fire by a minor', 'Railroad operations and maintenance',
           'Power generation/transmission/distribution', 'Fireworks', 'Firearms and explosives use', 'Other causes',
           'Natural', CAUSE_MISSING]
CLASSES = list('ABCDEFG')
GAP_NAMES = ['GAP 1-2 (managed for biodiversity)', 'GAP 3 (multiple use)', 'GAP 4 (no known mandate)', 'Not in PAD-US']

T_CONUS = Transformer.from_crs('EPSG:4326', 'ESRI:102003', always_xy=True)
T_AK = Transformer.from_crs('EPSG:4326', 'EPSG:3338', always_xy=True)
T_HI = Transformer.from_crs('EPSG:4326', 'ESRI:102007', always_xy=True)
T_PR = Transformer.from_crs('EPSG:4326', 'EPSG:32161', always_xy=True)

# CONUS extent in ESRI:102003 metres, with margin; insets placed in the lower left.
X0, X1 = -2_450_000.0, 2_300_000.0
Y0, Y1 = -1_750_000.0, 1_600_000.0  # y range is extended downward so the insets fit under the southwest
SCALE = (FRAME - 1) / max(X1 - X0, Y1 - Y0)
INSETS = {  # (transformer, own-centre lon/lat, scale factor, target centre in CONUS metres)
    'AK': (T_AK, (-152.0, 63.0), 0.35, (-1_850_000.0, -1_300_000.0)),
    'HI': (T_HI, (-157.3, 20.6), 1.0, (-900_000.0, -1_480_000.0)),
    'PR': (T_PR, (-66.4, 18.2), 1.0, (1_900_000.0, -1_550_000.0)),
}


def project(lon: np.ndarray, lat: np.ndarray, state: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """lon/lat -> frame units. ``state`` routes AK/HI/PR to their insets; without it, route by location."""
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    if state is None:
        state = np.where(lat > 50, 'AK', np.where((lon < -150) & (lat < 25), 'HI',
                                                   np.where((lon > -68) & (lat < 19), 'PR', '')))
    lon = np.where((state == 'AK') & (lon > 0), lon - 360.0, lon)  # western Aleutians sit across the antimeridian
    x, y = T_CONUS.transform(lon, lat)
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    for st, (tr, (clon, clat), k, (tx, ty)) in INSETS.items():
        m = state == st
        if m.any():
            ix, iy = tr.transform(lon[m], lat[m])
            cx, cy = tr.transform(clon, clat)
            x[m] = (np.asarray(ix) - cx) * k + tx
            y[m] = (np.asarray(iy) - cy) * k + ty
    fx = (x - X0) * SCALE
    fy = (Y1 - y) * SCALE  # screen y grows downward
    return fx, fy


def gap_codes(fod_ids: pd.Series) -> np.ndarray:
    if not os.path.exists(PADUS_OUT):
        print(f'PAD-US join not found ({PADUS_OUT}); every fire gets protection code 3')
        return np.full(len(fod_ids), 3, dtype=np.uint32)
    p = pd.read_parquet(PADUS_OUT, columns=['FOD_ID', 'Unit_Nm', 'GAP_Sts']).set_index('FOD_ID')
    p = p.reindex(fod_ids.to_numpy())
    inpad = p['Unit_Nm'].notna() & (p['Unit_Nm'] != 'Non-PAD-US Area')
    g = p['GAP_Sts'].astype(str)
    code = np.full(len(p), 3, dtype=np.uint32)
    code[(inpad & g.isin(['1', '2'])).to_numpy()] = 0
    code[(inpad & (g == '3')).to_numpy()] = 1
    code[(inpad & (g == '4')).to_numpy()] = 2
    return code


def outlines() -> list[list[list[float]]]:
    """State outlines from the vendored Natural Earth 110m topojson, projected into the frame."""
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, 'vendor', 'usa_110m.json')) as f:
        topo = json.load(f)
    sx, sy = topo['transform']['scale']
    tx, ty = topo['transform']['translate']
    arcs = []
    for arc in topo['arcs']:
        a = np.cumsum(np.array(arc, dtype=float), axis=0)
        arcs.append(np.column_stack([a[:, 0] * sx + tx, a[:, 1] * sy + ty]))

    def ring(idx: list[int]) -> np.ndarray:
        parts = [arcs[i] if i >= 0 else arcs[~i][::-1] for i in idx]
        return np.vstack(parts)

    lines = []
    for geom in topo['objects']['subunits']['geometries']:
        polys = geom['arcs'] if geom['type'] == 'MultiPolygon' else [geom['arcs']]
        st = geom.get('id', '')
        for poly in polys:
            for r in poly:
                pts = ring(r)
                x, y = project(pts[:, 0], pts[:, 1], np.full(len(pts), st if st in INSETS else ''))
                lines.append([[round(float(a), 1), round(float(b), 1)] for a, b in zip(x, y)])
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--site', default='site')
    args = ap.parse_args(argv)
    out = os.path.join(args.site, 'data')
    os.makedirs(out, exist_ok=True)

    df = load_fires(['FOD_ID', 'FIRE_YEAR', 'DISCOVERY_DATE', 'NWCG_CAUSE_CLASSIFICATION', 'NWCG_GENERAL_CAUSE',
                     'FIRE_SIZE_CLASS', 'STATE', 'LATITUDE', 'LONGITUDE'])
    states = sorted(df['STATE'].astype(str).unique())
    x, y = project(df['LONGITUDE'].to_numpy(), df['LATITUDE'].to_numpy(), df['STATE'].astype(str).to_numpy())
    inside = (x >= 0) & (x < FRAME) & (y >= 0) & (y < FRAME)
    doy = pd.to_datetime(df['DISCOVERY_DATE']).dt.dayofyear.to_numpy() - 1
    cause = df['NWCG_CAUSE_CLASSIFICATION'].astype(str).map({'Human': 0, 'Natural': 1}).fillna(2).to_numpy(np.uint32)
    cls = df['FIRE_SIZE_CLASS'].astype(str).map({c: i for i, c in enumerate(CLASSES)}).to_numpy(np.uint32)
    st = df['STATE'].astype(str).map({s: i for i, s in enumerate(states)}).to_numpy(np.uint32)
    gen = df['NWCG_GENERAL_CAUSE'].astype(str).map({g: i for i, g in enumerate(GENERAL)}).fillna(len(GENERAL) - 1).to_numpy(np.uint32)
    gap = gap_codes(df['FOD_ID'])
    attrs = ((df['FIRE_YEAR'].to_numpy(np.uint32) - 1992)
             | (doy.astype(np.uint32) << 5) | (cause << 14) | (cls << 16) | (gap << 19) | (st << 21) | (gen << 27))
    rec = np.zeros(len(df), dtype=[('x', '<u2'), ('y', '<u2'), ('a', '<u4')])
    rec['x'] = np.clip(np.round(x), 0, FRAME - 1).astype(np.uint16)
    rec['y'] = np.clip(np.round(y), 0, FRAME - 1).astype(np.uint16)
    rec['a'] = attrs
    # Sort by year then day so progressive drawing and time filters read naturally.
    order = np.lexsort((doy, df['FIRE_YEAR'].to_numpy()))
    rec, big, keep = rec[order], (cls >= 2)[order], inside[order]
    files = {'points_c_plus.bin': rec[big & keep], 'points_a_b.bin': rec[~big & keep]}
    for name, r in files.items():
        r.tofile(os.path.join(out, name))
        print(f'{name}: {len(r):,} fires, {r.nbytes / 1e6:.1f} MB')
    meta = {
        'frame': FRAME, 'record_bytes': 8, 'year0': 1992,
        'layout': 'uint16 x, uint16 y, uint32 attrs (little-endian); attrs bits: 0-4 year-1992, 5-13 doy-1, '
                  '14-15 cause (0 human, 1 natural, 2 missing), 16-18 size class (0=A..6=G), 19-20 protection '
                  '(0 GAP1-2, 1 GAP3, 2 GAP4, 3 not in PAD-US), 21-26 state index, 27-30 general cause index',
        'states': states, 'general_causes': GENERAL, 'size_classes': CLASSES, 'protection': GAP_NAMES,
        'files': {k: len(v) for k, v in files.items()}, 'outside_frame': int((~inside).sum()),
        'extent': [0, 0, FRAME, int(np.ceil((Y1 - Y0) * SCALE))],
        'projection': 'ESRI:102003 lower 48; EPSG:3338 x0.35 Alaska inset; ESRI:102007 Hawaii inset; EPSG:32161 Puerto Rico inset',
    }
    with open(os.path.join(out, 'points_meta.json'), 'w') as f:
        json.dump(meta, f, indent=1)
    with open(os.path.join(out, 'outline.json'), 'w') as f:
        json.dump(outlines(), f, separators=(',', ':'))
    print(f'outside frame: {meta["outside_frame"]}; outline and meta written to {out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
