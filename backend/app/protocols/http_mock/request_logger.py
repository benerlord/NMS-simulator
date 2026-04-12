"""Request logging for HTTP Mock Server."""

import json
import uuid
from datetime import datetime, timezone

from loguru import logger

from app.core.event_bus import event_bus
from app.dal.base import DAL


MAX_RESPONSE_BODY = 10 * 1024  # 10KB


class RequestLogger:
    """Logs HTTP requests to the database."""

    def __init__(self, dal: DAL):
        self._dal = dal

    async def log(
        self,
        method: str,
        path: str,
        query_string: str = "",
        headers: dict | None = None,
        request_body: str | None = None,
        status_code: int = 200,
        response_body: str | None = None,
        duration: int = 0,
        config_id: str | None = None,
        config_name: str | None = None,
        client_ip: str = "",
        error: str | None = None,
    ) -> None:
        """Record a request log entry."""
        log_id = f"log_{uuid.uuid4().hex[:12]}"
        timestamp = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

        # Truncate large response bodies
        if response_body and len(response_body) > MAX_RESPONSE_BODY:
            response_body = response_body[:MAX_RESPONSE_BODY] + "...[truncated]"

        try:
            await self._dal.persist.execute(
                """INSERT INTO request_logs
                   (id, timestamp, method, path, query_string, headers, request_body,
                    status_code, response_body, duration, config_id, config_name, client_ip, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    log_id, timestamp, method, path, query_string,
                    json.dumps(headers or {}, ensure_ascii=False),
                    request_body, status_code, response_body,
                    duration, config_id, config_name, client_ip, error,
                ),
            )
            await self._dal.persist.commit()
        except Exception as e:
            logger.error(f"RequestLogger: failed to write log: {e}")

        # Emit events
        await event_bus.emit("request.completed",
            method=method, path=path, statusCode=status_code,
            duration=duration, configId=config_id)

        # Cleanup old logs
        await self._cleanup()

    async def _cleanup(self) -> None:
        """Remove oldest logs if over max limit."""
        try:
            max_logs = await self._get_max_logs()
            count = await self._dal.persist.fetch_count("SELECT COUNT(*) FROM request_logs")
            if count > max_logs:
                to_delete = count - max_logs
                await self._dal.persist.execute(
                    f"DELETE FROM request_logs WHERE id IN (SELECT id FROM request_logs ORDER BY timestamp ASC LIMIT ?)",
                    (to_delete,),
                )
                await self._dal.persist.commit()
        except Exception as e:
            logger.debug(f"RequestLogger: cleanup error: {e}")

    async def _get_max_logs(self) -> int:
        row = await self._dal.persist.fetch_one(
            "SELECT value FROM system_settings WHERE key = 'max_request_logs'"
        )
        return int(row["value"]) if row else 10000

    async def list_logs(self, limit: int = 100, offset: int = 0,
                        method: str | None = None, path: str | None = None) -> dict:
        """Query request logs."""
        conditions = []
        params: list = []
        if method:
            conditions.append("method = ?")
            params.append(method)
        if path:
            conditions.append("path LIKE ?")
            params.append(f"%{path}%")

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        total = await self._dal.persist.fetch_count(f"SELECT COUNT(*) FROM request_logs{where}", tuple(params))

        params.extend([limit, offset])
        rows = await self._dal.persist.fetch_all(
            f"SELECT * FROM request_logs{where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            tuple(params),
        )
        return {"items": [dict(r) for r in rows], "total": total}

    async def clear_logs(self) -> int:
        """Delete all request logs."""
        count = await self._dal.persist.fetch_count("SELECT COUNT(*) FROM request_logs")
        await self._dal.persist.execute("DELETE FROM request_logs")
        await self._dal.persist.commit()
        return count
