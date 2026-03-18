import os
from dataclasses import dataclass
from functools import lru_cache
from typing import cast

from app.persistence.aof import AppendFsyncMode, RecoveryMode


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    app_version: str
    snapshot_path: str
    aof_path: str
    aof_fsync: AppendFsyncMode
    aof_recovery_mode: RecoveryMode
    enable_demo_crash: bool
    mongo_uri: str
    mongo_database: str
    mongo_collection: str
    storefront_seed_path: str
    storefront_origin_delay_ms: int


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("MINI_REDIS_APP_NAME", "mini-redis"),
        app_version=os.getenv("MINI_REDIS_APP_VERSION", "0.1.0"),
        snapshot_path=os.getenv("MINI_REDIS_SNAPSHOT_PATH", "data/snapshot.json"),
        aof_path=os.getenv("MINI_REDIS_AOF_PATH", "data/appendonly.aof.jsonl"),
        aof_fsync=_parse_fsync_mode(os.getenv("MINI_REDIS_AOF_FSYNC", "everysec")),
        aof_recovery_mode=_parse_recovery_mode(
            os.getenv("MINI_REDIS_AOF_RECOVERY_MODE", "truncate")
        ),
        enable_demo_crash=_parse_bool(os.getenv("MINI_REDIS_ENABLE_DEMO_CRASH", "false")),
        mongo_uri=os.getenv("MINI_REDIS_MONGO_URI", ""),
        mongo_database=os.getenv("MINI_REDIS_MONGO_DATABASE", "mini_redis_demo"),
        mongo_collection=os.getenv("MINI_REDIS_MONGO_COLLECTION", "products"),
        storefront_seed_path=os.getenv(
            "MINI_REDIS_STOREFRONT_SEED_PATH",
            "app/storefront/seed_products.json",
        ),
        storefront_origin_delay_ms=int(os.getenv("MINI_REDIS_STOREFRONT_ORIGIN_DELAY_MS", "140")),
    )


def _parse_fsync_mode(value: str) -> AppendFsyncMode:
    if value not in {"always", "everysec", "no"}:
        raise ValueError(f"Unsupported MINI_REDIS_AOF_FSYNC: {value}")
    return cast(AppendFsyncMode, value)


def _parse_recovery_mode(value: str) -> RecoveryMode:
    if value not in {"strict", "truncate"}:
        raise ValueError(f"Unsupported MINI_REDIS_AOF_RECOVERY_MODE: {value}")
    return cast(RecoveryMode, value)


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}
