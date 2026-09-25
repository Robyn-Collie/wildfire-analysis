import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import logging
from typing import Tuple, List
from sklearn.model_selection import train_test_split, cross_val_score, KFold
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error

# Get logger
logger = logging.getLogger(__name__)

RANDOM_STATE = 42


def split_data(X: pd.DataFrame, y: pd.Series):
    """The 80/20 random split used for the reported results."""
    return train_test_split(X, y, test_size=0.2, random_state=RANDOM_STATE)


def build_model(n_jobs: int = -1) -> RandomForestRegressor:
    """The Random Forest configuration used for the reported results."""
    # n_estimators=100: Number of trees. More is usually better but slower.
    # max_depth=10: Prevents overfitting by limiting tree complexity.
    # n_jobs=-1: Use all CPU cores.
    return RandomForestRegressor(n_estimators=100, max_depth=10, random_state=RANDOM_STATE, n_jobs=n_jobs)


def train_model(X: pd.DataFrame, y: pd.Series) -> RandomForestRegressor:
    """
    Trains a Random Forest Regressor, performs Cross-Validation, and evaluates performance.

    Args:
        X (pd.DataFrame): Features matrix.
        y (pd.Series): Target vector.

    Returns:
        RandomForestRegressor: The trained model.
    """
    logger.info("Splitting data into Train and Test sets (80/20)...")
    X_train, X_test, y_train, y_test = split_data(X, y)

    logger.info("Initializing Random Forest Regressor...")
    rf = build_model()

    # --- CROSS VALIDATION ---
    # We validate on the Training set to ensure the model's stability before final evaluation.
    logger.info("Performing 5-Fold Cross-Validation (This validates model stability)...")
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    
    # We use negative RMSE because scikit-learn maximizes scores (so higher is better)
    cv_scores = cross_val_score(rf, X_train, y_train, cv=kf, scoring='neg_root_mean_squared_error', n_jobs=-1)
    cv_rmse = -cv_scores.mean()
    
    logger.info(f"Cross-Validation Mean RMSE: {cv_rmse:.4f} (+/- {cv_scores.std():.4f})")
    
    # --- FINAL TRAINING ---
    logger.info("Training final model on full training set...")
    rf.fit(X_train, y_train)
    
    # --- FINAL EVALUATION ---
    logger.info("Evaluating on held-out Test Set...")
    y_pred = rf.predict(X_test)
    
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    mae = mean_absolute_error(y_test, y_pred)
    
    logger.info("=" * 40)
    logger.info("FINAL MODEL PERFORMANCE (TEST SET)")
    logger.info(f"RMSE (Root Mean Sq Error): {rmse:.4f} days")
    logger.info(f"MAE  (Mean Abs Error):    {mae:.4f} days")
    logger.info("=" * 40)
    
    # --- VISUALIZATION ---
    plot_feature_importance(rf, X.columns)
    plot_residuals(y_test, y_pred)
    
    return rf

def plot_residuals(y_true: pd.Series, y_pred: np.ndarray) -> None:
    """
    Plots Predicted vs Actual values to visualize model error.
    A perfect model would align all points on the red diagonal line.
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
    
    output_path = 'residuals.png'
    plt.savefig(output_path)
    plt.close()
    logger.info(f"Residuals plot saved to '{output_path}'")

def plot_feature_importance(model: RandomForestRegressor, feature_names: pd.Index) -> None:
    """
    Generates and saves a feature importance plot.
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
    
    output_path = 'feature_importance.png'
    plt.savefig(output_path)
    plt.close()
    logger.info(f"Feature importance plot saved to '{output_path}'")
