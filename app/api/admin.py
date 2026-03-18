import os
import threading
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.config import get_settings
from app.dependencies import get_snapshot_service, get_store
from app.domain.contracts import StoreProtocol
from app.domain.schemas import (
    InvalidateResponse,
    PersistenceDemoCrashResponse,
    PersistenceDemoRecordResponse,
    SnapshotResponse,
)
from app.persistence.service import SnapshotService

router = APIRouter(tags=["admin"])
StoreDep = Annotated[StoreProtocol, Depends(get_store)]
SnapshotServiceDep = Annotated[SnapshotService, Depends(get_snapshot_service)]

PERSISTENCE_DEMO_NAMESPACE = "demo-persistence"
PERSISTENCE_DEMO_KEY = "latest-write"
PERSISTENCE_DEMO_CRASH_DELAY_MS = 350


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


@router.get(
    "/admin/persistence-demo",
    response_model=PersistenceDemoRecordResponse,
)
def get_persistence_demo_record(store: StoreDep) -> PersistenceDemoRecordResponse:
    return _serialize_persistence_demo_record(store)


@router.post(
    "/admin/persistence-demo/write",
    response_model=PersistenceDemoRecordResponse,
)
def write_persistence_demo_record(store: StoreDep) -> PersistenceDemoRecordResponse:
    now_ms = _now_ms()
    store.set(
        key=PERSISTENCE_DEMO_KEY,
        value_str=f"survives-crash-{now_ms}",
        namespace=PERSISTENCE_DEMO_NAMESPACE,
    )
    return _serialize_persistence_demo_record(store)


@router.post(
    "/admin/persistence-demo/crash",
    response_model=PersistenceDemoCrashResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def crash_persistence_demo_api() -> PersistenceDemoCrashResponse:
    settings = get_settings()
    if not settings.enable_demo_crash:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Persistence demo crash endpoint is disabled.",
        )
    _schedule_demo_crash(PERSISTENCE_DEMO_CRASH_DELAY_MS)
    return PersistenceDemoCrashResponse(
        scheduled=True,
        delay_ms=PERSISTENCE_DEMO_CRASH_DELAY_MS,
        message="API process will terminate without graceful shutdown.",
    )


def _serialize_persistence_demo_record(store: StoreProtocol) -> PersistenceDemoRecordResponse:
    settings = get_settings()
    record = store.get(PERSISTENCE_DEMO_KEY, namespace=PERSISTENCE_DEMO_NAMESPACE)
    if record is None:
        return PersistenceDemoRecordResponse(
            key=PERSISTENCE_DEMO_KEY,
            namespace=PERSISTENCE_DEMO_NAMESPACE,
            exists=False,
            crash_enabled=settings.enable_demo_crash,
        )
    return PersistenceDemoRecordResponse(
        key=record.key,
        namespace=record.namespace,
        exists=True,
        value=record.value_str,
        created_at_ms=record.created_at_ms,
        updated_at_ms=record.updated_at_ms,
        crash_enabled=settings.enable_demo_crash,
    )


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _schedule_demo_crash(delay_ms: int) -> None:
    timer = threading.Timer(delay_ms / 1000, _hard_exit)
    timer.daemon = True
    timer.start()


def _hard_exit() -> None:
    os._exit(137)
