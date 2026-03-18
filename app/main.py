from fastapi import FastAPI

from app.api.router import api_router
from app.config import get_settings
from app.core import HashTable
from app.domain.models import StoreRecord
from app.engine import StoreEngine
from app.persistence import configure_snapshot_service, snapshot_lifespan


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=snapshot_lifespan,
    )
    table: HashTable[StoreRecord] = HashTable()
    app.state.store = StoreEngine(table=table)
    configure_snapshot_service(app, settings.snapshot_path)
    app.include_router(api_router)
    return app


app = create_app()
