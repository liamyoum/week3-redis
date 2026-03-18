from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_store
from app.domain.contracts import StoreProtocol
from app.domain.schemas import (
    CounterRequest,
    CounterResponse,
    DeleteResponse,
    PutValueRequest,
    ValueResponse,
)
from app.engine import CounterValueError

router = APIRouter(tags=["kv"])
StoreDep = Annotated[StoreProtocol, Depends(get_store)]


def _not_found(key: str, namespace: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Key '{key}' was not found in namespace '{namespace}'.",
    )


@router.put(
    "/kv/{key}",
    response_model=ValueResponse,
)
def put_value(key: str, request: PutValueRequest, store: StoreDep) -> ValueResponse:
    record = store.set(
        key=key,
        value_str=request.value,
        ttl_ms=request.ttl_ms,
        namespace=request.namespace,
    )
    return ValueResponse(
        key=record.key,
        value=record.value_str,
        namespace=record.namespace,
        expires_at_ms=record.expires_at_ms,
    )


@router.get(
    "/kv/{key}",
    response_model=ValueResponse,
    responses={404: {"description": "Not found"}},
)
def get_value(
    key: str,
    store: StoreDep,
    namespace: str = Query(default="default", min_length=1),
) -> ValueResponse:
    record = store.get(key, namespace=namespace)
    if record is None:
        raise _not_found(key, namespace)

    return ValueResponse(
        key=record.key,
        value=record.value_str,
        namespace=record.namespace,
        expires_at_ms=record.expires_at_ms,
    )


@router.delete(
    "/kv/{key}",
    response_model=DeleteResponse,
    responses={404: {"description": "Not found"}},
)
def delete_value(
    key: str,
    store: StoreDep,
    namespace: str = Query(default="default", min_length=1),
) -> DeleteResponse:
    deleted = store.delete(key, namespace=namespace)
    if not deleted:
        raise _not_found(key, namespace)

    return DeleteResponse(key=key, deleted=True, namespace=namespace)


@router.post(
    "/kv/{key}/incr",
    response_model=CounterResponse,
    responses={409: {"description": "Value is not an integer string"}},
)
def increment_value(key: str, request: CounterRequest, store: StoreDep) -> CounterResponse:
    try:
        value = store.incr(key, amount=request.amount, namespace=request.namespace)
    except CounterValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Key '{key}' does not contain an integer string.",
        ) from exc

    return CounterResponse(key=key, value=value, namespace=request.namespace)


@router.post(
    "/kv/{key}/decr",
    response_model=CounterResponse,
    responses={409: {"description": "Value is not an integer string"}},
)
def decrement_value(key: str, request: CounterRequest, store: StoreDep) -> CounterResponse:
    try:
        value = store.decr(key, amount=request.amount, namespace=request.namespace)
    except CounterValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Key '{key}' does not contain an integer string.",
        ) from exc

    return CounterResponse(key=key, value=value, namespace=request.namespace)
