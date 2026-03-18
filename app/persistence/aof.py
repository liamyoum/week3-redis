import json
import os
import time
from collections.abc import Callable, Iterable, Iterator
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Literal

from app.domain.contracts import StoreProtocol
from app.domain.models import SnapshotEntry, SnapshotPayload

AofEvent = dict[str, Any]
AppendFsyncMode = Literal["always", "everysec", "no"]
RecoveryMode = Literal["strict", "truncate"]


class AofCorruptionError(ValueError):
    """Raised when the AOF file contains an invalid non-recoverable record."""


class AofRepository:
    def __init__(
        self,
        aof_path: str | Path,
        fsync_mode: AppendFsyncMode = "everysec",
        recovery_mode: RecoveryMode = "truncate",
        now_monotonic: Callable[[], float] | None = None,
    ) -> None:
        # AOF 파일 경로도 Path 기준으로 통일해 다룬다.
        self._path = Path(aof_path)
        self._fsync_mode = fsync_mode
        self._recovery_mode = recovery_mode
        self._now_monotonic = now_monotonic or time.monotonic
        self._last_fsync_at = 0.0

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        return self._path.exists()

    def append(self, event: AofEvent) -> None:
        # AOF는 JSON Lines 형식으로 한 줄에 이벤트 하나씩 이어 붙인다.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(event)
        # 포맷 버전을 함께 남겨두면 추후 로그 구조가 바뀌어도 마이그레이션 포인트가 생긴다.
        payload.setdefault("format_version", 1)
        with self._path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
            file.write("\n")
            self._flush_for_policy(file)

    def load_all(self) -> list[AofEvent]:
        return list(self.iter_events())

    def iter_events(self) -> Iterator[AofEvent]:
        if not self.exists():
            return

        size = self._path.stat().st_size
        with self._path.open("rb") as file:
            while True:
                line = file.readline()
                if not line:
                    break
                if not line.strip():
                    continue

                is_last_record = file.tell() == size
                try:
                    event = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, JSONDecodeError) as exc:
                    # 마지막 레코드만 깨진 경우 truncate 모드에서는
                    # tail 손상으로 보고 복구를 진행한다.
                    if self._recovery_mode == "truncate" and is_last_record:
                        break
                    raise AofCorruptionError(
                        f"AOF record could not be decoded at path '{self._path}'."
                    ) from exc

                yield event

    def rewrite(self, events: Iterable[AofEvent]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
        with temp_path.open("w", encoding="utf-8") as file:
            for event in events:
                payload = dict(event)
                payload.setdefault("format_version", 1)
                file.write(json.dumps(payload, ensure_ascii=True, separators=(",", ":")))
                file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        temp_path.replace(self._path)
        self._last_fsync_at = self._now_monotonic()

    def reset(self) -> None:
        self.rewrite(())

    def _flush_for_policy(self, file: Any) -> None:
        if self._fsync_mode == "no":
            return

        file.flush()

        if self._fsync_mode == "always":
            os.fsync(file.fileno())
            self._last_fsync_at = self._now_monotonic()
            return

        if self._fsync_mode == "everysec":
            now = self._now_monotonic()
            if now - self._last_fsync_at >= 1.0:
                os.fsync(file.fileno())
                self._last_fsync_at = now
            return

        raise ValueError(f"Unsupported appendfsync mode: {self._fsync_mode}")


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
        # 현재 store 상태를 기반으로 AOF 이벤트를 순서대로 반영한 뒤 한 번에 import한다.
        base_snapshot = store.export_snapshot()
        events = self._repository.load_all()
        replayed_snapshot = self._apply_events(base_snapshot, events)
        max_seq = max((int(event.get("seq", 0)) for event in events), default=0)
        restore_seq = getattr(store, "restore_mutation_seq", None)
        if callable(restore_seq):
            restore_seq(max_seq)
        if replayed_snapshot == base_snapshot:
            return None
        store.import_snapshot(replayed_snapshot)
        return replayed_snapshot

    def rewrite_after(self, marker: int) -> None:
        # snapshot 저장 시점의 mutation seq를 기준으로 그 이후 이벤트만 다시 남긴다.
        # 이렇게 해야 snapshot 저장 도중 들어온 새 변경까지 지워버리는 문제를 막을 수 있다.
        retained_events = [
            event
            for event in self._repository.iter_events()
            if int(event.get("seq", 0)) > marker
        ]
        self._repository.rewrite(retained_events)

    def reset(self, _: int = 0) -> None:
        self._repository.reset()

    @staticmethod
    def _apply_events(
        base_snapshot: SnapshotPayload,
        events: Iterable[AofEvent],
    ) -> SnapshotPayload:
        # snapshot을 기준 상태로 잡고, 그 뒤에 쌓인 AOF 이벤트를 순서대로 반영한다.
        entries = {
            (entry.namespace, entry.key): entry
            for entry in base_snapshot.entries
        }
        namespace_versions = dict(base_snapshot.namespace_versions)
        saved_at_ms = base_snapshot.saved_at_ms
        changed = False

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
                changed = True
                continue

            if op == "delete":
                entries.pop((event["namespace"], event["key"]), None)
                changed = True
                continue

            if op == "invalidate":
                namespace_versions[event["namespace"]] = event["version"]
                changed = True
                continue

            raise ValueError(f"Unsupported AOF operation: {op}")

        if not changed:
            return base_snapshot

        return SnapshotPayload(
            version=1,
            saved_at_ms=saved_at_ms,
            namespace_versions=namespace_versions,
            entries=list(entries.values()),
        )
