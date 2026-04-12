"""Event bus for decoupled inter-component communication."""

import asyncio
import fnmatch
from collections import defaultdict
from typing import Any, Callable, Coroutine

from loguru import logger

# Handler type: async callable that accepts event name and arbitrary kwargs
EventHandler = Callable[..., Coroutine[Any, Any, None]]


class EventBus:
    """Async event bus with wildcard subscription support.

    Supports patterns like 'topology.*' to match 'topology.created',
    'topology.updated', etc.
    """

    def __init__(self) -> None:
        # pattern -> list of handlers
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def on(self, pattern: str, handler: EventHandler) -> None:
        """Register an event handler for a pattern."""
        self._handlers[pattern].append(handler)
        logger.debug(f"EventBus: registered handler for '{pattern}'")

    def off(self, pattern: str, handler: EventHandler) -> None:
        """Remove a specific handler for a pattern."""
        handlers = self._handlers.get(pattern)
        if handlers and handler in handlers:
            handlers.remove(handler)
            if not handlers:
                del self._handlers[pattern]
            logger.debug(f"EventBus: removed handler for '{pattern}'")

    async def emit(self, event: str, **kwargs: Any) -> None:
        """Emit an event, invoking all matching handlers."""
        matched_handlers: list[EventHandler] = []
        for pattern, handlers in self._handlers.items():
            if fnmatch.fnmatch(event, pattern):
                matched_handlers.extend(handlers)

        if not matched_handlers:
            return

        logger.debug(f"EventBus: emitting '{event}' to {len(matched_handlers)} handler(s)")

        for handler in matched_handlers:
            try:
                await handler(event, **kwargs)
            except Exception:
                logger.exception(f"EventBus: error in handler for '{event}'")

    def clear(self) -> None:
        """Remove all handlers."""
        self._handlers.clear()


# Global singleton
event_bus = EventBus()
