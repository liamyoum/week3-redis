#언제 저장하고 언제 복구할지

from collections.abc import AsyncIterator
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from app.domain.contracts import StoreProtocol
from app.persistence.aof import AofRepository, AofService
from app.persistence.repository import SnapshotRepository
from app.persistence.service import SnapshotService


def configure_aof_service(app: FastAPI, aof_path: str) -> AofService:
    # AOF service는 snapshot 이후 변경분을 누적 기록하고 startup에서 replay할 때 사용한다.
    service = AofService(AofRepository(aof_path))
    app.state.aof_service = service
    return service


def configure_snapshot_service(
    app: FastAPI,
    snapshot_path: str,
    after_save: Callable[[], None] | None = None,
) -> SnapshotService:
    # snapshot service를 app.state에 올려두면
    # startup/shutdown 훅과 admin API가 같은 객체를 함께 사용할 수 있다.
    service = SnapshotService(SnapshotRepository(snapshot_path), after_save=after_save)
    app.state.snapshot_service = service
    return service


def get_configured_store(app: FastAPI) -> StoreProtocol | None:
    # 현재 앱에 store가 붙어 있는지 안전하게 조회한다.
    # 다른 팀 구현과 연결되는 지점이라 getattr로 방어적으로 접근한다.
    store = getattr(app.state, "store", None)
    if store is None:
        return None
    return store


@asynccontextmanager
async def snapshot_lifespan(app: FastAPI) -> AsyncIterator[None]:
    # lifespan은 FastAPI가 시작될 때 한 번, 종료될 때 한 번 실행하는 구간이다.
    # 여기서 snapshot 복구/저장을 자동화하면 API 코드에서 별도 호출이 필요 없다.
    service = getattr(app.state, "snapshot_service", None)
    aof_service = getattr(app.state, "aof_service", None)
    store = get_configured_store(app)

    if service is not None and store is not None:
        # 앱 시작 시 snapshot 파일이 있으면 메모리 store를 먼저 복구해서
        # 재시작 이후에도 이전 데이터가 유지되도록 만든다.
        service.load_into(store)
    if aof_service is not None and store is not None:
        # snapshot 저장 이후에 쌓인 변경분은 AOF replay로 이어서 복구한다.
        aof_service.replay_into(store)

    # yield 이전은 startup, yield 이후는 shutdown 구간이다.
    yield

    service = getattr(app.state, "snapshot_service", None)
    store = get_configured_store(app)
    if service is not None and store is not None:
        # 앱 종료 시점의 최신 메모리 상태를 snapshot 파일로 저장해
        # 다음 실행에서 다시 복구할 수 있게 한다.
        service.save_from(store)


def snapshot_status(app: FastAPI) -> dict[str, Any]:
    # 현재 앱에 snapshot service가 설정되었는지 간단히 확인할 때 쓰는 보조 함수다.
    service = getattr(app.state, "snapshot_service", None)
    aof_service = getattr(app.state, "aof_service", None)
    return {
        "configured": service is not None,
        "path": None if service is None else service.snapshot_path,
        "aof_path": None if aof_service is None else aof_service.aof_path,
    }
