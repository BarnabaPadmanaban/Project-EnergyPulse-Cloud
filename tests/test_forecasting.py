"""
Unit tests for forecasting: chronological train/test split, metrics calculation, and no future leakage.
"""

import pytest
import pandas as pd
import numpy as np
from src.forecasting import EnergyForecaster


@pytest.fixture
def sample_hourly_df():
    """Create a 168-hour (7 days) synthetic hourly dataset."""
    timestamps = pd.date_range("2007-01-01", periods=200, freq="1h")
    hours = timestamps.hour
    values = 1.0 + 0.8 * np.sin(2 * np.pi * hours / 24) + np.random.normal(0, 0.05, 200)
    values = np.clip(values, 0.1, 5.0)

    df = pd.DataFrame({
        "timestamp": timestamps,
        "energy_consumption_kwh": values,
        "hour": hours,
        "day_of_week": timestamps.dayofweek,
        "is_weekend": timestamps.dayofweek.isin([5, 6]).astype(int),
        "is_peak_period": hours.isin([18, 19, 20, 21]).astype(int),
        "lag_1h": pd.Series(values).shift(1).bfill(),
        "lag_24h": pd.Series(values).shift(24).bfill(),
        "lag_168h": pd.Series(values).shift(168).bfill(),
        "rolling_mean_24h": pd.Series(values).rolling(24, min_periods=1).mean(),
    })
    return df


def test_chronological_split_no_overlap(sample_hourly_df):
    """Ensure train and test splits are strictly chronological without overlap."""
    train_df, test_df = EnergyForecaster.chronological_split(sample_hourly_df, test_ratio=0.2)

    assert len(train_df) == 160
    assert len(test_df) == 40
    # Every train timestamp must precede every test timestamp
    assert train_df["timestamp"].max() < test_df["timestamp"].min()


def test_forecast_training_and_metrics(sample_hourly_df):
    """Ensure training completes, computes positive MAE/RMSE, and compares with baseline."""
    forecaster = EnergyForecaster(model_type="ridge")
    summary, comparison_df = forecaster.train_and_evaluate(sample_hourly_df, test_ratio=0.2)

    assert "model_metrics" in summary
    assert "baseline_metrics" in summary
    assert summary["model_metrics"]["MAE"] > 0
    assert summary["model_metrics"]["RMSE"] > 0
    assert len(comparison_df) == 40
    assert "actual_kwh" in comparison_df.columns
    assert "predicted_kwh" in comparison_df.columns


def test_forecast_horizon_generation(sample_hourly_df):
    """Test recursive generation of future predictions for 24-hour horizon."""
    forecaster = EnergyForecaster(model_type="ridge")
    forecaster.train_and_evaluate(sample_hourly_df, test_ratio=0.2)

    future_df = forecaster.forecast_future(sample_hourly_df, horizon_hours=24)
    assert len(future_df) == 24
    assert future_df["timestamp"].iloc[0] == sample_hourly_df["timestamp"].iloc[-1] + pd.Timedelta(hours=1)
    assert (future_df["predicted_kwh"] >= 0).all()
