import sqlite3
import pandas as pd
import os
import logging

# Get logger
logger = logging.getLogger(__name__)

DB_FILENAME = 'FPA_FOD_20221014.sqlite'

# Repo root is one level up from src/. The database lives in data/ (not committed);
# run scripts/download_data.py to fetch it, or set WILDFIRE_DB_PATH to point elsewhere.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_PATH = os.path.join(REPO_ROOT, 'data', DB_FILENAME)

# Shown by the command-line entry point (run_pipeline.py) when the file is missing.
MISSING_DB_HELP = (
    f"Run 'python scripts/download_data.py' to put '{DB_FILENAME}' in the 'data' directory, "
    "or set WILDFIRE_DB_PATH to its location. "
    "Source: USDA Forest Service, FPA FOD 6th edition (doi:10.2737/RDS-2013-0009.6)"
)

# The model sample: fires from 2010 on that have a containment date. FOD_ID is the
# dataset's stable fire identifier; ordering by it makes the row order (and therefore
# the position-based train/test split) independent of the file's physical row order.
QUERY = """
SELECT
    FOD_ID,
    FIRE_YEAR,
    DISCOVERY_DATE,
    DISCOVERY_DOY,
    CONT_DATE,
    LATITUDE,
    LONGITUDE,
    FIRE_SIZE_CLASS,
    NWCG_GENERAL_CAUSE
FROM Fires
WHERE FIRE_YEAR >= 2010
  AND CONT_DATE IS NOT NULL
ORDER BY FOD_ID
"""


def load_data(db_path: str = None) -> pd.DataFrame:
    """
    Loads wildfire data from the SQLite database.

    Args:
        db_path (str): Path to the SQLite database file. Defaults to the
            WILDFIRE_DB_PATH environment variable, then data/FPA_FOD_20221014.sqlite
            under the repo root.

    Returns:
        pd.DataFrame: DataFrame containing the filtered wildfire data, ordered by FOD_ID.

    Raises:
        FileNotFoundError: if the database file does not exist.
        sqlite3.DatabaseError (or another exception): if the file cannot be read or
            queried. Errors propagate to the caller; nothing here exits the interpreter.
    """
    if db_path is None:
        db_path = os.environ.get('WILDFIRE_DB_PATH', DEFAULT_DB_PATH)

    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at '{db_path}'. {MISSING_DB_HELP}")

    logger.info(f"Connecting to database at {db_path}...")
    conn = sqlite3.connect(db_path)
    try:
        logger.info("Executing query...")
        df = pd.read_sql_query(QUERY, conn)
    finally:
        conn.close()

    logger.info(f"Successfully loaded {len(df)} records.")
    return df


if __name__ == "__main__":
    # Simple test to verify the loader works independently
    df = load_data()
    print(df.head())
