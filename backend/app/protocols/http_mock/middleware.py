"""Authentication and fault injection middleware for Mock Server."""

import asyncio
import base64
import json
import random

from loguru import logger

from app.services.session_manager import SessionManager


class AuthMiddleware:
    """Validates authentication based on API config auth settings."""

    def __init__(self, session_manager: SessionManager):
        self._session = session_manager

    def check(self, config: dict, headers: dict) -> tuple[bool, int, str]:
        """Check authentication.

        Returns (passed, status_code, error_message).
        """
        auth_cfg = config.get("auth", "{}")
        if isinstance(auth_cfg, str):
            auth_cfg = json.loads(auth_cfg)

        auth_type = auth_cfg.get("type", "none")

        if auth_type == "none":
            return True, 200, ""

        if auth_type == "xtoken":
            header_name = auth_cfg.get("headerName", "X-Auth-Token")
            token = headers.get(header_name) or headers.get(header_name.lower())
            if not token:
                return False, 401, "Missing authentication token"
            if not self._session.validate_token(token):
                return False, 401, "Invalid or expired token"
            return True, 200, ""

        if auth_type == "basic":
            auth_header = headers.get("Authorization") or headers.get("authorization")
            if not auth_header or not auth_header.startswith("Basic "):
                return False, 401, "Missing Basic authentication"
            try:
                decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
                username, password = decoded.split(":", 1)
            except Exception:
                return False, 401, "Invalid Basic authentication format"
            if not self._session.validate_basic(username, password):
                return False, 401, "Invalid credentials"
            return True, 200, ""

        return True, 200, ""


class FaultInjector:
    """Simulates delays and error responses."""

    async def apply(self, config: dict) -> tuple[bool, int]:
        """Apply fault injection.

        Returns (should_error, error_status_code).
        """
        fault_cfg = config.get("fault", "{}")
        if isinstance(fault_cfg, str):
            fault_cfg = json.loads(fault_cfg)

        delay = fault_cfg.get("delay", 0)
        error_rate = fault_cfg.get("errorRate", 0)
        error_status = fault_cfg.get("errorStatus", 500)

        # Apply delay
        if delay > 0:
            await asyncio.sleep(delay / 1000.0)

        # Apply error rate
        if error_rate > 0 and random.random() < error_rate:
            return True, error_status

        return False, 200
