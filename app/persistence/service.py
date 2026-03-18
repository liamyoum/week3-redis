from app.domain.contracts import StoreProtocol
from app.domain.models import SnapshotPayload
from app.persistence.repository import SnapshotRepository


class SnapshotService:
    def __init__(self, repository: SnapshotRepository) -> None:
        self._repository = repository

    @property
    def snapshot_path(self) -> str:
        return str(self._repository.path)

    def load_into(self, store: StoreProtocol) -> SnapshotPayload | None:
        if not self._repository.exists():
            return None
        snapshot = self._repository.load()
        store.import_snapshot(snapshot)
        return snapshot

    def save_from(self, store: StoreProtocol) -> SnapshotPayload:
        snapshot = store.export_snapshot()
        self._repository.save(snapshot)
        return snapshot
