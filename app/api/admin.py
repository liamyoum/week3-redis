from typing import NoReturn

from fastapi import APIRouter, HTTPException

from app.domain.schemas import InvalidateResponse, SnapshotResponse

router = APIRouter(tags=["admin"])


def _not_implemented() -> NoReturn:
    raise HTTPException(status_code=501, detail="Not implemented")


@router.post(
    "/namespaces/{namespace}/invalidate",
    response_model=InvalidateResponse,
    responses={501: {"description": "Not implemented"}},
)
def invalidate_namespace(namespace: str) -> InvalidateResponse:
    _ = namespace
    _not_implemented()


@router.post(
    "/admin/snapshot",
    response_model=SnapshotResponse,
    responses={501: {"description": "Not implemented"}},
)
def create_snapshot() -> SnapshotResponse:
    _not_implemented()
