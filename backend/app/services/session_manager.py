"""Token authentication management service."""

import json
import uuid
from datetime import datetime, timedelta, timezone

from loguru import logger

from app.core.exceptions import AppError, ERROR_NOT_FOUND
from app.dal.base import DAL


class SessionManager:
    """Manages Token-based authentication for Mock Server."""

    def __init__(self, dal: DAL):
        self._dal = dal
        # In-memory token store: {token: {"created_at": str, "expires_at": str}}
        self._tokens: dict[str, dict] = {}
        self._token_expiry: int = 1800  # seconds
        self._credentials: list[dict] = []

    async def start(self):
        """Load config from database on startup."""
        row = await self._dal.persist.fetch_one(
            "SELECT * FROM session_config WHERE id = 'default'"
        )
        if row:
            self._token_expiry = row["token_expiry"]
            self._credentials = json.loads(row["credentials"]) if row["credentials"] else []
        logger.info(f"SessionManager: loaded config, expiry={self._token_expiry}s, "
                     f"credentials={len(self._credentials)} users")

    async def stop(self):
        self._tokens.clear()

    def authenticate(self, username: str, password: str) -> str | None:
        """Verify credentials and issue a token. Returns token or None."""
        for cred in self._credentials:
            if cred["username"] == username and cred["password"] == password:
                token = f"x-{uuid.uuid4().hex}"
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                self._tokens[token] = {
                    "created_at": now.isoformat(),
                    "expires_at": (now + timedelta(seconds=self._token_expiry)).isoformat(),
                }
                logger.debug(f"SessionManager: issued token for user '{username}'")
                return token
        return None

    def validate_token(self, token: str) -> bool:
        """Check if token is valid and not expired."""
        info = self._tokens.get(token)
        if not info:
            return False
        expires_at = datetime.fromisoformat(info["expires_at"])
        if datetime.now(timezone.utc).replace(tzinfo=None) > expires_at:
            # Auto-cleanup expired token
            del self._tokens[token]
            return False
        return True

    def validate_basic(self, username: str, password: str) -> bool:
        """Validate basic auth credentials."""
        for cred in self._credentials:
            if cred["username"] == username and cred["password"] == password:
                return True
        return False

    def invalidate_token(self, token: str) -> bool:
        """Manually invalidate a specific token."""
        if token in self._tokens:
            del self._tokens[token]
            return True
        return False

    def clear_tokens(self):
        """Clear all tokens."""
        count = len(self._tokens)
        self._tokens.clear()
        logger.info(f"SessionManager: cleared {count} tokens")

    def list_tokens(self) -> list[dict]:
        """List all active tokens with expiry info."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        result = []
        expired_keys = []
        for token, info in self._tokens.items():
            expires_at = datetime.fromisoformat(info["expires_at"])
            is_expired = now > expires_at
            if is_expired:
                expired_keys.append(token)
                continue
            result.append({
                "token": token,
                "createdAt": info["created_at"],
                "expiresAt": info["expires_at"],
                "isExpired": False,
            })
        # Cleanup expired tokens
        for k in expired_keys:
            del self._tokens[k]
        return result

    async def get_config(self) -> dict:
        """Get session config."""
        return {
            "tokenExpiry": self._token_expiry,
            "credentials": self._credentials,
        }

    async def update_config(self, data: dict) -> dict:
        """Update session config and persist."""
        if "tokenExpiry" in data:
            self._token_expiry = data["tokenExpiry"]
        if "credentials" in data:
            self._credentials = data["credentials"]

        await self._dal.persist.execute(
            """UPDATE session_config SET token_expiry = ?, credentials = ?, updated_at = ?
               WHERE id = 'default'""",
            (self._token_expiry, json.dumps(self._credentials, ensure_ascii=False),
             datetime.now(timezone.utc).replace(tzinfo=None).isoformat()),
        )
        await self._dal.persist.commit()
        logger.info(f"SessionManager: config updated, expiry={self._token_expiry}s")
        return await self.get_config()

    def cleanup_expired(self):
        """Remove all expired tokens."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expired = [t for t, info in self._tokens.items()
                   if now > datetime.fromisoformat(info["expires_at"])]
        for t in expired:
            del self._tokens[t]
        if expired:
            logger.debug(f"SessionManager: cleaned up {len(expired)} expired tokens")
