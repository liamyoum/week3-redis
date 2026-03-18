from collections.abc import Iterable
from typing import Protocol, TypeVar

from app.domain.models import SnapshotPayload, StoreRecord

RecordT = TypeVar("RecordT")


class HashTableProtocol(Protocol[RecordT]):
    def put(self, key: str, value: RecordT) -> None:
        ...

    def get(self, key: str) -> RecordT | None:
        ...

    def delete(self, key: str) -> bool:
        ...

    def items(self) -> Iterable[tuple[str, RecordT]]:
        ...

    def __len__(self) -> int:
        ...


class StoreProtocol(Protocol):
    def set(
        self,
        key: str,
        value_str: str,
        ttl_ms: int | None = None,
        namespace: str = "default",
    ) -> StoreRecord:
        ...

    def get(self, key: str, namespace: str = "default") -> StoreRecord | None:
        ...

    def delete(self, key: str, namespace: str = "default") -> bool:
        ...

    def incr(self, key: str, amount: int = 1, namespace: str = "default") -> int:
        ...

    def decr(self, key: str, amount: int = 1, namespace: str = "default") -> int:
        ...

    def invalidate_namespace(self, namespace: str) -> int:
        ...

    def export_snapshot(self) -> SnapshotPayload:
        ...

    def import_snapshot(self, snapshot: SnapshotPayload) -> None:
        ...

    def cleanup_expired(self, limit: int | None = None) -> int:
        ...
