"""Session / Token management routes."""

from fastapi import APIRouter

from app.core.service_registry import registry
from app.models.response import success
from app.services.session_manager import SessionManager

router = APIRouter(prefix="/api/sessions", tags=["Token 认证"])


def _get_mgr() -> SessionManager:
    return registry.get("session_manager")


@router.get("")
async def list_sessions():
    mgr = _get_mgr()
    tokens = mgr.list_tokens()
    return success({"items": tokens, "total": len(tokens)})


@router.delete("/{token:path}")
async def delete_session(token: str):
    mgr = _get_mgr()
    mgr.invalidate_token(token)
    return success()


@router.delete("")
async def clear_sessions():
    mgr = _get_mgr()
    mgr.clear_tokens()
    return success()


@router.get("/config")
async def get_config():
    mgr = _get_mgr()
    config = await mgr.get_config()
    return success(config)


@router.put("/config")
async def update_config(body: dict):
    mgr = _get_mgr()
    config = await mgr.update_config(body)
    return success(config)
