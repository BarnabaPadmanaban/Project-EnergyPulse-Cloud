/**
 * Realistic synthetic telemetry fallback for Vercel Edge / static hosting
 * Used when a live Python backend API is not connected.
 */

export function getMockStatus() {
  return {
    status: "online",
    demo_mode: true,
    gcp_project_id: "energypulse-cloud-dev",
    gcp_region: "us-central1",
    bq_dataset_id: "energypulse_analytics",
    bq_table_id: "household_hourly_consumption",
    source_label: "UCI Benchmark Telemetry (Vercel Cloud Edge)",
    total_hourly_records: 168
  };
}

export function getMockAnalytics() {
  const timeseries = [];
  const startDate = new Date(2007, 0, 1, 0, 0, 0);

  for (let i = 0; i < 168; i++) {
    const curDate = new Date(startDate.getTime() + i * 3600 * 1000);
    const hour = curDate.getHours();
    const isPeak = hour >= 18 && hour <= 22 ? 1 : 0;
    
    // Realistic consumption curve: morning peak (7-9), evening peak (18-22), low night
    let base = 0.4 + 0.3 * Math.sin((hour - 4) * Math.PI / 12);
    if (isPeak) base += 0.8;
    if (hour >= 7 && hour <= 9) base += 0.5;
    
    // Add minor variance
    const noise = Math.sin(i * 1.5) * 0.15;
    const energy = Math.max(0.15, Math.round((base + noise) * 1000) / 1000);
    const rolling = Math.round((base + 0.05) * 1000) / 1000;
    const voltage = Math.round((234.5 + Math.cos(i * 0.8) * 2.2) * 10) / 10;

    const isoStr = curDate.toISOString().replace('T', ' ').slice(0, 19);
    timeseries.push({
      timestamp: isoStr,
      energy_kwh: energy,
      rolling_mean: rolling,
      voltage: voltage,
      is_peak: isPeak,
      hour: hour
    });
  }

  // Inject a known peak for realism matching the 173.9 kWh dataset
  timeseries[116].energy_kwh = 2.44; // Peak at 2007-01-05 20:00

  const diurnal = [];
  for (let h = 0; h < 24; h++) {
    const isP = (h >= 18 && h <= 22) ? 1 : 0;
    let avg = 0.4 + 0.3 * Math.sin((h - 4) * Math.PI / 12);
    if (isP) avg += 0.8;
    if (h >= 7 && h <= 9) avg += 0.5;
    diurnal.push({
      hour: `${String(h).padStart(2, '0')}:00`,
      hour_num: h,
      avg_kwh: Math.round(avg * 1000) / 1000,
      min_kwh: Math.round((avg * 0.4) * 1000) / 1000,
      max_kwh: Math.round((avg * 1.7) * 1000) / 1000,
      is_peak: isP
    });
  }

  return {
    kpis: {
      total_consumption_kwh: 173.9,
      avg_daily_kwh: 24.84,
      peak_demand_kwh: 2.44,
      peak_timestamp: "2007-01-05 20:00",
      avg_voltage: 235.0,
      record_count: 168,
      date_start: "2007-01-01 00:00:00",
      date_end: "2007-01-07 23:00:00"
    },
    timeseries: timeseries,
    diurnal: diurnal,
    submetering: {
      kitchen_kwh: 28.4,
      laundry_kwh: 22.1,
      climate_kwh: 64.8,
      other_kwh: 58.6
    },
    audit: {
      raw_rows: 10080,
      null_values_imputed: 126,
      duplicates_dropped: 0,
      total_hourly_rows: 168
    }
  };
}

export function getMockForecast(modelType = 'ridge', horizonHours = 24) {
  const isRf = modelType.toLowerCase().includes('rf') || modelType.toLowerCase().includes('random');
  const evalComparison = [];
  const baseTime = new Date(2007, 0, 6, 0, 0, 0);

  for (let i = 0; i < 48; i++) {
    const t = new Date(baseTime.getTime() + i * 3600 * 1000);
    const hour = t.getHours();
    let actual = 0.5 + 0.4 * Math.sin((hour - 4) * Math.PI / 12) + (hour >= 18 && hour <= 22 ? 0.7 : 0);
    actual = Math.max(0.18, Math.round(actual * 1000) / 1000);

    const error = isRf ? (Math.sin(i * 2.1) * 0.03) : (Math.cos(i * 1.8) * 0.12);
    const predicted = Math.max(0.15, Math.round((actual + error) * 1000) / 1000);
    const baseline = Math.max(0.15, Math.round((actual + Math.sin(i) * 0.04) * 1000) / 1000);

    evalComparison.push({
      timestamp: t.toISOString().replace('T', ' ').slice(0, 19),
      actual_kwh: actual,
      predicted_kwh: predicted,
      baseline_kwh: baseline
    });
  }

  return {
    summary: {
      model_name: isRf ? "Random Forest Regressor (100 Trees)" : "Ridge Regressor (L2 Linear)",
      model_metrics: {
        MAE: isRf ? 0.022 : 0.1324,
        RMSE: isRf ? 0.0328 : 0.1729,
        MAPE_percent: isRf ? 2.91 : 11.68
      },
      baseline_metrics: {
        MAE: 0.0214,
        RMSE: 0.0266,
        MAPE_percent: 2.38
      },
      mae_improvement_pct: isRf ? 95.8 : 82.4,
      train_rows: 134,
      test_rows: 34,
      test_ratio: 0.2
    },
    eval_comparison: evalComparison,
    future_horizon: []
  };
}

export function getMockAnomalies(kStd = 3.0, windowHours = 24) {
  return {
    summary: {
      total_anomalies_detected: 6,
      anomaly_rate_percent: 3.57,
      isolation_forest_anomalies: 5,
      rolling_window_hours: windowHours,
      std_multiplier: kStd
    },
    anomalies: [
      {
        timestamp: "2007-01-05 20:00:00",
        consumption_kwh: 2.44,
        upper_threshold: 1.82,
        voltage: 232.1,
        deviation_score: 3.8,
        category: "Heavy Load Surge (Appliance Inrush)"
      },
      {
        timestamp: "2007-01-04 19:00:00",
        consumption_kwh: 2.18,
        upper_threshold: 1.76,
        voltage: 231.4,
        deviation_score: 3.4,
        category: "Heavy Load Surge (Appliance Inrush)"
      },
      {
        timestamp: "2007-01-03 14:00:00",
        consumption_kwh: 1.65,
        upper_threshold: 1.21,
        voltage: 206.8,
        deviation_score: 3.2,
        category: "Power Quality Event (Voltage Sag < 210V)"
      },
      {
        timestamp: "2007-01-02 03:00:00",
        consumption_kwh: 0.02,
        upper_threshold: 0.45,
        voltage: 236.4,
        deviation_score: -3.1,
        category: "Inactive / Grid Outage Pattern"
      },
      {
        timestamp: "2007-01-06 21:00:00",
        consumption_kwh: 2.25,
        upper_threshold: 1.79,
        voltage: 233.0,
        deviation_score: 3.6,
        category: "Heavy Load Surge (Appliance Inrush)"
      },
      {
        timestamp: "2007-01-07 18:00:00",
        consumption_kwh: 1.98,
        upper_threshold: 1.68,
        voltage: 230.2,
        deviation_score: 3.1,
        category: "Heavy Load Surge (Appliance Inrush)"
      }
    ]
  };
}
