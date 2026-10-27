"""
Unit tests for raw schema validation and input handling.
"""

import pytest
import pandas as pd
from src.ingestion import DatasetIngestion
from config.settings import AppConfig


def test_schema_validation_success():
    """Verify schema passes when all expected columns are present."""
    data = {col: ["1.0"] for col in AppConfig.EXPECTED_RAW_COLUMNS}
    df = pd.DataFrame(data)
    assert DatasetIngestion.validate_schema(df) is True


def test_schema_validation_failure_missing_column():
    """Verify ValueError is raised if any expected column is absent."""
    data = {col: ["1.0"] for col in AppConfig.EXPECTED_RAW_COLUMNS[:-1]}
    df = pd.DataFrame(data)
    with pytest.raises(ValueError, match="Missing expected columns"):
        DatasetIngestion.validate_schema(df)


def test_invalid_upload_handling():
    """Verify handling of completely invalid or empty dataframes."""
    empty_df = pd.DataFrame()
    with pytest.raises(ValueError):
        DatasetIngestion.validate_schema(empty_df)
