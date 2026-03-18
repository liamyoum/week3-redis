from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("MINI_REDIS_SNAPSHOT_PATH", str(tmp_path / "snapshot.json"))
    monkeypatch.setenv("MINI_REDIS_AOF_PATH", str(tmp_path / "appendonly.aof.jsonl"))
    monkeypatch.setenv("MINI_REDIS_MONGO_URI", "")
    get_settings.cache_clear()
    return TestClient(create_app())
