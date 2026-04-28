"""Per-api handler closure for mock routes.

The actual request logic lives in `app.core.request_pipeline` (M3-03). This
module exists only to produce the per-api async callable that `RouteRegistry`
hands to Starlette — each route needs a stable `api_id` bound in a closure.
"""
from __future__ import annotations

from typing import Callable

from fastapi import Request
from fastapi.responses import Response

from app.core.request_pipeline import run as run_pipeline


def make_handler(api_id: str) -> Callable:
    async def handler(request: Request) -> Response:
        return await run_pipeline(api_id, request)

    return handler
