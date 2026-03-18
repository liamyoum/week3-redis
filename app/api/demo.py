import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ValidationError

from app.dependencies import get_store
from app.domain.contracts import StoreProtocol

router = APIRouter(tags=["demo"])
StoreDep = Annotated[StoreProtocol, Depends(get_store)]

DEMO_NAMESPACE = "demo-cache"
DEMO_KEY_PREFIX = "upstream:"
UPSTREAM_DELAY_SECONDS = 0.1


class DemoPayload(BaseModel):
    id: str
    name: str
    description: str
    price: int


class DemoItemResponse(BaseModel):
    item_id: str
    payload: DemoPayload


class CachedDemoResponse(BaseModel):
    item_id: str
    payload: DemoPayload
    cache_status: Literal["hit", "miss"]


async def _build_upstream_payload(item_id: str) -> DemoPayload:
    await asyncio.sleep(UPSTREAM_DELAY_SECONDS)
    return DemoPayload(
        id=item_id,
        name=f"item-{item_id}",
        description=f"Mock upstream item for {item_id}",
        price=max(1, sum(ord(char) for char in item_id)),
    )


def _cache_key(item_id: str) -> str:
    return f"{DEMO_KEY_PREFIX}{item_id}"


@router.get("/demo/upstream/{item_id}", response_model=DemoItemResponse)
async def get_upstream_item(item_id: str) -> DemoItemResponse:
    payload = await _build_upstream_payload(item_id)
    return DemoItemResponse(item_id=item_id, payload=payload)


@router.get("/demo/cached/{item_id}", response_model=CachedDemoResponse)
async def get_cached_item(item_id: str, store: StoreDep) -> CachedDemoResponse:
    cache_key = _cache_key(item_id)
    cached_record = store.get(cache_key, namespace=DEMO_NAMESPACE)
    if cached_record is not None:
        try:
            payload = DemoPayload.model_validate_json(cached_record.value_str)
        except ValidationError:
            store.delete(cache_key, namespace=DEMO_NAMESPACE)
        else:
            return CachedDemoResponse(item_id=item_id, payload=payload, cache_status="hit")

    payload = await _build_upstream_payload(item_id)
    store.set(
        key=cache_key,
        value_str=payload.model_dump_json(),
        namespace=DEMO_NAMESPACE,
    )
    return CachedDemoResponse(item_id=item_id, payload=payload, cache_status="miss")
