import pytest

from nfl.config import get_paths

DATA = get_paths()

requires_data = pytest.mark.skipif(
    not (DATA.marts / "predictions.parquet").exists(), reason="needs local data (run nfl run-all)"
)
