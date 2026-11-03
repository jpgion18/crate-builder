import pytest

from crate_builder import local_config
from seratobox_fixtures import library  # noqa: F401  (Rekordbox export tests' fake Serato library)


@pytest.fixture(autouse=True)
def isolated_local_config(tmp_path, monkeypatch):
    """Every test gets its own local_config file, never the real ~/.crate_builder/."""
    monkeypatch.setattr(local_config, "_CONFIG_PATH", str(tmp_path / "config.json"))
