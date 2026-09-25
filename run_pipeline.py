import sys
import os
import logging

# Configure logging: a standard format with timestamps
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('Pipeline')

# Add src to python path to allow imports if run from root
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

try:
    from data_loader import load_data
    from features import preprocess_data
    from train_model import train_model
except ImportError as e:
    logger.error(f"Error importing modules: {e}")
    logger.error("Please ensure you are running this script from the project root.")
    sys.exit(1)

def main():
    logger.info("==================================================")
    logger.info("   Wildfire Duration Prediction Pipeline")
    logger.info("==================================================")
    
    # 1. Load Data
    logger.info("[Step 1/3] Loading Data...")
    df = load_data()
    
    # 2. Preprocess Data
    logger.info("[Step 2/3] Preprocessing & Feature Engineering...")
    X, y = preprocess_data(df)
    
    # 3. Train Model and Evaluate
    logger.info("[Step 3/3] Training Model & Evaluating...")
    # This step now includes Cross-Validation inside train_model
    rf_model = train_model(X, y)
    
    logger.info("Pipeline completed successfully!")
    logger.info("Check 'feature_importance.png' and 'residuals.png' for visualization.")

if __name__ == "__main__":
    main()
