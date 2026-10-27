"""
Configuration settings for EnergyPulse Cloud.
Handles both Demo Mode (offline local execution) and Cloud Mode (GCS + BigQuery).
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if available
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class AppConfig:
    """Application configuration parameters."""
    
    # Execution mode
    DEMO_MODE: bool = os.getenv("DEMO_MODE", "True").lower() in ("true", "1", "yes")

    # Directory Paths
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = BASE_DIR / "data"
    RAW_DATA_DIR: Path = DATA_DIR / "raw"
    PROCESSED_DATA_DIR: Path = DATA_DIR / "processed"
    SAMPLE_DATA_PATH: Path = DATA_DIR / "sample_household_power.csv"

    # Dataset Constants
    UCI_DATASET_URL: str = "https://archive.ics.uci.edu/static/public/235/individual+household+electric+power+consumption.zip"
    UCI_ZIP_FILENAME: str = "individual+household+electric+power+consumption.zip"
    UCI_TXT_FILENAME: str = "household_power_consumption.txt"

    # Google Cloud Platform Settings
    GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "energypulse-cloud-dev")
    GCP_REGION: str = os.getenv("GCP_REGION", "us-central1")
    GCS_BUCKET_NAME: str = os.getenv("GCS_BUCKET_NAME", "energypulse-raw-data-bucket")
    BQ_DATASET_ID: str = os.getenv("BQ_DATASET_ID", "energypulse_analytics")
    BQ_TABLE_ID: str = os.getenv("BQ_TABLE_ID", "household_hourly_consumption")

    # Column Mapping for UCI Dataset
    EXPECTED_RAW_COLUMNS = [
        "Date",
        "Time",
        "Global_active_power",
        "Global_reactive_power",
        "Voltage",
        "Global_intensity",
        "Sub_metering_1",
        "Sub_metering_2",
        "Sub_metering_3",
    ]

    # Target unit specifications
    RAW_POWER_UNIT = "kW"
    HOURLY_ENERGY_UNIT = "kWh"

    @classmethod
    def ensure_directories(cls):
        """Ensure necessary local folders exist."""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)


AppConfig.ensure_directories()
