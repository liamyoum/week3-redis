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

## Team 4 Scope

Team member 4 owns snapshot persistence, startup and shutdown restore hooks,
the benchmark script, and 발표용 검증 정리 문서화.

### Snapshot Persistence

- Snapshot file path is configured with `MINI_REDIS_SNAPSHOT_PATH`
- Default snapshot file is `data/snapshot.json`
- Snapshot persistence lives under `app/persistence`
- App startup loads the snapshot only when `app.state.store` is configured
- App shutdown exports the current store snapshot back to disk
- Writes use a temporary file plus atomic replace so partial writes do not
  corrupt the main snapshot file

### Integration Contract For Other Teammates

To avoid merge conflicts, persistence assumes only one app-level integration
point:

- Team 2 or 3 should attach the concrete store instance to `app.state.store`
  before the FastAPI lifespan starts
- Persistence will call `store.import_snapshot(...)` on startup when a snapshot
  exists
- Persistence will call `store.export_snapshot()` on shutdown

This keeps the implementation isolated to `app/persistence` and one small hook
inside `app/main.py`.

### Benchmark Script

Run the local benchmark after the demo endpoints are implemented:

```bash
python3 scripts/bench.py --base-url http://127.0.0.1:8000 --requests 100
```

Optional markdown export:

```bash
python3 scripts/bench.py \
  --base-url http://127.0.0.1:8000 \
  --requests 100 \
  --report-path docs/benchmark-results.md
```

The benchmark assumes a fresh `item_id`, so the first cached request is a miss
and the remaining requests are hits.

### Presentation Verification Template

Use the table below after running the benchmark and snapshot recovery demo.

| Check | Expected Result | Actual Result |
| --- | --- | --- |
| Snapshot file save | `data/snapshot.json` created after shutdown | TBD |
| Snapshot restore | Saved keys are available after restart | TBD |
| Atomic replace | Snapshot file remains valid JSON after repeated saves | TBD |
| Upstream benchmark | Higher total and average latency than cached path | TBD |
| Cached benchmark | First call miss, repeated calls faster | TBD |
| Cache hit ratio | Approximately `99%` for 100 repeated requests | TBD |

### Local Validation

Current persistence branch validation:

| Item | Status |
| --- | --- |
| Snapshot repository round-trip test | Passed |
| App startup restore and shutdown save test | Passed |
| Existing seed integration tests | Passed |

Recommended local command:

```bash
PYTHONPATH=. python3 -m pytest -q
```

## Team Split

See `docs/team-split.md` for ownership boundaries and merge rules.
