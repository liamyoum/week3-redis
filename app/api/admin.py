import os
import threading
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from app.dependencies import get_snapshot_service, get_store
from app.domain.contracts import StoreProtocol
from app.domain.schemas import CrashResponse, InvalidateResponse, SnapshotResponse
from app.persistence.service import SnapshotService

router = APIRouter(tags=["admin"])
StoreDep = Annotated[StoreProtocol, Depends(get_store)]
SnapshotServiceDep = Annotated[SnapshotService, Depends(get_snapshot_service)]


def _default_crash_scheduler(reason: str, delay_ms: int) -> None:
    # 응답을 먼저 돌려준 뒤 프로세스를 강제 종료해야 프런트에서
    # "서버가 곧 내려간다"는 메시지를 정상적으로 받을 수 있다.
    def terminate() -> None:
        time.sleep(delay_ms / 1000)
        os._exit(1)

    threading.Thread(
        target=terminate,
        name=f"mini-redis-crash-{reason}",
        daemon=True,
    ).start()


@router.post(
    "/namespaces/{namespace}/invalidate",
    response_model=InvalidateResponse,
)
def invalidate_namespace(
    store: StoreDep,
    namespace: str = Path(min_length=1),
) -> InvalidateResponse:
    version = store.invalidate_namespace(namespace)
    return InvalidateResponse(namespace=namespace, version=version)


@router.post(
    "/admin/snapshot",
    response_model=SnapshotResponse,
)
def create_snapshot(
    store: StoreDep,
    snapshot_service: SnapshotServiceDep,
) -> SnapshotResponse:
    payload = snapshot_service.save_from(store)
    return SnapshotResponse(
        saved_at_ms=payload.saved_at_ms,
        path=snapshot_service.snapshot_path,
    )


@router.post(
    "/admin/crash",
    response_model=CrashResponse,
)
def crash_server(
    request: Request,
) -> CrashResponse:
    delay_ms = 700
    scheduler = getattr(request.app.state, "crash_scheduler", _default_crash_scheduler)
    cast_scheduler = scheduler if callable(scheduler) else _default_crash_scheduler
    cast_scheduler("manual-demo", delay_ms)
    return CrashResponse(
        status="scheduled",
        delay_ms=delay_ms,
        message="API 서버가 잠시 후 강제 종료됩니다. 스냅샷과 AOF 복구를 시연하세요.",
    )


@router.post(
    "/admin/restart",
    response_model=CrashResponse,
)
def restart_server(
    request: Request,
) -> CrashResponse:
    delay_ms = 700
    scheduler = getattr(request.app.state, "crash_scheduler", _default_crash_scheduler)
    cast_scheduler = scheduler if callable(scheduler) else _default_crash_scheduler
    cast_scheduler("restart-demo", delay_ms)
    return CrashResponse(
        status="scheduled",
        delay_ms=delay_ms,
        message="API 서버를 재시작합니다. 잠시 후 Docker가 자동으로 다시 올립니다.",
    )
