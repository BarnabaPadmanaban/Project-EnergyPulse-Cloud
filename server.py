"""
EnergyPulse Cloud - REST API Server for React Web Application.
Provides high-performance analytical endpoints for real-time energy telemetry,
chronological machine learning forecasting, and dual-layer anomaly detection.
"""

import os
import json
import logging
from pathlib import Path
from flask import Flask, request, jsonify, make_response
import pandas as pd
import numpy as np

from config.settings import AppConfig
from src.ingestion import DatasetIngestion
from src.etl import EnergyPulseETL
from src.forecasting import EnergyForecaster
from src.anomaly_detection import EnergyAnomalyDetector
from src.storage_client import CloudStorageClient
from src.bigquery_client import BigQueryWarehouseClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("energypulse_api")

app = Flask(__name__)

# Global state / cache
STATE = {
    "raw_df": None,
    "hourly_df": None,
    "audit_info": None,
    "source_label": "Benchmark Sample",
}

def init_data():
    """Load and process baseline dataset on startup."""
    ingestor = DatasetIngestion()
    if not AppConfig.SAMPLE_DATA_PATH.exists():
        from src.generate_sample import generate_sample_csv
        generate_sample_csv(AppConfig.SAMPLE_DATA_PATH)

    raw_df, label = ingestor.load_raw_dataframe(use_sample_if_missing=True)
    etl = EnergyPulseETL()
    hourly_df, audit = etl.run_pipeline(raw_df)

    STATE["raw_df"] = raw_df
    STATE["hourly_df"] = hourly_df
    STATE["audit_info"] = audit
    STATE["source_label"] = label
    logger.info("Initialized backend data: %d hourly rows from %s", len(hourly_df), label)

# CORS Middleware
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response

@app.route("/api/status", methods=["GET", "OPTIONS"])
def get_status():
    if request.method == "OPTIONS":
        return "", 200
    return jsonify({
        "status": "online",
        "demo_mode": AppConfig.DEMO_MODE,
        "gcp_project_id": AppConfig.GCP_PROJECT_ID,
        "gcp_region": AppConfig.GCP_REGION,
        "bq_dataset_id": AppConfig.BQ_DATASET_ID,
        "bq_table_id": AppConfig.BQ_TABLE_ID,
        "source_label": STATE["source_label"],
        "total_hourly_records": len(STATE["hourly_df"]) if STATE["hourly_df"] is not None else 0,
    })

@app.route("/api/analytics", methods=["GET", "OPTIONS"])
def get_analytics():
    if request.method == "OPTIONS":
        return "", 200

    df = STATE["hourly_df"]
    if df is None:
        init_data()
        df = STATE["hourly_df"]

    # Optional date filters
    start = request.args.get("start")
    end = request.args.get("end")
    if start and end:
        try:
            start_dt = pd.to_datetime(start)
            end_dt = pd.to_datetime(end)
            df = df[(df["timestamp"] >= start_dt) & (df["timestamp"] <= end_dt)]
        except Exception as e:
            logger.warning("Invalid date filter: %s", e)

    # Calculate KPIs
    total_kwh = float(df["energy_consumption_kwh"].sum())
    daily_grouped = df.groupby(df["timestamp"].dt.date)["energy_consumption_kwh"].sum()
    avg_daily_kwh = float(daily_grouped.mean()) if not daily_grouped.empty else 0.0
    peak_idx = df["energy_consumption_kwh"].idxmax()
    peak_kwh = float(df.loc[peak_idx, "energy_consumption_kwh"])
    peak_timestamp = str(df.loc[peak_idx, "timestamp"])
    avg_voltage = float(df["Voltage"].mean())

    # Format timeseries for chart
    timeseries = []
    for _, r in df.iterrows():
        timeseries.append({
            "timestamp": str(r["timestamp"]),
            "energy_kwh": round(float(r["energy_consumption_kwh"]), 3),
            "rolling_mean": round(float(r["rolling_mean_24h"]), 3),
            "voltage": round(float(r["Voltage"]), 1),
            "is_peak": int(r["is_peak_period"]),
            "hour": int(r["hour"]),
        })

    # Diurnal Profile (average by hour)
    diurnal = []
    hourly_grp = df.groupby("hour")["energy_consumption_kwh"].agg(["mean", "min", "max"]).reset_index()
    for _, r in hourly_grp.iterrows():
        h = int(r["hour"])
        diurnal.append({
            "hour": f"{h:02d}:00",
            "hour_num": h,
            "avg_kwh": round(float(r["mean"]), 3),
            "min_kwh": round(float(r["min"]), 3),
            "max_kwh": round(float(r["max"]), 3),
            "is_peak": 1 if 18 <= h <= 22 else 0,
        })

    # Submetering totals
    submetering = {
        "kitchen_kwh": round(float(df["sub_metering_kitchen_kwh"].sum()), 2),
        "laundry_kwh": round(float(df["sub_metering_laundry_kwh"].sum()), 2),
        "climate_kwh": round(float(df["sub_metering_climate_kwh"].sum()), 2),
        "other_kwh": round(float(df["sub_metering_other_kwh"].sum()), 2),
    }

    return jsonify({
        "kpis": {
            "total_consumption_kwh": round(total_kwh, 1),
            "avg_daily_kwh": round(avg_daily_kwh, 2),
            "peak_demand_kwh": round(peak_kwh, 2),
            "peak_timestamp": peak_timestamp,
            "avg_voltage": round(avg_voltage, 1),
            "record_count": len(df),
            "date_start": str(df["timestamp"].min()),
            "date_end": str(df["timestamp"].max()),
        },
        "timeseries": timeseries,
        "diurnal": diurnal,
        "submetering": submetering,
        "audit": STATE["audit_info"],
    })

@app.route("/api/forecast", methods=["POST", "OPTIONS"])
def get_forecast():
    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json(silent=True) or {}
    model_type = data.get("model_type", "ridge").lower()
    horizon = int(data.get("horizon_hours", 24))

    df = STATE["hourly_df"]
    if df is None:
        init_data()
        df = STATE["hourly_df"]

    forecaster = EnergyForecaster(model_type=model_type)
    summary, comp_df = forecaster.train_and_evaluate(df, test_ratio=0.2)
    future_df = forecaster.forecast_future(df, horizon_hours=horizon)

    # Convert test comparison to list
    eval_list = []
    for _, r in comp_df.iterrows():
        eval_list.append({
            "timestamp": str(r["timestamp"]),
            "actual_kwh": round(float(r["actual_kwh"]), 3),
            "predicted_kwh": round(float(r["predicted_kwh"]), 3),
            "baseline_kwh": round(float(r["baseline_kwh"]), 3),
            "error_kwh": round(float(r["absolute_error_kwh"]), 3),
        })

    # Future forecast list
    future_list = []
    for _, r in future_df.iterrows():
        future_list.append({
            "timestamp": str(r["timestamp"]),
            "predicted_kwh": round(float(r["predicted_kwh"]), 3),
            "hour": int(r["hour"]),
            "day_name": str(r["day_name"]),
            "is_peak": int(r["is_peak_period"]),
        })

    return jsonify({
        "summary": summary,
        "eval_comparison": eval_list,
        "future_forecast": future_list,
    })

@app.route("/api/anomalies", methods=["POST", "OPTIONS"])
def get_anomalies():
    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json(silent=True) or {}
    k_std = float(data.get("std_multiplier", 3.0))
    window = int(data.get("rolling_window_hours", 24))

    df = STATE["hourly_df"]
    if df is None:
        init_data()
        df = STATE["hourly_df"]

    detector = EnergyAnomalyDetector(rolling_window_hours=window, std_multiplier=k_std)
    full_df, summary = detector.analyze_anomalies(df)

    anomalies_only = full_df[full_df["is_anomaly"]]
    anom_list = []
    for _, r in anomalies_only.iterrows():
        anom_list.append({
            "timestamp": str(r["timestamp"]),
            "consumption_kwh": round(float(r["energy_consumption_kwh"]), 3),
            "upper_threshold": round(float(r["rolling_upper_threshold"]), 3),
            "voltage": round(float(r.get("Voltage", 230.0)), 1),
            "deviation_score": round(float(r["deviation_score"]), 2),
            "category": str(r["anomaly_category"]),
        })

    # Curve with thresholds
    threshold_curve = []
    for _, r in full_df.iterrows():
        threshold_curve.append({
            "timestamp": str(r["timestamp"]),
            "consumption_kwh": round(float(r["energy_consumption_kwh"]), 3),
            "upper_threshold": round(float(r["rolling_upper_threshold"]), 3),
            "is_anomaly": bool(r["is_anomaly"]),
            "category": str(r["anomaly_category"]) if r["is_anomaly"] else "Normal",
        })

    return jsonify({
        "summary": summary,
        "anomalies": anom_list,
        "curve": threshold_curve,
    })

@app.route("/api/sync-bigquery", methods=["POST", "OPTIONS"])
def sync_bigquery():
    if request.method == "OPTIONS":
        return "", 200

    df = STATE["hourly_df"]
    if df is None:
        init_data()
        df = STATE["hourly_df"]

    bq = BigQueryWarehouseClient()
    bq.init_warehouse_schema()
    loaded = bq.load_hourly_dataframe(df)

    return jsonify({
        "success": True,
        "records_synced": loaded,
        "target": f"{bq.project_id}.{bq.dataset_id}.{bq.table_id}",
        "mode": "GCP Cloud BigQuery" if not bq.demo_mode else "Local SQLite Warehouse Simulator",
    })

if __name__ == "__main__":
    init_data()
    port = int(os.environ.get("API_PORT", 5000))
    print(f"EnergyPulse REST API serving on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
