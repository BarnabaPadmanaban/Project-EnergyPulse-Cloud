"""
EnergyPulse Cloud - Interactive Analytics & Forecasting Dashboard.
Cloud-Based Energy Consumption Analytics, Anomaly Detection & Machine Learning Forecasting.
"""

import io
import logging
from datetime import datetime, date
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config.settings import AppConfig
from src.ingestion import DatasetIngestion
from src.etl import EnergyPulseETL
from src.forecasting import EnergyForecaster
from src.anomaly_detection import EnergyAnomalyDetector
from src.storage_client import CloudStorageClient
from src.bigquery_client import BigQueryWarehouseClient

# Streamlit Page Config
st.set_page_config(
    page_title="EnergyPulse Cloud | Energy Analytics & Forecasting",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling: Modern Deep Blue and Clean White Academic Theme
st.markdown("""
<style>
    /* Metric Cards */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 16px 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
    }
    div[data-testid="stMetric"] label {
        color: #94a3b8 !important;
        font-weight: 600;
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        color: #38bdf8 !important;
        font-weight: 700;
        font-size: 1.8rem;
    }
    /* Mode Banner */
    .mode-badge-demo {
        background-color: #fef3c7;
        color: #92400e;
        border: 1px solid #f59e0b;
        padding: 6px 14px;
        border-radius: 8px;
        font-weight: 600;
        font-size: 0.9rem;
        display: inline-block;
        margin-bottom: 12px;
    }
    .mode-badge-cloud {
        background-color: #dcfce7;
        color: #166534;
        border: 1px solid #22c55e;
        padding: 6px 14px;
        border-radius: 8px;
        font-weight: 600;
        font-size: 0.9rem;
        display: inline-block;
        margin-bottom: 12px;
    }
    /* Section headers */
    h2, h3 {
        color: #f8fafc;
        border-bottom: 1px solid #334155;
        padding-bottom: 6px;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner="Running ETL pipeline on dataset...")
def process_data(raw_df: pd.DataFrame):
    """Run cached ETL on raw dataframe."""
    etl = EnergyPulseETL()
    return etl.run_pipeline(raw_df)


@st.cache_data(show_spinner="Evaluating forecast model...")
def evaluate_forecasting(df: pd.DataFrame, model_type: str = "ridge"):
    """Run forecasting train/test evaluation."""
    forecaster = EnergyForecaster(model_type=model_type)
    return forecaster.train_and_evaluate(df, test_ratio=0.2)


@st.cache_data(show_spinner="Generating multi-step future forecast...")
def generate_future_forecast(df: pd.DataFrame, horizon_hours: int = 24, model_type: str = "ridge"):
    """Generate future forecast."""
    forecaster = EnergyForecaster(model_type=model_type)
    forecaster.train_and_evaluate(df, test_ratio=0.2)
    return forecaster.forecast_future(df, horizon_hours=horizon_hours)


@st.cache_data(show_spinner="Detecting consumption anomalies...")
def run_anomaly_detection(df: pd.DataFrame, rolling_window: int = 24, k_std: float = 3.0):
    """Run dual-method anomaly detection."""
    detector = EnergyAnomalyDetector(rolling_window_hours=rolling_window, std_multiplier=k_std)
    return detector.analyze_anomalies(df)


def main():
    # Header
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        st.title("⚡ EnergyPulse Cloud")
        st.caption("Cloud-Based Energy Consumption Analytics, Anomaly Detection & Predictive Forecasting")
    with col_t2:
        if AppConfig.DEMO_MODE:
            st.markdown(
                '<div class="mode-badge-demo">🟢 Mode: Local Demo (Zero-Cost / Offline)</div>',
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                '<div class="mode-badge-cloud">☁️ Mode: Google Cloud Platform (Active)</div>',
                unsafe_allow_html=True
            )

    # Sidebar
    st.sidebar.title("Dashboard Controls")
    
    # Dataset Selection & Ingestion
    st.sidebar.subheader("📁 Data Source")
    data_source_mode = st.sidebar.radio(
        "Choose Ingestion Source:",
        ["Benchmark Sample (Demo Mode)", "Download Official UCI Dataset", "Upload Custom CSV"],
        index=0,
    )

    ingestor = DatasetIngestion()
    raw_df = None
    source_description = ""

    if data_source_mode == "Benchmark Sample (Demo Mode)":
        if not AppConfig.SAMPLE_DATA_PATH.exists():
            from src.generate_sample import generate_sample_csv
            generate_sample_csv(AppConfig.SAMPLE_DATA_PATH)
        raw_df, source_description = ingestor.load_raw_dataframe(use_sample_if_missing=True)

    elif data_source_mode == "Download Official UCI Dataset":
        if st.sidebar.button("📥 Trigger Download from UCI"):
            with st.spinner("Downloading official UCI dataset (~20MB compressed)..."):
                try:
                    ingestor.download_uci_dataset()
                    st.sidebar.success("Download and extraction complete!")
                except Exception as e:
                    st.sidebar.error(f"Download error: {e}")
        try:
            raw_df, source_description = ingestor.load_raw_dataframe(max_rows=100_000)
        except Exception as e:
            st.sidebar.warning(f"UCI dataset not found yet. Click 'Trigger Download' or use Benchmark Sample.")
            raw_df, source_description = ingestor.load_raw_dataframe(use_sample_if_missing=True)

    elif data_source_mode == "Upload Custom CSV":
        uploaded_file = st.sidebar.file_uploader("Upload raw CSV (semicolon or comma delimited):", type=["csv", "txt"])
        if uploaded_file is not None:
            try:
                # Detect delimiter
                sample_bytes = uploaded_file.read(2048).decode("utf-8", errors="replace")
                uploaded_file.seek(0)
                delimiter = ";" if ";" in sample_bytes else ","
                raw_df = pd.read_csv(uploaded_file, sep=delimiter, low_memory=False, dtype=str)
                DatasetIngestion.validate_schema(raw_df)
                source_description = f"User Upload ({uploaded_file.name})"
                st.sidebar.success(f"Validated {len(raw_df)} uploaded rows.")
            except Exception as e:
                st.sidebar.error(f"Invalid upload file: {e}")
                raw_df, source_description = ingestor.load_raw_dataframe(use_sample_if_missing=True)
        else:
            raw_df, source_description = ingestor.load_raw_dataframe(use_sample_if_missing=True)

    # Run ETL
    hourly_df, audit_info = process_data(raw_df)

    # Date Filter in Sidebar
    st.sidebar.subheader("📅 Temporal Filter")
    min_date = hourly_df["timestamp"].min().date()
    max_date = hourly_df["timestamp"].max().date()

    date_range = st.sidebar.date_input(
        "Date Range Filter:",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
        start_date, end_date = date_range
        mask = (hourly_df["timestamp"].dt.date >= start_date) & (hourly_df["timestamp"].dt.date <= end_date)
        filtered_df = hourly_df.loc[mask].copy()
    else:
        filtered_df = hourly_df.copy()

    if filtered_df.empty:
        st.warning("Selected date range has no records. Resetting filter.")
        filtered_df = hourly_df.copy()

    # KPI Top Bar
    st.markdown("### 📊 Key Performance Indicators")
    total_consumption_kwh = filtered_df["energy_consumption_kwh"].sum()
    daily_grouped = filtered_df.groupby(filtered_df["timestamp"].dt.date)["energy_consumption_kwh"].sum()
    avg_daily_kwh = daily_grouped.mean() if not daily_grouped.empty else 0.0
    peak_idx = filtered_df["energy_consumption_kwh"].idxmax()
    peak_consumption_kwh = filtered_df.loc[peak_idx, "energy_consumption_kwh"]
    peak_time_str = filtered_df.loc[peak_idx, "timestamp"].strftime("%Y-%m-%d %H:%M")
    avg_voltage = filtered_df["Voltage"].mean()

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Total Consumption", f"{total_consumption_kwh:,.1f} kWh", help="Sum of hourly active energy (kWh)")
    kpi2.metric("Daily Average", f"{avg_daily_kwh:,.2f} kWh/day", help="Mean aggregate daily energy")
    kpi3.metric("Peak Demand", f"{peak_consumption_kwh:,.2f} kWh", f"Peak: {peak_time_str}")
    kpi4.metric("Avg Voltage", f"{avg_voltage:.1f} V", help="Mean supply voltage (nominal 230V)")

    # Tabs for Dashboard Sections
    tab_analytics, tab_forecast, tab_anomaly, tab_etl_audit, tab_cloud_docs = st.tabs([
        "📈 Consumption Analytics",
        "🔮 Predictive Forecasting",
        "🚨 Anomaly Detection",
        "🧹 Data Quality & ETL Audit",
        "☁️ Cloud Architecture & BQ"
    ])

    # ------------------ TAB 1: CONSUMPTION ANALYTICS ------------------
    with tab_analytics:
        st.subheader("Historical Electricity Consumption")
        fig_ts = go.Figure()
        fig_ts.add_trace(go.Scatter(
            x=filtered_df["timestamp"],
            y=filtered_df["energy_consumption_kwh"],
            mode="lines",
            name="Hourly Energy (kWh)",
            line=dict(color="#38bdf8", width=1.8),
            hovertemplate="<b>%{x}</b><br>Consumption: %{y:.3f} kWh<extra></extra>"
        ))
        fig_ts.add_trace(go.Scatter(
            x=filtered_df["timestamp"],
            y=filtered_df["rolling_mean_24h"],
            mode="lines",
            name="24h Rolling Mean",
            line=dict(color="#f59e0b", width=1.5, dash="dot"),
        ))
        fig_ts.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0f172a",
            plot_bgcolor="#1e293b",
            height=420,
            margin=dict(l=40, r=20, t=30, b=40),
            xaxis=dict(title="Timestamp (UTC)", showgrid=True, gridcolor="#334155"),
            yaxis=dict(title="Energy Consumption (kWh)", showgrid=True, gridcolor="#334155"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_ts, use_container_width=True)

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.subheader("Hourly Diurnal Profile (Peak vs Off-Peak)")
            hourly_agg = filtered_df.groupby("hour")["energy_consumption_kwh"].agg(["mean", "min", "max"]).reset_index()
            fig_hourly = go.Figure()
            fig_hourly.add_trace(go.Bar(
                x=hourly_agg["hour"],
                y=hourly_agg["mean"],
                marker_color=np.where(hourly_agg["hour"].between(18, 22), "#ef4444", "#3b82f6"),
                name="Mean Hourly kWh",
                hovertemplate="Hour %{x}:00<br>Mean: %{y:.3f} kWh<extra></extra>"
            ))
            fig_hourly.update_layout(
                template="plotly_dark",
                paper_bgcolor="#0f172a",
                plot_bgcolor="#1e293b",
                height=340,
                xaxis=dict(title="Hour of Day (0-23)", tickmode="linear", tick0=0, dtick=2),
                yaxis=dict(title="Average Consumption (kWh)"),
            )
            st.plotly_chart(fig_hourly, use_container_width=True)

        with col_c2:
            st.subheader("Sub-Metering Load Breakdown")
            sub_totals = {
                "Kitchen (Dishwasher/Microwave)": filtered_df["sub_metering_kitchen_kwh"].sum(),
                "Laundry (Washing/Dryer)": filtered_df["sub_metering_laundry_kwh"].sum(),
                "Climate (Water-Heater/AC)": filtered_df["sub_metering_climate_kwh"].sum(),
                "Base Load & Other Sockets": filtered_df["sub_metering_other_kwh"].sum(),
            }
            fig_pie = px.pie(
                names=list(sub_totals.keys()),
                values=list(sub_totals.values()),
                hole=0.45,
                color_discrete_sequence=["#f97316", "#06b6d4", "#a855f7", "#64748b"],
            )
            fig_pie.update_layout(
                template="plotly_dark",
                paper_bgcolor="#0f172a",
                plot_bgcolor="#1e293b",
                height=340,
                margin=dict(l=20, r=20, t=20, b=20),
            )
            st.plotly_chart(fig_pie, use_container_width=True)

    # ------------------ TAB 2: FORECASTING ------------------
    with tab_forecast:
        st.subheader("Time-Series Forecasting & Model Comparison")
        st.markdown("""
        **Methodology**: Time-series observations are partitioned **strictly chronologically** (80% Train, 20% Test) 
        to prevent future data leakage. Feature representations incorporate lagged demand ($t-1$, $t-24$, $t-168$), 
        rolling averages, and deterministic calendar signals. Benchmarked directly against a 24-hour persistence baseline.
        """)

        f_col1, f_col2 = st.columns([1, 2])
        with f_col1:
            model_choice = st.selectbox("Select Model Architecture:", ["Ridge", "Random_Forest"])
            horizon_hours = st.slider("Forecast Horizon (Hours):", min_value=12, max_value=72, value=24, step=12)

        summary_metrics, comp_df = evaluate_forecasting(filtered_df, model_type=model_choice)
        future_forecast_df = generate_future_forecast(filtered_df, horizon_hours=horizon_hours, model_type=model_choice)

        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        m_col1.metric("Model MAE", f"{summary_metrics['model_metrics']['MAE']:.4f} kWh",
                      delta=f"{summary_metrics['mae_improvement_pct']:.1f}% vs baseline", delta_color="inverse")
        m_col2.metric("Baseline MAE", f"{summary_metrics['baseline_metrics']['MAE']:.4f} kWh")
        m_col3.metric("Model RMSE", f"{summary_metrics['model_metrics']['RMSE']:.4f} kWh",
                      delta=f"{summary_metrics['rmse_improvement_pct']:.1f}% vs baseline", delta_color="inverse")
        m_col4.metric("Baseline RMSE", f"{summary_metrics['baseline_metrics']['RMSE']:.4f} kWh")

        # Actual vs Predicted Plot
        fig_eval = go.Figure()
        fig_eval.add_trace(go.Scatter(
            x=comp_df["timestamp"],
            y=comp_df["actual_kwh"],
            mode="lines",
            name="Actual Consumption (kWh)",
            line=dict(color="#38bdf8", width=2),
        ))
        fig_eval.add_trace(go.Scatter(
            x=comp_df["timestamp"],
            y=comp_df["predicted_kwh"],
            mode="lines",
            name=f"{model_choice} Forecast (kWh)",
            line=dict(color="#10b981", width=2, dash="dash"),
        ))
        fig_eval.add_trace(go.Scatter(
            x=comp_df["timestamp"],
            y=comp_df["baseline_kwh"],
            mode="lines",
            name="24h Persistence Baseline (kWh)",
            line=dict(color="#f43f5e", width=1, dash="dot"),
            opacity=0.6,
        ))
        # Add future forecast projection
        fig_eval.add_trace(go.Scatter(
            x=future_forecast_df["timestamp"],
            y=future_forecast_df["predicted_kwh"],
            mode="lines+markers",
            name=f"Future {horizon_hours}h Horizon",
            line=dict(color="#fbbf24", width=2.5),
            marker=dict(size=5),
        ))
        fig_eval.update_layout(
            title="Validation: Predicted vs Actual & Out-of-Sample Future Horizon",
            template="plotly_dark",
            paper_bgcolor="#0f172a",
            plot_bgcolor="#1e293b",
            height=430,
            xaxis=dict(title="Timestamp"),
            yaxis=dict(title="Energy Consumption (kWh)"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_eval, use_container_width=True)

        with st.expander("🔍 Model Limitations & Cloud Integration Details"):
            st.write(f"**Training Period**: {summary_metrics['train_period']} ({summary_metrics['train_samples']} hours)")
            st.write(f"**Test Period**: {summary_metrics['test_period']} ({summary_metrics['test_samples']} hours)")
            st.markdown("**Stated Limitations:**")
            for lim in summary_metrics["limitations"]:
                st.markdown(f"- {lim}")
            st.info(summary_metrics["cloud_ml_status"])

    # ------------------ TAB 3: ANOMALIES ------------------
    with tab_anomaly:
        st.subheader("Statistical & Machine Learning Anomaly Detection")
        st.markdown("""
        **Mathematical Formulation**: Thresholds are computed dynamically using a 24-hour moving window:
        $$\\text{Upper Bound} = \\text{Rolling Median}_{24\\text{h}} + k \\cdot \\text{Rolling Std}_{24\\text{h}}$$
        $$\\text{Lower Bound} = \\max\\left(0, \\text{Rolling Median}_{24\\text{h}} - k \\cdot \\text{Rolling Std}_{24\\text{h}}\\right)$$
        Cross-validated using multidimensional **Isolation Forest** on power, voltage, current, and hour.
        """)

        a_col1, a_col2 = st.columns([1, 1])
        with a_col1:
            k_std_slider = st.slider("Deviation Multiplier (k):", min_value=1.5, max_value=4.5, value=3.0, step=0.5)
        with a_col2:
            rolling_window_slider = st.slider("Rolling Window (Hours):", min_value=12, max_value=72, value=24, step=12)

        anomaly_df, anomaly_summary = run_anomaly_detection(
            filtered_df, rolling_window=rolling_window_slider, k_std=k_std_slider
        )

        anom_kpi1, anom_kpi2, anom_kpi3 = st.columns(3)
        anom_kpi1.metric("Total Anomalies Flagged", f"{anomaly_summary['total_anomalies_detected']}")
        anom_kpi2.metric("Anomaly Rate", f"{anomaly_summary['anomaly_rate_percent']:.2f}%")
        anom_kpi3.metric("Threshold Rule", f"k = {k_std_slider}σ ({rolling_window_slider}h Window)")

        # Anomaly Chart
        fig_anom = go.Figure()
        # Normal consumption
        fig_anom.add_trace(go.Scatter(
            x=anomaly_df["timestamp"],
            y=anomaly_df["energy_consumption_kwh"],
            mode="lines",
            name="Normal Consumption (kWh)",
            line=dict(color="#64748b", width=1.5),
        ))
        # Upper Threshold
        fig_anom.add_trace(go.Scatter(
            x=anomaly_df["timestamp"],
            y=anomaly_df["rolling_upper_threshold"],
            mode="lines",
            name="Dynamic Upper Threshold",
            line=dict(color="#f59e0b", width=1.2, dash="dash"),
        ))
        # Flagged Anomalies
        anomalies_sub = anomaly_df[anomaly_df["is_anomaly"]]
        fig_anom.add_trace(go.Scatter(
            x=anomalies_sub["timestamp"],
            y=anomalies_sub["energy_consumption_kwh"],
            mode="markers",
            name="Detected Anomaly",
            marker=dict(color="#ef4444", size=8, symbol="diamond"),
            customdata=anomalies_sub["anomaly_category"],
            hovertemplate="<b>%{x}</b><br>Observed: %{y:.3f} kWh<br>Type: %{customdata}<extra></extra>"
        ))
        fig_anom.update_layout(
            title="Energy Consumption with Dynamic Thresholds & Flagged Anomalies",
            template="plotly_dark",
            paper_bgcolor="#0f172a",
            plot_bgcolor="#1e293b",
            height=430,
            xaxis=dict(title="Timestamp"),
            yaxis=dict(title="Energy (kWh)"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_anom, use_container_width=True)

        st.warning(f"⚠️ **Engineering Distinction**: {anomaly_summary['cautionary_note']}")

        if not anomalies_sub.empty:
            st.markdown("#### Flagged Anomaly Observations")
            display_cols = [
                "timestamp", "energy_consumption_kwh", "rolling_upper_threshold",
                "Voltage", "deviation_score", "anomaly_category"
            ]
            st.dataframe(
                anomalies_sub[display_cols].sort_values("timestamp", ascending=False).head(50),
                use_container_width=True,
            )

    # ------------------ TAB 4: ETL AUDIT ------------------
    with tab_etl_audit:
        st.subheader("Data Quality Summary & ETL Audit")
        q_col1, q_col2, q_col3 = st.columns(3)
        q_col1.metric("Raw Rows Processed", f"{audit_info['initial_rows']:,}")
        q_col2.metric("Duplicates Removed", f"{audit_info['duplicates_removed']:,}")
        q_col3.metric("Hourly Rows Produced", f"{audit_info['hourly_rows_generated']:,}")

        st.markdown("#### Missing Value Imputation Log")
        missing_df = pd.DataFrame(
            list(audit_info["missing_values_imputed"].items()),
            columns=["Raw Column", "Missing Values Imputed via Linear Interpolation"]
        )
        st.dataframe(missing_df, use_container_width=True)

        st.markdown("#### Download Processed Datasets")
        d_col1, d_col2 = st.columns(2)
        with d_col1:
            csv_processed = filtered_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Download Processed Hourly Data (CSV)",
                data=csv_processed,
                file_name="energypulse_hourly_consumption.csv",
                mime="text/csv",
            )
        with d_col2:
            csv_preds = comp_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 Download Model Predictions (CSV)",
                data=csv_preds,
                file_name="energypulse_predictions_vs_actuals.csv",
                mime="text/csv",
            )

    # ------------------ TAB 5: CLOUD ARCHITECTURE ------------------
    with tab_cloud_docs:
        st.subheader("Cloud Pipeline Architecture")
        st.markdown("""
        ```mermaid
        graph LR
            A[Raw Dataset CSV / Stream] -->|Upload| B[(Google Cloud Storage Bucket)]
            B -->|Cloud Storage Event| C[Cloud Run Functions: Ingestion & ETL]
            C -->|Partitioned Ingestion| D[(Google BigQuery: Analytics Warehouse)]
            D -->|Managed ML ARIMA_PLUS| E[BigQuery ML Models]
            D -->|SQL Analytics API| F[EnergyPulse Streamlit Dashboard]
            E -->|Forecast Predictions| F
        ```
        """)

        st.markdown("#### Cloud Storage & Warehouse Health Check")
        c_check1, c_check2 = st.columns(2)
        with c_check1:
            st.write(f"**GCS Bucket**: `{AppConfig.GCS_BUCKET_NAME}`")
            st.write(f"**GCP Region**: `{AppConfig.GCP_REGION}`")
            gcs_client = CloudStorageClient()
            blobs = gcs_client.list_files()
            st.write(f"**Active Files in Storage**: {len(blobs)}")
            if blobs:
                st.code("\n".join(blobs[:5]))

        with c_check2:
            st.write(f"**BigQuery Dataset**: `{AppConfig.BQ_DATASET_ID}`")
            st.write(f"**BigQuery Table**: `{AppConfig.BQ_TABLE_ID}`")
            bq_client = BigQueryWarehouseClient()
            if st.button("🚀 Sync Hourly Data to Cloud Warehouse"):
                with st.spinner("Ingesting records into BigQuery..."):
                    bq_client.init_warehouse_schema(AppConfig.BASE_DIR / "sql" / "schema.sql")
                    rows_loaded = bq_client.load_hourly_dataframe(filtered_df)
                    st.success(f"Successfully synchronized {rows_loaded} records to warehouse table!")


if __name__ == "__main__":
    main()
