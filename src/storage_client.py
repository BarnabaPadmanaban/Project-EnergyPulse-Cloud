"""
Cloud Storage Client for EnergyPulse Cloud.
Manages raw and processed dataset transfers to/from Google Cloud Storage.
Seamlessly falls back to local directory persistence when running in Demo Mode.
"""

import os
import logging
from pathlib import Path
from typing import Optional, List
from config.settings import AppConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class CloudStorageClient:
    """Manages blob storage operations for GCS and local fallback."""

    def __init__(self, bucket_name: Optional[str] = None, demo_mode: Optional[bool] = None):
        self.bucket_name = bucket_name or AppConfig.GCS_BUCKET_NAME
        self.demo_mode = AppConfig.DEMO_MODE if demo_mode is None else demo_mode
        self.client = None
        self.bucket = None

        if not self.demo_mode:
            try:
                from google.cloud import storage
                self.client = storage.Client(project=AppConfig.GCP_PROJECT_ID)
                self.bucket = self.client.bucket(self.bucket_name)
                logger.info("Initialized Google Cloud Storage client for bucket: %s", self.bucket_name)
            except Exception as e:
                logger.warning(
                    "Could not initialize GCS client (%s). Operating in Local Storage Fallback Mode.", e
                )
                self.demo_mode = True
        else:
            logger.info("Operating CloudStorageClient in Local Demo Mode.")

    def upload_file(self, source_path: Path, destination_blob_name: str) -> str:
        """Upload a local file to GCS bucket (or copy to local storage in demo mode)."""
        if not source_path.exists():
            raise FileNotFoundError(f"Source file does not exist: {source_path}")

        if not self.demo_mode and self.bucket:
            blob = self.bucket.blob(destination_blob_name)
            blob.upload_from_filename(str(source_path))
            uri = f"gs://{self.bucket_name}/{destination_blob_name}"
            logger.info("Uploaded %s to %s", source_path.name, uri)
            return uri
        else:
            # Demo local storage simulation
            dest = AppConfig.DATA_DIR / "cloud_storage_mock" / destination_blob_name
            dest.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(source_path, dest)
            uri = f"mock-gcs://{self.bucket_name}/{destination_blob_name}"
            logger.info("[DEMO MODE] Stored file at simulated cloud path: %s", dest)
            return uri

    def download_file(self, blob_name: str, destination_path: Path) -> Path:
        """Download a blob from GCS (or retrieve from local simulation directory)."""
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.demo_mode and self.bucket:
            blob = self.bucket.blob(blob_name)
            blob.download_to_filename(str(destination_path))
            logger.info("Downloaded %s from GCS to %s", blob_name, destination_path)
            return destination_path
        else:
            mock_src = AppConfig.DATA_DIR / "cloud_storage_mock" / blob_name
            if mock_src.exists():
                import shutil
                shutil.copy2(mock_src, destination_path)
                logger.info("[DEMO MODE] Retrieved %s from simulated cloud storage.", blob_name)
                return destination_path
            elif AppConfig.SAMPLE_DATA_PATH.exists():
                import shutil
                shutil.copy2(AppConfig.SAMPLE_DATA_PATH, destination_path)
                logger.info("[DEMO MODE] Fallback: Copied sample data to %s", destination_path)
                return destination_path
            else:
                raise FileNotFoundError(f"Blob {blob_name} not found in simulated cloud storage.")

    def list_files(self, prefix: str = "") -> List[str]:
        """List blobs in bucket or simulated storage."""
        if not self.demo_mode and self.bucket:
            blobs = self.client.list_blobs(self.bucket_name, prefix=prefix)
            return [b.name for b in blobs]
        else:
            mock_dir = AppConfig.DATA_DIR / "cloud_storage_mock"
            if not mock_dir.exists():
                return []
            return [str(p.relative_to(mock_dir)).replace("\\", "/") for p in mock_dir.glob(f"{prefix}*")]
