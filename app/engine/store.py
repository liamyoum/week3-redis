import threading
import time
from collections.abc import Callable
from typing import Any, Literal

from app.domain.contracts import HashTableProtocol
from app.domain.models import SnapshotEntry, SnapshotPayload, StoreRecord

RecordState = Literal["missing", "expired", "stale", "live"]


class CounterValueError(ValueError):
    """Raised when counter operations are applied to a non-integer value."""


class StoreEngine:
    def __init__(
        self,
        table: HashTableProtocol[StoreRecord],
        now_ms: Callable[[], int] | None = None,
        mutation_logger: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._table = table
        self._now_ms = now_ms or self._default_now_ms
        self._namespace_versions: dict[str, int] = {}
        self._lock = threading.RLock()
        self._mutation_logger = mutation_logger

    def set(
        self,
        key: str,
        value_str: str,
        ttl_ms: int | None = None,
        namespace: str = "default",
    ) -> StoreRecord:
        with self._lock:
            now_ms = self._now_ms()
            storage_key = self._storage_key(namespace, key)
            current_version = self._current_namespace_version(namespace)
            existing, state = self._read_record(storage_key, namespace, now_ms)
            created_at_ms = (
                existing.created_at_ms
                if state == "live" and existing is not None
                else now_ms
            )
            record = StoreRecord(
                key=key,
                value_str=value_str,
                namespace=namespace,
                namespace_version=current_version,
                expires_at_ms=None if ttl_ms is None else now_ms + ttl_ms,
                created_at_ms=created_at_ms,
                updated_at_ms=now_ms,
            )
            self._table.put(storage_key, record)
            self._emit_upsert(record)
            return record

    def get(self, key: str, namespace: str = "default") -> StoreRecord | None:
        with self._lock:
            now_ms = self._now_ms()
            storage_key = self._storage_key(namespace, key)
            record, state = self._read_record(storage_key, namespace, now_ms)
            if state != "live":
                return None
            return record

    def delete(self, key: str, namespace: str = "default") -> bool:
        with self._lock:
            now_ms = self._now_ms()
            storage_key = self._storage_key(namespace, key)
            _, state = self._read_record(storage_key, namespace, now_ms)
            if state != "live":
                return False
            deleted = self._table.delete(storage_key)
            if deleted:
                self._emit_delete(key=key, namespace=namespace, ts_ms=now_ms)
            return deleted

    def incr(self, key: str, amount: int = 1, namespace: str = "default") -> int:
        return self._apply_delta(key=key, amount=amount, namespace=namespace)

    def decr(self, key: str, amount: int = 1, namespace: str = "default") -> int:
        return self._apply_delta(key=key, amount=-amount, namespace=namespace)

    def invalidate_namespace(self, namespace: str) -> int:
        with self._lock:
            next_version = self._current_namespace_version(namespace) + 1
            self._namespace_versions[namespace] = next_version
            self._emit_invalidate(namespace=namespace, version=next_version, ts_ms=self._now_ms())
            return next_version

    def export_snapshot(self) -> SnapshotPayload:
        with self._lock:
            saved_at_ms = self._now_ms()
            entries: list[SnapshotEntry] = []
            for _, record in self._table.items():
                if self._is_expired(record, saved_at_ms):
                    continue
                if self._is_stale(record):
                    continue
                entries.append(
                    SnapshotEntry(
                        key=record.key,
                        value_str=record.value_str,
                        namespace=record.namespace,
                        namespace_version=record.namespace_version,
                        expires_at_ms=record.expires_at_ms,
                        created_at_ms=record.created_at_ms,
                        updated_at_ms=record.updated_at_ms,
                    )
                )
            return SnapshotPayload(
                version=1,
                saved_at_ms=saved_at_ms,
                namespace_versions=dict(self._namespace_versions),
                entries=entries,
            )

    def import_snapshot(self, snapshot: SnapshotPayload) -> None:
        with self._lock:
            for storage_key, _ in list(self._table.items()):
                self._table.delete(storage_key)
            self._namespace_versions = dict(snapshot.namespace_versions)
            for entry in snapshot.entries:
                self._table.put(
                    self._storage_key(entry.namespace, entry.key),
                    StoreRecord(
                        key=entry.key,
                        value_str=entry.value_str,
                        namespace=entry.namespace,
                        namespace_version=entry.namespace_version,
                        expires_at_ms=entry.expires_at_ms,
                        created_at_ms=entry.created_at_ms,
                        updated_at_ms=entry.updated_at_ms,
                    ),
                )

    def cleanup_expired(self, limit: int | None = None) -> int:
        with self._lock:
            if limit is not None and limit <= 0:
                return 0

            now_ms = self._now_ms()
            expired_keys: list[str] = []
            for storage_key, record in self._table.items():
                if not self._is_expired(record, now_ms):
                    continue
                expired_keys.append(storage_key)
                if limit is not None and len(expired_keys) >= limit:
                    break

            deleted_count = 0
            for storage_key in expired_keys:
                if self._table.delete(storage_key):
                    deleted_count += 1
            return deleted_count

    @staticmethod
    def _default_now_ms() -> int:
        return time.time_ns() // 1_000_000

    @staticmethod
    def _storage_key(namespace: str, key: str) -> str:
        return f"{len(namespace)}:{namespace}{len(key)}:{key}"

    def _current_namespace_version(self, namespace: str) -> int:
        return self._namespace_versions.get(namespace, 0)

    def _is_stale(self, record: StoreRecord) -> bool:
        return record.namespace_version < self._current_namespace_version(record.namespace)

    @staticmethod
    def _is_expired(record: StoreRecord, now_ms: int) -> bool:
        return record.expires_at_ms is not None and record.expires_at_ms <= now_ms

    def _read_record(
        self,
        storage_key: str,
        namespace: str,
        now_ms: int,
    ) -> tuple[StoreRecord | None, RecordState]:
        record = self._table.get(storage_key)
        if record is None:
            return None, "missing"
        if self._is_expired(record, now_ms):
            self._table.delete(storage_key)
            return None, "expired"
        if record.namespace != namespace or self._is_stale(record):
            self._table.delete(storage_key)
            return None, "stale"
        return record, "live"

    def _apply_delta(self, key: str, amount: int, namespace: str) -> int:
        with self._lock:
            now_ms = self._now_ms()
            storage_key = self._storage_key(namespace, key)
            current_version = self._current_namespace_version(namespace)
            record, state = self._read_record(storage_key, namespace, now_ms)

            if state == "live" and record is not None:
                try:
                    current_value = int(record.value_str)
                except ValueError as exc:
                    raise CounterValueError(f"Value for key '{key}' is not an integer") from exc
                next_value = current_value + amount
                next_record = StoreRecord(
                    key=key,
                    value_str=str(next_value),
                    namespace=namespace,
                    namespace_version=current_version,
                    expires_at_ms=record.expires_at_ms,
                    created_at_ms=record.created_at_ms,
                    updated_at_ms=now_ms,
                )
            else:
                next_value = amount
                next_record = StoreRecord(
                    key=key,
                    value_str=str(next_value),
                    namespace=namespace,
                    namespace_version=current_version,
                    expires_at_ms=None,
                    created_at_ms=now_ms,
                    updated_at_ms=now_ms,
                )

            self._table.put(storage_key, next_record)
            self._emit_upsert(next_record)
            return next_value

    def _emit_upsert(self, record: StoreRecord) -> None:
        self._emit_mutation(
            {
                "op": "upsert",
                "ts_ms": record.updated_at_ms,
                "record": {
                    "key": record.key,
                    "value_str": record.value_str,
                    "namespace": record.namespace,
                    "namespace_version": record.namespace_version,
                    "expires_at_ms": record.expires_at_ms,
                    "created_at_ms": record.created_at_ms,
                    "updated_at_ms": record.updated_at_ms,
                },
            }
        )

    def _emit_delete(self, key: str, namespace: str, ts_ms: int) -> None:
        self._emit_mutation(
            {
                "op": "delete",
                "ts_ms": ts_ms,
                "key": key,
                "namespace": namespace,
            }
        )

    def _emit_invalidate(self, namespace: str, version: int, ts_ms: int) -> None:
        self._emit_mutation(
            {
                "op": "invalidate",
                "ts_ms": ts_ms,
                "namespace": namespace,
                "version": version,
            }
        )

    def _emit_mutation(self, event: dict[str, Any]) -> None:
        if self._mutation_logger is not None:
            self._mutation_logger(event)
