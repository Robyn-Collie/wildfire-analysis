"""Tests for src/data_loader.py against the synthetic database (no real DB needed)."""
import os
import sqlite3

import pandas as pd
import pytest

from src.data_loader import DB_FILENAME, DEFAULT_DB_PATH, MISSING_DB_HELP, load_data
from conftest import write_sqlite

EXPECTED_COLUMNS = ['FOD_ID', 'FIRE_YEAR', 'DISCOVERY_DATE', 'DISCOVERY_DOY', 'CONT_DATE',
                    'LATITUDE', 'LONGITUDE', 'FIRE_SIZE_CLASS', 'NWCG_GENERAL_CAUSE']


def test_default_path_points_into_repo_data_dir():
    assert DEFAULT_DB_PATH.endswith(os.path.join('data', DB_FILENAME))


def test_load_data_returns_only_2010_plus_with_containment_date(synthetic_db_path, synthetic_rows):
    df = load_data(synthetic_db_path)

    expected = synthetic_rows[(synthetic_rows['FIRE_YEAR'] >= 2010) & synthetic_rows['CONT_DATE'].notna()]
    assert len(df) == len(expected)
    assert 0 < len(df) < len(synthetic_rows), 'the filter must drop something but not everything'
    assert (df['FIRE_YEAR'] >= 2010).all()
    assert df['CONT_DATE'].notna().all()
    # Same rows, ordered by FOD_ID (the synthetic table is written in FOD_ID order).
    expected = expected.sort_index()  # the frame is indexed by FOD_ID
    assert df['FOD_ID'].tolist() == expected['FOD_ID'].tolist()
    assert df['DISCOVERY_DATE'].tolist() == expected['DISCOVERY_DATE'].tolist()
    assert df['NWCG_GENERAL_CAUSE'].tolist() == expected['NWCG_GENERAL_CAUSE'].tolist()


def test_load_data_orders_by_fod_id_not_physical_row_order(synthetic_rows, tmp_path):
    # The same rows inserted in reverse order must come back in the same FOD_ID order, so
    # the position-based split does not depend on the file's physical layout.
    path = str(tmp_path / 'reversed.sqlite')
    write_sqlite(synthetic_rows.iloc[::-1], path)
    df = load_data(path)
    assert df['FOD_ID'].is_monotonic_increasing and df['FOD_ID'].is_unique
    pd.testing.assert_frame_equal(df, load_data(str(tmp_path / 'reversed.sqlite')))
    assert df['FOD_ID'].tolist() == sorted(
        synthetic_rows[(synthetic_rows['FIRE_YEAR'] >= 2010) & synthetic_rows['CONT_DATE'].notna()]['FOD_ID'])


def test_load_data_selects_exactly_the_model_columns(loaded_df):
    assert list(loaded_df.columns) == EXPECTED_COLUMNS


def test_load_data_keeps_dates_as_text(loaded_df):
    # The loader does no parsing; features.py does. Dates arrive as 'M/D/YYYY' strings.
    assert loaded_df['DISCOVERY_DATE'].map(lambda s: isinstance(s, str)).all()
    assert loaded_df['DISCOVERY_DATE'].str.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}').all()
    assert pd.api.types.is_integer_dtype(loaded_df['FIRE_YEAR'])
    assert pd.api.types.is_integer_dtype(loaded_df['DISCOVERY_DOY'])


def test_load_data_uses_wildfire_db_path_env_when_no_argument(synthetic_db_path, loaded_df):
    # The autouse fixture sets WILDFIRE_DB_PATH to the synthetic file.
    assert os.environ['WILDFIRE_DB_PATH'] == synthetic_db_path
    df = load_data()
    pd.testing.assert_frame_equal(df, loaded_df)


def test_explicit_db_path_overrides_env(monkeypatch, synthetic_db_path, loaded_df, tmp_path):
    monkeypatch.setenv('WILDFIRE_DB_PATH', str(tmp_path / 'does_not_exist.sqlite'))
    df = load_data(synthetic_db_path)
    pd.testing.assert_frame_equal(df, loaded_df)


def test_missing_db_raises_file_not_found(tmp_path):
    # A library function raises; run_pipeline.py (the CLI) turns this into exit code 1.
    missing = str(tmp_path / 'nope.sqlite')
    with pytest.raises(FileNotFoundError) as excinfo:
        load_data(missing)
    assert missing in str(excinfo.value)
    assert MISSING_DB_HELP in str(excinfo.value)
    assert 'download_data.py' in str(excinfo.value) and 'WILDFIRE_DB_PATH' in str(excinfo.value)


def test_env_pointing_at_missing_db_raises_file_not_found(monkeypatch, tmp_path):
    monkeypatch.setenv('WILDFIRE_DB_PATH', str(tmp_path / 'nope.sqlite'))
    with pytest.raises(FileNotFoundError):
        load_data()


def test_unreadable_db_raises_database_error(tmp_path):
    # A file that exists but is not a SQLite database surfaces as a database error
    # (pandas wraps sqlite3.DatabaseError in pandas.errors.DatabaseError), not SystemExit.
    bogus = tmp_path / 'bogus.sqlite'
    bogus.write_text('this is not a database')
    with pytest.raises((sqlite3.DatabaseError, pd.errors.DatabaseError)) as excinfo:
        load_data(str(bogus))
    assert 'not a database' in str(excinfo.value)


def test_db_without_fires_table_raises(tmp_path):
    empty = str(tmp_path / 'empty.sqlite')
    sqlite3.connect(empty).close()
    with pytest.raises(Exception) as excinfo:
        load_data(empty)
    assert not isinstance(excinfo.value, SystemExit)
    assert 'Fires' in str(excinfo.value)


def test_run_pipeline_exits_1_with_help_when_db_missing(monkeypatch, tmp_path, capsys):
    # The usage message now lives in the CLI entry point.
    import subprocess, sys
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {**os.environ, 'WILDFIRE_DB_PATH': str(tmp_path / 'nope.sqlite')}
    proc = subprocess.run([sys.executable, os.path.join(repo_root, 'run_pipeline.py')],
                          cwd=repo_root, env=env, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 1
    assert 'Database not found' in proc.stderr and 'download_data.py' in proc.stderr
    assert 'Traceback' not in proc.stderr
