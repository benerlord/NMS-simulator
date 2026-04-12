"""System settings API routes."""

from fastapi import APIRouter

from app.core.service_registry import registry
from app.models.response import success
from app.dal.base import DAL

router = APIRouter(prefix="/api/settings", tags=["系统设置"])


def _get_dal() -> DAL:
    return registry.get("dal")


@router.get("")
async def list_settings(category: str | None = None):
    dal = _get_dal()
    if category:
        rows = await dal.persist.fetch_all(
            "SELECT * FROM system_settings WHERE category = ? ORDER BY key", (category,)
        )
    else:
        rows = await dal.persist.fetch_all(
            "SELECT * FROM system_settings ORDER BY category, key"
        )
    return success({"items": [dict(r) for r in rows]})


@router.put("/{key}")
async def update_setting(key: str, body: dict):
    dal = _get_dal()
    row = await dal.persist.fetch_one(
        "SELECT * FROM system_settings WHERE key = ?", (key,)
    )
    if not row:
        from app.core.exceptions import AppError, ERROR_NOT_FOUND
        raise AppError(ERROR_NOT_FOUND, f"设置项 '{key}' 不存在", status_code=404)

    value = body.get("value")
    if value is None:
        value = row["value"]

    await dal.persist.execute(
        "UPDATE system_settings SET value = ?, updated_at = datetime('now') WHERE key = ?",
        (str(value), key),
    )
    await dal.persist.commit()
    updated = await dal.persist.fetch_one(
        "SELECT * FROM system_settings WHERE key = ?", (key,)
    )
    return success(dict(updated))


@router.put("")
async def batch_update_settings(body: dict):
    dal = _get_dal()
    settings_list = body.get("settings", [])
    updated = 0
    for item in settings_list:
        key = item.get("key")
        value = item.get("value")
        if key and value is not None:
            await dal.persist.execute(
                "UPDATE system_settings SET value = ?, updated_at = datetime('now') WHERE key = ?",
                (str(value), key),
            )
            updated += 1
    await dal.persist.commit()
    return success({"updated": updated})
