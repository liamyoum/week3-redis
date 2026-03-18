from dataclasses import dataclass, field


@dataclass(slots=True)
class StoreRecord:
    key: str
    value_str: str
    namespace: str = "default"
    namespace_version: int = 0
    expires_at_ms: int | None = None
    created_at_ms: int = 0
    updated_at_ms: int = 0


@dataclass(slots=True)
class SnapshotEntry:
    key: str
    value_str: str
    namespace: str = "default"
    namespace_version: int = 0
    expires_at_ms: int | None = None
    created_at_ms: int = 0
    updated_at_ms: int = 0


@dataclass(slots=True)
class SnapshotPayload:
    version: int = 1
    saved_at_ms: int = 0
    namespace_versions: dict[str, int] = field(default_factory=dict)
    entries: list[SnapshotEntry] = field(default_factory=list)
