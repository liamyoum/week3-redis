from collections.abc import Callable

from app.domain.contracts import StoreProtocol
from app.domain.models import SnapshotPayload
from app.persistence.repository import SnapshotRepository


class SnapshotService:
    def __init__(
        self,
        repository: SnapshotRepository,
        after_save: Callable[[int], None] | None = None,
    ) -> None:
        # 파일 입출력 세부사항은 repository에 맡기고,
        # service는 store와 persistence 흐름만 조율한다.
        self._repository = repository
        self._after_save = after_save

    @property
    def snapshot_path(self) -> str:
        # API 응답이나 로그에서 바로 쓰기 쉽게 문자열 경로를 노출한다.
        return str(self._repository.path)

    def load_into(self, store: StoreProtocol) -> SnapshotPayload | None:
        # 저장된 파일이 없으면 복구할 상태가 없으므로 조용히 None을 반환한다.
        if not self._repository.exists():
            return None
        # 서버 시작 시 마지막으로 저장된 snapshot을 읽어
        # 현재 메모리 store 상태를 이전 실행 시점으로 복구한다.
        snapshot = self._repository.load()
        store.import_snapshot(snapshot)
        return snapshot

    def save_from(self, store: StoreProtocol) -> SnapshotPayload:
        # 현재 메모리 store 상태를 snapshot으로 내보낸 뒤
        # repository 계층에 파일 저장을 위임한다.
        marker = 0
        export_with_marker = getattr(store, "export_snapshot_with_marker", None)
        if callable(export_with_marker):
            # StoreEngine이 snapshot 시점의 mutation marker를 함께 제공하면
            # 이후 AOF rewrite에서 snapshot 이후 이벤트만 남길 수 있다.
            snapshot, marker = export_with_marker()
        else:
            snapshot = store.export_snapshot()
        self._repository.save(snapshot)
        if self._after_save is not None:
            # snapshot 시점 이후에 새로 쌓인 이벤트만 남기도록 AOF를 rewrite한다.
            self._after_save(marker)
        return snapshot
