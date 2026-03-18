import time

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
    assert direct_payload["latency_ms"] >= 0

    assert first_cached_payload["source"] == "cache"
    assert first_cached_payload["cache_status"] == "miss"
    assert first_cached_payload["latency_ms"] >= 0

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


def test_storefront_direct_reads_origin_stock_after_purchase_and_restock(
    client: TestClient,
) -> None:
    initial = client.get("/store/products/sunset-lamp/direct").json()

    purchase = client.post("/store/products/sunset-lamp/purchase", json={"quantity": 2})
    after_purchase = client.get("/store/products/sunset-lamp/direct").json()

    restock = client.post("/store/products/sunset-lamp/restock", json={"quantity": 3})
    after_restock = client.get("/store/products/sunset-lamp/direct").json()

    assert purchase.status_code == 200
    assert restock.status_code == 200
    assert after_purchase["product"]["stock"] == initial["product"]["stock"] - 2
    assert after_restock["product"]["stock"] == initial["product"]["stock"] + 1


def test_storefront_direct_and_cached_share_same_stock_source(client: TestClient) -> None:
    client.get("/store/products/sunset-lamp/cached")
    client.post("/store/products/sunset-lamp/purchase", json={"quantity": 2})

    direct = client.get("/store/products/sunset-lamp/direct")
    cached = client.get("/store/products/sunset-lamp/cached")

    assert direct.status_code == 200
    assert cached.status_code == 200
    assert direct.json()["product"]["stock"] == cached.json()["product"]["stock"]


def test_storefront_reserve_creates_ttl_hold_token(client: TestClient) -> None:
    response = client.post(
        "/store/products/cream-speaker/reserve",
        json={"session_id": "demo-session", "ttl_ms": 2000},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["product_id"] == "cream-speaker"
    assert payload["session_id"] == "demo-session"
    assert payload["hold_key"] == "storefront-product:cream-speaker:detail"
    assert payload["expires_at_ms"] > 0


def test_storefront_restock_increases_inventory(client: TestClient) -> None:
    before = client.get("/store/products/cream-speaker/cached").json()
    restock = client.post("/store/products/cream-speaker/restock", json={"quantity": 2})
    after = client.get("/store/products/cream-speaker/cached").json()

    assert restock.status_code == 200
    assert restock.json()["stock"] == before["product"]["stock"] + 2
    assert after["product"]["stock"] == before["product"]["stock"] + 2


def test_storefront_cache_ttl_expires_selected_product_cache(client: TestClient) -> None:
    first_cached = client.get("/store/products/cream-speaker/cached")
    ttl_response = client.post(
        "/store/products/cream-speaker/reserve",
        json={"session_id": "demo-session", "ttl_ms": 50},
    )
    second_cached = client.get("/store/products/cream-speaker/cached")
    time.sleep(0.06)
    third_cached = client.get("/store/products/cream-speaker/cached")

    assert first_cached.status_code == 200
    assert ttl_response.status_code == 200
    assert second_cached.json()["cache_status"] == "hit"
    assert third_cached.json()["cache_status"] == "miss"


def test_storefront_state_exposes_snapshot_and_post_snapshot_aof_events(client: TestClient) -> None:
    client.get("/store/products/sunset-lamp/cached")
    snapshot = client.post("/admin/snapshot")
    purchase = client.post("/store/products/sunset-lamp/purchase", json={"quantity": 1})
    invalidate = client.post("/store/products/sunset-lamp/invalidate")
    state = client.get("/store/state")

    assert snapshot.status_code == 200
    assert purchase.status_code == 200
    assert invalidate.status_code == 200
    assert state.status_code == 200

    payload = state.json()
    assert payload["snapshot_payload"] is not None
    assert payload["snapshot_payload"]["entries"]
    assert len(payload["aof_events"]) >= 2
    assert {event["op"] for event in payload["aof_events"]} >= {"upsert", "invalidate"}
