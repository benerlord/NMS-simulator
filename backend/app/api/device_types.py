"""Device types API routes."""

from fastapi import APIRouter

from app.core.exceptions import AppError, ERROR_NOT_FOUND, ERROR_CONFLICT
from app.core.service_registry import registry
from app.dal.base import DAL
from app.models.response import success

router = APIRouter(prefix="/api/device-types", tags=["设备类型"])


def _get_dal() -> DAL:
    return registry.get("dal")


@router.get("")
async def list_device_types():
    dal = _get_dal()
    types = await dal.persist.fetch_all("SELECT * FROM device_types ORDER BY built_in DESC, name")
    return success({"items": types, "total": len(types)})


@router.post("")
async def create_device_type(body: dict):
    dal = _get_dal()
    type_id = body.get("id") or body.get("name", "").lower().replace(" ", "_")
    existing = await dal.persist.fetch_one("SELECT id FROM device_types WHERE id = ?", (type_id,))
    if existing:
        raise AppError(ERROR_CONFLICT, f"设备类型 '{type_id}' 已存在", status_code=409)
    body["id"] = type_id
    body.setdefault("built_in", 0)
    await dal.save_config("device_types", body)
    return success(body)


@router.put("/{typeId}")
async def update_device_type(typeId: str, body: dict):
    dal = _get_dal()
    existing = await dal.get_config("device_types", typeId)
    if existing is None:
        raise AppError(ERROR_NOT_FOUND, f"设备类型 '{typeId}' 不存在", status_code=404)
    if existing.get("built_in"):
        restricted = {"id", "built_in"}
        for key in restricted:
            body.pop(key, None)
    body["id"] = typeId
    await dal.save_config("device_types", {**existing, **body})
    return success(body)


@router.delete("/{typeId}")
async def delete_device_type(typeId: str):
    dal = _get_dal()
    existing = await dal.get_config("device_types", typeId)
    if existing is None:
        raise AppError(ERROR_NOT_FOUND, f"设备类型 '{typeId}' 不存在", status_code=404)
    if existing.get("built_in"):
        raise AppError(ERROR_CONFLICT, "预定义类型不可删除", status_code=409)
    # Check if any device uses this type
    topo_mgr = registry.get_optional("topology_manager")
    if topo_mgr:
        using = [d for d in topo_mgr.list_devices() if d.type == typeId]
        if using:
            raise AppError(ERROR_CONFLICT, f"有 {len(using)} 个设备正在使用此类型，无法删除", status_code=409)
    await dal.delete_config("device_types", typeId)
    return success()
