from collections.abc import Callable

from app.domain.contracts import StoreProtocol
from app.domain.models import SnapshotPayload
from app.persistence.repository import SnapshotRepository


class SnapshotService:
    def __init__(
        self,
        repository: SnapshotRepository,
        after_save: Callable[[], None] | None = None,
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
        snapshot = store.export_snapshot()
        self._repository.save(snapshot)
        if self._after_save is not None:
            # snapshot이 최신 상태를 모두 담고 나면 AOF는 비워도 된다.
            self._after_save()
        return snapshot
