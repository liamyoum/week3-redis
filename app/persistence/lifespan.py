from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from app.domain.contracts import StoreProtocol
from app.persistence.repository import SnapshotRepository
from app.persistence.service import SnapshotService


def configure_snapshot_service(app: FastAPI, snapshot_path: str) -> SnapshotService:
    service = SnapshotService(SnapshotRepository(snapshot_path))
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
    store = get_configured_store(app)

    if service is not None and store is not None:
        service.load_into(store)

    yield

    service = getattr(app.state, "snapshot_service", None)
    store = get_configured_store(app)
    if service is not None and store is not None:
        service.save_from(store)


def snapshot_status(app: FastAPI) -> dict[str, Any]:
    service = getattr(app.state, "snapshot_service", None)
    return {
        "configured": service is not None,
        "path": None if service is None else service.snapshot_path,
    }
