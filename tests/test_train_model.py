"""Tests for src/train_model.py. All sklearn work is forced to n_jobs=1."""
import os

import numpy as np
import pytest
from sklearn.ensemble import RandomForestRegressor

import src.train_model as tm
from src.features import preprocess_data


@pytest.fixture
def xy(loaded_df):
    return preprocess_data(loaded_df)


@pytest.fixture
def single_core(monkeypatch):
    """Force every sklearn call inside train_model to a single core.

    build_model() defaults to n_jobs=-1 and cross_val_score is called with n_jobs=-1
    (src/train_model.py:45 and :53). The module looks both names up as globals at call
    time, so patching the module attributes is enough.
    """
    original_build = tm.build_model
    original_cvs = tm.cross_val_score
    monkeypatch.setattr(tm, 'build_model', lambda n_jobs=1: original_build(n_jobs=1))
    monkeypatch.setattr(tm, 'cross_val_score', lambda *a, **k: original_cvs(*a, **{**k, 'n_jobs': 1}))


# --------------------------------------------------------------------------- split

def test_split_data_is_deterministic(xy):
    X, y = xy
    a = tm.split_data(X, y)
    b = tm.split_data(X, y)
    for left, right in zip(a, b):
        assert left.index.tolist() == right.index.tolist()


def test_split_data_is_80_20_and_disjoint(xy):
    X, y = xy
    X_train, X_test, y_train, y_test = tm.split_data(X, y)
    n = len(X)
    assert len(X_test) == int(np.ceil(0.2 * n))
    assert len(X_train) + len(X_test) == n
    assert not set(X_train.index) & set(X_test.index)
    assert X_train.index.equals(y_train.index) and X_test.index.equals(y_test.index)


def test_split_uses_random_state_42(xy):
    from sklearn.model_selection import train_test_split
    X, y = xy
    assert tm.RANDOM_STATE == 42
    ours = tm.split_data(X, y)[1].index.tolist()
    ref = train_test_split(X, y, test_size=0.2, random_state=42)[1].index.tolist()
    assert ours == ref


# --------------------------------------------------------------------------- model config

def test_build_model_config():
    rf = tm.build_model()
    assert isinstance(rf, RandomForestRegressor)
    p = rf.get_params()
    assert p['n_estimators'] == 100
    assert p['max_depth'] == 10
    assert p['random_state'] == 42
    assert p['n_jobs'] == -1, 'default is all cores; callers pass n_jobs=1 on shared machines'
    assert tm.build_model(n_jobs=1).get_params()['n_jobs'] == 1


def test_build_model_returns_unfitted_estimator():
    rf = tm.build_model(n_jobs=1)
    assert not hasattr(rf, 'estimators_')


# --------------------------------------------------------------------------- end to end

def test_train_model_end_to_end_single_core(xy, single_core, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # the PNGs are written to the CWD (src/train_model.py:103, :130)
    X, y = xy

    rf = tm.train_model(X, y)

    assert isinstance(rf, RandomForestRegressor)
    assert hasattr(rf, 'estimators_') and len(rf.estimators_) == 100
    assert rf.n_jobs == 1
    assert rf.n_features_in_ == X.shape[1]
    assert list(rf.feature_names_in_) == list(X.columns)
    pred = rf.predict(X)
    assert pred.shape == (len(X),)
    assert np.isfinite(pred).all()
    assert (pred >= 0).all(), 'a tree ensemble on a non-negative target cannot predict below 0'

    for name in ['feature_importance.png', 'residuals.png']:
        path = tmp_path / name
        assert path.exists(), f'{name} should land in the CWD'
        assert os.path.getsize(path) > 1000
        assert path.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n'


def test_train_model_is_reproducible(xy, single_core, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    X, y = xy
    p1 = tm.train_model(X, y).predict(X)
    p2 = tm.train_model(X, y).predict(X)
    np.testing.assert_array_equal(p1, p2)
