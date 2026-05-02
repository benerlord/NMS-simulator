from datetime import datetime
from typing import Any, Optional

from pydantic import Field

from ._base import CamelModel


class SettingItem(CamelModel):
    key: str
    value: Any
    updated_at: Optional[datetime] = None


class SettingsRuntime(CamelModel):
    """Read-only env/process info shown for ops awareness."""

    app_host: str
    app_port: int
    log_level: str
    db_path: str
    ssl_enabled: bool = False


class SettingsData(CamelModel):
    items: list[SettingItem]
    runtime: SettingsRuntime


class SettingsResponse(CamelModel):
    code: int = 0
    data: SettingsData
    message: str = "ok"


class SettingItemResponse(CamelModel):
    code: int = 0
    data: SettingItem
    message: str = "ok"


class SettingsUpdate(CamelModel):
    autosave_interval: Optional[int] = Field(default=None, ge=5, le=3600)
    mock_path_prefix: Optional[str] = Field(default=None, max_length=200)
