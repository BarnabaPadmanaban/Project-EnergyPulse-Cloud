"""
Generate a realistic synthetic sample file matching the exact schema and delimiters
of the UCI Individual Household Electric Power Consumption dataset.
Used strictly for unit testing and offline Demo Mode exploration.
"""

from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from pathlib import Path

def generate_sample_csv(output_path: Path, num_minutes: int = 1440 * 7):
    """
    Generate synthetic 1-minute resolution household power records for 7 days (10,080 rows).
    Saves with semicolon (;) delimiter matching UCI raw format.
    """
    np.random.seed(42)
    start_time = datetime(2007, 1, 1, 0, 0, 0)
    timestamps = [start_time + timedelta(minutes=i) for i in range(num_minutes)]
    
    dates = [t.strftime("%d/%m/%Y") for t in timestamps]
    times = [t.strftime("%H:%M:%S") for t in timestamps]
    
    # Base daily pattern: higher morning (7-9) and evening (18-22)
    hours = np.array([t.hour + t.minute / 60.0 for t in timestamps])
    daily_pattern = 0.5 + 1.2 * np.exp(-((hours - 8) ** 2) / 4) + 2.0 * np.exp(-((hours - 20) ** 2) / 6)
    noise = np.random.normal(0, 0.15, num_minutes)
    active_power = np.clip(daily_pattern + noise, 0.1, 8.0)
    
    # Reactive power, Voltage, Current intensity
    reactive_power = np.clip(0.1 * active_power + np.random.normal(0.05, 0.02, num_minutes), 0.0, 1.2)
    voltage = np.clip(235.0 + np.random.normal(0, 3.0, num_minutes), 220.0, 250.0)
    intensity = np.round((active_power * 1000) / voltage, 1)
    
    # Sub-meterings (Wh per minute): kitchen, laundry, climate
    sub1 = np.where((hours >= 19) & (hours <= 21), np.random.choice([0, 15, 25], num_minutes), 0)
    sub2 = np.where((hours >= 9) & (hours <= 11) & (np.array([t.weekday() for t in timestamps]) >= 5), 18, 0)
    sub3 = np.clip(np.round(active_power * 5.0 + np.random.normal(0, 2, num_minutes)), 0, 30)

    # Convert to string and inject missing '?' markers (~1% of rows) to test ETL resilience
    active_power_str = [f"{val:.3f}" for val in active_power]
    reactive_power_str = [f"{val:.3f}" for val in reactive_power]
    voltage_str = [f"{val:.2f}" for val in voltage]
    intensity_str = [f"{val:.1f}" for val in intensity]
    sub1_str = [f"{val:.1f}" for val in sub1]
    sub2_str = [f"{val:.1f}" for val in sub2]
    sub3_str = [f"{val:.1f}" for val in sub3]

    # Inject 50 missing values
    missing_indices = np.random.choice(num_minutes, size=50, replace=False)
    for idx in missing_indices:
        active_power_str[idx] = "?"
        reactive_power_str[idx] = "?"
        voltage_str[idx] = "?"
        intensity_str[idx] = "?"
        sub1_str[idx] = "?"
        sub2_str[idx] = "?"
        sub3_str[idx] = "?"

    df = pd.DataFrame({
        "Date": dates,
        "Time": times,
        "Global_active_power": active_power_str,
        "Global_reactive_power": reactive_power_str,
        "Voltage": voltage_str,
        "Global_intensity": intensity_str,
        "Sub_metering_1": sub1_str,
        "Sub_metering_2": sub2_str,
        "Sub_metering_3": sub3_str,
    })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, sep=";", index=False)
    print(f"Generated {len(df)} sample rows to {output_path}")

if __name__ == "__main__":
    out_file = Path(__file__).resolve().parent.parent / "data" / "sample_household_power.csv"
    generate_sample_csv(out_file)
