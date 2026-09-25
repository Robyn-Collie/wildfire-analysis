#!/usr/bin/env python
"""Download the FPA FOD-Attributes annual CSVs (Pourmohamad et al. 2024, Zenodo 8381129) for
2010-2020 and build data/attributes_2010_2020.parquet with the at-discovery columns the
large-fire model uses.

Usage (from the repo root):
    .venv/bin/python scripts/download_attributes.py            # download + convert
    .venv/bin/python scripts/download_attributes.py --skip-download
    .venv/bin/python scripts/download_attributes.py --years 2010 2011

What it does
1. For each year, streams https://zenodo.org/api/records/8381129/files/<YYYY>_FPA_FOD_cons.csv/content
   into data/external/fpa_fod_attributes/<YYYY>_FPA_FOD_cons.csv.part (curl, resumable, retried),
   renames it on success, records the byte size, MD5 (compared with the Zenodo record's checksum)
   and SHA-256 into SHA256SUMS in that directory, and prints them.
2. Reads each CSV with duckdb (2 threads, 3 GB memory cap), keeps FOD_ID, FIRE_YEAR and the
   ATTRIBUTE_COLUMNS listed below, drops duplicated FOD_IDs (first row kept), checks the FOD_ID join
   against data/fires.parquet for that year (recorded in outputs/model/attributes_join.csv; the
   files are not row-for-row identical to FPA FOD v6, see the log), and appends to
   data/attributes_2010_2020.parquet.
3. Writes null rates per column per year to outputs/model/attributes_nulls.csv.
4. Deletes each CSV after conversion only when free disk on the data volume is below 8 GB.

Excluded on purpose: every *_5D_* column (the 5-day window is centred on discovery and so uses two
post-discovery days), the CEJST block (columns 84-190 of the file), the point-scale LANDFIRE
fields where a 1 km version exists (location precision is one PLSS section), Mang_Name, TRACT and
geometry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECORD = 'https://zenodo.org/api/records/8381129'
FILE_URL = RECORD + '/files/{year}_FPA_FOD_cons.csv/content'
EXT_DIR = os.path.join(REPO, 'data', 'external', 'fpa_fod_attributes')
OUT_PARQUET = os.path.join(REPO, 'data', 'attributes_2010_2020.parquet')
FIRES_PARQUET = os.path.join(REPO, 'data', 'fires.parquet')
NULLS_CSV = os.path.join(REPO, 'outputs', 'model', 'attributes_nulls.csv')
JOIN_CSV = os.path.join(REPO, 'outputs', 'model', 'attributes_join.csv')
YEARS = list(range(2010, 2021))
KEEP_CSV_IF_FREE_GB = 8.0

# Column groups kept from the 308-column file. Names are exactly as in the CSV header.
ATTRIBUTE_COLUMNS: dict[str, list[str]] = {
    'weather_same_day': ['pr', 'tmmn', 'tmmx', 'rmin', 'rmax', 'sph', 'vs', 'th', 'srad', 'etr',
                         'fm100', 'fm1000', 'bi', 'vpd', 'erc'],
    'climate_normals': ['pr_Normal', 'tmmn_Normal', 'tmmx_Normal', 'rmin_Normal', 'rmax_Normal', 'sph_Normal',
                        'srad_Normal', 'fm100_Normal', 'fm1000_Normal', 'bi_Normal', 'vpd_Normal', 'erc_Normal'],
    'climate_percentiles': ['tmmn_Percentile', 'tmmx_Percentile', 'sph_Percentile', 'vs_Percentile',
                            'fm100_Percentile', 'bi_Percentile', 'vpd_Percentile', 'erc_Percentile'],
    'climate_annual': ['Annual_etr', 'Annual_precipitation', 'Annual_tempreture', 'Aridity_index'],
    'terrain': ['Elevation', 'Slope', 'Aspect', 'TPI', 'TRI',
                'Elevation_1km', 'Slope_1km', 'Aspect_1km', 'TPI_1km', 'TRI_1km'],
    'fuels_vegetation': ['EVT_1km', 'EVC_1km', 'EVH_1km', 'FRG_1km', 'Land_Cover_1km', 'rpms_1km',
                         'MOD_NDVI_12m', 'NDVI-1day'],
    'protection': ['GAP_Sts', 'GAP_Prity', 'Mang_Type', 'Des_Tp'],
    'ecoregion': ['Ecoregion_US_L3CODE', 'Ecoregion_NA_L1CODE', 'NAME'],
    'social': ['RPL_THEMES', 'Population', 'Popo_1km', 'GHM'],
    'suppression_context': ['No_FireStation_1.0km', 'No_FireStation_5.0km', 'No_FireStation_10.0km',
                            'No_FireStation_20.0km', 'road_county_dis', 'road_interstate_dis',
                            'road_common_name_dis', 'road_other_dis', 'road_state_dis', 'road_US_dis',
                            'SDI', 'Evacuation', 'NPL'],
    'gacc_preparedness': ['GACCAbbrev', 'GACC_PL', 'GACC_New fire', 'GACC_Uncont LF',
                          'GACC_Type 1 IMTs', 'GACC_Type 2 IMTs'],
}
ALL_COLUMNS = [c for cols in ATTRIBUTE_COLUMNS.values() for c in cols]
assert len(ALL_COLUMNS) == len(set(ALL_COLUMNS))

# Cleaning applied during conversion (found by inspecting the 2010-2020 files, see docs/findings/large_fire_model.md):
#   * EVT_1km, EVC_1km, EVH_1km, FRG_1km, Land_Cover_1km are composition strings such as
#     "7299(43%) / 7297(23%) / 7298(14%)": the dominant class code is kept as <col> and its share as
#     <col>_share (per cent). Only the dominant class is retained.
#   * MOD_NDVI_12m is a string of 12 monthly NDVI values ("'0.18' '0.18' ..."): kept as
#     MOD_NDVI_12m_mean and MOD_NDVI_12m_max.
#   * "GACC_New fire" and "GACC_Uncont LF" contain blank strings: cast to numbers, blanks become NULL.
#   * Nodata sentinels become NULL: Elevation/Slope/Aspect = 32767; RPL_THEMES = -999;
#     Population = -99999; GHM and SDI < -1e30.
COMPOSITION_COLUMNS = ['EVT_1km', 'EVC_1km', 'EVH_1km', 'FRG_1km', 'Land_Cover_1km']
SENTINEL_NULL = {'Elevation': '= 32767', 'Slope': '= 32767', 'Aspect': '= 32767', 'RPL_THEMES': '= -999',
                 'Population': '= -99999', 'GHM': '< -1e30', 'SDI': '< -1e30'}
NUMERIC_TEXT = ['GACC_New fire', 'GACC_Uncont LF']


def select_expressions() -> list[str]:
    """SQL expressions (one or two per source column) implementing the cleaning above."""
    out = []
    for c in ALL_COLUMNS:
        q = f'"{c}"'
        if c in COMPOSITION_COLUMNS:
            out.append(f"try_cast(regexp_extract({q}::VARCHAR, '^\\s*([0-9.-]+)', 1) AS DOUBLE)::INTEGER AS {q}")
            out.append(f"try_cast(regexp_extract({q}::VARCHAR, '\\((\\d+)%\\)', 1) AS INTEGER) AS \"{c}_share\"")
        elif c == 'MOD_NDVI_12m':
            lst = f"list_transform(regexp_extract_all({q}::VARCHAR, '[-0-9.]+'), x -> try_cast(x AS DOUBLE))"
            out.append(f"list_aggregate({lst}, 'avg') AS \"MOD_NDVI_12m_mean\"")
            out.append(f"list_aggregate({lst}, 'max') AS \"MOD_NDVI_12m_max\"")
        elif c in NUMERIC_TEXT:
            out.append(f"try_cast(trim({q}::VARCHAR) AS DOUBLE) AS {q}")
        elif c in SENTINEL_NULL:
            out.append(f"CASE WHEN {q} {SENTINEL_NULL[c]} THEN NULL ELSE {q} END AS {q}")
        else:
            out.append(q)
    return out


def log(msg: str) -> None:
    print(time.strftime('%H:%M:%S'), msg, flush=True)


def free_gb(path: str) -> float:
    return shutil.disk_usage(path).free / 1e9


def file_hashes(path: str) -> tuple[str, str]:
    md5, sha = hashlib.md5(), hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            md5.update(chunk)
            sha.update(chunk)
    return md5.hexdigest(), sha.hexdigest()


def zenodo_checksums() -> dict[str, tuple[int, str]]:
    """Return {file name: (size bytes, md5)} from the Zenodo record, or {} if the API is unreachable."""
    try:
        with urllib.request.urlopen(RECORD, timeout=60) as r:
            rec = json.load(r)
        return {f['key']: (int(f['size']), f['checksum'].replace('md5:', '')) for f in rec['files']}
    except Exception as exc:  # noqa: BLE001
        log(f'could not read Zenodo record metadata ({exc}); MD5 will not be checked')
        return {}


def download_year(year: int, expected: dict[str, tuple[int, str]]) -> dict:
    name = f'{year}_FPA_FOD_cons.csv'
    final = os.path.join(EXT_DIR, name)
    part = final + '.part'
    if not os.path.exists(final):
        url = FILE_URL.format(year=year)
        log(f'downloading {name}')
        for attempt in range(1, 6):
            cmd = ['curl', '--fail', '--location', '--silent', '--show-error', '--retry', '5',
                   '--retry-all-errors', '--continue-at', '-', '--output', part, url]
            rc = subprocess.call(cmd)
            if rc == 0:
                break
            log(f'  curl exit {rc} on attempt {attempt}; retrying')
            time.sleep(10 * attempt)
        else:
            raise RuntimeError(f'download failed for {name}')
        os.replace(part, final)
    size = os.path.getsize(final)
    md5, sha = file_hashes(final)
    status = 'md5 not checked'
    if name in expected:
        exp_size, exp_md5 = expected[name]
        if size != exp_size or md5 != exp_md5:
            os.remove(final)
            raise RuntimeError(f'{name}: size {size} vs {exp_size}, md5 {md5} vs {exp_md5}; file removed, rerun')
        status = 'md5 matches Zenodo'
    log(f'  {name}: {size:,} bytes  sha256 {sha}  ({status})')
    return {'file': name, 'bytes': size, 'md5': md5, 'sha256': sha}


def write_sums(rows: list[dict]) -> None:
    path = os.path.join(EXT_DIR, 'SHA256SUMS')
    existing: dict[str, str] = {}
    if os.path.exists(path):
        for line in open(path):
            parts = line.split()
            if len(parts) >= 2:
                existing[parts[1].lstrip('*')] = line.rstrip('\n')
    for r in rows:
        existing[r['file']] = f"{r['sha256']}  {r['file']}  # {r['bytes']} bytes, md5 {r['md5']}"
    with open(path, 'w') as f:
        for k in sorted(existing):
            f.write(existing[k] + '\n')


def convert(years: list[int], delete_csv: bool) -> None:
    import duckdb
    import pandas as pd

    con = duckdb.connect()
    con.execute('SET threads=2')
    con.execute("SET memory_limit='3GB'")
    con.execute(f"SET temp_directory='{os.path.join(EXT_DIR, 'duckdb_tmp')}'")
    parts_dir = os.path.join(EXT_DIR, 'parquet_by_year')
    os.makedirs(parts_dir, exist_ok=True)
    null_rows = []
    join_rows = []
    quoted = ', '.join(select_expressions())
    for year in years:
        csv = os.path.join(EXT_DIR, f'{year}_FPA_FOD_cons.csv')
        out = os.path.join(parts_dir, f'{year}.parquet')
        if not os.path.exists(csv) and os.path.exists(out):
            log(f'{year}: CSV gone, keeping existing {out}')
        else:
            t0 = time.time()
            # Full-file sniffing so that columns that are empty for early years are typed by their values.
            con.execute(f"""
                COPY (SELECT FOD_ID::BIGINT AS FOD_ID, FIRE_YEAR::SMALLINT AS FIRE_YEAR, {quoted}
                      FROM read_csv('{csv}', header=true, sample_size=-1, ignore_errors=false)
                      QUALIFY row_number() OVER (PARTITION BY FOD_ID) = 1
                      ORDER BY FOD_ID)
                TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """)
            log(f'{year}: converted in {time.time() - t0:.0f}s')
        # Join check against fires.parquet for the same year. The annual files are not row-for-row
        # identical to FPA FOD v6 (2011 has one fire that v6 lacks; 2019 lacks 1,009 v6 rows; 2020 has
        # 8 duplicated FOD_IDs), so the result is recorded, not enforced.
        chk = con.execute(f"""
            WITH a AS (SELECT DISTINCT FOD_ID FROM read_parquet('{out}')),
                 f AS (SELECT FOD_ID FROM read_parquet('{FIRES_PARQUET}') WHERE FIRE_YEAR = {year})
            SELECT (SELECT count(*) FROM read_parquet('{out}')) AS n_attr_rows,
                   (SELECT count(*) FROM a) AS n_attr_distinct,
                   (SELECT count(*) FROM f) AS n_fires,
                   (SELECT count(*) FROM a JOIN f USING (FOD_ID)) AS n_joined,
                   (SELECT count(*) FROM a ANTI JOIN f USING (FOD_ID)) AS n_attr_only,
                   (SELECT count(*) FROM f ANTI JOIN a USING (FOD_ID)) AS n_fires_only
        """).fetchone()
        n_rows, n_distinct, n_fires, n_joined, n_attr_only, n_fires_only = chk
        join_rows.append({'year': year, 'attribute_rows': n_rows, 'attribute_distinct_fod_id': n_distinct,
                          'fires_parquet_rows': n_fires, 'joined': n_joined, 'attribute_only': n_attr_only,
                          'fires_only': n_fires_only, 'join_rate_of_fires': n_joined / n_fires})
        log(f'{year}: attribute rows {n_rows:,} (distinct {n_distinct:,}), fires.parquet rows {n_fires:,}, '
            f'joined {n_joined:,} ({n_joined / n_fires:.4%} of fires); attribute-only {n_attr_only}, '
            f'fires-only {n_fires_only}')
        out_cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{out}')").fetchall()
                    if r[0] not in ('FOD_ID', 'FIRE_YEAR')]
        nulls = con.execute(
            'SELECT ' + ', '.join(f'avg(CASE WHEN "{c}" IS NULL THEN 1.0 ELSE 0.0 END) AS "{c}"' for c in out_cols)
            + f" FROM read_parquet('{out}')").df().iloc[0]
        for c in out_cols:
            null_rows.append({'year': year, 'column': c, 'null_rate': float(nulls[c])})
        if delete_csv and os.path.exists(csv):
            os.remove(csv)
            log(f'{year}: CSV deleted (free disk was below {KEEP_CSV_IF_FREE_GB} GB)')
    t0 = time.time()
    # 56 FOD_IDs (2020 fires in FPA FOD v6) appear in both the 2019 and 2020 files; keep the row whose
    # FIRE_YEAR matches fires.parquet, else the first.
    con.execute(f"""
        COPY (SELECT a.* FROM read_parquet('{parts_dir}/*.parquet') a
              LEFT JOIN (SELECT FOD_ID, FIRE_YEAR AS fy FROM read_parquet('{FIRES_PARQUET}')) f USING (FOD_ID)
              QUALIFY row_number() OVER (PARTITION BY a.FOD_ID ORDER BY (a.FIRE_YEAR = f.fy) DESC, a.FIRE_YEAR) = 1
              ORDER BY a.FOD_ID)
        TO '{OUT_PARQUET}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)
    n_dup = con.execute(f"""SELECT count(*) - count(DISTINCT FOD_ID) FROM read_parquet('{parts_dir}/*.parquet')""").fetchone()[0]
    log(f'cross-year duplicate FOD_IDs collapsed: {n_dup}')
    n = con.execute(f"SELECT count(*) FROM read_parquet('{OUT_PARQUET}')").fetchone()[0]
    log(f'wrote {OUT_PARQUET}: {n:,} rows, {os.path.getsize(OUT_PARQUET) / 1e6:.0f} MB in {time.time() - t0:.0f}s')
    os.makedirs(os.path.dirname(NULLS_CSV), exist_ok=True)
    nulls_df = pd.DataFrame(null_rows)
    group_of = {c: g for g, cols in ATTRIBUTE_COLUMNS.items() for c in cols}
    nulls_df['group'] = nulls_df['column'].str.replace(r'_(share|mean|max)$', '', regex=True).map(group_of)
    nulls_df.to_csv(NULLS_CSV, index=False)
    join_df = pd.DataFrame(join_rows)
    join_df.to_csv(JOIN_CSV, index=False)
    log('FOD_ID join against fires.parquet by year:')
    print(join_df.to_string(index=False))
    wide = nulls_df.pivot(index='column', columns='year', values='null_rate')
    log('null rate per column (mean over years), worst 15:')
    print(wide.mean(axis=1).sort_values(ascending=False).head(15).round(3).to_string())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--years', nargs='+', type=int, default=YEARS)
    ap.add_argument('--skip-download', action='store_true')
    ap.add_argument('--skip-convert', action='store_true')
    args = ap.parse_args(argv)
    os.makedirs(EXT_DIR, exist_ok=True)
    if not args.skip_download:
        expected = zenodo_checksums()
        rows = []
        for y in args.years:
            rows.append(download_year(y, expected))
            write_sums(rows)
        log('SHA256SUMS written to ' + os.path.join(EXT_DIR, 'SHA256SUMS'))
    if not args.skip_convert:
        free = free_gb(EXT_DIR)
        delete_csv = free < KEEP_CSV_IF_FREE_GB
        log(f'free disk {free:.1f} GB -> {"deleting" if delete_csv else "keeping"} CSVs after conversion')
        convert(args.years, delete_csv)
    return 0


if __name__ == '__main__':
    sys.exit(main())
