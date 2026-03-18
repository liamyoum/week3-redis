import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    app_version: str
    snapshot_path: str
    aof_path: str
    aof_fsync: str
    aof_recovery_mode: str


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("MINI_REDIS_APP_NAME", "mini-redis"),
        app_version=os.getenv("MINI_REDIS_APP_VERSION", "0.1.0"),
        snapshot_path=os.getenv("MINI_REDIS_SNAPSHOT_PATH", "data/snapshot.json"),
        aof_path=os.getenv("MINI_REDIS_AOF_PATH", "data/appendonly.aof.jsonl"),
        aof_fsync=os.getenv("MINI_REDIS_AOF_FSYNC", "everysec"),
        aof_recovery_mode=os.getenv("MINI_REDIS_AOF_RECOVERY_MODE", "truncate"),
    )
