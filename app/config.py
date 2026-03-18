import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    app_version: str
    snapshot_path: str


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("MINI_REDIS_APP_NAME", "mini-redis"),
        app_version=os.getenv("MINI_REDIS_APP_VERSION", "0.1.0"),
        snapshot_path=os.getenv("MINI_REDIS_SNAPSHOT_PATH", "data/snapshot.json"),
    )
