"""
Unit tests for Cloud Run serverless function logic using mocks.
"""

from unittest.mock import patch, MagicMock
import pytest
from functions.main import process_and_load


def test_process_and_load_logic(monkeypatch):
    """Verify that process_and_load parses CSV content, computes hourly aggregations, and loads BigQuery."""
    # Synthetic raw CSV snippet
    raw_csv = (
        "Date;Time;Global_active_power;Global_reactive_power;Voltage;Global_intensity;Sub_metering_1;Sub_metering_2;Sub_metering_3\n"
        "01/01/2007;00:00:00;1.2;0.1;235.0;5.1;0.0;0.0;10.0\n"
        "01/01/2007;00:30:00;1.4;0.1;234.0;6.0;0.0;0.0;10.0\n"
        "01/01/2007;01:00:00;0.8;0.1;236.0;3.4;0.0;0.0;0.0\n"
    )

    with patch("functions.main.bigquery.Client") as mock_bq_client:
        mock_client_instance = MagicMock()
        mock_job = MagicMock()
        mock_job.result.return_value = None
        mock_client_instance.load_table_from_dataframe.return_value = mock_job
        mock_bq_client.return_value = mock_client_instance

        rows_loaded = process_and_load(raw_csv, source_name="test_upload.csv")

        # 2 distinct hours represented (00:00 and 01:00)
        assert rows_loaded == 2
        assert mock_client_instance.load_table_from_dataframe.called
