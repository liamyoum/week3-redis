from pathlib import Path

from app.domain.models import SnapshotPayload
from app.persistence.serialization import snapshot_from_json, snapshot_to_json


class SnapshotRepository:
    def __init__(self, snapshot_path: str | Path) -> None:
        # 문자열 경로가 들어와도 이후 파일 연산은 Path 기준으로 통일해 처리한다.
        self._path = Path(snapshot_path)

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        # 앱 시작 시 복구 가능한 snapshot이 있는지 먼저 확인할 때 사용한다.
        return self._path.exists()

    def load(self) -> SnapshotPayload:
        # snapshot 파일은 UTF-8 JSON으로 저장되므로 문자열로 읽은 뒤
        # serialization 계층에 넘겨 typed snapshot 객체로 복원한다.
        return snapshot_from_json(self._path.read_text(encoding="utf-8"))

    def save(self, snapshot: SnapshotPayload) -> None:
        # snapshot 경로의 상위 폴더가 없으면 먼저 생성한다.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # 저장 도중 프로세스가 중단되더라도 기존 snapshot 파일 손상을 줄이기 위해
        # 원본에 바로 덮어쓰지 않고 tmp 파일에 먼저 기록한다.
        temp_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
        temp_path.write_text(snapshot_to_json(snapshot), encoding="utf-8")
        # tmp 파일 기록이 끝난 뒤 원본 파일을 원자적으로 교체한다.
        temp_path.replace(self._path)
