"""API config management routes."""

import json
from fastapi import APIRouter, Query, UploadFile, File
from fastapi.responses import JSONResponse

from app.core.service_registry import registry
from app.models.response import success
from app.services.config_manager import ConfigManager

router = APIRouter(prefix="/api/api-configs", tags=["接口配置"])


def _get_mgr() -> ConfigManager:
    return registry.get("config_manager")


@router.get("")
async def list_configs(
    keyword: str | None = None,
    group: str | None = None,
    enabled: bool | None = None,
    dataSourceType: str | None = None,
):
    mgr = _get_mgr()
    configs = await mgr.list_configs(keyword=keyword, group=group, enabled=enabled, data_source_type=dataSourceType)
    return success({"items": configs, "total": len(configs)})


@router.get("/groups")
async def list_groups():
    mgr = _get_mgr()
    groups = await mgr.list_groups()
    return success(groups)


@router.get("/default-sql/{collection}")
async def get_default_sql(collection: str):
    mgr = _get_mgr()
    result = mgr.get_default_sql(collection)
    if not result:
        return success({"collection": collection, "sql": f"SELECT * FROM {collection}", "description": "默认查询"})
    return success(result)


@router.get("/export")
async def export_configs(group: str | None = None):
    mgr = _get_mgr()
    configs = await mgr.export_configs(group=group)
    return JSONResponse(content=configs, headers={
        "Content-Disposition": 'attachment; filename="api_configs.json"'
    })


@router.post("/import")
async def import_configs(body: dict):
    mgr = _get_mgr()
    configs = body.get("configs", [])
    overwrite = body.get("overwrite", False)
    result = await mgr.import_configs(configs, overwrite=overwrite)
    return success(result)


@router.post("")
async def create_config(body: dict):
    mgr = _get_mgr()
    config = await mgr.create_config(body)
    return success(config)


@router.get("/{configId}")
async def get_config(configId: str):
    mgr = _get_mgr()
    config = await mgr.get_config(configId)
    if not config:
        from app.core.exceptions import AppError, ERROR_NOT_FOUND
        raise AppError(ERROR_NOT_FOUND, f"配置 '{configId}' 不存在", status_code=404)
    return success(config)


@router.put("/{configId}")
async def update_config(configId: str, body: dict):
    mgr = _get_mgr()
    config = await mgr.update_config(configId, body)
    return success(config)


@router.delete("/{configId}")
async def delete_config(configId: str):
    mgr = _get_mgr()
    await mgr.delete_config(configId)
    return success()


@router.put("/{configId}/enabled")
async def toggle_enabled(configId: str, body: dict):
    mgr = _get_mgr()
    config = await mgr.set_enabled(configId, body.get("enabled", True))
    return success(config)


@router.post("/{configId}/test")
async def test_config(configId: str, body: dict):
    """Test execute an API config with given params."""
    mgr = _get_mgr()
    config = await mgr.get_config(configId)
    if not config:
        from app.core.exceptions import AppError, ERROR_NOT_FOUND
        raise AppError(ERROR_NOT_FOUND, f"配置 '{configId}' 不存在", status_code=404)

    # Delegate to query pipeline for execution
    pipeline = registry.get_optional("query_pipeline")
    if pipeline:
        import time
        start = time.time()
        result = await pipeline.execute(config, body.get("params", {}))
        duration = int((time.time() - start) * 1000)
        return success({**result, "executionTime": duration})

    return success({"message": "QueryPipeline 未就绪，请先启动 Mock Server"})
