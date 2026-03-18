from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PutValueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    ttl_ms: int | None = Field(default=None, gt=0)
    namespace: str = Field(default="default", min_length=1)


class CounterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: int = 1
    namespace: str = Field(default="default", min_length=1)


class ValueResponse(BaseModel):
    key: str
    value: str
    namespace: str
    expires_at_ms: int | None = None


class DeleteResponse(BaseModel):
    key: str
    deleted: bool
    namespace: str


class CounterResponse(BaseModel):
    key: str
    value: int
    namespace: str


class InvalidateResponse(BaseModel):
    namespace: str
    version: int


class SnapshotResponse(BaseModel):
    saved_at_ms: int
    path: str


class CrashResponse(BaseModel):
    status: str
    delay_ms: int = Field(ge=0)
    message: str


class HealthResponse(BaseModel):
    status: str
    service: str


class ProductCardResponse(BaseModel):
    id: str
    name: str
    tagline: str
    description: str
    image_url: str
    price: int
    stock: int
    accent_color: str
    badge: str
    emoji: str
    cache_namespace: str


class ProductListResponse(BaseModel):
    origin_source: str
    products: list[ProductCardResponse]


class ProductDetailResponse(BaseModel):
    product: ProductCardResponse
    source: Literal["direct", "cache"]
    origin_source: str
    cache_status: Literal["bypass", "hit", "miss"]
    latency_ms: float = Field(ge=0)


class ReserveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    ttl_ms: int = Field(default=15_000, gt=0, le=120_000)


class ReserveResponse(BaseModel):
    product_id: str
    session_id: str
    hold_key: str
    ttl_ms: int
    expires_at_ms: int


class PurchaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: int = Field(default=1, gt=0, le=5)


class PurchaseResponse(BaseModel):
    product_id: str
    quantity: int
    stock: int


class StoreStateResponse(BaseModel):
    origin_source: str
    origin_delay_ms: int = Field(ge=0)
    product_count: int = Field(ge=0)
    snapshot_path: str | None = None
    snapshot_exists: bool
    snapshot_size_bytes: int = Field(ge=0)
    aof_path: str | None = None
    aof_exists: bool
    aof_size_bytes: int = Field(ge=0)
