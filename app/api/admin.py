from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.dependencies import get_snapshot_service, get_store
from app.domain.contracts import StoreProtocol
from app.domain.schemas import InvalidateResponse, SnapshotResponse
from app.persistence.service import SnapshotService

router = APIRouter(tags=["admin"])
StoreDep = Annotated[StoreProtocol, Depends(get_store)]
SnapshotServiceDep = Annotated[SnapshotService, Depends(get_snapshot_service)]


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
