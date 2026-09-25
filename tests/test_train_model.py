"""Tests for src/train_model.py. WILDFIRE_N_JOBS is unset, so everything runs on one core."""
import json
import os

import numpy as np
import pytest
from sklearn.ensemble import RandomForestRegressor

import src.train_model as tm
from src.features import FEATURE_COLUMNS, preprocess_data


@pytest.fixture
def xy(loaded_df):
    return preprocess_data(loaded_df)


@pytest.fixture(autouse=True)
def no_n_jobs_env(monkeypatch):
    """The default (no WILDFIRE_N_JOBS) is single core; tests that set it do so explicitly."""
    monkeypatch.delenv(tm.N_JOBS_ENV, raising=False)


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


# --------------------------------------------------------------------------- n_jobs

def test_default_n_jobs_is_1_without_env():
    assert tm.default_n_jobs() == 1


@pytest.mark.parametrize('value, expected', [('1', 1), ('2', 2), ('-1', -1), (' 4 ', 4)])
def test_default_n_jobs_reads_env(monkeypatch, value, expected):
    monkeypatch.setenv(tm.N_JOBS_ENV, value)
    assert tm.default_n_jobs() == expected
    assert tm.build_model().get_params()['n_jobs'] == expected


@pytest.mark.parametrize('value', ['0', 'all', '', '1.5'])
def test_default_n_jobs_rejects_bad_values(monkeypatch, value):
    monkeypatch.setenv(tm.N_JOBS_ENV, value)
    with pytest.raises(ValueError):
        tm.default_n_jobs()


# --------------------------------------------------------------------------- model config

def test_build_model_config():
    rf = tm.build_model()
    assert isinstance(rf, RandomForestRegressor)
    p = rf.get_params()
    assert p['n_estimators'] == 100
    assert p['max_depth'] == 10
    assert p['random_state'] == 42
    assert p['n_jobs'] == 1, 'single core unless WILDFIRE_N_JOBS says otherwise'
    assert tm.build_model(n_jobs=2).get_params()['n_jobs'] == 2


def test_build_model_returns_unfitted_estimator():
    rf = tm.build_model()
    assert not hasattr(rf, 'estimators_')


# --------------------------------------------------------------------------- end to end

def test_train_model_end_to_end(xy, tmp_path, monkeypatch):
    cwd = tmp_path / 'elsewhere'  # a CWD that is not out_dir, to prove nothing lands there
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    out_dir = tmp_path / 'out'
    X, y = xy

    rf, metrics = tm.train_model(X, y, out_dir=str(out_dir))

    assert isinstance(rf, RandomForestRegressor)
    assert hasattr(rf, 'estimators_') and len(rf.estimators_) == 100
    assert rf.n_jobs == 1
    assert rf.n_features_in_ == X.shape[1]
    assert list(rf.feature_names_in_) == list(X.columns) == FEATURE_COLUMNS
    pred = rf.predict(X)
    assert pred.shape == (len(X),)
    assert np.isfinite(pred).all()
    assert (pred >= 0).all(), 'a tree ensemble on a non-negative target cannot predict below 0'

    # Metrics dict: the numbers exist as data, not only as log lines.
    X_train, X_test, y_train, y_test = tm.split_data(X, y)
    assert metrics['n_rows'] == len(y) and metrics['n_train'] == len(y_train) and metrics['n_test'] == len(y_test)
    assert metrics['n_features'] == 17 and metrics['features'] == FEATURE_COLUMNS
    assert metrics['n_estimators'] == 100 and metrics['max_depth'] == 10 and metrics['random_state'] == 42
    assert metrics['n_jobs'] == 1
    test_pred = rf.predict(X_test)
    assert metrics['test_rmse'] == pytest.approx(np.sqrt(np.mean((test_pred - y_test) ** 2)))
    assert metrics['test_mae'] == pytest.approx(np.mean(np.abs(test_pred - y_test)))
    assert metrics['cv_folds'] == 5 and len(metrics['cv_rmse_folds']) == 5
    assert metrics['cv_rmse'] == pytest.approx(np.mean(metrics['cv_rmse_folds']))
    assert metrics['cv_rmse_std'] == pytest.approx(np.std(metrics['cv_rmse_folds']))
    assert all(isinstance(metrics[k], float) for k in ['test_rmse', 'test_mae', 'cv_rmse', 'cv_rmse_std'])

    # Everything lands in out_dir, nothing in the CWD.
    with open(out_dir / 'metrics.json') as f:
        assert json.load(f) == metrics
    for name in ['feature_importance.png', 'residuals.png']:
        path = out_dir / name
        assert path.exists(), f'{name} should land in out_dir'
        assert os.path.getsize(path) > 1000
        assert path.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n'
        assert not (tmp_path / name).exists() and not os.path.exists(name)


def test_train_model_skip_cv(xy, tmp_path):
    X, y = xy
    rf, metrics = tm.train_model(X, y, out_dir=str(tmp_path), skip_cv=True)
    assert hasattr(rf, 'estimators_')
    assert 'test_rmse' in metrics and 'cv_rmse' not in metrics and 'cv_rmse_folds' not in metrics


def test_train_model_default_out_dir_is_outputs_under_repo_root():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert tm.DEFAULT_OUT_DIR == os.path.join(repo_root, 'outputs')


def test_train_model_is_reproducible_and_independent_of_n_jobs(xy, tmp_path):
    X, y = xy
    p1 = tm.train_model(X, y, out_dir=str(tmp_path / 'a'), skip_cv=True)[0].predict(X)
    p2 = tm.train_model(X, y, out_dir=str(tmp_path / 'b'), skip_cv=True)[0].predict(X)
    p3 = tm.train_model(X, y, out_dir=str(tmp_path / 'c'), skip_cv=True, n_jobs=2)[0].predict(X)
    np.testing.assert_array_equal(p1, p2)
    # With n_jobs=2 the per-tree predictions are summed in a different order, which moves
    # the last few bits (about 1e-15); the forest itself is identical (fixed random_state).
    np.testing.assert_allclose(p1, p3, rtol=1e-12, atol=0)
