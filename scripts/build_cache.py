"""
Extract the Fires table to a typed Parquet file so every analysis reads columnar data
instead of re-querying the 1 GB SQLite database.

Usage:
    python scripts/build_cache.py            # writes data/fires.parquet

The cache is derived data and is not committed (data/ is git-ignored). It is rebuilt
whenever the database hash changes; the hash is stored in the file's metadata.
"""
import hashlib
import json
import os
import sqlite3
import sys
import time

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
from src.data_loader import DEFAULT_DB_PATH  # noqa: E402

CACHE_PATH = os.path.join(REPO_ROOT, 'data', 'fires.parquet')

COLUMNS = [
    'FOD_ID', 'FPA_ID', 'SOURCE_SYSTEM_TYPE', 'SOURCE_SYSTEM', 'NWCG_REPORTING_AGENCY',
    'NWCG_REPORTING_UNIT_ID', 'NWCG_REPORTING_UNIT_NAME', 'FIRE_NAME',
    'ICS_209_PLUS_INCIDENT_JOIN_ID', 'ICS_209_PLUS_COMPLEX_JOIN_ID', 'MTBS_ID', 'MTBS_FIRE_NAME',
    'COMPLEX_NAME', 'FIRE_YEAR', 'DISCOVERY_DATE', 'DISCOVERY_DOY', 'DISCOVERY_TIME',
    'NWCG_CAUSE_CLASSIFICATION', 'NWCG_GENERAL_CAUSE', 'NWCG_CAUSE_AGE_CATEGORY',
    'CONT_DATE', 'CONT_DOY', 'CONT_TIME', 'FIRE_SIZE', 'FIRE_SIZE_CLASS',
    'LATITUDE', 'LONGITUDE', 'OWNER_DESCR', 'STATE', 'COUNTY', 'FIPS_CODE', 'FIPS_NAME',
]


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def parse_datetime(date: pd.Series, time_str: pd.Series) -> pd.Series:
    """Combine 'MM/DD/YYYY' and 'HHMM' into a timestamp; NaT when either part is missing or invalid."""
    d = pd.to_datetime(date, format='%m/%d/%Y', errors='coerce')
    t = time_str.fillna('').astype(str).str.strip()
    ok = t.str.fullmatch(r'\d{4}')
    hh = pd.to_numeric(t.str[:2].where(ok), errors='coerce')
    mm = pd.to_numeric(t.str[2:].where(ok), errors='coerce')
    ok = ok & (hh < 24) & (mm < 60)
    return (d + pd.to_timedelta(hh, unit='h') + pd.to_timedelta(mm, unit='m')).where(ok)


def build(db_path: str = None, cache_path: str = CACHE_PATH) -> str:
    db_path = db_path or os.environ.get('WILDFIRE_DB_PATH', DEFAULT_DB_PATH)
    t0 = time.time()
    db_hash = sha256(db_path)
    if os.path.exists(cache_path):
        meta = pq.read_schema(cache_path).metadata or {}
        if meta.get(b'db_sha256', b'').decode() == db_hash:
            print(f'{cache_path} is up to date (db {db_hash[:8]}).')
            return cache_path
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(f'SELECT {", ".join(COLUMNS)} FROM Fires', conn)
    conn.close()
    print(f'Read {len(df):,} rows in {time.time() - t0:.0f}s')

    for c in ['DISCOVERY_DATE', 'CONT_DATE']:
        df[c] = pd.to_datetime(df[c], format='%m/%d/%Y', errors='coerce')
    df['DISCOVERY_DATETIME'] = parse_datetime(df['DISCOVERY_DATE'].dt.strftime('%m/%d/%Y'), df['DISCOVERY_TIME'])
    df['CONT_DATETIME'] = parse_datetime(df['CONT_DATE'].dt.strftime('%m/%d/%Y'), df['CONT_TIME'])
    df['DURATION_DAYS'] = (df['CONT_DATE'] - df['DISCOVERY_DATE']).dt.days
    df['DURATION_HOURS'] = (df['CONT_DATETIME'] - df['DISCOVERY_DATETIME']).dt.total_seconds() / 3600
    df['DISCOVERY_MONTH'] = df['DISCOVERY_DATE'].dt.month.astype('Int8')
    for c in ['SOURCE_SYSTEM_TYPE', 'NWCG_REPORTING_AGENCY', 'NWCG_CAUSE_CLASSIFICATION',
              'NWCG_GENERAL_CAUSE', 'NWCG_CAUSE_AGE_CATEGORY', 'FIRE_SIZE_CLASS', 'OWNER_DESCR', 'STATE']:
        df[c] = df[c].astype('category')

    table = pa.Table.from_pandas(df, preserve_index=False)
    meta = dict(table.schema.metadata or {})
    meta[b'db_sha256'] = db_hash.encode()
    meta[b'built'] = time.strftime('%Y-%m-%d').encode()
    meta[b'columns_note'] = json.dumps({
        'DURATION_DAYS': 'CONT_DATE - DISCOVERY_DATE in whole days (NaN when CONT_DATE missing)',
        'DURATION_HOURS': 'CONT_DATETIME - DISCOVERY_DATETIME in hours (NaN unless both dates and times valid)',
    }).encode()
    table = table.replace_schema_metadata(meta)
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    pq.write_table(table, cache_path, compression='zstd')
    print(f'Wrote {cache_path} ({os.path.getsize(cache_path) / 1e6:.0f} MB) in {time.time() - t0:.0f}s')
    return cache_path


if __name__ == '__main__':
    build()
