from fastapi.testclient import TestClient


def test_crash_endpoint_schedules_process_exit_without_killing_test_server(client: TestClient) -> None:
    scheduled: list[tuple[str, int]] = []

    def fake_scheduler(reason: str, delay_ms: int) -> None:
        scheduled.append((reason, delay_ms))

    client.app.state.crash_scheduler = fake_scheduler

    response = client.post("/admin/crash")

    assert response.status_code == 200
    assert response.json()["status"] == "scheduled"
    assert response.json()["delay_ms"] == 700
    assert scheduled == [("manual-demo", 700)]


def test_restart_endpoint_schedules_process_exit_without_killing_test_server(client: TestClient) -> None:
    scheduled: list[tuple[str, int]] = []

    def fake_scheduler(reason: str, delay_ms: int) -> None:
        scheduled.append((reason, delay_ms))

    client.app.state.crash_scheduler = fake_scheduler

    response = client.post("/admin/restart")

    assert response.status_code == 200
    assert response.json()["status"] == "scheduled"
    assert response.json()["delay_ms"] == 700
    assert scheduled == [("restart-demo", 700)]
