"""Tests for the pure helpers in scripts/reproduce.py (no database, no model)."""
import numpy as np
import pandas as pd
import pytest

from scripts.reproduce import NORTHEAST, SOUTH, WEST, metrics, pct_better, region_of, to_datetime


# --------------------------------------------------------------------------- to_datetime

def test_to_datetime_date_only():
    got = to_datetime(pd.Series(['2/2/2005', '12/31/2020', 'garbage', None]))
    assert got.iloc[0] == pd.Timestamp('2005-02-02')
    assert got.iloc[1] == pd.Timestamp('2020-12-31')
    assert pd.isna(got.iloc[2])
    assert pd.isna(got.iloc[3])


@pytest.mark.parametrize('time_str, expected', [
    ('0845', pd.Timestamp('2012-03-01 08:45')),
    ('0000', pd.Timestamp('2012-03-01 00:00')),
    ('2359', pd.Timestamp('2012-03-01 23:59')),
    (' 0930 ', pd.Timestamp('2012-03-01 09:30')),  # surrounding whitespace is stripped
    (None, pd.NaT),
    ('', pd.NaT),
    ('2560', pd.NaT),   # hour 25
    ('2400', pd.NaT),   # hour 24
    ('1260', pd.NaT),   # minute 60
    ('845', pd.NaT),    # three digits
    ('12345', pd.NaT),  # five digits
    ('ab12', pd.NaT),
])
def test_to_datetime_with_time(time_str, expected):
    got = to_datetime(pd.Series(['3/1/2012']), pd.Series([time_str]))
    if expected is pd.NaT:
        assert pd.isna(got.iloc[0])
    else:
        assert got.iloc[0] == expected


def test_to_datetime_missing_date_with_valid_time_is_nat():
    got = to_datetime(pd.Series([None, 'x/y/z']), pd.Series(['0800', '0800']))
    assert got.isna().all()


def test_to_datetime_preserves_index():
    idx = pd.Index([10, 20, 30])
    got = to_datetime(pd.Series(['1/1/2015'] * 3, index=idx), pd.Series(['0100', None, '0300'], index=idx))
    assert got.index.equals(idx)
    assert got.loc[10] == pd.Timestamp('2015-01-01 01:00')
    assert pd.isna(got.loc[20])
    assert got.loc[30] == pd.Timestamp('2015-01-01 03:00')


# --------------------------------------------------------------------------- metrics

def test_metrics_on_known_errors():
    m = metrics([0, 1, 2], [0, 2, 4])  # errors 0, 1, 2
    assert m['rmse'] == pytest.approx(np.sqrt(5 / 3))
    assert m['mae'] == pytest.approx(1.0)
    assert set(m) == {'rmse', 'mae'}
    assert type(m['rmse']) is float and type(m['mae']) is float


def test_metrics_perfect_prediction_is_zero():
    m = metrics(pd.Series([3, 4, 5]), np.array([3, 4, 5]))
    assert m == {'rmse': 0.0, 'mae': 0.0}


def test_metrics_accepts_series_and_arrays_and_is_symmetric_in_sign():
    y = pd.Series([1.0, 2.0, 3.0], index=[7, 8, 9])
    assert metrics(y, np.array([2.0, 2.0, 2.0])) == metrics(y, np.array([0.0, 2.0, 4.0]))


def test_predict_zero_baseline_mae_equals_mean_target():
    y = np.array([0, 0, 0, 5, 10])
    assert metrics(y, np.zeros(5))['mae'] == pytest.approx(y.mean())


# --------------------------------------------------------------------------- pct_better

def test_pct_better():
    assert pct_better(1.0, 2.0) == pytest.approx(50.0)
    assert pct_better(2.0, 2.0) == pytest.approx(0.0)
    assert pct_better(3.0, 2.0) == pytest.approx(-50.0)  # model worse than baseline is negative
    assert pct_better(6.6, 7.05) == pytest.approx(100 * (7.05 - 6.6) / 7.05)
    assert type(pct_better(1, 2)) is float


# --------------------------------------------------------------------------- region_of

def test_region_of_maps_states():
    s = pd.Series(['CA', 'TX', 'AK', 'NY', 'HI', 'MO', 'WA', 'FL', 'PA', 'PR'], index=list('abcdefghij'))
    got = region_of(s)
    assert got.tolist() == ['West', 'South', 'Alaska', 'Northeast', 'Other', 'Other',
                            'West', 'South', 'Northeast', 'Other']
    assert got.index.equals(s.index)


def test_region_lists_are_disjoint_and_exclude_alaska():
    groups = [set(WEST), set(SOUTH), set(NORTHEAST)]
    for i in range(3):
        for j in range(i + 1, 3):
            assert not groups[i] & groups[j]
    assert 'AK' not in WEST and 'AK' not in SOUTH and 'AK' not in NORTHEAST
    assert len(WEST) == 11 and len(SOUTH) == 14 and len(NORTHEAST) == 9


def test_region_of_handles_missing_state():
    got = region_of(pd.Series(['CA', None]))
    assert got.tolist() == ['West', 'Other']
