# week3-redis

Mini Redis team project with a presentation-ready storefront demo.

## Project Overview

이 저장소는 직접 구현한 Mini Redis를 FastAPI API로 노출하고, 이를 `한정 굿즈 드롭`
웹서비스에 연결해 캐시의 가치와 영속성을 직관적으로 보여주는 데모를 포함한다.

핵심 메시지는 아래 3가지다.

- 같은 상품을 반복 조회할 때 Mongo 원본보다 Mini Redis 캐시가 빠르다.
- TTL, counter, invalidate가 실제 서비스 동작으로 연결된다.
- snapshot + AOF로 서버 재시작 후에도 상태를 복구할 수 있다.

## Architecture

- `app/core`: custom hash table
- `app/engine`: TTL, invalidate, counter semantics
- `app/persistence`: snapshot + AOF persistence
- `app/storefront`: Mongo/seed 상품 카탈로그와 데모 서비스 로직
- `app/api`: FastAPI routers
- `frontend`: 정적 발표용 UI

런타임 구성은 아래와 같다.

- `MongoDB`: 원본 상품 데이터 저장
- `Mini Redis`: 상품 상세 캐시, 재고 카운터, TTL 홀드, invalidate, snapshot/AOF
- `Frontend`: direct vs cache 비교, persistence 상태, raw KV console

## Run

로컬 백엔드만 실행:

```bash
make install
make run
```

발표용 전체 스택 실행:

```bash
make docker-up
```

접속 주소:

- Frontend: `http://127.0.0.1:8080`
- API docs: `http://127.0.0.1:8000/docs`

종료:

```bash
make docker-down
```

## Demo Flow

### Storefront

- `GET /store/products`
- `GET /store/products/{product_id}/direct`
- `GET /store/products/{product_id}/cached`
- `POST /store/products/{product_id}/reserve`
- `POST /store/products/{product_id}/purchase`
- `POST /store/products/{product_id}/invalidate`
- `GET /store/state`

### Core Redis APIs

- `PUT /kv/{key}`
- `GET /kv/{key}`
- `DELETE /kv/{key}`
- `POST /kv/{key}/incr`
- `POST /kv/{key}/decr`
- `POST /namespaces/{namespace}/invalidate`
- `POST /admin/snapshot`

## What To Show In The Presentation

1. 상품 하나를 선택하고 `DB Direct` 와 `Redis Cache` 를 각각 조회한다.
2. 같은 상품을 다시 조회해 `miss -> hit` 전환과 응답시간 차이를 보여준다.
3. `15초 홀드` 버튼으로 TTL countdown을 보여준다.
4. `재고 1 차감` 버튼으로 counter 기반 재고 감소를 보여준다.
5. `캐시 무효화` 버튼으로 다음 cached 요청이 다시 miss가 되는 것을 보여준다.
6. `Snapshot 저장` 후 `data/snapshot.json`, `data/appendonly.aof.jsonl` 파일 상태를 확인한다.
7. 서버 재시작 후 상태가 복구되는 것을 확인한다.
8. 하단 `Mini Redis Console` 로 raw `SET/GET/DEL/INCR/DECR` 도 시연한다.

## Benchmark

기본 벤치는 storefront direct/cache 기준으로 동작한다.

```bash
python3 scripts/bench.py --base-url http://127.0.0.1:8000 --requests 20
```

기존 synthetic demo endpoint 기준으로도 비교할 수 있다.

```bash
python3 scripts/bench.py \
  --base-url http://127.0.0.1:8000 \
  --scenario demo \
  --requests 20
```

## Quality Checks

```bash
make lint
make typecheck
make test
```

## Persistence

- Snapshot path: `data/snapshot.json`
- AOF path: `data/appendonly.aof.jsonl`
- startup: snapshot load -> AOF replay
- shutdown: snapshot save -> post-snapshot AOF rewrite

## Notes

- MongoDB가 연결되지 않으면 앱은 자동으로 seed 상품 카탈로그로 fallback 한다.
- storefront direct 경로에는 발표 안정성을 위해 작은 고정 지연이 들어간다.
- Mini Redis 내부 값은 문자열 기반이며, 상품 상세 캐시는 JSON 문자열로 직렬화해 저장한다.
