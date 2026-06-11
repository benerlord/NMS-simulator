import atexit
from contextlib import asynccontextmanager
from typing import Optional

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
from app.admin.node_group import router as node_group_router
from app.admin.alarm_schema import router as alarm_schema_router
from app.admin.node_alarm import router as node_alarm_router
from app.admin.node_fields import router as node_fields_router
from app.admin.domain import router as domain_router
from app.admin.mock_instance import router as mock_instance_router
from app.core.config import settings
from app.core.instance_runner import InstanceRunner
from app.core.ws_hub import router as ws_router
from app.db.connection import init_db
from app.mock.registry import registry as mock_registry

_runner: Optional[InstanceRunner] = None


def _cleanup():
    if _runner:
        _runner.shutdown_all()


atexit.register(_cleanup)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _runner
    init_db()
    mock_registry.bind(app)
    mock_registry.load_all()

    _runner = InstanceRunner()
    _runner.start_monitor()
    app.state.instance_runner = _runner

    yield

    _cleanup()


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
app.include_router(node_group_router)
app.include_router(alarm_schema_router)
app.include_router(node_alarm_router)
app.include_router(node_fields_router)
app.include_router(domain_router)
app.include_router(mock_instance_router)
app.include_router(ws_router)


def main() -> None:
    import uvicorn

    kwargs: dict = {}

    if settings.ssl_enabled:
        from app.core.cert_utils import ensure_cert

        certfile, keyfile = ensure_cert(settings.ssl_certfile, settings.ssl_keyfile)
        kwargs["ssl_certfile"] = certfile
        kwargs["ssl_keyfile"] = keyfile
        if settings.ssl_keyfile_password:
            kwargs["ssl_keyfile_password"] = settings.ssl_keyfile_password
        print(f"  protocol  = HTTPS (self-signed cert)")
        print(f"  certfile  = {certfile}")

    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        log_level=settings.log_level.lower(),
        **kwargs,
    )


if __name__ == "__main__":
    main()
