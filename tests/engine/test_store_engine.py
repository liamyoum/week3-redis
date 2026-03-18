from collections.abc import Iterable

import pytest

from app.domain.models import SnapshotEntry, SnapshotPayload, StoreRecord
from app.engine import CounterValueError, StoreEngine


class FakeClock:
    def __init__(self, current_ms: int = 0) -> None:
        self.current_ms = current_ms

    def now_ms(self) -> int:
        return self.current_ms

    def advance(self, delta_ms: int) -> None:
        self.current_ms += delta_ms


class FakeHashTable:
    def __init__(self) -> None:
        self._data: dict[str, StoreRecord] = {}
        self.delete_calls: list[str] = []

    def put(self, key: str, value: StoreRecord) -> None:
        self._data[key] = value

    def get(self, key: str) -> StoreRecord | None:
        return self._data.get(key)

    def delete(self, key: str) -> bool:
        self.delete_calls.append(key)
        return self._data.pop(key, None) is not None

    def items(self) -> Iterable[tuple[str, StoreRecord]]:
        return list(self._data.items())

    def __len__(self) -> int:
        return len(self._data)


def make_engine(start_ms: int = 0) -> tuple[StoreEngine, FakeHashTable, FakeClock]:
    clock = FakeClock(start_ms)
    table = FakeHashTable()
    engine = StoreEngine(table=table, now_ms=clock.now_ms)
    return engine, table, clock


def test_set_get_overwrite_and_namespace_isolation() -> None:
    engine, table, clock = make_engine(start_ms=1_000)

    first = engine.set("alpha", "1")
    assert first == StoreRecord(
        key="alpha",
        value_str="1",
        namespace="default",
        namespace_version=0,
        expires_at_ms=None,
        created_at_ms=1_000,
        updated_at_ms=1_000,
    )

    clock.advance(50)
    overwritten = engine.set("alpha", "2")
    clock.advance(10)
    namespaced = engine.set("alpha", "team-value", namespace="team")

    assert overwritten.created_at_ms == 1_000
    assert overwritten.updated_at_ms == 1_050
    assert namespaced.namespace == "team"
    assert namespaced.created_at_ms == 1_060
    assert engine.get("alpha") == overwritten
    assert engine.get("alpha", namespace="team") == namespaced
    assert len(table) == 2


def test_delete_returns_expected_results_and_lazily_cleans_non_live_records() -> None:
    engine, table, clock = make_engine()

    engine.set("live", "value")
    assert engine.delete("live") is True
    assert engine.delete("missing") is False

    engine.set("ttl", "value", ttl_ms=5)
    clock.advance(5)
    assert engine.delete("ttl") is False
    assert len(table) == 0

    engine.set("stale", "value", namespace="team")
    assert engine.invalidate_namespace("team") == 1
    assert engine.delete("stale", namespace="team") is False
    assert len(table) == 0


def test_cleanup_expired_respects_limit_and_leaves_stale_records_until_accessed() -> None:
    engine, table, clock = make_engine()

    engine.set("first", "1", ttl_ms=5)
    engine.set("second", "2", ttl_ms=5)
    engine.set("stale", "3", namespace="team")
    engine.invalidate_namespace("team")

    clock.advance(5)

    assert engine.cleanup_expired(limit=1) == 1
    assert len(table) == 2

    assert engine.cleanup_expired() == 1
    assert len(table) == 1

    assert engine.get("stale", namespace="team") is None
    assert len(table) == 0


def test_invalidate_namespace_bumps_version_without_scanning_existing_keys() -> None:
    engine, table, _ = make_engine()

    engine.set("alpha", "value", namespace="team")

    assert engine.invalidate_namespace("team") == 1
    assert table.delete_calls == []
    assert engine.get("alpha", namespace="team") is None

    refreshed = engine.set("alpha", "new", namespace="team")
    assert refreshed.namespace_version == 1
    assert engine.invalidate_namespace("team") == 2


def test_incr_and_decr_create_missing_keys_and_preserve_live_ttl_metadata() -> None:
    engine, _, clock = make_engine(start_ms=100)

    assert engine.incr("missing") == 1
    assert engine.decr("other-missing") == -1

    original = engine.set("counter", "10", ttl_ms=50)
    clock.advance(10)
    next_value = engine.decr("counter", amount=3)
    updated = engine.get("counter")

    assert next_value == 7
    assert updated is not None
    assert updated.value_str == "7"
    assert updated.expires_at_ms == original.expires_at_ms
    assert updated.created_at_ms == original.created_at_ms
    assert updated.updated_at_ms == 110


def test_counter_operations_recreate_expired_and_stale_records() -> None:
    engine, _, clock = make_engine(start_ms=10)

    expired = engine.set("expired", "2", ttl_ms=5)
    clock.advance(5)
    assert engine.incr("expired", amount=3) == 3
    recreated_expired = engine.get("expired")
    assert recreated_expired is not None
    assert recreated_expired.value_str == "3"
    assert recreated_expired.expires_at_ms is None
    assert recreated_expired.created_at_ms != expired.created_at_ms

    stale = engine.set("stale", "4", namespace="team")
    assert engine.invalidate_namespace("team") == 1
    clock.advance(1)
    assert engine.incr("stale", amount=2, namespace="team") == 2
    recreated_stale = engine.get("stale", namespace="team")
    assert recreated_stale is not None
    assert recreated_stale.value_str == "2"
    assert recreated_stale.namespace_version == 1
    assert recreated_stale.created_at_ms != stale.created_at_ms


def test_counter_operations_raise_for_non_numeric_live_values() -> None:
    engine, _, _ = make_engine()

    engine.set("name", "alice")

    with pytest.raises(CounterValueError):
        engine.incr("name")

    record = engine.get("name")
    assert record is not None
    assert record.value_str == "alice"


def test_export_snapshot_skips_expired_and_stale_entries() -> None:
    engine, _, clock = make_engine(start_ms=1_000)

    live = engine.set("live", "value")
    engine.set("expired", "gone", ttl_ms=10)
    engine.set("stale", "old", namespace="team")
    assert engine.invalidate_namespace("team") == 1
    fresh = engine.set("fresh", "new", namespace="team")

    clock.advance(10)
    snapshot = engine.export_snapshot()

    assert snapshot.saved_at_ms == 1_010
    assert snapshot.version == 1
    assert snapshot.namespace_versions == {"team": 1}
    assert snapshot.entries == [
        SnapshotEntry(
            key=live.key,
            value_str=live.value_str,
            namespace=live.namespace,
            namespace_version=live.namespace_version,
            expires_at_ms=live.expires_at_ms,
            created_at_ms=live.created_at_ms,
            updated_at_ms=live.updated_at_ms,
        ),
        SnapshotEntry(
            key=fresh.key,
            value_str=fresh.value_str,
            namespace=fresh.namespace,
            namespace_version=fresh.namespace_version,
            expires_at_ms=fresh.expires_at_ms,
            created_at_ms=fresh.created_at_ms,
            updated_at_ms=fresh.updated_at_ms,
        ),
    ]


def test_import_snapshot_replaces_existing_state_and_restores_namespace_versions() -> None:
    source_engine, _, source_clock = make_engine(start_ms=50)
    source_engine.set("keep", "value")
    source_engine.set("old", "legacy", namespace="team")
    assert source_engine.invalidate_namespace("team") == 1
    source_engine.set("fresh", "current", namespace="team")
    source_engine.set("expired", "skip", ttl_ms=5)
    source_clock.advance(5)
    snapshot = source_engine.export_snapshot()

    target_engine, target_table, _ = make_engine()
    target_engine.set("trash", "value")

    target_engine.import_snapshot(snapshot)

    assert target_engine.get("trash") is None
    assert len(target_table) == 2

    keep = target_engine.get("keep")
    fresh = target_engine.get("fresh", namespace="team")

    assert keep is not None
    assert keep.value_str == "value"
    assert target_engine.get("old", namespace="team") is None
    assert fresh is not None
    assert fresh.value_str == "current"
    assert fresh.namespace_version == 1
    assert target_engine.invalidate_namespace("team") == 2


def test_import_snapshot_clears_previous_state_with_manual_payload() -> None:
    engine, table, _ = make_engine()
    engine.set("existing", "value")

    payload = SnapshotPayload(
        version=1,
        saved_at_ms=123,
        namespace_versions={"custom": 2},
        entries=[
            SnapshotEntry(
                key="imported",
                value_str="42",
                namespace="custom",
                namespace_version=2,
                expires_at_ms=None,
                created_at_ms=100,
                updated_at_ms=120,
            )
        ],
    )

    engine.import_snapshot(payload)

    assert len(table) == 1
    assert engine.get("existing") is None
    imported = engine.get("imported", namespace="custom")
    assert imported is not None
    assert imported.value_str == "42"
    assert imported.namespace_version == 2


def test_store_engine_emits_aof_style_mutation_events() -> None:
    events: list[dict[str, object]] = []
    clock = FakeClock(100)
    table = FakeHashTable()
    engine = StoreEngine(
        table=table,
        now_ms=clock.now_ms,
        mutation_logger=events.append,
    )

    engine.set("alpha", "1")
    clock.advance(1)
    engine.incr("alpha", amount=2)
    clock.advance(1)
    assert engine.delete("alpha") is True
    clock.advance(1)
    assert engine.invalidate_namespace("team") == 1

    assert [event["op"] for event in events] == [
        "upsert",
        "upsert",
        "delete",
        "invalidate",
    ]
    assert [event["seq"] for event in events] == [1, 2, 3, 4]
    record = events[1]["record"]
    assert isinstance(record, dict)
    assert record["value_str"] == "3"
    assert events[2]["key"] == "alpha"
    assert events[3]["version"] == 1
