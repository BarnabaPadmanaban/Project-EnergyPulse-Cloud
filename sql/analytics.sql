-- EnergyPulse Cloud Analytical Queries for Dashboard and Reporting

-- 1. KPI Summary Metrics (Overall period)
SELECT
    COUNT(*) AS total_recorded_hours,
    ROUND(SUM(energy_consumption_kwh), 2) AS total_consumption_kwh,
    ROUND(AVG(energy_consumption_kwh), 3) AS avg_hourly_kwh,
    ROUND(MAX(energy_consumption_kwh), 3) AS peak_hourly_kwh,
    ROUND(AVG(Voltage), 1) AS avg_voltage_v,
    ROUND(SUM(sub_metering_kitchen_kwh), 2) AS total_kitchen_kwh,
    ROUND(SUM(sub_metering_laundry_kwh), 2) AS total_laundry_kwh,
    ROUND(SUM(sub_metering_climate_kwh), 2) AS total_climate_kwh,
    ROUND(SUM(sub_metering_other_kwh), 2) AS total_base_other_kwh
FROM `energypulse-cloud-dev.energypulse_analytics.household_hourly_consumption`;

-- 2. Daily Consumption Summary with Peak Hourly Usage
SELECT
    DATE(timestamp) AS usage_date,
    ROUND(SUM(energy_consumption_kwh), 3) AS daily_total_kwh,
    ROUND(AVG(energy_consumption_kwh), 3) AS daily_avg_hourly_kwh,
    ROUND(MAX(energy_consumption_kwh), 3) AS daily_peak_kwh,
    MAX(CASE WHEN is_peak_period = 1 THEN energy_consumption_kwh ELSE 0 END) AS peak_period_max_kwh
FROM `energypulse-cloud-dev.energypulse_analytics.household_hourly_consumption`
GROUP BY usage_date
ORDER BY usage_date ASC;

-- 3. Diurnal (Hourly) Demand Profile (Average Consumption by Hour of Day)
SELECT
    hour,
    ROUND(AVG(energy_consumption_kwh), 4) AS avg_kwh,
    ROUND(MIN(energy_consumption_kwh), 4) AS min_kwh,
    ROUND(MAX(energy_consumption_kwh), 4) AS max_kwh,
    ROUND(AVG(sub_metering_kitchen_kwh), 4) AS avg_kitchen_kwh,
    ROUND(AVG(sub_metering_laundry_kwh), 4) AS avg_laundry_kwh,
    ROUND(AVG(sub_metering_climate_kwh), 4) AS avg_climate_kwh
FROM `energypulse-cloud-dev.energypulse_analytics.household_hourly_consumption`
GROUP BY hour
ORDER BY hour ASC;

-- 4. Day of Week Consumption Profile (Weekday vs Weekend)
SELECT
    day_name,
    day_of_week,
    ROUND(AVG(energy_consumption_kwh), 3) AS avg_hourly_kwh,
    ROUND(SUM(energy_consumption_kwh), 2) AS total_day_kwh
FROM `energypulse-cloud-dev.energypulse_analytics.household_hourly_consumption`
GROUP BY day_name, day_of_week
ORDER BY day_of_week ASC;
