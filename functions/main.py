"""
Cloud Run Function for EnergyPulse Cloud.
Serverless data processing trigger.
Listens to Cloud Storage bucket object finalize events (or HTTP POST webhook trigger),
executes the ETL pipeline, and streams/loads processed hourly records into BigQuery.
"""

import os
import json
import logging
from io import StringIO
import functions_framework
import pandas as pd
from google.cloud import storage, bigquery

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "energypulse-cloud-dev")
DATASET_ID = os.environ.get("BQ_DATASET_ID", "energypulse_analytics")
TABLE_ID = os.environ.get("BQ_TABLE_ID", "household_hourly_consumption")


def process_and_load(raw_csv_content: str, source_name: str):
    """Clean and aggregate raw content, then load into BigQuery."""
    logger.info("Starting ETL processing for %s", source_name)
    
    # Auto-detect delimiter
    delimiter = ";" if ";" in raw_csv_content[:500] else ","
    df_raw = pd.read_csv(StringIO(raw_csv_content), sep=delimiter, low_memory=False, dtype=str)

    # 1. Clean timestamps and deduplicate
    df = df_raw.drop_duplicates()
    df["Date"] = df["Date"].astype(str).str.strip()
    df["Time"] = df["Time"].astype(str).str.strip()
    df["timestamp"] = pd.to_datetime(
        df["Date"] + " " + df["Time"],
        format="%d/%m/%Y %H:%M:%S",
        errors="coerce",
        dayfirst=True
    )
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    # Numeric conversion
    numeric_cols = [
        "Global_active_power", "Global_reactive_power", "Voltage",
        "Global_intensity", "Sub_metering_1", "Sub_metering_2", "Sub_metering_3"
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].replace("?", None), errors="coerce")
            df[col] = df[col].interpolate(method="linear").bfill().ffill()

    # Hourly Resampling
    df_hourly = df.set_index("timestamp").resample("1h").agg({
        "Global_active_power": "mean",
        "Global_reactive_power": "mean",
        "Voltage": "mean",
        "Global_intensity": "mean",
        "Sub_metering_1": "sum",
        "Sub_metering_2": "sum",
        "Sub_metering_3": "sum",
    }).interpolate(method="time").dropna().reset_index()

    # Feature Engineering
    df_hourly["energy_consumption_kwh"] = df_hourly["Global_active_power"].round(4)
    df_hourly["sub_metering_kitchen_kwh"] = (df_hourly["Sub_metering_1"] / 1000.0).round(4)
    df_hourly["sub_metering_laundry_kwh"] = (df_hourly["Sub_metering_2"] / 1000.0).round(4)
    df_hourly["sub_metering_climate_kwh"] = (df_hourly["Sub_metering_3"] / 1000.0).round(4)
    
    sub_total = df_hourly["sub_metering_kitchen_kwh"] + df_hourly["sub_metering_laundry_kwh"] + df_hourly["sub_metering_climate_kwh"]
    df_hourly["sub_metering_other_kwh"] = (df_hourly["energy_consumption_kwh"] - sub_total).clip(lower=0.0).round(4)

    df_hourly["hour"] = df_hourly["timestamp"].dt.hour
    df_hourly["day_of_week"] = df_hourly["timestamp"].dt.dayofweek
    df_hourly["day_name"] = df_hourly["timestamp"].dt.day_name()
    df_hourly["month"] = df_hourly["timestamp"].dt.month
    df_hourly["year"] = df_hourly["timestamp"].dt.year
    df_hourly["is_weekend"] = df_hourly["day_of_week"].isin([5, 6]).astype(int)
    df_hourly["is_peak_period"] = df_hourly["hour"].between(18, 22).astype(int)

    df_hourly["lag_1h"] = df_hourly["energy_consumption_kwh"].shift(1).bfill()
    df_hourly["lag_24h"] = df_hourly["energy_consumption_kwh"].shift(24).bfill()
    df_hourly["lag_168h"] = df_hourly["energy_consumption_kwh"].shift(168).bfill()
    df_hourly["rolling_mean_24h"] = df_hourly["energy_consumption_kwh"].rolling(24, min_periods=1).mean()

    # Load into BigQuery
    bq_client = bigquery.Client(project=PROJECT_ID)
    table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        time_partitioning=bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="timestamp"
        ),
        clustering_fields=["is_peak_period", "hour"],
    )
    load_job = bq_client.load_table_from_dataframe(df_hourly, table_ref, job_config=job_config)
    load_job.result()
    logger.info("Loaded %d hourly records into %s", len(df_hourly), table_ref)
    return len(df_hourly)


@functions_framework.cloud_event
def gcs_trigger_pipeline(cloud_event):
    """
    Background Cloud Function triggered by Google Cloud Storage 'object.finalize' event.
    """
    data = cloud_event.data
    bucket_name = data.get("bucket")
    file_name = data.get("name")

    logger.info("Received GCS event for bucket=%s file=%s", bucket_name, file_name)
    if not file_name.endswith((".csv", ".txt")):
        logger.info("Ignoring non-data file: %s", file_name)
        return

    storage_client = storage.Client(project=PROJECT_ID)
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(file_name)
    raw_content = blob.download_as_text()

    rows = process_and_load(raw_content, source_name=file_name)
    logger.info("Completed processing for %s: %d hourly rows inserted.", file_name, rows)


@functions_framework.http
def http_trigger_pipeline(request):
    """
    HTTP endpoint to trigger ETL manually or via automated webhook/cron.
    Accepts JSON body: {"bucket": "bucket_name", "file_name": "path/file.csv"}
    """
    try:
        request_json = request.get_json(silent=True) or {}
        bucket_name = request_json.get("bucket", os.environ.get("GCS_BUCKET_NAME"))
        file_name = request_json.get("file_name", "sample_household_power.csv")

        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(file_name)
        raw_content = blob.download_as_text()

        rows = process_and_load(raw_content, source_name=file_name)
        return json.dumps({
            "status": "success",
            "message": f"Processed {file_name} from {bucket_name}",
            "hourly_records_loaded": rows,
        }), 200, {"Content-Type": "application/json"}
    except Exception as e:
        logger.exception("Error processing HTTP pipeline request: %s", e)
        return json.dumps({"status": "error", "message": str(e)}), 500, {"Content-Type": "application/json"}
