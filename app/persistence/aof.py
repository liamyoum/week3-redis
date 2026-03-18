import json
from pathlib import Path
from typing import Any

from app.domain.contracts import StoreProtocol
from app.domain.models import SnapshotEntry, SnapshotPayload

AofEvent = dict[str, Any]


class AofRepository:
    def __init__(self, aof_path: str | Path) -> None:
        # AOF 파일 경로도 Path 기준으로 통일해 다룬다.
        self._path = Path(aof_path)

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        return self._path.exists()

    def append(self, event: AofEvent) -> None:
        # AOF는 JSON Lines 형식으로 한 줄에 이벤트 하나씩 이어 붙인다.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=True, separators=(",", ":")))
            file.write("\n")

    def load_all(self) -> list[AofEvent]:
        if not self.exists():
            return []

        # 서버 재시작 시에는 파일에 쌓인 모든 이벤트를 순서대로 읽어 replay한다.
        events: list[AofEvent] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            events.append(json.loads(line))
        return events

    def reset(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("", encoding="utf-8")


class AofService:
    def __init__(self, repository: AofRepository) -> None:
        # AOF도 service/repository 구조로 분리해 store 흐름과 파일 입출력을 분리한다.
        self._repository = repository

    @property
    def aof_path(self) -> str:
        return str(self._repository.path)

    def append_event(self, event: AofEvent) -> None:
        # 모든 쓰기 연산은 JSONL 한 줄씩 append해서 snapshot 이후 변경분을 남긴다.
        self._repository.append(event)

    def replay_into(self, store: StoreProtocol) -> SnapshotPayload | None:
        events = self._repository.load_all()
        if not events:
            return None

        # 현재 store 상태를 기반으로 AOF 이벤트를 순서대로 반영한 뒤 한 번에 import한다.
        base_snapshot = store.export_snapshot()
        replayed_snapshot = self._apply_events(base_snapshot, events)
        store.import_snapshot(replayed_snapshot)
        return replayed_snapshot

    def reset(self) -> None:
        # snapshot에 최신 상태가 반영된 뒤에는 그 이후 변경만 다시 쌓으면 되므로 AOF를 비운다.
        self._repository.reset()

    @staticmethod
    def _apply_events(base_snapshot: SnapshotPayload, events: list[AofEvent]) -> SnapshotPayload:
        # snapshot을 기준 상태로 잡고, 그 뒤에 쌓인 AOF 이벤트를 순서대로 반영한다.
        entries = {
            (entry.namespace, entry.key): entry
            for entry in base_snapshot.entries
        }
        namespace_versions = dict(base_snapshot.namespace_versions)
        saved_at_ms = base_snapshot.saved_at_ms

        for event in events:
            op = event["op"]
            saved_at_ms = max(saved_at_ms, int(event.get("ts_ms", saved_at_ms)))

            if op == "upsert":
                record = event["record"]
                entry = SnapshotEntry(
                    key=record["key"],
                    value_str=record["value_str"],
                    namespace=record["namespace"],
                    namespace_version=record["namespace_version"],
                    expires_at_ms=record["expires_at_ms"],
                    created_at_ms=record["created_at_ms"],
                    updated_at_ms=record["updated_at_ms"],
                )
                entries[(entry.namespace, entry.key)] = entry
                namespace_versions[entry.namespace] = max(
                    namespace_versions.get(entry.namespace, 0),
                    entry.namespace_version,
                )
                continue

            if op == "delete":
                entries.pop((event["namespace"], event["key"]), None)
                continue

            if op == "invalidate":
                namespace_versions[event["namespace"]] = event["version"]
                continue

            raise ValueError(f"Unsupported AOF operation: {op}")

        return SnapshotPayload(
            version=1,
            saved_at_ms=saved_at_ms,
            namespace_versions=namespace_versions,
            entries=list(entries.values()),
        )
