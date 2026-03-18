from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_persistence_demo_write_is_visible_and_recorded_in_aof(
    client: TestClient,
    tmp_path: Path,
) -> None:
    initial = client.get("/admin/persistence-demo")
    written = client.post("/admin/persistence-demo/write")
    reloaded = client.get("/admin/persistence-demo")

    assert initial.status_code == 200
    assert initial.json()["exists"] is False
    assert initial.json()["crash_enabled"] is True

    assert written.status_code == 200
    payload = written.json()
    assert payload["exists"] is True
    assert payload["namespace"] == "demo-persistence"
    assert payload["key"] == "latest-write"
    assert payload["value"].startswith("survives-crash-")
    assert payload["updated_at_ms"] is not None

    assert reloaded.status_code == 200
    assert reloaded.json() == payload

    aof_contents = (tmp_path / "appendonly.aof.jsonl").read_text(encoding="utf-8")
    assert payload["value"] in aof_contents


def test_persistence_demo_crash_endpoint_schedules_hard_exit(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduled_delays: list[int] = []

    monkeypatch.setattr(
        "app.api.admin._schedule_demo_crash",
        lambda delay_ms: scheduled_delays.append(delay_ms),
    )

    response = client.post("/admin/persistence-demo/crash")

    assert response.status_code == 202
    assert response.json()["scheduled"] is True
    assert response.json()["delay_ms"] == 350
    assert scheduled_delays == [350]
