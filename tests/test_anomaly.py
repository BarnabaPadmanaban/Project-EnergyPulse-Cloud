"""
Unit tests for anomaly detection: statistical rolling threshold and Isolation Forest.
Tests on normal data and artificially injected spikes/drops.
"""

import pytest
import pandas as pd
import numpy as np
from src.anomaly_detection import EnergyAnomalyDetector


@pytest.fixture
def synthetic_hourly_stream():
    """Create a 100-hour baseline series with artificial anomalies injected."""
    timestamps = pd.date_range("2007-01-01", periods=100, freq="1h")
    # Baseline steady consumption ~ 1.0 kWh
    values = np.random.normal(1.0, 0.1, 100)
    voltage = np.random.normal(234.0, 2.0, 100)

    # Inject extreme surge at index 50 (8.5 kWh - appliance overload)
    values[50] = 8.5

    # Inject drop / outage at index 75 (0.0 kWh)
    values[75] = 0.0

    df = pd.DataFrame({
        "timestamp": timestamps,
        "energy_consumption_kwh": values,
        "hour": timestamps.hour,
        "Voltage": voltage,
        "Global_reactive_power": 0.1,
        "Global_intensity": 4.5,
    })
    return df


def test_anomaly_detection_identifies_injected_spikes(synthetic_hourly_stream):
    """Verify detector flags artificially injected surge at index 50."""
    detector = EnergyAnomalyDetector(rolling_window_hours=24, std_multiplier=3.0)
    df_results, summary = detector.analyze_anomalies(synthetic_hourly_stream)

    assert "total_anomalies_detected" in summary
    assert summary["total_anomalies_detected"] >= 1

    # Row 50 must be detected as an anomaly
    assert df_results.loc[50, "is_anomaly"] == True
    assert "Surge" in df_results.loc[50, "anomaly_category"] or "Statistical" in df_results.loc[50, "anomaly_category"]


def test_anomaly_explanation_and_formula():
    """Verify anomaly summary provides explicit formula and engineering distinction note."""
    detector = EnergyAnomalyDetector()
    timestamps = pd.date_range("2007-01-01", periods=30, freq="1h")
    df = pd.DataFrame({
        "timestamp": timestamps,
        "energy_consumption_kwh": [1.0] * 30,
        "hour": timestamps.hour,
        "Voltage": [230.0] * 30,
    })
    _, summary = detector.analyze_anomalies(df)
    assert "RollingMedian" in summary["threshold_formula"]
    assert "Important Engineering Distinction" in summary["cautionary_note"]
