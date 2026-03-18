import json
from dataclasses import asdict

from app.domain.models import SnapshotEntry, SnapshotPayload


def snapshot_to_json(snapshot: SnapshotPayload) -> str:
    return json.dumps(asdict(snapshot), ensure_ascii=True, separators=(",", ":"))


def snapshot_from_json(raw: str) -> SnapshotPayload:
    payload = json.loads(raw)
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
    return SnapshotPayload(
        version=payload.get("version", 1),
        saved_at_ms=payload.get("saved_at_ms", 0),
        namespace_versions=dict(payload.get("namespace_versions", {})),
        entries=entries,
    )
