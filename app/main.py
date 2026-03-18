from fastapi import FastAPI

from app.api.router import api_router
from app.config import get_settings
from app.core import HashTable
from app.domain.models import StoreRecord
from app.engine import StoreEngine
from app.persistence import configure_aof_service, configure_snapshot_service, snapshot_lifespan


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
    aof_service = configure_aof_service(app, settings.aof_path)
    app.state.store = StoreEngine(table=table, mutation_logger=aof_service.append_event)
    # snapshot persistence를 별도로 붙여서
    # 메모리 store 상태를 파일로 저장하고 재시작 시 복구할 수 있게 한다.
    configure_snapshot_service(app, settings.snapshot_path, after_save=aof_service.reset)
    app.include_router(api_router)
    return app


app = create_app()
