import json
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import logging
from typing import Dict, Tuple
from sklearn.model_selection import train_test_split, cross_val_score, KFold
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error

# Get logger
logger = logging.getLogger(__name__)

RANDOM_STATE = 42

# Model configuration used for the reported results.
N_ESTIMATORS = 100
MAX_DEPTH = 10
TEST_SIZE = 0.2
CV_FOLDS = 5

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT_DIR = os.path.join(REPO_ROOT, 'outputs')

# Parallelism is read from one place. WILDFIRE_N_JOBS defaults to 1 (single core), which
# is the project rule on shared machines; set it to -1 for all cores. Results do not
# depend on it because every estimator has a fixed random_state; only wall time does.
N_JOBS_ENV = 'WILDFIRE_N_JOBS'


def default_n_jobs() -> int:
    """Number of parallel jobs from the WILDFIRE_N_JOBS environment variable (default 1)."""
    raw = os.environ.get(N_JOBS_ENV, '1').strip()
    try:
        n_jobs = int(raw)
    except ValueError:
        raise ValueError(f'{N_JOBS_ENV} must be an integer (got {raw!r})')
    if n_jobs == 0:
        raise ValueError(f'{N_JOBS_ENV} must be -1 or a positive integer (got 0)')
    return n_jobs


def split_data(X: pd.DataFrame, y: pd.Series):
    """The 80/20 random split used for the reported results."""
    return train_test_split(X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE)


def build_model(n_jobs: int = None) -> RandomForestRegressor:
    """The Random Forest configuration used for the reported results."""
    # n_estimators=100: Number of trees. More is usually better but slower.
    # max_depth=10: Prevents overfitting by limiting tree complexity.
    # n_jobs: from WILDFIRE_N_JOBS unless given explicitly.
    if n_jobs is None:
        n_jobs = default_n_jobs()
    return RandomForestRegressor(n_estimators=N_ESTIMATORS, max_depth=MAX_DEPTH,
                                 random_state=RANDOM_STATE, n_jobs=n_jobs)


def train_model(X: pd.DataFrame, y: pd.Series, n_jobs: int = None, out_dir: str = DEFAULT_OUT_DIR,
                skip_cv: bool = False) -> Tuple[RandomForestRegressor, Dict]:
    """
    Trains a Random Forest Regressor, performs Cross-Validation, and evaluates performance.

    Args:
        X (pd.DataFrame): Features matrix.
        y (pd.Series): Target vector.
        n_jobs (int): Parallel jobs for the forest; defaults to WILDFIRE_N_JOBS (1).
        out_dir (str): Where metrics.json and the two plots are written (default outputs/
            under the repo root). Created if missing.
        skip_cv (bool): Skip the 5-fold cross-validation (the CV keys are then absent).

    Returns:
        (RandomForestRegressor, dict): The trained model and the metrics that were also
            written to <out_dir>/metrics.json.
    """
    if n_jobs is None:
        n_jobs = default_n_jobs()
    os.makedirs(out_dir, exist_ok=True)

    logger.info("Splitting data into Train and Test sets (80/20)...")
    X_train, X_test, y_train, y_test = split_data(X, y)

    logger.info(f"Initializing Random Forest Regressor (n_jobs={n_jobs})...")
    rf = build_model(n_jobs=n_jobs)

    metrics = {
        'model': 'RandomForestRegressor',
        'n_estimators': N_ESTIMATORS, 'max_depth': MAX_DEPTH, 'random_state': RANDOM_STATE,
        'test_size': TEST_SIZE, 'n_jobs': n_jobs,
        'n_rows': int(len(y)), 'n_train': int(len(y_train)), 'n_test': int(len(y_test)),
        'n_features': int(X.shape[1]), 'features': list(X.columns),
    }

    # --- CROSS VALIDATION ---
    # We validate on the Training set to ensure the model's stability before final evaluation.
    if not skip_cv:
        logger.info("Performing 5-Fold Cross-Validation (This validates model stability)...")
        kf = KFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)

        # We use negative RMSE because scikit-learn maximizes scores (so higher is better).
        # n_jobs=1: the folds run sequentially; parallelism (if any) stays inside the forest,
        # so the training frame is not pickled to five worker processes.
        cv_scores = cross_val_score(rf, X_train, y_train, cv=kf, scoring='neg_root_mean_squared_error', n_jobs=1)
        cv_rmse = float(-cv_scores.mean())
        metrics['cv_folds'] = CV_FOLDS
        metrics['cv_rmse'] = cv_rmse
        metrics['cv_rmse_std'] = float(cv_scores.std())
        metrics['cv_rmse_folds'] = [float(-s) for s in cv_scores]
        logger.info(f"Cross-Validation Mean RMSE: {cv_rmse:.4f} (+/- {cv_scores.std():.4f})")

    # --- FINAL TRAINING ---
    logger.info("Training final model on full training set...")
    rf.fit(X_train, y_train)

    # --- FINAL EVALUATION ---
    logger.info("Evaluating on held-out Test Set...")
    y_pred = rf.predict(X_test)

    rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
    mae = float(mean_absolute_error(y_test, y_pred))
    metrics['test_rmse'] = rmse
    metrics['test_mae'] = mae

    logger.info("=" * 40)
    logger.info("FINAL MODEL PERFORMANCE (TEST SET)")
    logger.info(f"RMSE (Root Mean Sq Error): {rmse:.4f} days")
    logger.info(f"MAE  (Mean Abs Error):    {mae:.4f} days")
    logger.info("=" * 40)

    metrics_path = os.path.join(out_dir, 'metrics.json')
    with open(metrics_path, 'w') as f:
        json.dump(metrics, f, indent=2)
    logger.info(f"Metrics written to '{metrics_path}'")

    # --- VISUALIZATION ---
    plot_feature_importance(rf, X.columns, out_dir)
    plot_residuals(y_test, y_pred, out_dir)

    return rf, metrics

def plot_residuals(y_true: pd.Series, y_pred: np.ndarray, out_dir: str = DEFAULT_OUT_DIR) -> str:
    """
    Plots Predicted vs Actual values to visualize model error.
    A perfect model would align all points on the red diagonal line.
    Returns the path of the PNG written to out_dir.
    """
    logger.info("Generating Residuals Plot...")
    plt.figure(figsize=(10, 6))

    # Scatter plot with transparency to handle dense data
    sns.scatterplot(x=y_true, y=y_pred, alpha=0.1)

    # Diagonal line (Perfect Prediction)
    max_val = max(y_true.max(), y_pred.max())
    plt.plot([0, max_val], [0, max_val], 'r--', lw=2, label='Perfect Prediction')

    plt.title('Predicted vs Actual Duration (Residual Analysis)')
    plt.xlabel('Actual Duration (Days)')
    plt.ylabel('Predicted Duration (Days)')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    os.makedirs(out_dir, exist_ok=True)
    output_path = os.path.join(out_dir, 'residuals.png')
    plt.savefig(output_path)
    plt.close()
    logger.info(f"Residuals plot saved to '{output_path}'")
    return output_path

def plot_feature_importance(model: RandomForestRegressor, feature_names: pd.Index,
                            out_dir: str = DEFAULT_OUT_DIR) -> str:
    """
    Generates and saves a feature importance plot. Returns the path of the PNG written to out_dir.
    """
    logger.info("Generating Feature Importance Plot...")

    importances = model.feature_importances_
    indices = np.argsort(importances)[::-1]

    # Create DataFrame for plotting
    fi_df = pd.DataFrame({
        'Feature': [feature_names[i] for i in indices],
        'Importance': importances[indices]
    })

    plt.figure(figsize=(10, 6))
    sns.barplot(x='Importance', y='Feature', data=fi_df.head(10))
    plt.title('Top 10 Feature Importances - Wildfire Duration')
    plt.xlabel('Importance (Gini Impurity Reduction)')
    plt.ylabel('Feature')
    plt.tight_layout()

    os.makedirs(out_dir, exist_ok=True)
    output_path = os.path.join(out_dir, 'feature_importance.png')
    plt.savefig(output_path)
    plt.close()
    logger.info(f"Feature importance plot saved to '{output_path}'")
    return output_path
