from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.domain.models import SnapshotEntry, SnapshotPayload, StoreRecord
from app.main import create_app
from app.persistence.aof import AofCorruptionError, AofRepository, AofService
from app.persistence.repository import SnapshotRepository
from app.persistence.service import SnapshotService


class FakeStore:
    def __init__(self, snapshot: SnapshotPayload | None = None, marker: int = 0) -> None:
        self.snapshot = snapshot or SnapshotPayload()
        self.imported_snapshot: SnapshotPayload | None = None
        self.marker = marker

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

    def export_snapshot_with_marker(self) -> tuple[SnapshotPayload, int]:
        return self.snapshot, self.marker

    def import_snapshot(self, snapshot: SnapshotPayload) -> None:
        self.imported_snapshot = snapshot
        self.snapshot = snapshot

    def cleanup_expired(self, limit: int | None = None) -> int:
        _ = limit
        raise NotImplementedError

    def restore_mutation_seq(self, seq: int) -> None:
        self.marker = max(self.marker, seq)


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


def test_snapshot_service_can_reset_aof_after_snapshot_save(tmp_path: Path) -> None:
    repository = SnapshotRepository(tmp_path / "snapshot.json")
    aof_repository = AofRepository(tmp_path / "appendonly.aof.jsonl")
    aof_service = AofService(aof_repository)
    service = SnapshotService(repository, after_save=aof_service.rewrite_after)
    source_store = FakeStore(make_snapshot(), marker=2)

    aof_service.append_event(
        {
            "seq": 1,
            "op": "delete",
            "ts_ms": 1_710_000_000_200,
            "key": "demo:1",
            "namespace": "default",
        }
    )
    aof_service.append_event(
        {
            "seq": 3,
            "op": "upsert",
            "ts_ms": 1_710_000_000_300,
            "record": {
                "key": "demo:2",
                "value_str": "latest",
                "namespace": "default",
                "namespace_version": 2,
                "expires_at_ms": None,
                "created_at_ms": 1_710_000_000_200,
                "updated_at_ms": 1_710_000_000_300,
            },
        }
    )

    service.save_from(source_store)

    assert repository.exists() is True
    events = aof_repository.load_all()
    assert len(events) == 1
    assert events[0]["record"]["key"] == "demo:2"


def test_aof_service_replays_mutations_over_base_snapshot(tmp_path: Path) -> None:
    aof_service = AofService(AofRepository(tmp_path / "appendonly.aof.jsonl"))
    store = FakeStore(make_snapshot())

    aof_service.append_event(
        {
            "seq": 1,
            "op": "upsert",
            "ts_ms": 1_710_000_000_200,
            "record": {
                "key": "counter",
                "value_str": "3",
                "namespace": "default",
                "namespace_version": 2,
                "expires_at_ms": None,
                "created_at_ms": 1_710_000_000_150,
                "updated_at_ms": 1_710_000_000_200,
            },
        }
    )
    aof_service.append_event(
        {
            "seq": 2,
            "op": "invalidate",
            "ts_ms": 1_710_000_000_300,
            "namespace": "default",
            "version": 3,
        }
    )
    aof_service.append_event(
        {
            "seq": 3,
            "op": "delete",
            "ts_ms": 1_710_000_000_400,
            "key": "demo:1",
            "namespace": "default",
        }
    )

    replayed_snapshot = aof_service.replay_into(store)

    assert replayed_snapshot is not None
    assert replayed_snapshot.saved_at_ms == 1_710_000_000_400
    assert replayed_snapshot.namespace_versions == {"default": 3}
    assert replayed_snapshot.entries == [
        SnapshotEntry(
            key="counter",
            value_str="3",
            namespace="default",
            namespace_version=2,
            expires_at_ms=None,
            created_at_ms=1_710_000_000_150,
            updated_at_ms=1_710_000_000_200,
        )
    ]
    assert store.snapshot == replayed_snapshot


def test_aof_repository_truncates_corrupted_tail_in_truncate_mode(tmp_path: Path) -> None:
    repository = AofRepository(
        tmp_path / "appendonly.aof.jsonl",
        recovery_mode="truncate",
    )
    repository.append({"seq": 1, "op": "delete", "ts_ms": 1, "key": "a", "namespace": "default"})
    repository.path.write_bytes(repository.path.read_bytes() + b'{"seq":2,"op":"upsert"')

    events = repository.load_all()

    assert len(events) == 1
    assert events[0]["seq"] == 1


def test_aof_repository_raises_for_corrupted_tail_in_strict_mode(tmp_path: Path) -> None:
    repository = AofRepository(
        tmp_path / "appendonly.aof.jsonl",
        recovery_mode="strict",
    )
    repository.append({"seq": 1, "op": "delete", "ts_ms": 1, "key": "a", "namespace": "default"})
    repository.path.write_bytes(repository.path.read_bytes() + b'{"seq":2,"op":"upsert"')

    with pytest.raises(AofCorruptionError):
        repository.load_all()


def test_aof_repository_respects_fsync_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fsync_calls: list[int] = []
    times = iter([1.0, 1.2, 2.5])

    def fake_fsync(fd: int) -> None:
        fsync_calls.append(fd)

    monkeypatch.setattr("app.persistence.aof.os.fsync", fake_fsync)

    repository = AofRepository(
        tmp_path / "appendonly.aof.jsonl",
        fsync_mode="everysec",
        now_monotonic=lambda: next(times),
    )

    repository.append({"seq": 1, "op": "delete", "ts_ms": 1, "key": "a", "namespace": "default"})
    repository.append({"seq": 2, "op": "delete", "ts_ms": 2, "key": "b", "namespace": "default"})
    repository.append({"seq": 3, "op": "delete", "ts_ms": 3, "key": "c", "namespace": "default"})

    assert len(fsync_calls) == 2


def test_aof_service_rewrite_after_keeps_only_post_snapshot_events(tmp_path: Path) -> None:
    repository = AofRepository(tmp_path / "appendonly.aof.jsonl")
    service = AofService(repository)
    repository.append({"seq": 1, "op": "delete", "ts_ms": 1, "key": "a", "namespace": "default"})
    repository.append({"seq": 2, "op": "delete", "ts_ms": 2, "key": "b", "namespace": "default"})
    repository.append({"seq": 3, "op": "delete", "ts_ms": 3, "key": "c", "namespace": "default"})

    service.rewrite_after(2)

    events = repository.load_all()
    assert len(events) == 1
    assert events[0]["key"] == "c"


def test_aof_replay_restores_marker_for_future_snapshot_rewrite(tmp_path: Path) -> None:
    snapshot_repository = SnapshotRepository(tmp_path / "snapshot.json")
    aof_repository = AofRepository(tmp_path / "appendonly.aof.jsonl")
    aof_service = AofService(aof_repository)
    snapshot_service = SnapshotService(snapshot_repository, after_save=aof_service.rewrite_after)
    store = FakeStore(make_snapshot())

    aof_service.append_event(
        {
            "seq": 4,
            "op": "upsert",
            "ts_ms": 1_710_000_000_500,
            "record": {
                "key": "demo:2",
                "value_str": "fresh",
                "namespace": "default",
                "namespace_version": 2,
                "expires_at_ms": None,
                "created_at_ms": 1_710_000_000_400,
                "updated_at_ms": 1_710_000_000_500,
            },
        }
    )

    replayed = aof_service.replay_into(store)
    assert replayed is not None

    snapshot_service.save_from(store)

    assert aof_repository.load_all() == []


def test_app_lifespan_restores_on_startup_and_saves_on_shutdown(tmp_path: Path) -> None:
    snapshot_path = tmp_path / "snapshot.json"
    aof_path = tmp_path / "appendonly.aof.jsonl"
    snapshot = make_snapshot()
    SnapshotRepository(snapshot_path).save(snapshot)
    AofRepository(aof_path).append(
        {
            "seq": 1,
            "op": "upsert",
            "ts_ms": 1_710_000_000_300,
            "record": {
                "key": "restored",
                "value_str": "live",
                "namespace": "default",
                "namespace_version": 2,
                "expires_at_ms": None,
                "created_at_ms": 1_710_000_000_250,
                "updated_at_ms": 1_710_000_000_300,
            },
        }
    )

    app = create_app()
    app.state.aof_service = AofService(AofRepository(aof_path))
    app.state.snapshot_service = SnapshotService(
        SnapshotRepository(snapshot_path),
        after_save=app.state.aof_service.rewrite_after,
    )
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
        ),
        marker=1,
    )

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert app.state.store.imported_snapshot is not None
        assert app.state.store.imported_snapshot.namespace_versions == {"default": 2}
        assert any(entry.key == "demo:1" for entry in app.state.store.imported_snapshot.entries)
        assert any(entry.key == "restored" for entry in app.state.store.imported_snapshot.entries)
        assert any(entry.key == "restored" for entry in app.state.store.snapshot.entries)

    reloaded = SnapshotRepository(snapshot_path).load()
    assert reloaded == app.state.store.snapshot
    assert AofRepository(aof_path).load_all() == []
