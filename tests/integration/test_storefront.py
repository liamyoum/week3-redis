from fastapi.testclient import TestClient


def test_storefront_lists_seed_products(client: TestClient) -> None:
    response = client.get("/store/products")

    assert response.status_code == 200
    payload = response.json()
    assert payload["origin_source"] in {"seed", "seed-fallback"}
    assert len(payload["products"]) == 3
    assert payload["products"][0]["cache_namespace"].startswith("storefront-product:")
    assert payload["products"][0]["image_url"].startswith("https://")


def test_storefront_direct_and_cached_paths_show_latency_and_hit_status(client: TestClient) -> None:
    direct = client.get("/store/products/sunset-lamp/direct")
    first_cached = client.get("/store/products/sunset-lamp/cached")
    second_cached = client.get("/store/products/sunset-lamp/cached")

    assert direct.status_code == 200
    assert first_cached.status_code == 200
    assert second_cached.status_code == 200

    direct_payload = direct.json()
    first_cached_payload = first_cached.json()
    second_cached_payload = second_cached.json()

    assert direct_payload["source"] == "direct"
    assert direct_payload["cache_status"] == "bypass"
    assert direct_payload["latency_ms"] >= 100

    assert first_cached_payload["source"] == "cache"
    assert first_cached_payload["cache_status"] == "miss"
    assert first_cached_payload["latency_ms"] >= 100

    assert second_cached_payload["cache_status"] == "hit"
    assert second_cached_payload["latency_ms"] >= 0
    assert second_cached_payload["latency_ms"] < first_cached_payload["latency_ms"]


def test_storefront_purchase_invalidate_and_snapshot_flow(client: TestClient) -> None:
    initial = client.get("/store/products/sunset-lamp/cached").json()
    purchase = client.post("/store/products/sunset-lamp/purchase", json={"quantity": 2})
    invalidation = client.post("/store/products/sunset-lamp/invalidate")
    recached = client.get("/store/products/sunset-lamp/cached")
    snapshot = client.post("/admin/snapshot")
    state = client.get("/store/state")

    assert purchase.status_code == 200
    assert purchase.json()["stock"] == initial["product"]["stock"] - 2

    assert invalidation.status_code == 200
    assert invalidation.json()["namespace"] == "storefront-product:sunset-lamp"
    assert invalidation.json()["version"] == 1

    assert recached.status_code == 200
    assert recached.json()["cache_status"] == "miss"
    assert recached.json()["product"]["stock"] == initial["product"]["stock"] - 2

    assert snapshot.status_code == 200
    assert state.status_code == 200
    state_payload = state.json()
    assert state_payload["snapshot_exists"] is True
    assert state_payload["snapshot_size_bytes"] > 0


def test_storefront_reserve_creates_ttl_hold_token(client: TestClient) -> None:
    response = client.post(
        "/store/products/cream-speaker/reserve",
        json={"session_id": "demo-session", "ttl_ms": 2000},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["product_id"] == "cream-speaker"
    assert payload["session_id"] == "demo-session"
    assert payload["hold_key"] == "hold:demo-session:cream-speaker"
    assert payload["expires_at_ms"] > 0
