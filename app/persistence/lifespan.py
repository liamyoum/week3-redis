from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from app.domain.contracts import StoreProtocol
from app.persistence.aof import AofRepository, AofService, AppendFsyncMode, RecoveryMode
from app.persistence.repository import SnapshotRepository
from app.persistence.service import SnapshotService


def configure_aof_service(
    app: FastAPI,
    aof_path: str,
    fsync_mode: AppendFsyncMode = "everysec",
    recovery_mode: RecoveryMode = "truncate",
) -> AofService:
    service = AofService(
        AofRepository(
            aof_path,
            fsync_mode=fsync_mode,
            recovery_mode=recovery_mode,
        )
    )
    app.state.aof_service = service
    return service


def configure_snapshot_service(
    app: FastAPI,
    snapshot_path: str,
    after_save: Callable[[int], None] | None = None,
) -> SnapshotService:
    service = SnapshotService(SnapshotRepository(snapshot_path), after_save=after_save)
    app.state.snapshot_service = service
    return service


def get_configured_store(app: FastAPI) -> StoreProtocol | None:
    store = getattr(app.state, "store", None)
    if store is None:
        return None
    return store


@asynccontextmanager
async def snapshot_lifespan(app: FastAPI) -> AsyncIterator[None]:
    service = getattr(app.state, "snapshot_service", None)
    aof_service = getattr(app.state, "aof_service", None)
    store = get_configured_store(app)

    if service is not None and store is not None:
        service.load_into(store)
    if aof_service is not None and store is not None:
        aof_service.replay_into(store)

    yield

    service = getattr(app.state, "snapshot_service", None)
    store = get_configured_store(app)
    if service is not None and store is not None:
        service.save_from(store)
    catalog = getattr(app.state, "product_catalog", None)
    close = getattr(catalog, "close", None)
    if callable(close):
        close()


def snapshot_status(app: FastAPI) -> dict[str, Any]:
    service = getattr(app.state, "snapshot_service", None)
    aof_service = getattr(app.state, "aof_service", None)
    return {
        "configured": service is not None,
        "path": None if service is None else service.snapshot_path,
        "aof_path": None if aof_service is None else aof_service.aof_path,
    }
