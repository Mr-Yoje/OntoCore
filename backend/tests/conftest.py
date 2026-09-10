import pytest


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ONTOCORE_DATA_DIR", str(tmp_path / "ontocore-data"))
