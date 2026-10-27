"""
Data Ingestion Module for EnergyPulse Cloud.
Handles downloading, extracting, validating, and reading the UCI Household Electric Power Consumption dataset.
Supports both the genuine UCI archive and local development sample files.
"""

import os
import zipfile
import logging
from pathlib import Path
from typing import Optional, Tuple
import requests
import pandas as pd

from config.settings import AppConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class DatasetIngestion:
    """Manages raw dataset acquisition, extraction, and initial validation."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or AppConfig.DATA_DIR
        self.raw_dir = self.data_dir / "raw"
        self.zip_path = self.raw_dir / AppConfig.UCI_ZIP_FILENAME
        self.txt_path = self.raw_dir / AppConfig.UCI_TXT_FILENAME
        self.sample_path = AppConfig.SAMPLE_DATA_PATH

        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def download_uci_dataset(self, url: Optional[str] = None, timeout: int = 60) -> Path:
        """
        Download the official UCI Household Electric Power Consumption dataset ZIP file.
        Uses streaming to handle ~20MB download safely.
        """
        download_url = url or AppConfig.UCI_DATASET_URL
        fallback_url = "https://archive.ics.uci.edu/ml/machine-learning-databases/00235/household_power_consumption.zip"

        if self.txt_path.exists() and self.txt_path.stat().st_size > 10_000_000:
            logger.info("Extracted raw dataset already exists at %s", self.txt_path)
            return self.txt_path

        logger.info("Attempting download from primary URL: %s", download_url)
        for target_url in [download_url, fallback_url]:
            try:
                with requests.get(target_url, stream=True, timeout=timeout) as r:
                    r.raise_for_status()
                    with open(self.zip_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                logger.info("Download completed successfully. Saved to %s (%d bytes)",
                            self.zip_path, self.zip_path.stat().st_size)
                return self.extract_archive()
            except Exception as e:
                logger.warning("Failed downloading from %s: %s", target_url, e)

        raise RuntimeError("Unable to download dataset from official sources. Check internet connection or use Demo Mode.")

    def extract_archive(self) -> Path:
        """Extract the downloaded zip archive to find household_power_consumption.txt."""
        if not self.zip_path.exists():
            raise FileNotFoundError(f"Archive file not found at {self.zip_path}")

        logger.info("Extracting %s...", self.zip_path)
        with zipfile.ZipFile(self.zip_path, "r") as archive:
            archive.extractall(self.raw_dir)

        if not self.txt_path.exists():
            # Check for alternative naming in archive
            txt_files = list(self.raw_dir.glob("*.txt"))
            if txt_files:
                self.txt_path = txt_files[0]
            else:
                raise FileNotFoundError("Could not find extracted .txt file inside archive.")

        logger.info("Extracted dataset to %s (%d bytes)", self.txt_path, self.txt_path.stat().st_size)
        return self.txt_path

    def load_raw_dataframe(self, max_rows: Optional[int] = None, use_sample_if_missing: bool = True) -> Tuple[pd.DataFrame, str]:
        """
        Load raw dataframe with validation.
        Returns (DataFrame, source_description).
        """
        target_path: Optional[Path] = None
        source_label = "Real UCI Dataset"

        if self.txt_path.exists():
            target_path = self.txt_path
        elif self.zip_path.exists():
            self.extract_archive()
            target_path = self.txt_path
        elif use_sample_if_missing and self.sample_path.exists():
            target_path = self.sample_path
            source_label = "Synthetic Development Sample (Demo Mode)"
        else:
            raise FileNotFoundError("No raw dataset or sample data available. Download UCI dataset or generate sample.")

        logger.info("Loading raw data from %s (source: %s)...", target_path, source_label)

        # Read first row to determine delimiter and validate header
        with open(target_path, "r", encoding="utf-8", errors="replace") as f:
            first_line = f.readline().strip()
            delimiter = ";" if ";" in first_line else ","

        df = pd.read_csv(
            target_path,
            sep=delimiter,
            nrows=max_rows,
            low_memory=False,
            dtype=str  # Read as string to safely handle '?' missing value markers
        )

        self.validate_schema(df)
        logger.info("Loaded %d rows and %d columns from %s", len(df), len(df.columns), target_path.name)
        return df, source_label

    @staticmethod
    def validate_schema(df: pd.DataFrame) -> bool:
        """
        Validate that required columns exist in raw dataframe.
        Raises ValueError if schema mismatch occurs.
        """
        expected = AppConfig.EXPECTED_RAW_COLUMNS
        missing = [col for col in expected if col not in df.columns]
        if missing:
            raise ValueError(f"Schema validation failed. Missing expected columns: {missing}")
        return True


if __name__ == "__main__":
    ingestor = DatasetIngestion()
    print("Testing load with sample...")
    if ingestor.sample_path.exists():
        df_sample, label = ingestor.load_raw_dataframe(max_rows=100)
        print(f"Loaded {len(df_sample)} rows ({label})")
