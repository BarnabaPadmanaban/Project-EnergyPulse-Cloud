-- BigQuery ML Time-Series Forecasting Query
-- Creates an ARIMA_PLUS model to forecast hourly energy consumption with automatic seasonality decomposition

-- 1. Create or Replace ARIMA_PLUS Model
CREATE OR REPLACE MODEL `energypulse-cloud-dev.energypulse_analytics.arima_consumption_model`
OPTIONS(
    model_type = 'ARIMA_PLUS',
    time_series_timestamp_col = 'timestamp',
    time_series_data_col = 'energy_consumption_kwh',
    auto_arima = TRUE,
    data_frequency = 'HOURLY',
    holiday_region = 'FR' -- Based on UCI dataset location (France)
) AS
SELECT
    timestamp,
    energy_consumption_kwh
FROM `energypulse-cloud-dev.energypulse_analytics.household_hourly_consumption`
WHERE timestamp < '2010-01-01';

-- 2. Evaluate ARIMA_PLUS Model Performance
SELECT
    *
FROM ML.EVALUATE(
    MODEL `energypulse-cloud-dev.energypulse_analytics.arima_consumption_model`
);

-- 3. Forecast Future Consumption Horizon (e.g. 72 hours with 95% confidence intervals)
SELECT
    forecast_timestamp,
    ROUND(forecast_value, 4) AS predicted_kwh,
    ROUND(standard_error, 4) AS standard_error,
    ROUND(confidence_level, 2) AS confidence_level,
    ROUND(prediction_interval_lower_bound, 4) AS lower_bound_kwh,
    ROUND(prediction_interval_upper_bound, 4) AS upper_bound_kwh
FROM ML.FORECAST(
    MODEL `energypulse-cloud-dev.energypulse_analytics.arima_consumption_model`,
    STRUCT(72 AS horizon, 0.95 AS confidence_level)
);
