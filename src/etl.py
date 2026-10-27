"""
ETL Pipeline for EnergyPulse Cloud.
Handles schema validation, timestamp parsing, missing value interpolation,
data quality auditing, feature engineering, and hourly aggregation.
"""

import logging
from typing import Dict, Any, Tuple
import numpy as np
import pandas as pd

from config.settings import AppConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class EnergyPulseETL:
    """Performs ETL on raw household electrical consumption data."""

    def __init__(self):
        self.numeric_cols = [
            "Global_active_power",
            "Global_reactive_power",
            "Voltage",
            "Global_intensity",
            "Sub_metering_1",
            "Sub_metering_2",
            "Sub_metering_3",
        ]

    def validate_and_clean_raw(self, df_raw: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Validate schema, convert timestamps, remove duplicates, impute missing values,
        and validate physical sensor ranges.
        Returns (cleaned_df, quality_audit).
        """
        audit: Dict[str, Any] = {
            "initial_rows": len(df_raw),
            "duplicates_removed": 0,
            "missing_values_imputed": {},
            "invalid_range_corrections": 0,
            "final_clean_minute_rows": 0,
        }

        # 1. Verify schema
        required = ["Date", "Time"] + self.numeric_cols
        missing = [c for c in required if c not in df_raw.columns]
        if missing:
            raise ValueError(f"Missing required columns for ETL: {missing}")

        df = df_raw.copy()

        # 2. Check and remove exact duplicates
        dup_count = df.duplicated().sum()
        audit["duplicates_removed"] = int(dup_count)
        if dup_count > 0:
            logger.info("Removing %d duplicate raw rows", dup_count)
            df = df.drop_duplicates()

        # 3. Parse Timestamp (UCI format is dd/mm/yyyy hh:mm:ss)
        logger.info("Parsing dates and times into unified ISO timestamps...")
        # Handle string stripping
        df["Date"] = df["Date"].astype(str).str.strip()
        df["Time"] = df["Time"].astype(str).str.strip()

        # Parse timestamp safely
        df["timestamp"] = pd.to_datetime(
            df["Date"] + " " + df["Time"],
            format="%d/%m/%Y %H:%M:%S",
            errors="coerce",
            dayfirst=True,
        )

        invalid_timestamps = df["timestamp"].isna().sum()
        if invalid_timestamps > 0:
            logger.warning("Found %d rows with unparseable timestamps; removing them", invalid_timestamps)
            df = df.dropna(subset=["timestamp"])

        # 4. Sort chronologically
        df = df.sort_values("timestamp").reset_index(drop=True)

        # 5. Clean numeric columns & replace '?' with NaN
        for col in self.numeric_cols:
            # Replace '?' and other non-numeric strings
            if df[col].dtype == object or str(df[col].dtype) == "string":
                df[col] = df[col].replace("?", np.nan).astype(float)
            else:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            missing_count = int(df[col].isna().sum())
            audit["missing_values_imputed"][col] = missing_count

            # Impute missing values via linear interpolation (with forward/backward fill fallbacks)
            if missing_count > 0:
                df[col] = df[col].interpolate(method="linear").bfill().ffill()

        # 6. Physical consistency checks
        # Active power and Voltage must be non-negative.
        invalid_power = (df["Global_active_power"] < 0) | (df["Global_active_power"] > 25.0)
        invalid_voltage = (df["Voltage"] < 150.0) | (df["Voltage"] > 300.0)
        invalid_mask = invalid_power | invalid_voltage
        invalid_count = int(invalid_mask.sum())
        audit["invalid_range_corrections"] = invalid_count
        if invalid_count > 0:
            logger.warning("Corrected %d readings failing physical range checks", invalid_count)
            df.loc[df["Global_active_power"] < 0, "Global_active_power"] = 0.0
            df.loc[df["Global_active_power"] > 25.0, "Global_active_power"] = 25.0
            df.loc[invalid_voltage, "Voltage"] = 230.0  # nominal European residential voltage

        audit["final_clean_minute_rows"] = len(df)
        return df, audit

    def aggregate_to_hourly(self, df_clean: pd.DataFrame) -> pd.DataFrame:
        """
        Aggregate minute-level observations into hourly consumption records.
        Calculates energy in kWh:
          - Active Power (kW) averaged over 1 hour = kWh.
          - Sub-meterings (Wh/min summed over 60 mins) converted to kWh by dividing by 1000.
        """
        if df_clean.empty:
            raise ValueError("Cannot aggregate empty dataframe.")

        df = df_clean.set_index("timestamp").sort_index()

        # Resample to 1-hour intervals
        resampled = df.resample("1h").agg({
            "Global_active_power": "mean",     # Mean kW over the hour
            "Global_reactive_power": "mean",   # Mean reactive kW
            "Voltage": "mean",                 # Mean voltage (V)
            "Global_intensity": "mean",        # Mean current (A)
            "Sub_metering_1": "sum",           # Total Wh in that hour
            "Sub_metering_2": "sum",           # Total Wh in that hour
            "Sub_metering_3": "sum",           # Total Wh in that hour
        })

        # Drop any hours that have completely missing values after resampling
        resampled = resampled.interpolate(method="time").dropna()

        # Feature Engineering & Unit Conversions:
        # 1. Total hourly consumption in kWh (since active power is in kW, 1 hour at X kW = X kWh)
        resampled["energy_consumption_kwh"] = np.round(resampled["Global_active_power"] * 1.0, 4)

        # 2. Convert Sub-meterings from Watt-hour to Kilowatt-hour (kWh)
        resampled["sub_metering_kitchen_kwh"] = np.round(resampled["Sub_metering_1"] / 1000.0, 4)
        resampled["sub_metering_laundry_kwh"] = np.round(resampled["Sub_metering_2"] / 1000.0, 4)
        resampled["sub_metering_climate_kwh"] = np.round(resampled["Sub_metering_3"] / 1000.0, 4)

        # 3. Calculate remaining household energy (un-submetered sockets, lights, etc.)
        sub_sum = (
            resampled["sub_metering_kitchen_kwh"]
            + resampled["sub_metering_laundry_kwh"]
            + resampled["sub_metering_climate_kwh"]
        )
        resampled["sub_metering_other_kwh"] = np.clip(
            np.round(resampled["energy_consumption_kwh"] - sub_sum, 4), 0.0, None
        )

        # 4. Temporal Features
        resampled = resampled.reset_index()
        resampled["hour"] = resampled["timestamp"].dt.hour
        resampled["day_of_week"] = resampled["timestamp"].dt.dayofweek
        resampled["day_name"] = resampled["timestamp"].dt.day_name()
        resampled["month"] = resampled["timestamp"].dt.month
        resampled["year"] = resampled["timestamp"].dt.year
        resampled["is_weekend"] = resampled["day_of_week"].isin([5, 6]).astype(int)
        # Peak demand hours: 18:00 to 22:00
        resampled["is_peak_period"] = resampled["hour"].between(18, 22).astype(int)

        # 5. Lag Features for time-series modeling (1-hour lag, 24-hour lag, 168-hour / 7-day lag)
        resampled["lag_1h"] = resampled["energy_consumption_kwh"].shift(1)
        resampled["lag_24h"] = resampled["energy_consumption_kwh"].shift(24)
        resampled["lag_168h"] = resampled["energy_consumption_kwh"].shift(168)
        resampled["rolling_mean_24h"] = (
            resampled["energy_consumption_kwh"].rolling(window=24, min_periods=1).mean()
        )

        # Fill earliest lag values to avoid initial NaN drops
        resampled["lag_1h"] = resampled["lag_1h"].bfill().ffill().fillna(0.0)
        resampled["lag_24h"] = resampled["lag_24h"].bfill().ffill().fillna(resampled["lag_1h"])
        resampled["lag_168h"] = resampled["lag_168h"].bfill().ffill().fillna(resampled["lag_24h"]).fillna(resampled["lag_1h"])

        logger.info("Aggregated to %d hourly records with engineered features.", len(resampled))
        return resampled

    def run_pipeline(self, df_raw: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Execute full ETL pipeline:
        Raw -> Validation & Imputation -> Hourly Aggregation & Feature Engineering.
        """
        clean_minute_df, audit = self.validate_and_clean_raw(df_raw)
        hourly_df = self.aggregate_to_hourly(clean_minute_df)
        audit["hourly_rows_generated"] = len(hourly_df)
        audit["date_range_start"] = str(hourly_df["timestamp"].min())
        audit["date_range_end"] = str(hourly_df["timestamp"].max())
        return hourly_df, audit
