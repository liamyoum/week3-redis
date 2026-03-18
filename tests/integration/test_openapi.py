from fastapi.testclient import TestClient


def test_openapi_contains_seed_routes_and_models(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200

    schema = response.json()
    paths = schema["paths"]
    components = schema["components"]["schemas"]

    assert "/health" in paths
    assert "/kv/{key}" in paths
    assert "/kv/{key}/incr" in paths
    assert "/kv/{key}/decr" in paths
    assert "/namespaces/{namespace}/invalidate" in paths
    assert "/admin/snapshot" in paths

    assert "requestBody" in paths["/kv/{key}"]["put"]
    assert "requestBody" in paths["/kv/{key}/incr"]["post"]
    assert "requestBody" in paths["/kv/{key}/decr"]["post"]

    assert "PutValueRequest" in components
    assert "CounterRequest" in components
    assert "HealthResponse" in components
    assert "ValueResponse" in components
    assert "DeleteResponse" in components
    assert "CounterResponse" in components
    assert "InvalidateResponse" in components
    assert "SnapshotResponse" in components
