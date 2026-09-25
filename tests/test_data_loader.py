"""Tests for src/data_loader.py against the synthetic database (no real DB needed)."""
import os

import pandas as pd
import pytest

from src.data_loader import DB_FILENAME, DEFAULT_DB_PATH, load_data

EXPECTED_COLUMNS = ['FIRE_YEAR', 'DISCOVERY_DATE', 'DISCOVERY_DOY', 'CONT_DATE',
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
    # Same rows, in table order.
    assert df['DISCOVERY_DATE'].tolist() == expected['DISCOVERY_DATE'].tolist()
    assert df['NWCG_GENERAL_CAUSE'].tolist() == expected['NWCG_GENERAL_CAUSE'].tolist()


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


def test_missing_db_raises_systemexit_DEFECT(tmp_path, caplog):
    # DEFECT (documented, not endorsed): load_data calls sys.exit(1) when the file is
    # missing (src/data_loader.py:39). A library function should raise an exception
    # (FileNotFoundError) and let the CLI entry point decide to exit; sys.exit from a
    # function makes the loader unusable from notebooks, tests and other callers.
    # This test pins the CURRENT behaviour so the change is deliberate when made.
    missing = str(tmp_path / 'nope.sqlite')
    with pytest.raises(SystemExit) as excinfo:
        load_data(missing)
    assert excinfo.value.code == 1
    assert any('Database not found' in r.getMessage() for r in caplog.records)


def test_env_pointing_at_missing_db_raises_systemexit_DEFECT(monkeypatch, tmp_path):
    # Same defect via the environment variable path.
    monkeypatch.setenv('WILDFIRE_DB_PATH', str(tmp_path / 'nope.sqlite'))
    with pytest.raises(SystemExit):
        load_data()


def test_unreadable_db_raises_systemexit_DEFECT(tmp_path, caplog):
    # DEFECT (documented): any exception during the query is swallowed and turned into
    # sys.exit(1) (src/data_loader.py:70-72). A file that exists but is not a SQLite
    # database with a Fires table should surface as an exception the caller can handle.
    bogus = tmp_path / 'bogus.sqlite'
    bogus.write_text('this is not a database')
    with pytest.raises(SystemExit) as excinfo:
        load_data(str(bogus))
    assert excinfo.value.code == 1
    assert any('An error occurred while loading data' in r.getMessage() for r in caplog.records)
