"""Tests for scripts/build_cache.py (SQLite -> typed Parquet cache)."""
import hashlib
import os

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

import scripts.build_cache as bc
from conftest import (CAUSES, INVALID_TIME_ID, KNOWN_ROW_2006, KNOWN_ROW_2010, MISSING_CONT_DATE_ID,
                      MISSING_CONT_TIME_ID, MISSING_DISC_TIME_ID, N_ROWS, NEGATIVE_DURATION_ID)


def sha256_of(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


@pytest.fixture
def cache(synthetic_db_path, tmp_path):
    path = str(tmp_path / 'fires.parquet')
    out = bc.build(synthetic_db_path, path)
    assert out == path
    return path


@pytest.fixture
def cached_df(cache) -> pd.DataFrame:
    return pd.read_parquet(cache).set_index('FOD_ID', drop=False)


def test_cache_has_all_rows_and_derived_columns(cached_df):
    assert len(cached_df) == N_ROWS
    for col in ['DISCOVERY_DATETIME', 'CONT_DATETIME', 'DURATION_DAYS', 'DURATION_HOURS', 'DISCOVERY_MONTH']:
        assert col in cached_df.columns, col
    assert set(bc.COLUMNS) <= set(cached_df.columns)


def test_cache_dtypes(cached_df):
    assert pd.api.types.is_datetime64_any_dtype(cached_df['DISCOVERY_DATE'])
    assert pd.api.types.is_datetime64_any_dtype(cached_df['CONT_DATE'])
    assert pd.api.types.is_datetime64_any_dtype(cached_df['DISCOVERY_DATETIME'])
    assert isinstance(cached_df['NWCG_GENERAL_CAUSE'].dtype, pd.CategoricalDtype)
    assert set(cached_df['NWCG_GENERAL_CAUSE'].cat.categories) == set(CAUSES)
    assert isinstance(cached_df['STATE'].dtype, pd.CategoricalDtype)
    assert str(cached_df['DISCOVERY_MONTH'].dtype) == 'Int8'


def test_known_rows_have_correct_durations(cached_df):
    r = cached_df.loc[KNOWN_ROW_2006]
    assert r['DISCOVERY_DATE'] == pd.Timestamp('2006-03-01')
    assert r['DISCOVERY_DATETIME'] == pd.Timestamp('2006-03-01 08:30')
    assert r['CONT_DATETIME'] == pd.Timestamp('2006-03-03 14:15')
    assert r['DURATION_DAYS'] == 2
    assert r['DURATION_HOURS'] == pytest.approx(53.75)
    assert r['DISCOVERY_MONTH'] == 3

    r = cached_df.loc[KNOWN_ROW_2010]
    assert r['DISCOVERY_DATETIME'] == pd.Timestamp('2010-06-15 14:00')
    assert r['DURATION_DAYS'] == 5
    assert r['DURATION_HOURS'] == pytest.approx(115.0)


def test_duration_days_matches_ground_truth_for_every_row(cached_df, synthetic_rows):
    expected = (pd.to_datetime(synthetic_rows['CONT_DATE'], format='%m/%d/%Y', errors='coerce')
                - pd.to_datetime(synthetic_rows['DISCOVERY_DATE'], format='%m/%d/%Y')).dt.days
    got = cached_df['DURATION_DAYS'].reindex(synthetic_rows.index)
    assert got.isna().equals(expected.isna())
    np.testing.assert_array_equal(got.dropna().to_numpy(), expected.dropna().to_numpy())


def test_missing_containment_date_gives_nan_duration(cached_df):
    r = cached_df.loc[MISSING_CONT_DATE_ID]
    assert pd.isna(r['CONT_DATE'])
    assert pd.isna(r['CONT_DATETIME'])
    assert pd.isna(r['DURATION_DAYS'])
    assert pd.isna(r['DURATION_HOURS'])
    assert not pd.isna(r['DISCOVERY_DATE'])


def test_missing_or_invalid_time_gives_nat_datetime_but_keeps_days(cached_df):
    # Missing DISCOVERY_TIME: no timestamp, no hours, but the date-level duration survives.
    r = cached_df.loc[MISSING_DISC_TIME_ID]
    assert pd.isna(r['DISCOVERY_DATETIME'])
    assert pd.isna(r['DURATION_HOURS'])
    assert not pd.isna(r['DISCOVERY_DATE'])
    assert not pd.isna(r['DURATION_DAYS'])

    # Missing CONT_TIME.
    r = cached_df.loc[MISSING_CONT_TIME_ID]
    assert pd.isna(r['CONT_DATETIME'])
    assert pd.isna(r['DURATION_HOURS'])
    assert not pd.isna(r['DURATION_DAYS'])

    # Invalid DISCOVERY_TIME '2560' (hour 25): coerced to NaT rather than a bogus timestamp.
    r = cached_df.loc[INVALID_TIME_ID]
    assert r['DISCOVERY_TIME'] == '2560'
    assert pd.isna(r['DISCOVERY_DATETIME'])
    assert pd.isna(r['DURATION_HOURS'])
    assert not pd.isna(r['CONT_DATETIME'])
    assert r['DURATION_DAYS'] == 0


def test_negative_duration_is_kept_in_cache_not_filtered(cached_df):
    # The cache is a faithful extract; filtering is the consumer's job (features.py drops it).
    r = cached_df.loc[NEGATIVE_DURATION_ID]
    assert r['DURATION_DAYS'] == -2
    assert r['DURATION_HOURS'] == pytest.approx(-48.0)


def test_metadata_records_db_hash_and_column_notes(cache, synthetic_db_path):
    meta = pq.read_schema(cache).metadata
    assert meta[b'db_sha256'].decode() == sha256_of(synthetic_db_path)
    assert meta[b'db_sha256'].decode() == bc.sha256(synthetic_db_path)
    assert b'built' in meta
    assert b'DURATION_DAYS' in meta[b'columns_note']


def test_second_build_is_a_noop_when_hash_matches(cache, synthetic_db_path, capsys):
    stat_before = os.stat(cache)
    capsys.readouterr()
    out = bc.build(synthetic_db_path, cache)
    assert out == cache
    assert 'is up to date' in capsys.readouterr().out
    stat_after = os.stat(cache)
    assert (stat_after.st_mtime_ns, stat_after.st_size) == (stat_before.st_mtime_ns, stat_before.st_size)


def test_rebuilds_when_db_hash_changes(cache, synthetic_db_path, tmp_path, capsys):
    # A cache stamped with a different hash is rebuilt (the hash check is what keeps the cache honest).
    table = pq.read_table(cache)
    meta = dict(table.schema.metadata)
    meta[b'db_sha256'] = b'0' * 64
    pq.write_table(table.replace_schema_metadata(meta), cache)
    capsys.readouterr()
    bc.build(synthetic_db_path, cache)
    assert 'Wrote' in capsys.readouterr().out
    assert pq.read_schema(cache).metadata[b'db_sha256'].decode() == sha256_of(synthetic_db_path)


def test_parse_datetime_helper_directly():
    dates = pd.Series(['1/2/2012', '1/2/2012', '1/2/2012', '1/2/2012', '1/2/2012', None])
    times = pd.Series(['0845', None, '2560', '845', ' 2359 ', '1200'])
    got = bc.parse_datetime(dates, times)
    assert got.iloc[0] == pd.Timestamp('2012-01-02 08:45')
    assert pd.isna(got.iloc[1])
    assert pd.isna(got.iloc[2])
    assert pd.isna(got.iloc[3])
    assert got.iloc[4] == pd.Timestamp('2012-01-02 23:59')
    assert pd.isna(got.iloc[5])
