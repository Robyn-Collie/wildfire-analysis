import sqlite3
import pandas as pd
import sys
import os
import logging

# Get logger
logger = logging.getLogger(__name__)

DB_FILENAME = 'FPA_FOD_20221014.sqlite'

# Repo root is one level up from src/. The database lives in data/ (not committed);
# run scripts/download_data.py to fetch it, or set WILDFIRE_DB_PATH to point elsewhere.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB_PATH = os.path.join(REPO_ROOT, 'data', DB_FILENAME)


def load_data(db_path: str = None) -> pd.DataFrame:
    """
    Loads wildfire data from the SQLite database.
    
    Args:
        db_path (str): Path to the SQLite database file. Defaults to the
            WILDFIRE_DB_PATH environment variable, then data/FPA_FOD_20221014.sqlite
            under the repo root.
        
    Returns:
        pd.DataFrame: DataFrame containing the filtered wildfire data.
    """
    if db_path is None:
        db_path = os.environ.get('WILDFIRE_DB_PATH', DEFAULT_DB_PATH)

    # Check if database exists
    if not os.path.exists(db_path):
        logger.error(f"Database not found at '{db_path}'.")
        logger.error(f"Run 'python scripts/download_data.py' to put '{DB_FILENAME}' in the 'data' directory,")
        logger.error("or set WILDFIRE_DB_PATH to its location.")
        logger.error("Source: USDA Forest Service, FPA FOD 6th edition (doi:10.2737/RDS-2013-0009.6)")
        sys.exit(1)

    logger.info(f"Connecting to database at {db_path}...")
    
    try:
        conn = sqlite3.connect(db_path)
        
        # Query to select only necessary columns and filter by year and containment date
        # We query specific columns to minimize memory usage and focus on relevant data
        query = """
        SELECT 
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
        """
        
        logger.info("Executing query...")
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        logger.info(f"Successfully loaded {len(df)} records.")
        return df
        
    except Exception as e:
        logger.error(f"An error occurred while loading data: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Simple test to verify the loader works independently
    df = load_data()
    print(df.head())
