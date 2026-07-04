"""System settings admin API.

Two layers are surfaced:
- DB-backed settings (`settings` table): hot-editable keys consumed by the
  running process — currently `autosave_interval` and `mock_path_prefix`.
- Process runtime (`SettingsRuntime`): env-driven values bound at uvicorn
  startup (`app_host` / `app_port` / `log_level` / `db_path`); read-only and
  changing these requires a restart.

`mock_path_prefix` is hot-reloaded into RouteRegistry on PUT so users do not
have to bounce the server to switch prefixes.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from app.admin.schemas import (
    SettingItem,
    SettingItemResponse,
    SettingsData,
    SettingsResponse,
    SettingsRuntime,
    SettingsUpdate,
)
from app.core.config import settings as runtime_settings
from app.db.connection import connect, transaction

router = APIRouter(prefix="/admin/api", tags=["系统设置"])

_TYPED_KEYS: dict[str, type] = {
    "autosave_interval": int,
    "mock_path_prefix": str,
    "request_log_max": int,
}


def _parse_dt(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, str):
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    return val


def _coerce_value(key: str, raw: str) -> Any:
    target = _TYPED_KEYS.get(key, str)
    if target is int:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return raw
    return raw


def _row_to_item(row) -> SettingItem:
    return SettingItem(
        key=row["key"],
        value=_coerce_value(row["key"], row["value"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


def _runtime_block() -> SettingsRuntime:
    return SettingsRuntime(
        app_host=runtime_settings.app_host,
        app_port=runtime_settings.app_port,
        log_level=runtime_settings.log_level,
        db_path=str(runtime_settings.db_path),
        ssl_enabled=runtime_settings.ssl_enabled,
    )


def _validate_prefix(value: str) -> str:
    cleaned = value.strip()
    if cleaned == "":
        return ""
    if not cleaned.startswith("/"):
        raise HTTPException(
            status_code=400,
            detail={
                "code": 40001,
                "message": "mock_path_prefix 必须以 / 开头或为空",
                "details": {"value": value},
            },
        )
    if cleaned != "/" and cleaned.endswith("/"):
        cleaned = cleaned.rstrip("/")
    return cleaned


@router.get("/settings", response_model=SettingsResponse)
def list_settings() -> dict:
    with connect() as conn:
        rows = conn.execute(
            "SELECT key, value, updated_at FROM settings ORDER BY key"
        ).fetchall()
    items = [_row_to_item(r) for r in rows]
    data = SettingsData(items=items, runtime=_runtime_block())
    return {
        "code": 0,
        "data": data.model_dump(mode="json", by_alias=True),
        "message": "ok",
    }


@router.get("/settings/{key}", response_model=SettingItemResponse)
def get_setting(key: str) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT key, value, updated_at FROM settings WHERE key = ?",
            (key,),
        ).fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail={"code": 40401, "message": "Setting 不存在", "details": {"key": key}},
        )
    return {
        "code": 0,
        "data": _row_to_item(row).model_dump(mode="json", by_alias=True),
        "message": "ok",
    }


@router.put("/settings", response_model=SettingsResponse)
def update_settings(body: SettingsUpdate) -> dict:
    payload = body.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(
            status_code=400,
            detail={"code": 40002, "message": "请求体不能为空"},
        )

    if "mock_path_prefix" in payload:
        payload["mock_path_prefix"] = _validate_prefix(payload["mock_path_prefix"] or "")

    with transaction() as conn:
        for key, value in payload.items():
            stored = str(value)
            conn.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, datetime('now'))
                ON CONFLICT(key) DO UPDATE SET
                  value = excluded.value,
                  updated_at = excluded.updated_at
                """,
                (key, stored),
            )
            if key == "autosave_interval":
                runtime_settings.autosave_interval = int(stored)

    with connect() as conn:
        rows = conn.execute(
            "SELECT key, value, updated_at FROM settings ORDER BY key"
        ).fetchall()
    items = [_row_to_item(r) for r in rows]
    data = SettingsData(items=items, runtime=_runtime_block())
    return {
        "code": 0,
        "data": data.model_dump(mode="json", by_alias=True),
        "message": "ok",
    }
