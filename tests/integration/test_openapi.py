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
    assert "/store/products" in paths
    assert "/store/products/{product_id}/direct" in paths
    assert "/store/products/{product_id}/cached" in paths
    assert "/store/products/{product_id}/reserve" in paths
    assert "/store/products/{product_id}/purchase" in paths
    assert "/store/products/{product_id}/restock" in paths
    assert "/store/products/{product_id}/invalidate" in paths
    assert "/store/state" in paths

    assert "requestBody" in paths["/kv/{key}"]["put"]
    assert "requestBody" in paths["/kv/{key}/incr"]["post"]
    assert "requestBody" in paths["/kv/{key}/decr"]["post"]
    assert "requestBody" in paths["/store/products/{product_id}/reserve"]["post"]
    assert "requestBody" in paths["/store/products/{product_id}/purchase"]["post"]
    assert "requestBody" in paths["/store/products/{product_id}/restock"]["post"]

    assert "PutValueRequest" in components
    assert "CounterRequest" in components
    assert "HealthResponse" in components
    assert "ValueResponse" in components
    assert "DeleteResponse" in components
    assert "CounterResponse" in components
    assert "InvalidateResponse" in components
    assert "SnapshotResponse" in components
    assert "ProductCardResponse" in components
    assert "ProductListResponse" in components
    assert "ProductDetailResponse" in components
    assert "ReserveRequest" in components
    assert "ReserveResponse" in components
    assert "PurchaseRequest" in components
    assert "PurchaseResponse" in components
    assert "StoreStateResponse" in components
