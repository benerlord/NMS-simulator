"""Protocol plugin abstract base class and manager."""

from abc import ABC, abstractmethod
from typing import Any

from loguru import logger

from app.core.event_bus import event_bus


class ProtocolPlugin(ABC):
    """Abstract base class for protocol plugins."""

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def restart(self) -> None:
        await self.stop()
        await self.start()

    @abstractmethod
    def status(self) -> dict: ...

    @abstractmethod
    def health_check(self) -> dict: ...

    @abstractmethod
    async def reload_config(self) -> None: ...


class ProtocolManager:
    """Manages protocol plugin lifecycle."""

    def __init__(self):
        self._plugins: dict[str, ProtocolPlugin] = {}

    def register_plugin(self, name: str, plugin: ProtocolPlugin) -> None:
        self._plugins[name] = plugin
        logger.info(f"ProtocolManager: registered plugin '{name}'")

    def get_plugin(self, name: str) -> ProtocolPlugin | None:
        return self._plugins.get(name)

    async def start_plugin(self, name: str) -> None:
        plugin = self._plugins.get(name)
        if not plugin:
            raise KeyError(f"Plugin '{name}' not found")
        try:
            await plugin.start()
            logger.info(f"ProtocolManager: started '{name}'")
        except Exception as e:
            logger.error(f"ProtocolManager: failed to start '{name}': {e}")
            await event_bus.emit("protocol.error", plugin=name, error=str(e))
            raise

    async def stop_plugin(self, name: str) -> None:
        plugin = self._plugins.get(name)
        if not plugin:
            raise KeyError(f"Plugin '{name}' not found")
        try:
            await plugin.stop()
            logger.info(f"ProtocolManager: stopped '{name}'")
        except Exception as e:
            logger.error(f"ProtocolManager: failed to stop '{name}': {e}")
            raise

    async def restart_plugin(self, name: str) -> None:
        await self.stop_plugin(name)
        await self.start_plugin(name)

    def status_all(self) -> list[dict]:
        result = []
        for name, plugin in self._plugins.items():
            try:
                result.append({"name": name, **plugin.status()})
            except Exception as e:
                result.append({"name": name, "status": "error", "error": str(e)})
        return result

    async def start_all(self) -> None:
        for name in self._plugins:
            try:
                await self.start_plugin(name)
            except Exception:
                pass  # Error already logged

    async def stop_all(self) -> None:
        for name in list(self._plugins.keys()):
            try:
                await self.stop_plugin(name)
            except Exception:
                pass
