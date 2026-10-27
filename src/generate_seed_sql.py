import pandas as pd
from pathlib import Path

def generate_seed_sql():
    df = pd.read_csv("data/processed/energypulse_hourly_consumption.csv")
    lines = []
    lines.append("INSERT INTO `gen-lang-client-0409693030.energypulse_analytics.household_hourly_consumption` (")
    lines.append("  timestamp, Global_active_power, Global_reactive_power, Voltage, Global_intensity,")
    lines.append("  Sub_metering_1, Sub_metering_2, Sub_metering_3, energy_consumption_kwh,")
    lines.append("  sub_metering_kitchen_kwh, sub_metering_laundry_kwh, sub_metering_climate_kwh, sub_metering_other_kwh,")
    lines.append("  hour, day_of_week, day_name, month, year, is_weekend, is_peak_period,")
    lines.append("  lag_1h, lag_24h, lag_168h, rolling_mean_24h")
    lines.append(") VALUES")

    value_tuples = []
    for _, r in df.iterrows():
        val = (
            f"(TIMESTAMP('{r['timestamp']}'), {r['Global_active_power']:.4f}, {r['Global_reactive_power']:.4f}, "
            f"{r['Voltage']:.2f}, {r['Global_intensity']:.2f}, {r['Sub_metering_1']:.2f}, {r['Sub_metering_2']:.2f}, "
            f"{r['Sub_metering_3']:.2f}, {r['energy_consumption_kwh']:.4f}, {r['sub_metering_kitchen_kwh']:.4f}, "
            f"{r['sub_metering_laundry_kwh']:.4f}, {r['sub_metering_climate_kwh']:.4f}, {r['sub_metering_other_kwh']:.4f}, "
            f"{int(r['hour'])}, {int(r['day_of_week'])}, '{r['day_name']}', {int(r['month'])}, {int(r['year'])}, "
            f"{int(r['is_weekend'])}, {int(r['is_peak_period'])}, {r['lag_1h']:.4f}, {r['lag_24h']:.4f}, "
            f"{r['lag_168h']:.4f}, {r['rolling_mean_24h']:.4f})"
        )
        value_tuples.append(val)

    lines.append(",\n".join(value_tuples) + ";")
    sql_content = "\n".join(lines)
    out_file = Path("sql/seed_data.sql")
    out_file.write_text(sql_content, encoding="utf-8")
    print(f"Generated {out_file} with {len(df)} records ({len(sql_content)} characters).")

if __name__ == "__main__":
    generate_seed_sql()
