"""FastAPI application entry point."""

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.config import settings
from app.core.exceptions import AppError, register_exception_handlers
from app.core.service_registry import registry
from app.api.router import api_router
from app.dal.base import DAL
from app.dal.memory_store import MemoryStore
from app.dal.persist_store import PersistStore
from app.services.topology_manager import TopologyManager
from app.services.config_manager import ConfigManager
from app.services.session_manager import SessionManager
from app.protocols.base import ProtocolManager
from app.protocols.http_mock.server import HttpMockServer


def setup_logging() -> None:
    """Configure loguru logging."""
    logger.remove()

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # Console output
    logger.add(
        sys.stderr,
        format=log_format,
        level=settings.log_level,
        colorize=True,
    )

    # File output
    logger.add(
        f"{settings.log_dir}/nms_{{time:YYYY-MM-DD}}.log",
        format=log_format,
        level=settings.log_level,
        rotation="00:00",
        retention="30 days",
        encoding="utf-8",
    )


def setup_services() -> None:
    """Register all services into the ServiceRegistry.

    DAL owns PersistStore and MemoryStore lifecycles, so we only
    register DAL as a service (it starts/stops its children).
    We still register persist/memory for DI lookup but not as services.
    """
    persist = PersistStore()
    memory = MemoryStore()
    dal = DAL(persist, memory)

    registry.register("dal", dal)

    topo_mgr = TopologyManager(memory)
    registry.register("topology_manager", topo_mgr)

    config_mgr = ConfigManager(dal)
    registry.register("config_manager", config_mgr)

    session_mgr = SessionManager(dal)
    registry.register("session_manager", session_mgr)

    # Protocol plugins
    proto_mgr = ProtocolManager()
    http_mock = HttpMockServer(
        dal=dal, memory=memory,
        config_manager=config_mgr, session_manager=session_mgr,
        host=settings.host, port=settings.mock_port,
    )
    proto_mgr.register_plugin("http-mock", http_mock)
    registry.register("protocol_manager", proto_mgr)
    registry.register("query_pipeline", http_mock.pipeline)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    setup_logging()
    logger.info("NMS Simulator starting up...")
    logger.info(f"Management API: http://{settings.host}:{settings.port}")
    logger.info(f"Log level: {settings.log_level}")

    setup_services()
    await registry.start_all()

    # Load active topology into memory if one exists
    dal: DAL = registry.get("dal")
    topo_mgr: TopologyManager = registry.get("topology_manager")
    active_topo = await dal.get_active_topology()
    if active_topo:
        topo = await dal.load_topology(active_topo["id"])
        if topo:
            import json
            data = json.loads(topo["data"]) if isinstance(topo["data"], str) else topo["data"]
            topo_mgr.load_data(data)

    yield

    await registry.stop_all()
    logger.info("NMS Simulator shut down.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# Register exception handlers
register_exception_handlers(app)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include API routes
app.include_router(api_router)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}



if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
