"""Dynamic route dispatcher for HTTP Mock Server."""

import json
from typing import Any

from loguru import logger

from app.core.event_bus import event_bus
from app.services.config_manager import ConfigManager


class RouteDispatcher:
    """Maintains dynamic route table and dispatches requests to configs."""

    def __init__(self, config_manager: ConfigManager):
        self._config_manager = config_manager
        # Route table: {(method, path): config_dict}
        self._routes: dict[tuple[str, str], dict] = {}

    async def load_all(self) -> None:
        """Load all enabled configs into route table."""
        configs = await self._config_manager.list_configs(enabled=True)
        self._routes.clear()
        for cfg in configs:
            method = cfg["method"].upper()
            path = cfg["path"]
            self._routes[(method, path)] = cfg
        logger.info(f"RouteDispatcher: loaded {len(self._routes)} routes")

        # Listen for config changes
        event_bus.on("config.api.updated", self._on_config_updated)

    async def _on_config_updated(self, event: str, **kwargs: Any) -> None:
        """Reload routes when config changes."""
        await self.load_all()
        logger.debug(f"RouteDispatcher: routes reloaded after {kwargs.get('action', 'unknown')} event")

    def match(self, method: str, path: str) -> dict | None:
        """Find matching route config for method + path."""
        return self._routes.get((method.upper(), path))

    def list_routes(self) -> list[dict]:
        """List all registered routes."""
        return [
            {
                "method": method,
                "path": path,
                "configId": cfg.get("id"),
                "name": cfg.get("name"),
                "enabled": bool(cfg.get("enabled", 1)),
            }
            for (method, path), cfg in self._routes.items()
        ]

    def unload(self) -> None:
        """Clear all routes and remove event listener."""
        self._routes.clear()
        event_bus.off("config.api.updated", self._on_config_updated)
