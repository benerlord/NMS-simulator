"""API router aggregation."""

from fastapi import APIRouter

from app.api.topologies import router as topologies_router
from app.api.device_types import router as device_types_router
from app.api.api_configs import router as api_configs_router
from app.api.sessions import router as sessions_router
from app.api.protocols import router as protocols_router
from app.api.settings import router as settings_router

api_router = APIRouter()
api_router.include_router(topologies_router)
api_router.include_router(device_types_router)
api_router.include_router(api_configs_router)
api_router.include_router(sessions_router)
api_router.include_router(protocols_router)
api_router.include_router(settings_router)
