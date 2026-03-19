# week3-redis

직접 구현한 Mini Redis를 FastAPI로 노출하고, 이를 상품 드롭 데모 서비스에 연결해
캐시 성능과 영속성을 함께 보여주는 팀 프로젝트입니다.

## 핵심 목표

- 원본 데이터(MongoDB 또는 seed JSON)와 Mini Redis 캐시의 응답 차이를 비교한다.
- TTL, 카운터, 네임스페이스 무효화가 실제 서비스 동작으로 이어지는 모습을 보여준다.
- Snapshot + AOF 하이브리드 영속성으로 서버 재시작 후에도 상태를 복구한다.

## 프로젝트 구조

- `app/core`
  커스텀 hash table 구현
- `app/engine`
  Redis 핵심 동작
  `SET/GET/DEL`, `INCR/DECR`, TTL, namespace invalidation
- `app/persistence`
  Snapshot + AOF 영속성 계층
- `app/storefront`
  상품 카탈로그와 드롭 데모 서비스 로직
- `app/api`
  FastAPI 라우터
- `frontend`
  발표용 정적 UI
- `data`
  snapshot / AOF 파일 저장 위치

## 런타임 구성

- `Frontend`
  브라우저에서 direct 조회, cache 조회, persistence 상태를 시각적으로 확인
- `FastAPI API`
  storefront API, core Redis API, admin API 제공
- `MongoDB`
  원본 상품 데이터 저장소
- `Mini Redis`
  상품 상세 캐시, 재고 카운터, TTL 홀드, invalidate, snapshot/AOF 복구 담당

## 빠른 실행

### 1. 로컬 백엔드만 실행

```bash
make install
make run
```

접속:

- API docs: `http://127.0.0.1:8000/docs`

### 2. 발표용 전체 스택 실행

```bash
make docker-up
```

접속:

- Frontend: `http://127.0.0.1:8080`
- API docs: `http://127.0.0.1:8000/docs`

종료:

```bash
make docker-down
```

## 데모에서 보여주는 기능

### Storefront 시나리오

- `GET /store/products`
  상품 목록 조회
- `GET /store/products/{product_id}/direct`
  원본 데이터 직접 조회
- `GET /store/products/{product_id}/cached`
  Mini Redis 캐시 경유 조회
- `POST /store/products/{product_id}/reserve`
  TTL 홀드 생성
- `POST /store/products/{product_id}/purchase`
  재고 감소
- `POST /store/products/{product_id}/restock`
  재고 증가
- `POST /store/products/{product_id}/invalidate`
  캐시 무효화
- `GET /store/state`
  snapshot/AOF 상태와 현재 persistence 정보 조회

### Core Redis API

- `PUT /kv/{key}`
- `GET /kv/{key}`
- `DELETE /kv/{key}`
- `POST /kv/{key}/incr`
- `POST /kv/{key}/decr`
- `POST /namespaces/{namespace}/invalidate`
- `POST /admin/snapshot`

### Persistence Demo API

- `GET /admin/persistence-demo`
  persistence 데모용 레코드 상태 확인
- `POST /admin/persistence-demo/write`
  crash 전에 남겨둘 값을 Mini Redis에 기록
- `POST /admin/persistence-demo/crash`
  강제 종료 시연용 엔드포인트

## 영속성 방식

이 프로젝트는 Snapshot + AOF 하이브리드 영속성을 사용합니다.

- Snapshot
  현재 Mini Redis 메모리 상태 전체를 파일로 저장
- AOF
  snapshot 이후에 발생한 변경 연산만 순차 기록
- startup
  `snapshot load -> AOF replay`
- shutdown
  `snapshot save -> post-snapshot AOF rewrite`

파일 위치:

- Snapshot: `data/snapshot.json`
- AOF: `data/appendonly.aof.jsonl`

## 벤치마크

storefront direct/cache 기준:

```bash
python3 scripts/bench.py --base-url http://127.0.0.1:8000 --requests 20
```

synthetic demo endpoint 기준:

```bash
python3 scripts/bench.py \
  --base-url http://127.0.0.1:8000 \
  --scenario demo \
  --requests 20
```

## 품질 확인

```bash
make lint
make typecheck
make test
```

## 참고

- MongoDB 연결이 안 되면 seed 상품 카탈로그로 자동 fallback 합니다.
- direct 경로는 원본 데이터를 읽고, cached hit 경로는 Mini Redis payload만 사용합니다.
- Mini Redis 내부 값은 문자열 기반이며, 상품 상세 캐시는 JSON 문자열로 직렬화해 저장합니다.
