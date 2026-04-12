"""Service registry for lifecycle management and dependency injection."""

from typing import Any, Protocol, runtime_checkable

from loguru import logger


@runtime_checkable
class Service(Protocol):
    """Protocol that services should implement."""

    async def start(self) -> None: ...
    async def stop(self) -> None: ...


class ServiceRegistry:
    """Manages service registration, startup, and shutdown.

    Services are started in registration order and stopped in reverse order.
    """

    def __init__(self) -> None:
        self._services: dict[str, Any] = {}
        self._order: list[str] = []

    def register(self, name: str, service: Any) -> None:
        """Register a service by name."""
        if name in self._services:
            raise ValueError(f"Service '{name}' already registered")
        self._services[name] = service
        self._order.append(name)
        logger.debug(f"ServiceRegistry: registered '{name}'")

    def get(self, name: str) -> Any:
        """Get a service by name."""
        service = self._services.get(name)
        if service is None:
            raise KeyError(f"Service '{name}' not found")
        return service

    def get_optional(self, name: str) -> Any | None:
        """Get a service by name, returning None if not found."""
        return self._services.get(name)

    async def start_all(self) -> None:
        """Start all services in registration order."""
        for name in self._order:
            service = self._services[name]
            if isinstance(service, Service):
                logger.info(f"Starting service: {name}")
                await service.start()

    async def stop_all(self) -> None:
        """Stop all services in reverse registration order."""
        for name in reversed(self._order):
            service = self._services[name]
            if isinstance(service, Service):
                try:
                    logger.info(f"Stopping service: {name}")
                    await service.stop()
                except Exception:
                    logger.exception(f"Error stopping service: {name}")


# Global singleton
registry = ServiceRegistry()
