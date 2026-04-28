"""Mock dynamic route registry.

Maintains FastAPI routes under a configurable prefix (default empty — i.e.
each api_configs.path is mounted as-is on the root), one per api_configs row.
The prefix is read from the `settings.mock_path_prefix` row at startup; an
empty value means "no prefix at all" so external callers can hit the path
exactly as configured. Admin CRUD hooks into register/unregister/update;
startup lifespan calls load_all. The enabled toggle does NOT touch routing —
the handler checks enabled state per-request and returns 404 when disabled.
"""
from __future__ import annotations

import logging
from threading import RLock
from typing import Optional

from fastapi import FastAPI
from starlette.routing import Route

from app.db.connection import connect
from app.mock.handler import make_handler

logger = logging.getLogger(__name__)


def _route_name(api_id: str) -> str:
    return f"mock_{api_id}"


class RouteRegistry:
    def __init__(self) -> None:
        self._app: Optional[FastAPI] = None
        self._lock = RLock()
        # api_id -> (method_upper, full_path)
        self._routes: dict[str, tuple[str, str]] = {}
        self._prefix: str = ""

    def bind(self, app: FastAPI) -> None:
        self._app = app

    def _app_or_raise(self) -> FastAPI:
        if self._app is None:
            raise RuntimeError("RouteRegistry.bind(app) not called")
        return self._app

    def _load_prefix(self) -> str:
        with connect() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = 'mock_path_prefix'"
            ).fetchone()
        return row["value"] if row else ""

    def load_all(self) -> None:
        with self._lock:
            self._prefix = self._load_prefix()
            logger.info("mock.registry: prefix = %r", self._prefix)
            with connect() as conn:
                rows = conn.execute(
                    "SELECT id, method, path FROM api_configs"
                ).fetchall()
            for row in rows:
                self._register_unlocked(row["id"], row["method"], row["path"])
            logger.info("mock.registry: loaded %d routes", len(rows))

    def register(self, api_id: str, method: str, path: str) -> None:
        with self._lock:
            if api_id in self._routes:
                return
            self._register_unlocked(api_id, method, path)

    def unregister(self, api_id: str) -> None:
        with self._lock:
            entry = self._routes.pop(api_id, None)
            if not entry:
                return
            app = self._app_or_raise()
            target_name = _route_name(api_id)
            app.router.routes = [
                r
                for r in app.router.routes
                if not (
                    isinstance(r, Route)
                    and getattr(r, "name", None) == target_name
                )
            ]

    def update(self, api_id: str, method: str, path: str) -> None:
        with self._lock:
            self.unregister(api_id)
            self._register_unlocked(api_id, method, path)

    def reload(self) -> None:
        """Re-read mock_path_prefix and re-register every route under it.

        Used by /admin/api/settings PUT when mock_path_prefix changes so callers
        do not have to restart the process to pick up the new prefix.
        """
        with self._lock:
            app = self._app_or_raise()
            current_ids = list(self._routes.keys())
            for api_id in current_ids:
                self.unregister(api_id)
            self.load_all()

    def _register_unlocked(self, api_id: str, method: str, path: str) -> None:
        app = self._app_or_raise()
        # Strip query string — ? should never be in a route path; if it is present
        # (legacy/bad data) we strip it rather than silently failing to route.
        route_path = path.split("?")[0]
        prefix = self._prefix
        full_path = f"{prefix}{route_path}" if prefix else route_path
        handler = make_handler(api_id)
        app.router.add_route(
            full_path,
            handler,
            methods=[method.upper()],
            name=_route_name(api_id),
            include_in_schema=False,
        )
        self._routes[api_id] = (method.upper(), full_path)


registry = RouteRegistry()
