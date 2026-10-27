"""
Unit tests for ETL pipeline: timestamp parsing, missing values, duplicates, and hourly aggregation.
"""

import pytest
import pandas as pd
import numpy as np
from src.etl import EnergyPulseETL


@pytest.fixture
def sample_raw_df():
    """Create a 120-minute synthetic dataframe (2 full hours) with duplicates and missing values."""
    dates = ["01/01/2007"] * 120
    times = [f"{m // 60:02d}:{m % 60:02d}:00" for m in range(120)]
    df = pd.DataFrame({
        "Date": dates,
        "Time": times,
        "Global_active_power": ["1.5"] * 120,
        "Global_reactive_power": ["0.1"] * 120,
        "Voltage": ["234.5"] * 120,
        "Global_intensity": ["6.4"] * 120,
        "Sub_metering_1": ["0.0"] * 120,
        "Sub_metering_2": ["0.0"] * 120,
        "Sub_metering_3": ["10.0"] * 120,
    })
    # Inject a duplicate row
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    # Inject a missing value encoded as '?'
    df.loc[10, "Global_active_power"] = "?"
    return df


def test_etl_cleans_duplicates_and_missing(sample_raw_df):
    """Verify duplicates are dropped and '?' missing values are imputed."""
    etl = EnergyPulseETL()
    clean_df, audit = etl.validate_and_clean_raw(sample_raw_df)

    assert audit["duplicates_removed"] == 1
    assert audit["missing_values_imputed"]["Global_active_power"] == 1
    assert not clean_df["Global_active_power"].isna().any()
    assert len(clean_df) == 120


def test_hourly_aggregation_and_unit_conversion(sample_raw_df):
    """Verify aggregation from 1-minute measurements to hourly records with accurate kWh conversions."""
    etl = EnergyPulseETL()
    hourly_df, audit = etl.run_pipeline(sample_raw_df)

    # 120 minutes = exactly 2 hours
    assert len(hourly_df) == 2
    assert "energy_consumption_kwh" in hourly_df.columns
    assert "sub_metering_climate_kwh" in hourly_df.columns

    # Active power is 1.5 kW average -> hourly energy must equal 1.5 kWh
    first_hour_kwh = hourly_df.iloc[0]["energy_consumption_kwh"]
    assert pytest.approx(first_hour_kwh, rel=1e-2) == 1.5

    # Sub_metering_3 was 10 Wh/min * 60 min = 600 Wh = 0.6 kWh
    first_hour_climate = hourly_df.iloc[0]["sub_metering_climate_kwh"]
    assert pytest.approx(first_hour_climate, rel=1e-2) == 0.6
