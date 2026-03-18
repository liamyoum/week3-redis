from typing import cast

from fastapi import HTTPException, Request, status

from app.domain.contracts import StoreProtocol
from app.persistence.service import SnapshotService


def get_store(request: Request) -> StoreProtocol:
    store = getattr(request.app.state, "store", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Store is not configured.",
        )
    return cast(StoreProtocol, store)


def get_snapshot_service(request: Request) -> SnapshotService:
    service = getattr(request.app.state, "snapshot_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Snapshot service is not configured.",
        )
    return cast(SnapshotService, service)
