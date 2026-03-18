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


class HealthResponse(BaseModel):
    status: str
    service: str
