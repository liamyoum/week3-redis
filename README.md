# week3-redis

Mini Redis team project.

## Project Overview

This repository starts from a common seed PR that freezes the package layout,
HTTP routes, shared data contracts, and the local quality toolchain. The actual
Mini Redis logic will be implemented in follow-up branches owned by each team
member.

## Architecture

- `app/api`: FastAPI routers and external HTTP contract
- `app/domain`: shared models, protocols, and request/response schemas
- `app/core`: custom hash table implementation owned by team member 1
- `app/engine`: store semantics such as TTL and invalidation owned by team
  member 2
- `app/persistence`: snapshot save/restore owned by team member 4

The initial app only exposes a working `/health` endpoint. KV and admin routes
exist as stubs so the public API shape is fixed before implementation starts.

## API Contracts

- `GET /health`
- `PUT /kv/{key}`
- `GET /kv/{key}`
- `DELETE /kv/{key}`
- `POST /kv/{key}/incr`
- `POST /kv/{key}/decr`
- `POST /namespaces/{namespace}/invalidate`
- `POST /admin/snapshot`

KV and admin endpoints currently return `501 Not Implemented` in the seed PR.

## Hash Table Design Talking Points

- Custom hash table with a bucket array
- FNV-1a 64-bit hashing
- Separate chaining for collision handling
- Resize when load factor exceeds `0.75`
- Public methods limited to `put`, `get`, `delete`, `items`, and `__len__`

## Test Strategy

- Integration test for `/health`
- Contract tests that ensure all stub routes exist and return `501`
- OpenAPI schema tests to freeze request and response models
- Follow-up branches will add unit tests for core, engine, and persistence

## Performance Comparison Plan

- Use a local mock upstream API with deterministic delay
- Compare uncached requests against cached requests through the Mini Redis API
- Record total time, average latency, and cache hit ratio in the README

## Team Split

See `docs/team-split.md` for ownership boundaries and merge rules.
