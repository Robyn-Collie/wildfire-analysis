"""Tests for src/features.py (preprocess_data)."""
import logging

import numpy as np
import pandas as pd
import pytest

from src.features import preprocess_data
from conftest import CAUSES

CAUSE_COLUMNS = [f'CAUSE_{c}' for c in CAUSES]
NON_FEATURE_COLUMNS = ['FIRE_YEAR', 'FIRE_SIZE_CLASS', 'DISCOVERY_DATE', 'CONT_DATE',
                       'DISCOVERY_DOY', 'DURATION_DAYS', 'NWCG_GENERAL_CAUSE']


def small_frame(**overrides) -> pd.DataFrame:
    """A four-row frame in the shape load_data returns; columns can be overridden."""
    base = {
        'FIRE_YEAR': [2012, 2012, 2015, 2016],
        'DISCOVERY_DATE': ['3/1/2012', '1/1/2012', '7/4/2015', '12/31/2016'],
        'DISCOVERY_DOY': [61, 1, 185, 366],
        'CONT_DATE': ['3/5/2012', '1/1/2012', '7/14/2015', '12/31/2016'],
        'LATITUDE': [34.0, 35.0, 44.0, 61.0],
        'LONGITUDE': [-118.0, -119.0, -110.0, -150.0],
        'FIRE_SIZE_CLASS': ['A', 'B', 'G', 'C'],
        'NWCG_GENERAL_CAUSE': ['Natural', 'Smoking', 'Fireworks', 'Natural'],
    }
    base.update(overrides)
    return pd.DataFrame(base)


# --------------------------------------------------------------------------- target

def test_duration_days_is_cont_minus_discovery_in_whole_days():
    X, y = preprocess_data(small_frame())
    assert y.tolist() == [4, 0, 10, 0]
    assert pd.api.types.is_integer_dtype(y)


def test_duration_matches_ground_truth_on_synthetic_db(loaded_df):
    X, y = preprocess_data(loaded_df)
    expected = (pd.to_datetime(loaded_df['CONT_DATE'], format='%m/%d/%Y')
                - pd.to_datetime(loaded_df['DISCOVERY_DATE'], format='%m/%d/%Y')).dt.days
    expected = expected[expected >= 0]
    pd.testing.assert_series_equal(y, expected, check_names=False)
    assert y.max() == 400, 'the synthetic tail row (400 days) must survive preprocessing'


def test_negative_duration_rows_are_dropped_and_logged(caplog):
    df = small_frame(CONT_DATE=['3/5/2012', '12/30/2011', '7/14/2015', '12/31/2016'])  # row 1 is -2 days
    with caplog.at_level(logging.WARNING, logger='src.features'):
        X, y = preprocess_data(df)
    assert len(X) == 3 and len(y) == 3
    assert 1 not in X.index
    assert y.tolist() == [4, 10, 0]
    msgs = [r.getMessage() for r in caplog.records if r.name == 'src.features' and r.levelno == logging.WARNING]
    assert msgs == ['Dropped 1 records with invalid (negative) duration.']


def test_no_warning_when_nothing_is_dropped(caplog):
    with caplog.at_level(logging.WARNING, logger='src.features'):
        preprocess_data(small_frame())
    assert not [r for r in caplog.records if r.name == 'src.features' and r.levelno >= logging.WARNING]


def test_synthetic_db_negative_row_is_dropped(loaded_df, caplog):
    raw = (pd.to_datetime(loaded_df['CONT_DATE'], format='%m/%d/%Y')
           - pd.to_datetime(loaded_df['DISCOVERY_DATE'], format='%m/%d/%Y')).dt.days
    n_negative = int((raw < 0).sum())
    assert n_negative == 1, 'conftest plants exactly one negative-duration row in the 2010+ subset'
    with caplog.at_level(logging.WARNING, logger='src.features'):
        X, y = preprocess_data(loaded_df)
    assert len(y) == len(loaded_df) - 1
    assert (y >= 0).all()


# --------------------------------------------------------------------------- cyclical DOY

def test_sin_cos_doy_are_bounded(loaded_df):
    X, _ = preprocess_data(loaded_df)
    for col in ['SIN_DOY', 'COS_DOY']:
        assert X[col].between(-1, 1).all()
    np.testing.assert_allclose(X['SIN_DOY'] ** 2 + X['COS_DOY'] ** 2, 1.0, atol=1e-12)


def test_day_1_and_day_365_are_close_and_day_183_is_far():
    df = small_frame(DISCOVERY_DOY=[1, 365, 183, 100])
    X, _ = preprocess_data(df)
    pts = X[['SIN_DOY', 'COS_DOY']].to_numpy()
    d_1_365 = np.linalg.norm(pts[0] - pts[1])
    d_1_183 = np.linalg.norm(pts[0] - pts[2])
    assert d_1_365 == pytest.approx(2 * np.sin(np.pi / 365), abs=1e-9)  # one day apart on the circle
    assert d_1_365 < 0.02
    assert d_1_183 > 1.99  # nearly diametrically opposite


def test_doy_366_collides_with_doy_1_KNOWN_ISSUE():
    # KNOWN ISSUE (documented): src/features.py:45-46 divide by a fixed 365, so in a leap
    # year DISCOVERY_DOY 366 (Dec 31) is encoded at exactly the same angle as DOY 1
    # (Jan 1), and every leap-year date after Feb 28 is shifted one day relative to the
    # same calendar date in a non-leap year. This test pins the CURRENT behaviour.
    df = small_frame(DISCOVERY_DOY=[366, 1, 183, 100])
    X, _ = preprocess_data(df)
    assert X.loc[0, 'SIN_DOY'] == pytest.approx(X.loc[1, 'SIN_DOY'], abs=1e-12)
    assert X.loc[0, 'COS_DOY'] == pytest.approx(X.loc[1, 'COS_DOY'], abs=1e-12)
    assert X.loc[0, 'SIN_DOY'] == pytest.approx(np.sin(2 * np.pi * 366 / 365))


@pytest.mark.xfail(strict=False, reason='features.py divides DOY by 365 regardless of leap year; '
                                        'Dec 31 of a leap year should sit at the year-end angle (sin 0, cos 1)')
def test_doy_366_encodes_as_year_end_EXPECTED_FIX():
    # The behaviour we want once the fix lands (divide by 366 in leap years, or use the
    # calendar date): Dec 31 always maps to the same point regardless of leap year.
    df = small_frame(DISCOVERY_DOY=[366, 1, 183, 100])
    X, _ = preprocess_data(df)
    assert X.loc[0, 'SIN_DOY'] == pytest.approx(0.0, abs=1e-9)
    assert X.loc[0, 'COS_DOY'] == pytest.approx(1.0, abs=1e-9)


def test_synthetic_db_contains_doy_366_rows(loaded_df):
    # Guard: the fixture really exercises the leap-year edge in the model subset.
    assert (loaded_df['DISCOVERY_DOY'] == 366).sum() >= 1


# --------------------------------------------------------------------------- one-hot and schema

def test_one_hot_columns_for_all_13_causes_present(loaded_df):
    X, _ = preprocess_data(loaded_df)
    assert [c for c in X.columns if c.startswith('CAUSE_')] == CAUSE_COLUMNS
    cause_block = X[CAUSE_COLUMNS].astype(int)
    assert (cause_block.sum(axis=1) == 1).all(), 'exactly one cause per row'
    assert (cause_block.sum(axis=0) > 0).all(), 'every cause column is used'


def test_x_has_exactly_the_17_reported_features(loaded_df):
    # Matches outputs/reproduction_model.json 'features' (n_features == 17).
    X, _ = preprocess_data(loaded_df)
    assert list(X.columns) == ['LATITUDE', 'LONGITUDE', 'SIN_DOY', 'COS_DOY'] + CAUSE_COLUMNS
    assert X.shape[1] == 17


def test_x_excludes_leaky_and_non_feature_columns(loaded_df):
    X, _ = preprocess_data(loaded_df)
    for col in NON_FEATURE_COLUMNS:
        assert col not in X.columns, col


def test_x_has_no_nans_and_is_numeric(loaded_df):
    X, _ = preprocess_data(loaded_df)
    assert not X.isna().any().any()
    for col in X.columns:
        assert pd.api.types.is_numeric_dtype(X[col]) or pd.api.types.is_bool_dtype(X[col]), col


def test_y_aligned_with_x_index_and_input_not_mutated(loaded_df):
    before = loaded_df.copy()
    X, y = preprocess_data(loaded_df)
    assert X.index.equals(y.index)
    assert set(X.index) <= set(loaded_df.index), 'preprocess keeps the original index labels'
    assert (y >= 0).all()
    pd.testing.assert_frame_equal(loaded_df, before)  # the input frame is untouched


def test_schema_drift_when_a_cause_is_absent_DEFECT(loaded_df):
    # DEFECT (documented): pd.get_dummies builds columns from the categories PRESENT in
    # the input (src/features.py:52), so a frame that lacks one cause yields a
    # different feature matrix. A model trained on 17 columns cannot score a batch with
    # 16, and a batch with a new/renamed cause would silently add a column. The fix is
    # to encode against the fixed CAUSES list (pd.Categorical(..., categories=CAUSES) or
    # a fitted OneHotEncoder). This test pins the CURRENT behaviour.
    full_X, _ = preprocess_data(loaded_df)
    subset = loaded_df[loaded_df['NWCG_GENERAL_CAUSE'] != 'Fireworks']
    sub_X, _ = preprocess_data(subset)
    assert full_X.shape[1] == 17
    assert sub_X.shape[1] == 16
    assert 'CAUSE_Fireworks' in full_X.columns
    assert 'CAUSE_Fireworks' not in sub_X.columns


def test_single_cause_input_yields_single_cause_column_DEFECT():
    # Same defect, extreme case: a one-cause batch produces a 5-column X.
    X, _ = preprocess_data(small_frame(NWCG_GENERAL_CAUSE=['Natural'] * 4))
    assert list(X.columns) == ['LATITUDE', 'LONGITUDE', 'SIN_DOY', 'COS_DOY', 'CAUSE_Natural']
