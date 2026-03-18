from pathlib import Path

from fastapi.testclient import TestClient

from app.domain.models import SnapshotEntry, SnapshotPayload, StoreRecord
from app.main import create_app
from app.persistence.repository import SnapshotRepository
from app.persistence.service import SnapshotService


class FakeStore:
    def __init__(self, snapshot: SnapshotPayload | None = None) -> None:
        self.snapshot = snapshot or SnapshotPayload()
        self.imported_snapshot: SnapshotPayload | None = None

    def set(
        self,
        key: str,
        value_str: str,
        ttl_ms: int | None = None,
        namespace: str = "default",
    ) -> StoreRecord:
        return StoreRecord(
            key=key,
            value_str=value_str,
            namespace=namespace,
            expires_at_ms=ttl_ms,
        )

    def get(self, key: str, namespace: str = "default") -> None:
        _ = key, namespace
        raise NotImplementedError

    def delete(self, key: str, namespace: str = "default") -> bool:
        _ = key, namespace
        raise NotImplementedError

    def incr(self, key: str, amount: int = 1, namespace: str = "default") -> int:
        _ = key, amount, namespace
        raise NotImplementedError

    def decr(self, key: str, amount: int = 1, namespace: str = "default") -> int:
        _ = key, amount, namespace
        raise NotImplementedError

    def invalidate_namespace(self, namespace: str) -> int:
        _ = namespace
        raise NotImplementedError

    def export_snapshot(self) -> SnapshotPayload:
        return self.snapshot

    def import_snapshot(self, snapshot: SnapshotPayload) -> None:
        self.imported_snapshot = snapshot
        self.snapshot = snapshot

    def cleanup_expired(self, limit: int | None = None) -> int:
        _ = limit
        raise NotImplementedError


def make_snapshot() -> SnapshotPayload:
    return SnapshotPayload(
        version=1,
        saved_at_ms=1_710_000_000_000,
        namespace_versions={"default": 2},
        entries=[
            SnapshotEntry(
                key="demo:1",
                value_str='{"id":1,"name":"cached"}',
                namespace="default",
                namespace_version=2,
                expires_at_ms=None,
                created_at_ms=1_710_000_000_000,
                updated_at_ms=1_710_000_000_100,
            )
        ],
    )


def test_snapshot_repository_round_trip(tmp_path: Path) -> None:
    repository = SnapshotRepository(tmp_path / "data" / "snapshot.json")
    snapshot = make_snapshot()

    repository.save(snapshot)

    loaded = repository.load()
    assert loaded == snapshot


def test_snapshot_service_loads_and_saves_store(tmp_path: Path) -> None:
    repository = SnapshotRepository(tmp_path / "snapshot.json")
    service = SnapshotService(repository)
    original_snapshot = make_snapshot()
    source_store = FakeStore(original_snapshot)

    saved_snapshot = service.save_from(source_store)
    target_store = FakeStore()
    loaded_snapshot = service.load_into(target_store)

    assert saved_snapshot == original_snapshot
    assert loaded_snapshot == original_snapshot
    assert target_store.imported_snapshot == original_snapshot


def test_app_lifespan_restores_on_startup_and_saves_on_shutdown(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "snapshot.json"
    snapshot = make_snapshot()
    SnapshotRepository(snapshot_path).save(snapshot)

    app = create_app()
    app.state.snapshot_service = SnapshotService(SnapshotRepository(snapshot_path))
    app.state.store = FakeStore(
        SnapshotPayload(
            version=1,
            saved_at_ms=1_710_000_001_000,
            namespace_versions={"default": 3},
            entries=[
                SnapshotEntry(
                    key="demo:2",
                    value_str="replacement",
                    namespace="default",
                    namespace_version=3,
                    created_at_ms=1_710_000_001_000,
                    updated_at_ms=1_710_000_001_100,
                )
            ],
        )
    )

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert app.state.store.imported_snapshot == snapshot

    reloaded = SnapshotRepository(snapshot_path).load()
    assert reloaded == app.state.store.snapshot
