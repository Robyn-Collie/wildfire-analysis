import pandas as pd
import numpy as np
import logging
from typing import Tuple

# Get logger
logger = logging.getLogger(__name__)

# The FPA FOD text date format ('M/D/YYYY', unpadded, e.g. '2/2/2005'). Parsed with an
# explicit format so a differently formatted file raises instead of being guessed.
DATE_FORMAT = '%m/%d/%Y'

# The 13 NWCG_GENERAL_CAUSE values in the FPA FOD 6th edition (SELECT DISTINCT), in
# alphabetical order. The one-hot columns are always exactly these, in this order,
# whatever subset of causes a given batch of rows happens to contain.
CAUSE_LEVELS = [
    'Arson/incendiarism',
    'Debris and open burning',
    'Equipment and vehicle use',
    'Firearms and explosives use',
    'Fireworks',
    'Missing data/not specified/undetermined',
    'Misuse of fire by a minor',
    'Natural',
    'Other causes',
    'Power generation/transmission/distribution',
    'Railroad operations and maintenance',
    'Recreation and ceremony',
    'Smoking',
]
CAUSE_COLUMNS = [f'CAUSE_{c}' for c in CAUSE_LEVELS]

# The feature matrix schema: X.columns is always exactly this list, in this order.
FEATURE_COLUMNS = ['LATITUDE', 'LONGITUDE', 'SIN_DOY', 'COS_DOY'] + CAUSE_COLUMNS

# Input columns preprocess_data needs. Anything else the loader selects (FOD_ID,
# FIRE_YEAR, DISCOVERY_DOY, FIRE_SIZE_CLASS) is ignored: it is an identifier, a
# calculation aid, or known only after the fire (FIRE_SIZE_CLASS would be leakage).
REQUIRED_COLUMNS = ['DISCOVERY_DATE', 'CONT_DATE', 'LATITUDE', 'LONGITUDE', 'NWCG_GENERAL_CAUSE']


def preprocess_data(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Applies feature engineering to the raw wildfire data.

    Args:
        df (pd.DataFrame): Raw data loaded from the database (see REQUIRED_COLUMNS).

    Returns:
        tuple: (X, y) where X is the feature matrix with columns FEATURE_COLUMNS and
            y is the target vector (whole days from discovery to containment). Both keep
            the input's index labels; rows with a negative duration are dropped.

    Raises:
        KeyError: if a required column is missing.
        ValueError: if a date does not match DATE_FORMAT, a duration is NaN (a missing
            date), a cause is null or not one of CAUSE_LEVELS, or a feature has nulls.
    """
    logger.info("Starting feature engineering...")

    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise KeyError(f'preprocess_data needs columns {missing_cols}')

    # Copy to avoid SettingWithCopyWarning
    df = df.copy()

    # 1. Convert dates to datetime objects
    # Why? We need to perform date arithmetic to calculate the duration.
    # errors='raise' (the default): a date in any other format is a data error, not a guess.
    df['DISCOVERY_DATE'] = pd.to_datetime(df['DISCOVERY_DATE'], format=DATE_FORMAT)
    df['CONT_DATE'] = pd.to_datetime(df['CONT_DATE'], format=DATE_FORMAT)

    # 2. Calculate Target: Duration in Days
    # Why? This is our target variable. We calculate it as the difference between containment and discovery.
    df['DURATION_DAYS'] = (df['CONT_DATE'] - df['DISCOVERY_DATE']).dt.days

    # 3. Handle Data Quality Issues
    # A NaN duration means a missing date. The loader promises CONT_DATE IS NOT NULL, so
    # any NaN here is a contract violation and is reported as such, never as "negative".
    n_nan = int(df['DURATION_DAYS'].isna().sum())
    if n_nan:
        raise ValueError(f'{n_nan} records have a missing DISCOVERY_DATE or CONT_DATE (NaN duration); '
                         'load_data filters CONT_DATE IS NOT NULL, so the input is not what the loader produces.')
    # Why? A negative duration (containment before discovery) is impossible and indicates data error.
    negative = df['DURATION_DAYS'] < 0
    n_negative = int(negative.sum())
    if n_negative > 0:
        logger.warning(f"Dropped {n_negative} records with invalid (negative) duration.")
        df = df[~negative].copy()
    df['DURATION_DAYS'] = df['DURATION_DAYS'].astype('int64')

    # 4. Cyclical Time Features
    # Why? The day of year is cyclical: Dec 31 is temporally close to Jan 1. Using raw
    # numbers (1 vs 365) implies a large distance. Transforming into sine and cosine
    # components preserves this cyclical relationship.
    # The angle is 2*pi*(DOY-1)/days_in_year, computed from DISCOVERY_DATE rather than the
    # DISCOVERY_DOY column: Jan 1 is angle 0, Dec 31 is one day short of a full turn, and
    # days_in_year is 366 in leap years so Dec 31 of a leap year (DOY 366) does not land on
    # the same angle as Jan 1.
    doy = df['DISCOVERY_DATE'].dt.dayofyear
    days_in_year = np.where(df['DISCOVERY_DATE'].dt.is_leap_year, 366, 365)
    angle = 2 * np.pi * (doy - 1) / days_in_year
    df['SIN_DOY'] = np.sin(angle)
    df['COS_DOY'] = np.cos(angle)

    # 5. One-Hot Encoding for Categorical Variables
    # Why? Models require numerical input. 'NWCG_GENERAL_CAUSE' is categorical (e.g., 'Arson', 'Lightning').
    # One-hot encoding creates binary columns for each category, preventing the model from inferring
    # false ordinal relationships (e.g., assuming category 2 is "greater" than category 1).
    # Encoding against the fixed CAUSE_LEVELS keeps the schema stable: a batch that lacks a
    # cause still gets that (all-zero) column, and a new or misspelt cause value is an error
    # rather than a silently added column. A null cause is also an error: it would encode as
    # an all-zero row, indistinguishable from nothing.
    n_null_cause = int(df['NWCG_GENERAL_CAUSE'].isna().sum())
    if n_null_cause:
        raise ValueError(f'{n_null_cause} records have a null NWCG_GENERAL_CAUSE; map them to '
                         f"'Missing data/not specified/undetermined' explicitly before calling preprocess_data.")
    unknown = sorted(set(df['NWCG_GENERAL_CAUSE'].unique()) - set(CAUSE_LEVELS))
    if unknown:
        raise ValueError(f'Unknown NWCG_GENERAL_CAUSE values: {unknown}. Known values: {CAUSE_LEVELS}')
    df['NWCG_GENERAL_CAUSE'] = pd.Categorical(df['NWCG_GENERAL_CAUSE'], categories=CAUSE_LEVELS)
    dummies = pd.get_dummies(df['NWCG_GENERAL_CAUSE'], prefix='CAUSE')

    # 6. Feature Selection
    # Why? Only features available at discovery time, selected by an explicit whitelist
    # (FEATURE_COLUMNS) rather than by dropping what we happen to know about:
    # - Dates/IDs: used for calculation but not raw features.
    # - FIRE_SIZE_CLASS: the final fire size, not known at discovery (data leakage).
    # - FIRE_YEAR: we want the model to learn seasonal patterns (via DOY), not just "2015 was bad".
    X = pd.concat([df[['LATITUDE', 'LONGITUDE', 'SIN_DOY', 'COS_DOY']], dummies], axis=1)
    y = df['DURATION_DAYS']

    # No imputation. A missing coordinate must not become 0 N 0 E; a null anywhere in X is
    # a data error the caller has to handle explicitly.
    null_counts = X.isna().sum()
    if null_counts.any():
        raise ValueError(f'Feature columns contain nulls: {null_counts[null_counts > 0].to_dict()}')

    assert list(X.columns) == FEATURE_COLUMNS, f'feature schema drift: {list(X.columns)}'
    assert X.index.equals(y.index)

    logger.info(f"Feature engineering complete.")
    logger.info(f"Features (X): {X.shape}, Target (y): {y.shape}")

    return X, y


if __name__ == "__main__":
    # Smoke test: two rows, one in a leap year on Dec 31 (DOY 366).
    print("Running features.py smoke test...")
    data = {
        'FIRE_YEAR': [2020, 2020],
        'DISCOVERY_DATE': ['1/1/2020', '12/31/2020'],
        'CONT_DATE': ['1/2/2020', '12/31/2020'],
        'DISCOVERY_DOY': [1, 366],
        'LATITUDE': [34.0, 35.0],
        'LONGITUDE': [-118.0, -119.0],
        'FIRE_SIZE_CLASS': ['A', 'B'],
        'NWCG_GENERAL_CAUSE': ['Natural', 'Smoking'],
    }
    X, y = preprocess_data(pd.DataFrame(data))
    assert list(X.columns) == FEATURE_COLUMNS and y.tolist() == [1, 0]
    assert abs(X.loc[1, 'SIN_DOY'] + np.sin(2 * np.pi / 366)) < 1e-12, 'Dec 31 of a leap year is one day before Jan 1'
    print("Features:", X.columns.tolist())
