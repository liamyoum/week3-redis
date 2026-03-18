import json
from dataclasses import asdict

from app.domain.models import SnapshotEntry, SnapshotPayload


def snapshot_to_json(snapshot: SnapshotPayload) -> str:
    # StoreEngine이 내보낸 SnapshotPayload는 dataclass 객체라서
    # 바로 파일에 저장할 수 없다. 따라서 JSON 문자열로 직렬화해
    # snapshot.json 파일에 쓸 수 있는 형태로 바꾼다.
    return json.dumps(asdict(snapshot), ensure_ascii=True, separators=(",", ":"))


def snapshot_from_json(raw: str) -> SnapshotPayload:
    # 디스크에서 읽어온 JSON 문자열을 파이썬 dict로 먼저 변환한다.
    payload = json.loads(raw)
    # entries는 단순 dict 목록이 아니라 SnapshotEntry 객체 목록으로 복원해야
    # 이후 store.import_snapshot(...)에서 타입이 맞는 구조를 그대로 사용할 수 있다.
    entries = [
        SnapshotEntry(
            key=entry["key"],
            value_str=entry["value_str"],
            namespace=entry.get("namespace", "default"),
            namespace_version=entry.get("namespace_version", 0),
            expires_at_ms=entry.get("expires_at_ms"),
            created_at_ms=entry.get("created_at_ms", 0),
            updated_at_ms=entry.get("updated_at_ms", 0),
        )
        for entry in payload.get("entries", [])
    ]
    # 최종적으로 JSON 전체를 SnapshotPayload 객체로 다시 묶어서 반환한다.
    return SnapshotPayload(
        version=payload.get("version", 1),
        saved_at_ms=payload.get("saved_at_ms", 0),
        namespace_versions=dict(payload.get("namespace_versions", {})),
        entries=entries,
    )
