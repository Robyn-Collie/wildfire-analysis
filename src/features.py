import pandas as pd
import numpy as np
import logging
from typing import Tuple

# Get logger
logger = logging.getLogger(__name__)

def preprocess_data(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Applies feature engineering to the raw wildfire data.
    
    Args:
        df (pd.DataFrame): Raw data loaded from the database.
        
    Returns:
        tuple: (X, y) where X is the feature matrix and y is the target vector.
    """
    logger.info("Starting feature engineering...")
    
    # Copy to avoid SettingWithCopyWarning
    df = df.copy()
    
    # 1. Convert dates to datetime objects
    # Why? We need to perform date arithmetic to calculate the duration.
    df['DISCOVERY_DATE'] = pd.to_datetime(df['DISCOVERY_DATE'])
    df['CONT_DATE'] = pd.to_datetime(df['CONT_DATE'])
    
    # 2. Calculate Target: Duration in Days
    # Why? This is our target variable. We calculate it as the difference between containment and discovery.
    df['DURATION_DAYS'] = (df['CONT_DATE'] - df['DISCOVERY_DATE']).dt.days
    
    # 3. Handle Data Quality Issues
    # Why? A negative duration (containment before discovery) is impossible and indicates data error.
    initial_len = len(df)
    df = df[df['DURATION_DAYS'] >= 0].copy()
    dropped_count = initial_len - len(df)
    if dropped_count > 0:
        logger.warning(f"Dropped {dropped_count} records with invalid (negative) duration.")
    
    # 4. Cyclical Time Features
    # Why? The Day of Year (1-365) is cyclical. Day 365 (Dec 31) is temporally close to Day 1 (Jan 1).
    # Using raw numbers (1 vs 365) implies a large distance. 
    # Transforming into Sine and Cosine components preserves this cyclical relationship.
    df['SIN_DOY'] = np.sin(2 * np.pi * df['DISCOVERY_DOY'] / 365)
    df['COS_DOY'] = np.cos(2 * np.pi * df['DISCOVERY_DOY'] / 365)
    
    # 5. One-Hot Encoding for Categorical Variables
    # Why? Models require numerical input. 'NWCG_GENERAL_CAUSE' is categorical (e.g., 'Arson', 'Lightning').
    # One-hot encoding creates binary columns for each category, preventing the model from inferring 
    # false ordinal relationships (e.g., assuming category 2 is "greater" than category 1).
    df = pd.get_dummies(df, columns=['NWCG_GENERAL_CAUSE'], prefix='CAUSE')
    
    # 6. Feature Selection
    # Why? We remove columns that are not predictive features available at discovery time:
    # - Dates/IDs: Used for calculation but not raw features.
    # - FIRE_SIZE_CLASS: This is likely the final fire size, which is not known at discovery (Data Leakage).
    # - FIRE_YEAR: We want the model to learn seasonal patterns (via DOY), not just "2015 was bad".
    drop_cols = ['FIRE_YEAR', 'DISCOVERY_DATE', 'CONT_DATE', 'DISCOVERY_DOY', 'FIRE_SIZE_CLASS']
    
    # Check which columns exist before dropping (in case one-hot removed them or they weren't loaded)
    existing_drop_cols = [col for col in drop_cols if col in df.columns]
    df_model = df.drop(columns=existing_drop_cols)
    
    # Separate Target (y) and Features (X)
    y = df_model['DURATION_DAYS']
    X = df_model.drop(columns=['DURATION_DAYS'])
    
    # Fill any NaNs created by OHE (though get_dummies usually handles this) or original data
    X = X.fillna(0)
    
    logger.info(f"Feature engineering complete.")
    logger.info(f"Features (X): {X.shape}, Target (y): {y.shape}")
    
    return X, y

if __name__ == "__main__":
    # Simple test case
    print("Running features.py test...")
    data = {
        'FIRE_YEAR': [2020, 2020],
        'DISCOVERY_DATE': ['2020-01-01', '2020-12-31'],
        'CONT_DATE': ['2020-01-02', '2020-12-31'],
        'DISCOVERY_DOY': [1, 366],
        'LATITUDE': [34.0, 35.0],
        'LONGITUDE': [-118.0, -119.0],
        'FIRE_SIZE_CLASS': ['A', 'B'],
        'NWCG_GENERAL_CAUSE': ['Natural', 'Human']
    }
    df_test = pd.DataFrame(data)
    X, y = preprocess_data(df_test)
    print("Features:", X.columns.tolist())
