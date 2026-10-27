-- EnergyPulse Cloud BigQuery Schema DDL
-- Partitioned by day on timestamp column to optimize scan costs and query performance
-- Clustered by is_peak_period and hour for fast temporal filtering

CREATE TABLE IF NOT EXISTS `energypulse-cloud-dev.energypulse_analytics.household_hourly_consumption` (
    timestamp TIMESTAMP NOT NULL OPTIONS(description="Hourly start timestamp in UTC"),
    Global_active_power FLOAT64 OPTIONS(description="Mean active power in kilowatts (kW) across the hour"),
    Global_reactive_power FLOAT64 OPTIONS(description="Mean reactive power in kilowatts (kW)"),
    Voltage FLOAT64 OPTIONS(description="Mean voltage in Volts (V)"),
    Global_intensity FLOAT64 OPTIONS(description="Mean current intensity in Amperes (A)"),
    Sub_metering_1 FLOAT64 OPTIONS(description="Kitchen active energy in Watt-hours (Wh)"),
    Sub_metering_2 FLOAT64 OPTIONS(description="Laundry active energy in Watt-hours (Wh)"),
    Sub_metering_3 FLOAT64 OPTIONS(description="Climate/Water heating active energy in Watt-hours (Wh)"),
    energy_consumption_kwh FLOAT64 NOT NULL OPTIONS(description="Total electrical consumption in kilowatt-hours (kWh)"),
    sub_metering_kitchen_kwh FLOAT64 OPTIONS(description="Kitchen electrical consumption in kWh"),
    sub_metering_laundry_kwh FLOAT64 OPTIONS(description="Laundry electrical consumption in kWh"),
    sub_metering_climate_kwh FLOAT64 OPTIONS(description="Climate control electrical consumption in kWh"),
    sub_metering_other_kwh FLOAT64 OPTIONS(description="Unmetered base electrical consumption in kWh"),
    hour INT64 OPTIONS(description="Hour of day (0-23)"),
    day_of_week INT64 OPTIONS(description="Day of week (0=Monday, 6=Sunday)"),
    day_name STRING OPTIONS(description="Name of day (Monday..Sunday)"),
    month INT64 OPTIONS(description="Month number (1-12)"),
    year INT64 OPTIONS(description="Year (YYYY)"),
    is_weekend INT64 OPTIONS(description="Binary flag (1 for Saturday/Sunday, 0 otherwise)"),
    is_peak_period INT64 OPTIONS(description="Peak demand indicator (1 for 18:00-22:00, 0 otherwise)"),
    lag_1h FLOAT64 OPTIONS(description="1-hour lag consumption in kWh"),
    lag_24h FLOAT64 OPTIONS(description="24-hour lag consumption in kWh"),
    lag_168h FLOAT64 OPTIONS(description="168-hour (7-day) lag consumption in kWh"),
    rolling_mean_24h FLOAT64 OPTIONS(description="24-hour trailing rolling mean in kWh")
)
PARTITION BY DATE(timestamp)
CLUSTER BY is_peak_period, hour
OPTIONS(
    description="Cleaned, aggregated hourly household electricity consumption dataset with temporal features",
    labels=[("project", "energypulse_cloud"), ("environment", "production")]
);
