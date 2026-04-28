from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.admin.routes import router as admin_router
from app.admin.topology import router as topology_router
from app.admin.node_type import router as node_type_router
from app.admin.node import router as node_router
from app.admin.edge import router as edge_router
from app.admin.api_config import router as api_config_router
from app.admin.sql_helper import router as sql_helper_router
from app.admin.token import router as token_router
from app.admin.settings import router as settings_router
from app.core.config import settings
from app.core.ws_hub import router as ws_router
from app.db.connection import init_db
from app.mock.registry import registry as mock_registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    mock_registry.bind(app)
    mock_registry.load_all()
    yield


app = FastAPI(title="NMS Mock", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)
app.include_router(topology_router)
app.include_router(node_type_router)
app.include_router(node_router)
app.include_router(edge_router)
app.include_router(api_config_router)
app.include_router(sql_helper_router)
app.include_router(token_router)
app.include_router(settings_router)
app.include_router(ws_router)


def main() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
