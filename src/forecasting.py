"""
Forecasting Module for EnergyPulse Cloud.
Implements chronological time-series forecasting, baseline comparisons,
rigorous error metrics (MAE, RMSE, MAPE), and managed cloud BigQuery ML hooks.
"""

import logging
from typing import Dict, Any, Tuple, Optional
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class EnergyForecaster:
    """
    Time-series forecasting model with strictly chronological train/test splitting,
    lag-based feature engineering without data leakage, and baseline benchmarking.
    """

    FEATURE_COLS = [
        "hour",
        "day_of_week",
        "is_weekend",
        "is_peak_period",
        "lag_1h",
        "lag_24h",
        "lag_168h",
        "rolling_mean_24h",
    ]
    TARGET_COL = "energy_consumption_kwh"

    def __init__(self, model_type: str = "ridge"):
        self.model_type = model_type.lower()
        if self.model_type == "random_forest":
            self.model = RandomForestRegressor(n_estimators=100, random_state=42, max_depth=12, n_jobs=-1)
        else:
            self.model = Ridge(alpha=1.0)

    @staticmethod
    def chronological_split(
        df: pd.DataFrame, test_ratio: float = 0.2
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Split time-series data chronologically.
        Guarantees that train observations strictly precede test observations.
        """
        df_sorted = df.sort_values("timestamp").reset_index(drop=True)
        split_idx = int(len(df_sorted) * (1.0 - test_ratio))
        train_df = df_sorted.iloc[:split_idx].copy()
        test_df = df_sorted.iloc[split_idx:].copy()
        return train_df, test_df

    @staticmethod
    def calculate_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
        """Calculate MAE, RMSE, and MAPE."""
        mae = float(mean_absolute_error(y_true, y_pred))
        rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
        # Avoid division by zero in MAPE
        non_zero_mask = y_true > 1e-4
        if np.any(non_zero_mask):
            mape = float(np.mean(np.abs((y_true[non_zero_mask] - y_pred[non_zero_mask]) / y_true[non_zero_mask])) * 100.0)
        else:
            mape = 0.0

        return {
            "MAE": round(mae, 4),
            "RMSE": round(rmse, 4),
            "MAPE_percent": round(mape, 2),
        }

    def train_and_evaluate(
        self, df: pd.DataFrame, test_ratio: float = 0.2
    ) -> Tuple[Dict[str, Any], pd.DataFrame]:
        """
        Train ML model against chronological split and compare with a 24-hour persistence baseline.
        Returns (evaluation_summary, comparison_dataframe).
        """
        # Ensure required features exist
        missing_features = [f for f in self.FEATURE_COLS if f not in df.columns]
        if missing_features:
            raise ValueError(f"Missing required forecast features in dataframe: {missing_features}")

        train_df, test_df = self.chronological_split(df, test_ratio=test_ratio)

        X_train = train_df[self.FEATURE_COLS].bfill().ffill().fillna(0.0).values
        y_train = train_df[self.TARGET_COL].values
        X_test = test_df[self.FEATURE_COLS].bfill().ffill().fillna(0.0).values
        y_test = test_df[self.TARGET_COL].values

        # 1. Fit ML model
        self.model.fit(X_train, y_train)
        y_pred = np.clip(self.model.predict(X_test), 0.0, None)

        # 2. Baseline Model: 24-hour seasonal persistence (lag_24h)
        y_baseline = test_df["lag_24h"].values

        # 3. Calculate metrics
        ml_metrics = self.calculate_metrics(y_test, y_pred)
        baseline_metrics = self.calculate_metrics(y_test, y_baseline)

        # Calculate improvement percentage
        mae_improvement = (
            ((baseline_metrics["MAE"] - ml_metrics["MAE"]) / baseline_metrics["MAE"]) * 100.0
            if baseline_metrics["MAE"] > 0 else 0.0
        )
        rmse_improvement = (
            ((baseline_metrics["RMSE"] - ml_metrics["RMSE"]) / baseline_metrics["RMSE"]) * 100.0
            if baseline_metrics["RMSE"] > 0 else 0.0
        )

        comparison_df = pd.DataFrame({
            "timestamp": test_df["timestamp"].values,
            "actual_kwh": np.round(y_test, 4),
            "predicted_kwh": np.round(y_pred, 4),
            "baseline_kwh": np.round(y_baseline, 4),
            "absolute_error_kwh": np.round(np.abs(y_test - y_pred), 4),
        })

        summary = {
            "model_type": f"{self.model_type.upper()} Regressor",
            "train_samples": len(train_df),
            "test_samples": len(test_df),
            "train_period": f"{train_df['timestamp'].min()} to {train_df['timestamp'].max()}",
            "test_period": f"{test_df['timestamp'].min()} to {test_df['timestamp'].max()}",
            "model_metrics": ml_metrics,
            "baseline_metrics": baseline_metrics,
            "mae_improvement_pct": round(mae_improvement, 2),
            "rmse_improvement_pct": round(rmse_improvement, 2),
            "limitations": [
                "Assumes recurring consumer activity patterns based on historical lags and time of day.",
                "Does not account for external weather changes (e.g. sudden cold snaps) without ambient temperature inputs.",
                "Unannounced occupant travel or long holidays may produce localized forecast errors.",
            ],
            "cloud_ml_status": (
                "Managed BigQuery ML (ARIMA_PLUS) query prepared in sql/forecasting.sql; "
                "available when GCP BigQuery permissions are configured."
            ),
        }

        return summary, comparison_df

    def forecast_future(self, df: pd.DataFrame, horizon_hours: int = 24) -> pd.DataFrame:
        """
        Generate recursive multi-step future forecasts for the requested horizon (e.g. 24, 48, 72 hours).
        """
        last_row = df.sort_values("timestamp").iloc[-1]
        last_timestamp = last_row["timestamp"]
        
        future_records = []
        recent_history = list(df["energy_consumption_kwh"].iloc[-168:].values)

        for step in range(1, horizon_hours + 1):
            next_timestamp = last_timestamp + pd.Timedelta(hours=step)
            hour = next_timestamp.hour
            day_of_week = next_timestamp.dayofweek
            is_weekend = int(day_of_week in [5, 6])
            is_peak = int(18 <= hour <= 22)

            lag_1h = recent_history[-1]
            lag_24h = recent_history[-24] if len(recent_history) >= 24 else lag_1h
            lag_168h = recent_history[-168] if len(recent_history) >= 168 else lag_24h
            rolling_mean_24h = float(np.mean(recent_history[-24:]))

            features = np.array([[
                hour, day_of_week, is_weekend, is_peak,
                lag_1h, lag_24h, lag_168h, rolling_mean_24h
            ]])

            pred_val = float(np.clip(self.model.predict(features)[0], 0.0, None))
            recent_history.append(pred_val)

            future_records.append({
                "timestamp": next_timestamp,
                "predicted_kwh": round(pred_val, 4),
                "is_peak_period": is_peak,
                "hour": hour,
                "day_name": next_timestamp.strftime("%A"),
            })

        return pd.DataFrame(future_records)
