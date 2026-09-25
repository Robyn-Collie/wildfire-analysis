"""Tests for src/features.py (preprocess_data)."""
import logging

import numpy as np
import pandas as pd
import pytest

from src.features import CAUSE_LEVELS, FEATURE_COLUMNS, preprocess_data
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
    assert y.name == 'DURATION_DAYS'


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
# The angle is 2*pi*(DOY-1)/days_in_year computed from DISCOVERY_DATE (days_in_year is 366
# in a leap year). Jan 1 is angle 0; Dec 31 is one day short of a full turn.

def dates_frame(dates):
    """small_frame with the given discovery dates, contained the same day."""
    return small_frame(DISCOVERY_DATE=list(dates), CONT_DATE=list(dates))


def angle_of(X, i):
    return np.arctan2(X.loc[i, 'SIN_DOY'], X.loc[i, 'COS_DOY'])


def test_sin_cos_doy_are_bounded(loaded_df):
    X, _ = preprocess_data(loaded_df)
    for col in ['SIN_DOY', 'COS_DOY']:
        assert X[col].between(-1, 1).all()
    np.testing.assert_allclose(X['SIN_DOY'] ** 2 + X['COS_DOY'] ** 2, 1.0, atol=1e-12)


def test_day_1_and_day_365_are_close_and_day_183_is_far():
    X, _ = preprocess_data(dates_frame(['1/1/2015', '12/31/2015', '7/2/2015', '4/10/2015']))  # DOY 1, 365, 183, 100
    pts = X[['SIN_DOY', 'COS_DOY']].to_numpy()
    d_1_365 = np.linalg.norm(pts[0] - pts[1])
    d_1_183 = np.linalg.norm(pts[0] - pts[2])
    assert d_1_365 == pytest.approx(2 * np.sin(np.pi / 365), abs=1e-9)  # one day apart on the circle
    assert d_1_365 < 0.02
    assert d_1_183 > 1.99  # nearly diametrically opposite


def test_jan_1_is_angle_zero_in_leap_and_non_leap_years():
    X, _ = preprocess_data(dates_frame(['1/1/2015', '1/1/2016', '1/1/2020', '1/1/2021']))
    np.testing.assert_allclose(X['SIN_DOY'], 0.0, atol=1e-12)
    np.testing.assert_allclose(X['COS_DOY'], 1.0, atol=1e-12)


def test_doy_366_does_not_collide_with_doy_1():
    # Formerly a KNOWN ISSUE: with a fixed 365 divisor, Dec 31 of a leap year (DOY 366) was
    # encoded at exactly the same angle as Jan 1. Now it is one day (2*pi/366) before it.
    X, _ = preprocess_data(dates_frame(['12/31/2016', '1/1/2016', '7/1/2016', '4/9/2016']))
    d = np.linalg.norm(X.loc[0, ['SIN_DOY', 'COS_DOY']].to_numpy() - X.loc[1, ['SIN_DOY', 'COS_DOY']].to_numpy())
    assert d == pytest.approx(2 * np.sin(np.pi / 366), abs=1e-9)
    assert X.loc[0, 'SIN_DOY'] != pytest.approx(X.loc[1, 'SIN_DOY'], abs=1e-6)


def test_doy_366_encodes_as_year_end():
    # Formerly an xfail: Dec 31 of a leap year sits at the year-end angle, one day step short
    # of a full turn (sin -sin(2pi/366), cos cos(2pi/366)), at the same point as Dec 31 of a
    # non-leap year to within the leap-day stretch (2*pi/(365*366), about 5e-5 rad).
    X, _ = preprocess_data(dates_frame(['12/31/2016', '12/31/2015', '12/31/2020', '12/31/2019']))
    assert X.loc[0, 'SIN_DOY'] == pytest.approx(-np.sin(2 * np.pi / 366), abs=1e-12)
    assert X.loc[0, 'COS_DOY'] == pytest.approx(np.cos(2 * np.pi / 366), abs=1e-12)
    assert X.loc[1, 'SIN_DOY'] == pytest.approx(-np.sin(2 * np.pi / 365), abs=1e-12)
    for leap, plain in [(0, 1), (2, 3)]:
        assert abs(angle_of(X, leap) - angle_of(X, plain)) == pytest.approx(2 * np.pi / (365 * 366), abs=1e-9)
        assert abs(angle_of(X, leap) - angle_of(X, plain)) < 2 * np.pi / 365 / 100


def test_same_calendar_date_in_leap_and_non_leap_year_is_within_one_day_step():
    # Mar 1 is DOY 60 in 2019 and DOY 61 in 2020; the leap-aware angle keeps the two within
    # a fraction of a day step of each other (the old fixed-365 formula put them one day apart).
    X, _ = preprocess_data(dates_frame(['3/1/2019', '3/1/2020', '8/15/2019', '8/15/2020']))
    step = 2 * np.pi / 365
    assert abs(angle_of(X, 0) - angle_of(X, 1)) < step
    assert abs(angle_of(X, 2) - angle_of(X, 3)) < step
    assert abs(angle_of(X, 0) - angle_of(X, 1)) == pytest.approx(2 * np.pi * (60 / 366 - 59 / 365), abs=1e-12)


def test_discovery_doy_column_is_ignored():
    # The angle comes from DISCOVERY_DATE; a wrong or absent DISCOVERY_DOY changes nothing.
    ref, _ = preprocess_data(small_frame())
    wrong, _ = preprocess_data(small_frame(DISCOVERY_DOY=[300, 300, 300, 300]))
    pd.testing.assert_frame_equal(ref, wrong)
    absent, _ = preprocess_data(small_frame().drop(columns=['DISCOVERY_DOY']))
    pd.testing.assert_frame_equal(ref, absent)


def test_synthetic_db_contains_doy_366_rows(loaded_df):
    # Guard: the fixture really exercises the leap-year edge in the model subset.
    assert (loaded_df['DISCOVERY_DOY'] == 366).sum() >= 1
    X, _ = preprocess_data(loaded_df)
    rows = loaded_df.index[loaded_df['DISCOVERY_DOY'] == 366]
    np.testing.assert_allclose(X.loc[rows, 'SIN_DOY'], -np.sin(2 * np.pi / 366), atol=1e-12)


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
    assert list(X.columns) == FEATURE_COLUMNS
    assert X.shape[1] == 17


def test_cause_levels_are_the_13_causes_in_alphabetical_order():
    assert CAUSE_LEVELS == CAUSES
    assert CAUSE_LEVELS == sorted(CAUSE_LEVELS)
    assert len(set(CAUSE_LEVELS)) == 13


def test_x_excludes_leaky_and_non_feature_columns(loaded_df):
    X, _ = preprocess_data(loaded_df)
    for col in NON_FEATURE_COLUMNS + ['FOD_ID']:
        assert col not in X.columns, col


def test_extra_input_columns_never_leak_into_x():
    # A whitelist, not a blacklist: a caller who adds FIRE_SIZE (or anything) to the query
    # does not get it as a feature.
    X, _ = preprocess_data(small_frame(FIRE_SIZE=[0.1, 5.0, 12000.0, 30.0], STATE=['CA'] * 4))
    assert list(X.columns) == FEATURE_COLUMNS


def test_missing_required_column_raises_key_error():
    with pytest.raises(KeyError, match='LATITUDE'):
        preprocess_data(small_frame().drop(columns=['LATITUDE']))


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


def test_schema_is_fixed_when_a_cause_is_absent(loaded_df):
    # Formerly a DEFECT: get_dummies built columns from the causes present in the input.
    # Now the 13 CAUSE_* columns are fixed, so a batch missing a cause has the same 17
    # columns with that cause's column all zero, and a fitted model can score it.
    full_X, _ = preprocess_data(loaded_df)
    subset = loaded_df[loaded_df['NWCG_GENERAL_CAUSE'] != 'Fireworks']
    sub_X, _ = preprocess_data(subset)
    assert list(full_X.columns) == list(sub_X.columns) == FEATURE_COLUMNS
    assert full_X['CAUSE_Fireworks'].astype(int).sum() > 0
    assert sub_X['CAUSE_Fireworks'].astype(int).sum() == 0


def test_single_cause_input_still_yields_all_13_cause_columns():
    X, _ = preprocess_data(small_frame(NWCG_GENERAL_CAUSE=['Natural'] * 4))
    assert list(X.columns) == FEATURE_COLUMNS
    assert X['CAUSE_Natural'].astype(int).tolist() == [1, 1, 1, 1]
    others = [c for c in CAUSE_COLUMNS if c != 'CAUSE_Natural']
    assert len(others) == 12
    assert (X[others].astype(int).sum(axis=0) == 0).all()


def test_unknown_cause_raises_value_error():
    with pytest.raises(ValueError, match='Unknown NWCG_GENERAL_CAUSE'):
        preprocess_data(small_frame(NWCG_GENERAL_CAUSE=['Natural', 'Lightning', 'Smoking', 'Natural']))


def test_null_cause_raises_value_error():
    # A null cause would encode as an all-zero row (indistinguishable from nothing); it is an error.
    with pytest.raises(ValueError, match='null NWCG_GENERAL_CAUSE'):
        preprocess_data(small_frame(NWCG_GENERAL_CAUSE=['Natural', None, 'Smoking', 'Natural']))


# --------------------------------------------------------------------------- validation

def test_iso_or_day_first_dates_raise_instead_of_being_guessed():
    with pytest.raises(ValueError):
        preprocess_data(small_frame(DISCOVERY_DATE=['2012-03-01', '2012-01-01', '2015-07-04', '2016-12-31']))
    with pytest.raises(ValueError):
        preprocess_data(small_frame(CONT_DATE=['3/5/2012', '1/1/2012', '25/7/2015', '12/31/2016']))


def test_missing_containment_date_raises_not_dropped_as_negative(caplog):
    # A NaN duration is a missing date, a loader contract violation; it is not counted or
    # logged as a "negative" duration.
    with caplog.at_level(logging.WARNING, logger='src.features'):
        with pytest.raises(ValueError, match='missing DISCOVERY_DATE or CONT_DATE'):
            preprocess_data(small_frame(CONT_DATE=['3/5/2012', None, '7/14/2015', '12/31/2016']))
    assert not [r for r in caplog.records if 'negative' in r.getMessage()]


def test_nan_and_negative_durations_are_counted_separately():
    df = small_frame(CONT_DATE=['3/5/2012', None, '7/10/2015', '12/31/2016'])  # row 1 NaN, row 2 negative (-4 days)
    with pytest.raises(ValueError, match='1 records have a missing'):
        preprocess_data(df)


def test_missing_coordinate_raises_instead_of_becoming_zero():
    # Formerly fillna(0) would place a fire with no coordinates at 0 N 0 E.
    with pytest.raises(ValueError, match='LATITUDE'):
        preprocess_data(small_frame(LATITUDE=[34.0, np.nan, 44.0, 61.0]))
    with pytest.raises(ValueError, match='LONGITUDE'):
        preprocess_data(small_frame(LONGITUDE=[-118.0, -119.0, np.nan, -150.0]))
