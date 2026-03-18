from typing import Any

from fastapi.testclient import TestClient


def test_kv_and_admin_routes_exist_as_stubs(client: TestClient) -> None:
    cases: list[tuple[str, str, dict[str, Any] | None, dict[str, str] | None]] = [
        ("put", "/kv/example", {"value": "hello", "ttl_ms": 1000, "namespace": "default"}, None),
        ("get", "/kv/example", None, {"namespace": "default"}),
        ("delete", "/kv/example", None, {"namespace": "default"}),
        ("post", "/kv/example/incr", {"amount": 1, "namespace": "default"}, None),
        ("post", "/kv/example/decr", {"amount": 1, "namespace": "default"}, None),
        ("post", "/namespaces/default/invalidate", None, None),
        ("post", "/admin/snapshot", None, None),
    ]

    for method, path, body, params in cases:
        request_kwargs: dict[str, object] = {}
        if body is not None:
            request_kwargs["json"] = body
        if params is not None:
            request_kwargs["params"] = params

        response = getattr(client, method)(path, **request_kwargs)
        assert response.status_code == 501
        assert response.json() == {"detail": "Not implemented"}
