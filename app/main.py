from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.config import get_settings
from app.core import HashTable
from app.domain.models import StoreRecord
from app.engine import StoreEngine
from app.persistence import (
    configure_aof_service,
    configure_snapshot_service,
    snapshot_lifespan,
    snapshot_status,
)
from app.storefront import StorefrontService, build_product_catalog


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=snapshot_lifespan,
    )
    # Mini Redis의 실제 저장소는 프로세스 메모리에 생성된다.
    # 모든 API 요청은 app.state.store를 통해 같은 StoreEngine 인스턴스를 공유한다.
    table: HashTable[StoreRecord] = HashTable()
    # AOF는 flush 정책과 손상 복구 정책을 설정값으로 받아 생성한다.
    aof_service = configure_aof_service(
        app,
        settings.aof_path,
        fsync_mode=settings.aof_fsync,
        recovery_mode=settings.aof_recovery_mode,
    )
    app.state.store = StoreEngine(table=table, mutation_logger=aof_service.append_event)
    app.state.product_catalog = build_product_catalog(
        mongo_uri=settings.mongo_uri,
        database_name=settings.mongo_database,
        collection_name=settings.mongo_collection,
        seed_path=settings.storefront_seed_path,
    )
    # snapshot persistence를 별도로 붙여서
    # 메모리 store 상태를 파일로 저장하고 재시작 시 복구할 수 있게 한다.
    configure_snapshot_service(app, settings.snapshot_path, after_save=aof_service.rewrite_after)
    app.state.storefront_service = StorefrontService(
        store=app.state.store,
        catalog=app.state.product_catalog,
        snapshot_status_provider=lambda: snapshot_status(app),
        origin_delay_ms=settings.storefront_origin_delay_ms,
    )
    app.include_router(api_router)
    frontend_dir = Path("frontend")
    if frontend_dir.exists():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    return app


app = create_app()
