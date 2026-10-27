"""
Unit tests for dashboard helper routines, KPI calculations, and data formatting.
"""

import pandas as pd
import numpy as np


def compute_dashboard_kpis(df: pd.DataFrame):
    """Utility function replicating dashboard KPI card computation."""
    total_kwh = float(df["energy_consumption_kwh"].sum())
    # Daily aggregation
    daily_grouped = df.groupby(df["timestamp"].dt.date)["energy_consumption_kwh"].sum()
    avg_daily_kwh = float(daily_grouped.mean())
    peak_idx = df["energy_consumption_kwh"].idxmax()
    peak_kwh = float(df.loc[peak_idx, "energy_consumption_kwh"])
    peak_timestamp = str(df.loc[peak_idx, "timestamp"])

    return {
        "total_kwh": round(total_kwh, 2),
        "avg_daily_kwh": round(avg_daily_kwh, 2),
        "peak_kwh": round(peak_kwh, 3),
        "peak_timestamp": peak_timestamp,
    }


def test_dashboard_kpi_computation():
    """Verify calculation of Total, Average Daily, and Peak metrics."""
    timestamps = pd.date_range("2007-01-01 00:00:00", periods=48, freq="1h")
    values = [1.0] * 48
    values[15] = 4.8  # Peak hour on day 1

    df = pd.DataFrame({
        "timestamp": timestamps,
        "energy_consumption_kwh": values,
    })

    kpis = compute_dashboard_kpis(df)
    # Total is 47 * 1.0 + 4.8 = 51.8 kWh
    assert kpis["total_kwh"] == 51.8
    # 2 full days, avg daily = 51.8 / 2 = 25.9 kWh
    assert kpis["avg_daily_kwh"] == 25.9
    assert kpis["peak_kwh"] == 4.8
    assert "15:00:00" in kpis["peak_timestamp"]
