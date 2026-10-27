"""
Anomaly Detection Module for EnergyPulse Cloud.
Implements interpretable rolling-window statistical thresholds (Median + k*Deviation)
and unsupervised Isolation Forest for multi-feature electrical anomaly detection.
Distinguishes unusual consumer load spikes from physical power-quality fluctuations.
"""

import logging
from typing import Dict, Any, Tuple
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class EnergyAnomalyDetector:
    """
    Detects and interprets anomalies in electricity consumption profiles.
    """

    def __init__(self, rolling_window_hours: int = 24, std_multiplier: float = 3.0, contamination: float = 0.02):
        self.rolling_window = rolling_window_hours
        self.k = std_multiplier
        self.contamination = contamination
        self.iso_forest = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_estimators=100
        )

    def detect_statistical_anomalies(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Interpretable Rolling Statistical Method:
        Calculates Upper and Lower dynamic thresholds:
          Upper = RollingMedian_24h + k * RollingStd_24h
          Lower = max(0, RollingMedian_24h - k * RollingStd_24h)
        """
        df_out = df.copy().sort_values("timestamp").reset_index(drop=True)
        series = df_out["energy_consumption_kwh"]

        # Calculate rolling statistics with minimum period of 1 to avoid initial NaNs
        rolling_median = series.rolling(window=self.rolling_window, min_periods=3).median().bfill()
        rolling_std = series.rolling(window=self.rolling_window, min_periods=3).std().fillna(0.1)

        upper_bound = np.round(rolling_median + (self.k * rolling_std), 4)
        lower_bound = np.round(np.clip(rolling_median - (self.k * rolling_std), 0.0, None), 4)

        df_out["rolling_median"] = np.round(rolling_median, 4)
        df_out["rolling_upper_threshold"] = upper_bound
        df_out["rolling_lower_threshold"] = lower_bound

        is_high = series > upper_bound
        is_low = (series < lower_bound) & (series < 0.05) & (rolling_median > 0.5)
        df_out["is_statistical_anomaly"] = is_high | is_low

        # Severity score: normalized distance from rolling median
        df_out["deviation_score"] = np.round(np.abs(series - rolling_median) / (rolling_std + 1e-4), 2)
        return df_out

    def detect_isolation_forest_anomalies(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Multi-dimensional Isolation Forest on electrical features:
        Consumption (kWh), Voltage (V), Reactive Power (kW), Current (A), and Hour of Day.
        """
        df_out = df.copy()
        feature_cols = ["energy_consumption_kwh", "hour"]
        optional_features = ["Voltage", "Global_reactive_power", "Global_intensity"]
        for opt in optional_features:
            if opt in df_out.columns:
                feature_cols.append(opt)

        X = df_out[feature_cols].fillna(0).values
        self.iso_forest.fit(X)

        # -1 indicates anomaly, 1 indicates inlier
        preds = self.iso_forest.predict(X)
        scores = self.iso_forest.decision_function(X)

        df_out["is_isolation_forest_anomaly"] = (preds == -1)
        df_out["isolation_score"] = np.round(scores, 4)
        return df_out

    @staticmethod
    def classify_anomaly_nature(row: pd.Series) -> str:
        """
        Distinguishes unusual consumption behaviors from potential electrical anomalies:
        - High Appliance Surge: High power, normal voltage (215V - 245V).
        - Voltage Fluctuation: Voltage < 210V or > 250V.
        - Power Outage / Zero Drop: Power ~ 0.0 while historic baseline > 0.5.
        - Standard Deviation Surge: Statistical spike.
        """
        power = row.get("energy_consumption_kwh", 0.0)
        voltage = row.get("Voltage", 230.0)
        upper = row.get("rolling_upper_threshold", 5.0)

        if voltage < 210.0 or voltage > 250.0:
            return "Power Quality Event (Voltage Fluctuation - Grid/Supply Anomaly)"
        elif power > upper and power > 4.5:
            return "Heavy Load Surge (Unusual Peak Consumer Demand)"
        elif power < 0.05 and row.get("rolling_median", 0.0) > 0.6:
            return "Drop / Inactive Period (Potential Outage or Vacancy)"
        else:
            return "Statistical Outlier (Usage Deviation)"

    def analyze_anomalies(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Full anomaly detection pipeline combining statistical thresholds and ML.
        Returns annotated dataframe and audit summary.
        """
        df_stat = self.detect_statistical_anomalies(df)
        df_full = self.detect_isolation_forest_anomalies(df_stat)

        # Combined flag: flagged by statistical rule OR isolation forest
        df_full["is_anomaly"] = (
            df_full["is_statistical_anomaly"] | df_full["is_isolation_forest_anomaly"]
        )

        df_full["anomaly_category"] = df_full.apply(
            lambda r: self.classify_anomaly_nature(r) if r["is_anomaly"] else "Normal",
            axis=1
        )

        anomalies_only = df_full[df_full["is_anomaly"]]

        summary = {
            "total_records_analyzed": len(df_full),
            "total_anomalies_detected": int(df_full["is_anomaly"].sum()),
            "statistical_anomalies": int(df_full["is_statistical_anomaly"].sum()),
            "isolation_forest_anomalies": int(df_full["is_isolation_forest_anomaly"].sum()),
            "anomaly_rate_percent": round((df_full["is_anomaly"].sum() / len(df_full)) * 100.0, 2),
            "threshold_formula": (
                f"Upper = RollingMedian({self.rolling_window}h) + {self.k} * RollingStd({self.rolling_window}h)"
            ),
            "breakdown_by_category": anomalies_only["anomaly_category"].value_counts().to_dict(),
            "cautionary_note": (
                "Important Engineering Distinction: Smart meter time-series anomalies reflect "
                "statistical deviations in consumer habits or power quality readings. "
                "They should not be confused with confirmed physical equipment failures or "
                "fault relay trips, which require auxiliary SCADA/breaker telemetry."
            ),
        }

        return df_full, summary
