"""
BigQuery Client for EnergyPulse Cloud.
Handles cloud data warehouse dataset creation, table ingestion, and analytical SQL querying.
Includes an in-memory / SQLite local fallback to ensure seamless zero-cost demo execution.
"""

import os
import sqlite3
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
import pandas as pd

from config.settings import AppConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class BigQueryWarehouseClient:
    """Manages cloud analytics and querying via BigQuery with local database simulation fallback."""

    def __init__(
        self,
        project_id: Optional[str] = None,
        dataset_id: Optional[str] = None,
        table_id: Optional[str] = None,
        demo_mode: Optional[bool] = None,
    ):
        self.project_id = project_id or AppConfig.GCP_PROJECT_ID
        self.dataset_id = dataset_id or AppConfig.BQ_DATASET_ID
        self.table_id = table_id or AppConfig.BQ_TABLE_ID
        self.demo_mode = AppConfig.DEMO_MODE if demo_mode is None else demo_mode
        self.full_table_ref = f"{self.project_id}.{self.dataset_id}.{self.table_id}"
        self.client = None

        # Local simulation database path
        self.local_db_path = AppConfig.DATA_DIR / "local_warehouse.db"

        if not self.demo_mode:
            try:
                from google.cloud import bigquery
                self.client = bigquery.Client(project=self.project_id)
                logger.info("Initialized Google BigQuery client for project: %s", self.project_id)
            except Exception as e:
                logger.warning(
                    "BigQuery client could not be initialized (%s). Operating in Local Warehouse Demo Mode.", e
                )
                self.demo_mode = True
        else:
            logger.info("Operating BigQueryWarehouseClient in Local Demo Mode.")

    def init_warehouse_schema(self, ddl_script_path: Optional[Path] = None) -> bool:
        """
        Initialize dataset and tables in BigQuery (or local SQLite simulator).
        """
        if not self.demo_mode and self.client:
            from google.cloud import bigquery
            dataset_ref = bigquery.DatasetReference(self.project_id, self.dataset_id)
            try:
                self.client.get_dataset(dataset_ref)
                logger.info("BigQuery dataset %s already exists.", self.dataset_id)
            except Exception:
                dataset = bigquery.Dataset(dataset_ref)
                dataset.location = AppConfig.GCP_REGION
                self.client.create_dataset(dataset, exists_ok=True)
                logger.info("Created BigQuery dataset: %s", self.dataset_id)

            if ddl_script_path and ddl_script_path.exists():
                ddl = ddl_script_path.read_text(encoding="utf-8")
                # Format with target project and dataset
                formatted_ddl = ddl.replace("energypulse-cloud-dev", self.project_id)
                formatted_ddl = formatted_ddl.replace("energypulse_analytics", self.dataset_id)
                formatted_ddl = formatted_ddl.replace("household_hourly_consumption", self.table_id)
                query_job = self.client.query(formatted_ddl)
                query_job.result()
                logger.info("Executed BigQuery table DDL from %s", ddl_script_path.name)
            return True
        else:
            # Local SQLite schema setup
            with sqlite3.connect(self.local_db_path) as conn:
                conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table_id} (
                    timestamp TEXT PRIMARY KEY,
                    Global_active_power REAL,
                    Global_reactive_power REAL,
                    Voltage REAL,
                    Global_intensity REAL,
                    Sub_metering_1 REAL,
                    Sub_metering_2 REAL,
                    Sub_metering_3 REAL,
                    energy_consumption_kwh REAL,
                    sub_metering_kitchen_kwh REAL,
                    sub_metering_laundry_kwh REAL,
                    sub_metering_climate_kwh REAL,
                    sub_metering_other_kwh REAL,
                    hour INTEGER,
                    day_of_week INTEGER,
                    day_name TEXT,
                    month INTEGER,
                    year INTEGER,
                    is_weekend INTEGER,
                    is_peak_period INTEGER,
                    lag_1h REAL,
                    lag_24h REAL,
                    lag_168h REAL,
                    rolling_mean_24h REAL
                )
                """)
            logger.info("[DEMO MODE] Initialized local SQLite warehouse table: %s", self.table_id)
            return True

    def load_hourly_dataframe(self, df: pd.DataFrame, write_disposition: str = "WRITE_TRUNCATE") -> int:
        """
        Load processed hourly records into BigQuery (or local SQLite warehouse).
        """
        if df.empty:
            logger.warning("Empty dataframe provided to load_hourly_dataframe.")
            return 0

        df_to_load = df.copy()
        if "timestamp" in df_to_load.columns:
            df_to_load["timestamp"] = df_to_load["timestamp"].astype(str)

        if not self.demo_mode and self.client:
            from google.cloud import bigquery
            table_ref = f"{self.project_id}.{self.dataset_id}.{self.table_id}"
            job_config = bigquery.LoadJobConfig(
                write_disposition=getattr(bigquery.WriteDisposition, write_disposition, bigquery.WriteDisposition.WRITE_TRUNCATE),
                time_partitioning=bigquery.TimePartitioning(
                    type_=bigquery.TimePartitioningType.DAY,
                    field="timestamp"
                ),
                clustering_fields=["is_peak_period", "hour"],
            )
            load_job = self.client.load_table_from_dataframe(df_to_load, table_ref, job_config=job_config)
            load_job.result()  # Wait for load to finish
            logger.info("Successfully loaded %d records into BigQuery table: %s", len(df_to_load), table_ref)
            return len(df_to_load)
        else:
            # Load into local SQLite
            with sqlite3.connect(self.local_db_path) as conn:
                if write_disposition == "WRITE_TRUNCATE":
                    conn.execute(f"DELETE FROM {self.table_id}")
                df_to_load.to_sql(self.table_id, conn, if_exists="append", index=False)
            logger.info("[DEMO MODE] Loaded %d records into local SQLite warehouse table: %s", len(df_to_load), self.table_id)
            return len(df_to_load)

    def execute_query(self, sql_query: str) -> pd.DataFrame:
        """Execute analytical query against BigQuery (or local SQLite)."""
        if not self.demo_mode and self.client:
            query_job = self.client.query(sql_query)
            return query_job.to_dataframe()
        else:
            # Adapt BigQuery standard SQL dialect differences for SQLite if needed
            adapted_sql = sql_query.replace(self.full_table_ref, self.table_id)
            adapted_sql = adapted_sql.replace(f"`{self.dataset_id}.{self.table_id}`", self.table_id)
            adapted_sql = adapted_sql.replace(f"{self.dataset_id}.{self.table_id}", self.table_id)
            with sqlite3.connect(self.local_db_path) as conn:
                return pd.read_sql_query(adapted_sql, conn)
