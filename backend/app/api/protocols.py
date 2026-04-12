"""Protocol management API routes."""

import json
from fastapi import APIRouter, Query

from app.core.service_registry import registry
from app.core.exceptions import AppError, ERROR_NOT_FOUND
from app.models.response import success
from app.protocols.base import ProtocolManager

router = APIRouter(prefix="/api/protocols", tags=["协议管理"])


def _get_mgr() -> ProtocolManager:
    return registry.get("protocol_manager")


@router.get("")
async def list_protocols():
    mgr = _get_mgr()
    return success(mgr.status_all())


@router.post("/{protocolName}/start")
async def start_protocol(protocolName: str):
    mgr = _get_mgr()
    await mgr.start_plugin(protocolName)
    return success(mgr.get_plugin(protocolName).status())


@router.post("/{protocolName}/stop")
async def stop_protocol(protocolName: str):
    mgr = _get_mgr()
    await mgr.stop_plugin(protocolName)
    return success(mgr.get_plugin(protocolName).status())


@router.post("/{protocolName}/restart")
async def restart_protocol(protocolName: str):
    mgr = _get_mgr()
    await mgr.restart_plugin(protocolName)
    return success(mgr.get_plugin(protocolName).status())


@router.get("/{protocolName}/health")
async def health_check(protocolName: str):
    mgr = _get_mgr()
    plugin = mgr.get_plugin(protocolName)
    if not plugin:
        raise AppError(ERROR_NOT_FOUND, f"协议 '{protocolName}' 不存在", status_code=404)
    return success(plugin.health_check())


@router.post("/start-all")
async def start_all():
    mgr = _get_mgr()
    await mgr.start_all()
    return success(mgr.status_all())


@router.post("/stop-all")
async def stop_all():
    mgr = _get_mgr()
    await mgr.stop_all()
    return success(mgr.status_all())


# ---- HTTP Mock specific ----

@router.get("/http-mock/config")
async def get_mock_config():
    from app.protocols.http_mock.server import HttpMockServer
    mgr = _get_mgr()
    plugin: HttpMockServer = mgr.get_plugin("http-mock")
    if not plugin:
        raise AppError(ERROR_NOT_FOUND, "http-mock 插件未注册", status_code=404)
    return success({"host": plugin._host, "port": plugin._port})


@router.put("/http-mock/config")
async def update_mock_config(body: dict):
    # Update protocol config in DB
    dal = registry.get("dal")
    config = json.dumps(body, ensure_ascii=False)
    await dal.persist.execute(
        "UPDATE protocol_configs SET config = ?, updated_at = datetime('now') WHERE name = 'http-mock'",
        (config,),
    )
    await dal.persist.commit()
    return success(body)


@router.get("/http-mock/routes")
async def list_routes():
    from app.protocols.http_mock.server import HttpMockServer
    mgr = _get_mgr()
    plugin: HttpMockServer = mgr.get_plugin("http-mock")
    if not plugin:
        raise AppError(ERROR_NOT_FOUND, "http-mock 插件未注册", status_code=404)
    routes = plugin.dispatcher.list_routes()
    return success({"items": routes, "total": len(routes)})


# ---- Request Logs ----

@router.get("/http-mock/logs")
async def list_request_logs(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    method: str | None = None,
    path: str | None = None,
):
    from app.protocols.http_mock.server import HttpMockServer
    mgr = _get_mgr()
    plugin: HttpMockServer = mgr.get_plugin("http-mock")
    if not plugin:
        raise AppError(ERROR_NOT_FOUND, "http-mock 插件未注册", status_code=404)
    result = await plugin.request_logger.list_logs(limit=limit, offset=offset, method=method, path=path)
    return success(result)


@router.delete("/http-mock/logs")
async def clear_request_logs():
    from app.protocols.http_mock.server import HttpMockServer
    mgr = _get_mgr()
    plugin: HttpMockServer = mgr.get_plugin("http-mock")
    if not plugin:
        raise AppError(ERROR_NOT_FOUND, "http-mock 插件未注册", status_code=404)
    count = await plugin.request_logger.clear_logs()
    return success({"deleted": count})
