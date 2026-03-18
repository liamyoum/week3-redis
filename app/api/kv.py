from typing import NoReturn

from fastapi import APIRouter, HTTPException, Query

from app.domain.schemas import (
    CounterRequest,
    CounterResponse,
    DeleteResponse,
    PutValueRequest,
    ValueResponse,
)

router = APIRouter(tags=["kv"])


def _not_implemented() -> NoReturn:
    raise HTTPException(status_code=501, detail="Not implemented")


@router.put(
    "/kv/{key}",
    response_model=ValueResponse,
    responses={501: {"description": "Not implemented"}},
)
def put_value(key: str, request: PutValueRequest) -> ValueResponse:
    _ = key, request
    _not_implemented()


@router.get(
    "/kv/{key}",
    response_model=ValueResponse,
    responses={501: {"description": "Not implemented"}},
)
def get_value(key: str, namespace: str = Query(default="default", min_length=1)) -> ValueResponse:
    _ = key, namespace
    _not_implemented()


@router.delete(
    "/kv/{key}",
    response_model=DeleteResponse,
    responses={501: {"description": "Not implemented"}},
)
def delete_value(
    key: str,
    namespace: str = Query(default="default", min_length=1),
) -> DeleteResponse:
    _ = key, namespace
    _not_implemented()


@router.post(
    "/kv/{key}/incr",
    response_model=CounterResponse,
    responses={501: {"description": "Not implemented"}},
)
def increment_value(key: str, request: CounterRequest) -> CounterResponse:
    _ = key, request
    _not_implemented()


@router.post(
    "/kv/{key}/decr",
    response_model=CounterResponse,
    responses={501: {"description": "Not implemented"}},
)
def decrement_value(key: str, request: CounterRequest) -> CounterResponse:
    _ = key, request
    _not_implemented()
