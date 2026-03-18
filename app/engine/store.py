import threading
import time
from collections.abc import Callable
from typing import Any, Literal

from app.domain.contracts import HashTableProtocol
from app.domain.models import SnapshotEntry, SnapshotPayload, StoreRecord

# 엔진이 내부 조회 결과를 어떻게 해석했는지 표현하는 상태값이다.
# - missing: 아예 값이 없음
# - expired: TTL 기준으로 이미 만료됨
# - stale: namespace version 기준으로 오래된 값이 됨
# - live: 지금 시점에서 정상적으로 사용할 수 있는 값
RecordState = Literal["missing", "expired", "stale", "live"]


class CounterValueError(ValueError):
    """Raised when counter operations are applied to a non-integer value."""


class StoreEngine:
    # StoreEngine은 A 파트의 HashTable 위에서 실제 "저장소 의미론"을 구현한다.
    # 즉, 단순 put/get 래퍼가 아니라 다음 규칙을 한곳에서 책임진다.
    # - 동시성 제어(global lock)
    # - TTL 만료 판정
    # - namespace invalidation
    # - incr/decr 같은 read-modify-write 연산
    # - snapshot export/import
    def __init__(
        self,
        table: HashTableProtocol[StoreRecord],
        now_ms: Callable[[], int] | None = None,
        mutation_logger: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        # 실제 저장은 외부에서 주입받은 HashTableProtocol 구현체에 위임한다.
        self._table = table
        # now_ms를 주입 가능하게 만든 이유는 테스트에서 시간을 고정/전진시키기 쉽도록 하기 위해서다.
        self._now_ms = now_ms or self._default_now_ms
        # namespace별 현재 버전 정보를 저장한다.
        # invalidate_namespace()가 호출되면 이 버전만 증가시키고,
        # 기존 레코드는 접근 시 stale인지 판단해 정리한다.
        self._namespace_versions: dict[str, int] = {}
        # StoreEngine 전체를 보호하는 전역 락이다.
        # set/get/incr/export_snapshot 등 모든 주요 연산은 이 락 아래에서 직렬화된다.
        self._lock = threading.RLock()
        self._mutation_logger = mutation_logger
        self._mutation_seq = 0

    def set(
        self,
        key: str,
        value_str: str,
        ttl_ms: int | None = None,
        namespace: str = "default",
    ) -> StoreRecord:
        with self._lock:
            # 현재 시각을 먼저 읽어두면 같은 연산 안에서
            # created/updated/ttl 계산을 일관되게 처리할 수 있다.
            now_ms = self._now_ms()
            # 내부 저장은 (namespace, key)를 합친 storage key 기준으로 한다.
            # 그래야 같은 key 이름이라도 namespace가 다르면 충돌 없이 공존할 수 있다.
            storage_key = self._storage_key(namespace, key)
            # 새 레코드는 "현재 namespace의 최신 버전"으로 저장되어야 한다.
            current_version = self._current_namespace_version(namespace)
            # 같은 위치에 기존 레코드가 있더라도,
            # 만료/무효화 상태라면 먼저 정리된 뒤 새 값이 들어간다.
            existing, state = self._read_record(storage_key, namespace, now_ms)
            # live overwrite인 경우에만 created_at을 유지한다.
            # 즉 "같은 살아있는 키를 덮어쓴 것"이면 생성 시각은 그대로 두고,
            # 그 외에는 지금 시각을 새 생성 시각으로 삼는다.
            created_at_ms = (
                existing.created_at_ms
                if state == "live" and existing is not None
                else now_ms
            )
            # TTL이 주어지면 절대 만료 시각(expires_at_ms)을 계산해서 저장한다.
            # ttl_ms 자체를 저장하는 게 아니라 "언제 만료되는지"를 미리 기록해둔다.
            record = StoreRecord(
                key=key,
                value_str=value_str,
                namespace=namespace,
                namespace_version=current_version,
                expires_at_ms=None if ttl_ms is None else now_ms + ttl_ms,
                created_at_ms=created_at_ms,
                updated_at_ms=now_ms,
            )
            # HashTable에는 항상 storage key -> StoreRecord 형태로 저장한다.
            self._table.put(storage_key, record)
            self._emit_upsert(record)
            return record

    def get(self, key: str, namespace: str = "default") -> StoreRecord | None:
        with self._lock:
            now_ms = self._now_ms()
            storage_key = self._storage_key(namespace, key)
            # _read_record()는 단순 조회 이상의 역할을 한다.
            # 만료/무효화된 레코드를 발견하면 즉시 삭제까지 수행한 뒤 상태를 돌려준다.
            record, state = self._read_record(storage_key, namespace, now_ms)
            if state != "live":
                return None
            return record

    def delete(self, key: str, namespace: str = "default") -> bool:
        with self._lock:
            now_ms = self._now_ms()
            storage_key = self._storage_key(namespace, key)
            # delete 역시 먼저 레코드 상태를 확인한다.
            # 만약 expired/stale라면 이미 _read_record() 안에서 정리되므로 False를 반환한다.
            _, state = self._read_record(storage_key, namespace, now_ms)
            if state != "live":
                return False
            deleted = self._table.delete(storage_key)
            if deleted:
                self._emit_delete(key=key, namespace=namespace, ts_ms=now_ms)
            return deleted

    def incr(self, key: str, amount: int = 1, namespace: str = "default") -> int:
        # incr/decr는 공통적으로 "현재 값을 읽고, 계산하고, 다시 저장"하는
        # read-modify-write 패턴이므로 하나의 helper로 모아 처리한다.
        return self._apply_delta(key=key, amount=amount, namespace=namespace)

    def decr(self, key: str, amount: int = 1, namespace: str = "default") -> int:
        # decr는 amount를 음수로 바꿔 동일한 helper에 위임한다.
        return self._apply_delta(key=key, amount=-amount, namespace=namespace)

    def invalidate_namespace(self, namespace: str) -> int:
        with self._lock:
            # 이 메서드는 같은 namespace의 기존 키들을 즉시 전부 삭제하지 않는다.
            # 대신 버전만 1 올려서 "이전 버전 레코드는 이제 stale"이라고 표시한다.
            # 실제 stale 레코드 삭제는 이후 접근 시 lazy하게 일어난다.
            next_version = self._current_namespace_version(namespace) + 1
            self._namespace_versions[namespace] = next_version
            self._emit_invalidate(namespace=namespace, version=next_version, ts_ms=self._now_ms())
            return next_version

    def export_snapshot(self) -> SnapshotPayload:
        snapshot, _ = self.export_snapshot_with_marker()
        return snapshot

    def export_snapshot_with_marker(self) -> tuple[SnapshotPayload, int]:
        with self._lock:
            # 스냅샷 시점의 시간을 saved_at_ms에 남긴다.
            saved_at_ms = self._now_ms()
            entries: list[SnapshotEntry] = []
            for _, record in self._table.items():
                # 이미 TTL이 만료된 값은 스냅샷에 싣지 않는다.
                if self._is_expired(record, saved_at_ms):
                    continue
                # namespace invalidation으로 stale해진 값도 스냅샷에서 제외한다.
                if self._is_stale(record):
                    continue
                # live 레코드만 SnapshotEntry로 복사해 payload에 담는다.
                # 즉, 스냅샷은 현재 시점에 "유효한 데이터만" 보존하려는 의도다.
                entries.append(
                    SnapshotEntry(
                        key=record.key,
                        value_str=record.value_str,
                        namespace=record.namespace,
                        namespace_version=record.namespace_version,
                        expires_at_ms=record.expires_at_ms,
                        created_at_ms=record.created_at_ms,
                        updated_at_ms=record.updated_at_ms,
                    )
                )
            # payload에는 엔트리뿐 아니라 namespace 버전 정보도 함께 담는다.
            # 그래야 import 시 invalidation 상태까지 같이 복원할 수 있다.
            return (
                SnapshotPayload(
                    version=1,
                    saved_at_ms=saved_at_ms,
                    namespace_versions=dict(self._namespace_versions),
                    entries=entries,
                ),
                # marker는 스냅샷 시점까지 반영된 mutation 순번이다.
                # 이후 persistence/AOF 계층에서 증분 반영 기준점으로 사용할 수 있다.
                self._mutation_seq,
            )

    def import_snapshot(self, snapshot: SnapshotPayload) -> None:
        with self._lock:
            # import는 "기존 상태에 덧붙이기"가 아니라 "현재 상태를 통째로 교체"하는 동작이다.
            # 그래서 먼저 기존 테이블 내용을 전부 삭제한다.
            for storage_key, _ in list(self._table.items()):
                self._table.delete(storage_key)
            # namespace version도 snapshot 기준으로 갈아끼운다.
            self._namespace_versions = dict(snapshot.namespace_versions)
            for entry in snapshot.entries:
                # snapshot의 각 항목을 다시 StoreRecord로 복원해 해시테이블에 적재한다.
                self._table.put(
                    self._storage_key(entry.namespace, entry.key),
                    StoreRecord(
                        key=entry.key,
                        value_str=entry.value_str,
                        namespace=entry.namespace,
                        namespace_version=entry.namespace_version,
                        expires_at_ms=entry.expires_at_ms,
                        created_at_ms=entry.created_at_ms,
                        updated_at_ms=entry.updated_at_ms,
                    ),
                )

    def cleanup_expired(self, limit: int | None = None) -> int:
        with self._lock:
            # 0 이하 limit은 "아무 것도 지우지 않음"으로 처리한다.
            if limit is not None and limit <= 0:
                return 0

            now_ms = self._now_ms()
            expired_keys: list[str] = []
            # 순회 중에 바로 delete를 섞기보다, 먼저 만료된 storage key 목록을 모은다.
            # 이렇게 하면 iteration 도중 구조가 바뀌는 위험을 줄이고,
            # 삭제 개수 제한(limit)도 한곳에서 깔끔하게 적용할 수 있다.
            for storage_key, record in self._table.items():
                if not self._is_expired(record, now_ms):
                    continue
                expired_keys.append(storage_key)
                if limit is not None and len(expired_keys) >= limit:
                    break

            deleted_count = 0
            for storage_key in expired_keys:
                if self._table.delete(storage_key):
                    deleted_count += 1
            return deleted_count

    @staticmethod
    def _default_now_ms() -> int:
        # 엔진 전체에서 사용하는 기본 시간 단위는 millisecond다.
        return time.time_ns() // 1_000_000

    @staticmethod
    def _storage_key(namespace: str, key: str) -> str:
        # 단순히 f"{namespace}:{key}"로 합치는 대신 길이 정보를 같이 넣는다.
        # 이렇게 하면 경계가 모호해지는 문자열 충돌 가능성을 줄일 수 있다.
        return f"{len(namespace)}:{namespace}{len(key)}:{key}"

    def _current_namespace_version(self, namespace: str) -> int:
        # 아직 한 번도 invalidate된 적 없는 namespace는 기본 버전 0으로 본다.
        return self._namespace_versions.get(namespace, 0)

    def _is_stale(self, record: StoreRecord) -> bool:
        # 레코드가 저장될 당시의 namespace version이
        # 현재 namespace의 최신 version보다 낮으면 stale이다.
        return record.namespace_version < self._current_namespace_version(record.namespace)

    @staticmethod
    def _is_expired(record: StoreRecord, now_ms: int) -> bool:
        # expires_at_ms가 없으면 만료 없는 값이고,
        # 있으면 현재 시각과 비교해 이미 만료됐는지 판단한다.
        return record.expires_at_ms is not None and record.expires_at_ms <= now_ms

    def _read_record(
        self,
        storage_key: str,
        namespace: str,
        now_ms: int,
    ) -> tuple[StoreRecord | None, RecordState]:
        # _read_record()는 엔진의 "정상 조회 + 정리"를 담당하는 핵심 helper다.
        # 단순히 값을 읽는 데서 끝나지 않고, expired/stale를 발견하면 즉시 삭제한다.
        record = self._table.get(storage_key)
        if record is None:
            return None, "missing"
        if self._is_expired(record, now_ms):
            # lazy expiration: 읽는 순간 만료를 발견하면 바로 지우고 miss 처리한다.
            self._table.delete(storage_key)
            return None, "expired"
        if record.namespace != namespace or self._is_stale(record):
            # storage key 설계상 namespace mismatch는 사실상 거의 발생하지 않아야 하지만,
            # 방어적으로 확인해두면 잘못된 레코드도 stale과 동일하게 정리할 수 있다.
            self._table.delete(storage_key)
            return None, "stale"
        return record, "live"

    def _apply_delta(self, key: str, amount: int, namespace: str) -> int:
        with self._lock:
            # incr/decr는 읽고-계산하고-다시 저장하는 연산이므로
            # 반드시 하나의 락 구간 안에서 끝까지 처리돼야 값이 꼬이지 않는다.
            now_ms = self._now_ms()
            storage_key = self._storage_key(namespace, key)
            current_version = self._current_namespace_version(namespace)
            record, state = self._read_record(storage_key, namespace, now_ms)

            if state == "live" and record is not None:
                try:
                    # 저장 형식은 문자열이지만, 카운터 연산 시에는 정수로 해석 가능해야 한다.
                    current_value = int(record.value_str)
                except ValueError as exc:
                    raise CounterValueError(f"Value for key '{key}' is not an integer") from exc
                next_value = current_value + amount
                # live 레코드를 갱신하는 경우에는 기존 TTL과 created_at을 유지한다.
                next_record = StoreRecord(
                    key=key,
                    value_str=str(next_value),
                    namespace=namespace,
                    namespace_version=current_version,
                    expires_at_ms=record.expires_at_ms,
                    created_at_ms=record.created_at_ms,
                    updated_at_ms=now_ms,
                )
            else:
                # missing/expired/stale은 모두 "지금 사용할 수 있는 값이 없음"으로 보고
                # 0에서 시작하는 새 카운터를 만든다.
                next_value = amount
                next_record = StoreRecord(
                    key=key,
                    value_str=str(next_value),
                    namespace=namespace,
                    namespace_version=current_version,
                    # recreate-on-miss에서는 TTL을 이어받지 않고 새 값으로 시작한다.
                    expires_at_ms=None,
                    created_at_ms=now_ms,
                    updated_at_ms=now_ms,
                )

            # 계산 결과를 다시 저장하고, API 계층에서 바로 쓸 수 있도록 정수 결과를 반환한다.
            self._table.put(storage_key, next_record)
            self._emit_upsert(next_record)
            return next_value

    def _emit_upsert(self, record: StoreRecord) -> None:
        self._emit_mutation(
            {
                "op": "upsert",
                "ts_ms": record.updated_at_ms,
                "record": {
                    "key": record.key,
                    "value_str": record.value_str,
                    "namespace": record.namespace,
                    "namespace_version": record.namespace_version,
                    "expires_at_ms": record.expires_at_ms,
                    "created_at_ms": record.created_at_ms,
                    "updated_at_ms": record.updated_at_ms,
                },
            }
        )

    def _emit_delete(self, key: str, namespace: str, ts_ms: int) -> None:
        self._emit_mutation(
            {
                "op": "delete",
                "ts_ms": ts_ms,
                "key": key,
                "namespace": namespace,
            }
        )

    def _emit_invalidate(self, namespace: str, version: int, ts_ms: int) -> None:
        self._emit_mutation(
            {
                "op": "invalidate",
                "ts_ms": ts_ms,
                "namespace": namespace,
                "version": version,
            }
        )

    def _emit_mutation(self, event: dict[str, Any]) -> None:
        if self._mutation_logger is not None:
            self._mutation_seq += 1
            event["seq"] = self._mutation_seq
            self._mutation_logger(event)
