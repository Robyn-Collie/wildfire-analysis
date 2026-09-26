"""
Shared fixtures for the test suite.

The real FPA FOD database is 1 GB and is not available in CI, so every test runs
against a tiny synthetic SQLite file built here. The synthetic table `Fires` has the
same column names and declared types as the real one (minus the OBJECTID/Shape
geometry columns and the SOURCE_REPORTING_* / LOCAL_* / FIRE_CODE columns that no
code in this repo reads). Rows are generated deterministically from a fixed seed
plus a handful of hand-set rows whose ids are exported as constants below.

Observed format of the real file (data/FPA_FOD_20221014.sqlite, PRAGMA table_info and
SELECT ... LIMIT 3): dates are unpadded 'M/D/YYYY' text such as '2/2/2005', times are
zero-padded 'HHMM' text such as '0845'. The synthetic rows use the same formats.
"""
import os
import sqlite3
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

# Headless matplotlib. src.train_model imports pyplot at module import time, so this
# has to happen before any test module imports it. pytest.ini cannot set env vars
# without the pytest-env plugin, hence it lives here.
os.environ.setdefault('MPLBACKEND', 'Agg')

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# The 13 NWCG_GENERAL_CAUSE values in the real table (SELECT DISTINCT NWCG_GENERAL_CAUSE).
CAUSES = [
    'Arson/incendiarism',
    'Debris and open burning',
    'Equipment and vehicle use',
    'Firearms and explosives use',
    'Fireworks',
    'Missing data/not specified/undetermined',
    'Misuse of fire by a minor',
    'Natural',
    'Other causes',
    'Power generation/transmission/distribution',
    'Railroad operations and maintenance',
    'Recreation and ceremony',
    'Smoking',
]
STATES = ['CA', 'TX', 'AK', 'GA', 'NY', 'OR', 'AZ', 'FL', 'CO', 'MT', 'NC', 'PA', 'WA', 'MS', 'ID', 'HI']
AGENCIES = ['FS', 'BLM', 'ST/C&L', 'NPS', 'FWS', 'BIA']
OWNERS = ['USFS', 'PRIVATE', 'BLM', 'STATE OR PRIVATE', 'MISSING/NOT SPECIFIED']
SOURCE_TYPES = ['FED', 'NONFED', 'INTERAGCY']
YEARS = list(range(2005, 2021))  # 16 years, 2005-2020, four of them leap years

N_ROWS = 300
FOD_ID_BASE = 1000

# Hand-set rows (FOD_ID = FOD_ID_BASE + i). Tests import these by name.
KNOWN_ROW_2006 = 1001      # 3/1/2006 08:30 -> 3/3/2006 14:15: 2 days, 53.75 hours (FIRE_YEAR < 2010)
KNOWN_ROW_2010 = 1021      # 6/15/2010 14:00 -> 6/20/2010 09:00: 5 days, 115 hours
NEGATIVE_DURATION_ID = 1005  # CONT_DATE two days before DISCOVERY_DATE (FIRE_YEAR 2010)
INVALID_TIME_ID = 1012     # DISCOVERY_TIME '2560' (hour 25 is impossible)
MISSING_DISC_TIME_ID = 1013  # DISCOVERY_TIME NULL
MISSING_CONT_TIME_ID = 1006  # CONT_TIME NULL
MISSING_CONT_DATE_ID = 1007  # CONT_DATE NULL (FIRE_YEAR 2012, so it is dropped by load_data)

# The columns and declared types of the real table, in the real order (PRAGMA table_info).
COLUMN_TYPES = [
    ('FOD_ID', 'int32'), ('FPA_ID', 'text(100)'), ('SOURCE_SYSTEM_TYPE', 'text(255)'),
    ('SOURCE_SYSTEM', 'text(30)'), ('NWCG_REPORTING_AGENCY', 'text(255)'),
    ('NWCG_REPORTING_UNIT_ID', 'text(255)'), ('NWCG_REPORTING_UNIT_NAME', 'text(255)'),
    ('FIRE_NAME', 'text(255)'), ('ICS_209_PLUS_INCIDENT_JOIN_ID', 'text(255)'),
    ('ICS_209_PLUS_COMPLEX_JOIN_ID', 'text(255)'), ('MTBS_ID', 'text(255)'),
    ('MTBS_FIRE_NAME', 'text(50)'), ('COMPLEX_NAME', 'text(255)'), ('FIRE_YEAR', 'int16'),
    ('DISCOVERY_DATE', 'text(10)'), ('DISCOVERY_DOY', 'int32'), ('DISCOVERY_TIME', 'text(4)'),
    ('NWCG_CAUSE_CLASSIFICATION', 'text(255)'), ('NWCG_GENERAL_CAUSE', 'text(255)'),
    ('NWCG_CAUSE_AGE_CATEGORY', 'text(255)'), ('CONT_DATE', 'text(10)'), ('CONT_DOY', 'int32'),
    ('CONT_TIME', 'text(4)'), ('FIRE_SIZE', 'float64'), ('FIRE_SIZE_CLASS', 'text(1)'),
    ('LATITUDE', 'float64'), ('LONGITUDE', 'float64'), ('OWNER_DESCR', 'text(100)'),
    ('STATE', 'text(255)'), ('COUNTY', 'text(255)'), ('FIPS_CODE', 'text(255)'),
    ('FIPS_NAME', 'text(255)'),
]
COLUMNS = [c for c, _ in COLUMN_TYPES]


def fmt_date(d: date) -> str:
    """Unpadded M/D/YYYY, exactly as the real file stores it ('2/2/2005')."""
    return f'{d.month}/{d.day}/{d.year}'


def fire_size_class(acres: float) -> str:
    """FPA FOD size classes: A <= 0.25, B 0.26-9.9, C 10-99.9, D 100-299, E 300-999, F 1000-4999, G 5000+."""
    if acres <= 0.25:
        return 'A'
    if acres < 10:
        return 'B'
    if acres < 100:
        return 'C'
    if acres < 300:
        return 'D'
    if acres < 1000:
        return 'E'
    if acres < 5000:
        return 'F'
    return 'G'


def cause_classification(cause: str) -> str:
    if cause == 'Natural':
        return 'Natural'
    if cause == 'Missing data/not specified/undetermined':
        return 'Missing data/not specified/undetermined'
    return 'Human'


def make_rows() -> pd.DataFrame:
    """Deterministic synthetic Fires rows. Same call, same frame, every time."""
    rng = np.random.default_rng(20221014)
    rows = []
    for i in range(N_ROWS):
        year = YEARS[i % len(YEARS)]
        leap = (year % 4 == 0) and (year % 100 != 0 or year % 400 == 0)
        cause = CAUSES[i % len(CAUSES)]

        # Discovery date. Every 24th row starting at i=3 lands on a leap year (i % 16 in {3, 11}
        # -> 2008 or 2016) and is pinned to Dec 31 so DISCOVERY_DOY == 366.
        if i % 24 == 3:
            assert leap, (i, year)
            disc = date(year, 12, 31)
        else:
            disc = date(year, 1, 1) + timedelta(days=int(rng.integers(0, 365)))

        # Duration in whole days: mostly 0, a tail out to 400.
        p = rng.random()
        if p < 0.60:
            dur = 0
        elif p < 0.80:
            dur = int(rng.integers(1, 4))
        elif p < 0.95:
            dur = int(rng.integers(4, 31))
        elif p < 0.99:
            dur = int(rng.integers(31, 121))
        else:
            dur = 400
        cont = None if i % 10 == 7 else disc + timedelta(days=dur)

        disc_time = None if i % 9 == 4 else f'{int(rng.integers(0, 24)):02d}{int(rng.integers(0, 60)):02d}'
        cont_time = None if (cont is None or i % 11 == 6) else \
            f'{int(rng.integers(0, 24)):02d}{int(rng.integers(0, 60)):02d}'

        acres = round(float(10 ** rng.uniform(-2, 4.5)), 2)
        rows.append({
            'FOD_ID': FOD_ID_BASE + i,
            'FPA_ID': f'FS-{i}',
            'SOURCE_SYSTEM_TYPE': SOURCE_TYPES[i % 3],
            'SOURCE_SYSTEM': 'FS-FIRESTAT',
            'NWCG_REPORTING_AGENCY': AGENCIES[i % len(AGENCIES)],
            'NWCG_REPORTING_UNIT_ID': f'US{STATES[i % len(STATES)]}{i % 7:03d}',
            'NWCG_REPORTING_UNIT_NAME': f'Unit {i % 7}',
            'FIRE_NAME': f'FIRE {i}',
            'ICS_209_PLUS_INCIDENT_JOIN_ID': f'{year}_{i}' if acres >= 1000 else None,
            'ICS_209_PLUS_COMPLEX_JOIN_ID': None,
            'MTBS_ID': f'MT{i}' if acres >= 1000 else None,
            'MTBS_FIRE_NAME': f'FIRE {i}' if acres >= 1000 else None,
            'COMPLEX_NAME': None,
            'FIRE_YEAR': year,
            'DISCOVERY_DATE': fmt_date(disc),
            'DISCOVERY_DOY': disc.timetuple().tm_yday,
            'DISCOVERY_TIME': disc_time,
            'NWCG_CAUSE_CLASSIFICATION': cause_classification(cause),
            'NWCG_GENERAL_CAUSE': cause,
            'NWCG_CAUSE_AGE_CATEGORY': 'Minor' if cause == 'Misuse of fire by a minor' else None,
            'CONT_DATE': None if cont is None else fmt_date(cont),
            'CONT_DOY': None if cont is None else cont.timetuple().tm_yday,
            'CONT_TIME': cont_time,
            'FIRE_SIZE': acres,
            'FIRE_SIZE_CLASS': fire_size_class(acres),
            'LATITUDE': round(25 + 45 * float(rng.random()), 4),
            'LONGITUDE': round(-160 + 95 * float(rng.random()), 4),
            'OWNER_DESCR': OWNERS[i % len(OWNERS)],
            'STATE': STATES[i % len(STATES)],
            'COUNTY': f'{i % 50}',
            'FIPS_CODE': f'{i % 50:05d}',
            'FIPS_NAME': f'County {i % 50}',
        })

    df = pd.DataFrame(rows, columns=COLUMNS).set_index('FOD_ID', drop=False)

    # Hand-set rows so tests can assert exact values.
    def set_row(fod_id, disc, disc_time, cont, cont_time):
        df.loc[fod_id, ['DISCOVERY_DATE', 'DISCOVERY_DOY', 'DISCOVERY_TIME']] = [
            fmt_date(disc), disc.timetuple().tm_yday, disc_time]
        df.loc[fod_id, ['CONT_DATE', 'CONT_DOY', 'CONT_TIME']] = [
            None if cont is None else fmt_date(cont), None if cont is None else cont.timetuple().tm_yday, cont_time]

    set_row(KNOWN_ROW_2006, date(2006, 3, 1), '0830', date(2006, 3, 3), '1415')
    set_row(KNOWN_ROW_2010, date(2010, 6, 15), '1400', date(2010, 6, 20), '0900')
    set_row(NEGATIVE_DURATION_ID, date(2010, 8, 10), '1200', date(2010, 8, 8), '1200')
    set_row(INVALID_TIME_ID, date(2017, 4, 2), '2560', date(2017, 4, 2), '1800')

    # Sanity checks on the generator itself (not on the code under test).
    assert int(df.loc[KNOWN_ROW_2006, 'FIRE_YEAR']) == 2006
    assert int(df.loc[KNOWN_ROW_2010, 'FIRE_YEAR']) == 2010
    assert int(df.loc[NEGATIVE_DURATION_ID, 'FIRE_YEAR']) == 2010
    assert int(df.loc[INVALID_TIME_ID, 'FIRE_YEAR']) == 2017
    assert pd.isna(df.loc[MISSING_DISC_TIME_ID, 'DISCOVERY_TIME'])
    assert pd.isna(df.loc[MISSING_CONT_TIME_ID, 'CONT_TIME'])
    assert pd.isna(df.loc[MISSING_CONT_DATE_ID, 'CONT_DATE'])
    model_subset = df[(df['FIRE_YEAR'] >= 2010) & df['CONT_DATE'].notna()]
    assert set(model_subset['NWCG_GENERAL_CAUSE']) == set(CAUSES)
    assert (df['DISCOVERY_DOY'] == 366).sum() >= 5
    assert set(df['FIRE_SIZE_CLASS']) == set('ABCDEFG')
    return df


def write_sqlite(df: pd.DataFrame, path: str) -> None:
    conn = sqlite3.connect(path)
    try:
        cols_sql = ', '.join(f'"{c}" {t}' for c, t in COLUMN_TYPES)
        conn.execute(f'CREATE TABLE Fires (OBJECTID INTEGER PRIMARY KEY, {cols_sql})')
        placeholders = ', '.join('?' for _ in COLUMNS)
        records = [tuple(None if pd.isna(v) else (v.item() if hasattr(v, 'item') else v) for v in row)
                   for row in df[COLUMNS].itertuples(index=False, name=None)]
        conn.executemany(f'INSERT INTO Fires ({", ".join(COLUMNS)}) VALUES ({placeholders})', records)
        conn.commit()
    finally:
        conn.close()


@pytest.fixture(scope='session')
def synthetic_rows() -> pd.DataFrame:
    """Ground truth: the frame that was written to the synthetic database, indexed by FOD_ID."""
    return make_rows()


@pytest.fixture(scope='session')
def synthetic_db_path(tmp_path_factory, synthetic_rows) -> str:
    """Path to a synthetic FPA FOD SQLite file with a `Fires` table of N_ROWS rows."""
    path = str(tmp_path_factory.mktemp('fpa_fod') / 'FPA_FOD_synthetic.sqlite')
    write_sqlite(synthetic_rows, path)
    return path


@pytest.fixture(autouse=True)
def wildfire_db_env(monkeypatch, synthetic_db_path) -> str:
    """Every test sees WILDFIRE_DB_PATH pointing at the synthetic file, never at data/."""
    monkeypatch.setenv('WILDFIRE_DB_PATH', synthetic_db_path)
    return synthetic_db_path


@pytest.fixture
def loaded_df(synthetic_db_path) -> pd.DataFrame:
    """What src.data_loader.load_data returns for the synthetic database."""
    from src.data_loader import load_data
    return load_data(synthetic_db_path)
