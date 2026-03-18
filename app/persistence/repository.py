from pathlib import Path

from app.domain.models import SnapshotPayload
from app.persistence.serialization import snapshot_from_json, snapshot_to_json


class SnapshotRepository:
    def __init__(self, snapshot_path: str | Path) -> None:
        self._path = Path(snapshot_path)

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        return self._path.exists()

    def load(self) -> SnapshotPayload:
        return snapshot_from_json(self._path.read_text(encoding="utf-8"))

    def save(self, snapshot: SnapshotPayload) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
        temp_path.write_text(snapshot_to_json(snapshot), encoding="utf-8")
        temp_path.replace(self._path)
