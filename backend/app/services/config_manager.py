"""HTTP API config management service."""

import json
import uuid
from datetime import datetime, timezone

from loguru import logger

from app.core.event_bus import event_bus
from app.core.exceptions import AppError, ERROR_CONFLICT, ERROR_NOT_FOUND
from app.dal.base import DAL


# Default SQL templates for each collection
DEFAULT_SQLS = {
    "devices": {
        "sql": "SELECT * FROM devices WHERE (:type IS NULL OR type = :type) AND (:status IS NULL OR status = :status) ORDER BY name ASC",
        "description": "设备查询",
    },
    "ports": {
        "sql": "SELECT p.*, d.name AS deviceName, d.dn AS deviceDn FROM ports p JOIN devices d ON p.deviceId = d.id WHERE (:deviceId IS NULL OR p.deviceId = :deviceId) AND (:status IS NULL OR p.status = :status) ORDER BY p.name ASC",
        "description": "端口查询（已自动 JOIN 关联设备）",
    },
    "links": {
        "sql": (
            "SELECT l.*, "
            "d1.name AS sourceDeviceName, d1.dn AS sourceDeviceDn, "
            "p1.name AS sourcePortName, p1.dn AS sourcePortDn, "
            "d2.name AS targetDeviceName, d2.dn AS targetDeviceDn, "
            "p2.name AS targetPortName, p2.dn AS targetPortDn "
            "FROM links l "
            "JOIN devices d1 ON l.sourceDeviceId = d1.id "
            "JOIN ports p1 ON l.sourcePortId = p1.id "
            "JOIN devices d2 ON l.targetDeviceId = d2.id "
            "JOIN ports p2 ON l.targetPortId = p2.id"
        ),
        "description": "链路查询（已自动 JOIN 关联设备和端口 DN）",
    },
    "alarms": {
        "sql": "SELECT a.*, d.name AS deviceName, d.dn AS deviceDn FROM alarms a JOIN devices d ON a.deviceId = d.id WHERE (:level IS NULL OR a.level = :level) AND (:status IS NULL OR a.status = :status) ORDER BY a.occurTime DESC",
        "description": "告警查询（已自动 JOIN 关联设备）",
    },
    "metrics": {
        "sql": "SELECT m.*, d.name AS deviceName, d.dn AS deviceDn FROM metrics m JOIN devices d ON m.deviceId = d.id WHERE (:deviceId IS NULL OR m.deviceId = :deviceId) ORDER BY m.collectTime DESC",
        "description": "指标查询（已自动 JOIN 关联设备）",
    },
}


class ConfigManager:
    """Manages HTTP API interface configurations."""

    def __init__(self, dal: DAL):
        self._dal = dal

    async def list_configs(
        self, keyword: str | None = None, group: str | None = None,
        enabled: bool | None = None, data_source_type: str | None = None,
    ) -> list[dict]:
        conditions = []
        params: list = []
        if keyword:
            conditions.append("(name LIKE ? OR path LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%"])
        if group is not None:
            conditions.append("group_name = ?")
            params.append(group)
        if enabled is not None:
            conditions.append("enabled = ?")
            params.append(1 if enabled else 0)

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = await self._dal.persist.fetch_all(
            f"SELECT * FROM api_configs{where} ORDER BY group_name, name", tuple(params)
        )

        result = []
        for r in rows:
            item = dict(r)
            # Filter by data_source_type in-memory (stored as JSON)
            if data_source_type:
                ds = json.loads(item.get("data_source", "{}"))
                if ds.get("type") != data_source_type:
                    continue
            result.append(item)
        return result

    async def get_config(self, config_id: str) -> dict | None:
        row = await self._dal.persist.fetch_one(
            "SELECT * FROM api_configs WHERE id = ?", (config_id,)
        )
        return dict(row) if row else None

    async def create_config(self, data: dict) -> dict:
        config_id = data.get("id") or f"api_{uuid.uuid4().hex[:8]}"
        method = data["method"].upper()
        path = data["path"]

        # Check route uniqueness
        existing = await self._dal.persist.fetch_one(
            "SELECT id FROM api_configs WHERE method = ? AND path = ?", (method, path)
        )
        if existing:
            raise AppError(ERROR_CONFLICT, f"路由 {method} {path} 已存在", status_code=409)

        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        await self._dal.persist.execute(
            """INSERT INTO api_configs (id, name, group_name, enabled, method, path,
               auth, data_source, query, response, fault, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                config_id,
                data["name"],
                data.get("group", data.get("group_name", "")),
                1 if data.get("enabled", True) else 0,
                method,
                path,
                json.dumps(data.get("auth", {"type": "none"}), ensure_ascii=False),
                json.dumps(data["dataSource"], ensure_ascii=False),
                json.dumps(data.get("query", {"params": [], "pagination": {"enabled": False}}), ensure_ascii=False),
                json.dumps(data.get("response", {"contentType": "application/json", "template": {}}), ensure_ascii=False),
                json.dumps(data.get("fault", {"delay": 0, "errorRate": 0, "errorStatus": 500}), ensure_ascii=False),
                now, now,
            ),
        )
        await self._dal.persist.commit()

        config = await self.get_config(config_id)
        await event_bus.emit("config.api.updated", action="created", configId=config_id)
        logger.info(f"ConfigManager: created api config '{data['name']}' ({method} {path})")
        return config

    async def update_config(self, config_id: str, data: dict) -> dict:
        existing = await self.get_config(config_id)
        if not existing:
            raise AppError(ERROR_NOT_FOUND, f"配置 '{config_id}' 不存在", status_code=404)

        method = data.get("method", existing["method"]).upper()
        path = data.get("path", existing["path"])

        # Check route uniqueness (if changed)
        if method != existing["method"] or path != existing["path"]:
            dup = await self._dal.persist.fetch_one(
                "SELECT id FROM api_configs WHERE method = ? AND path = ? AND id != ?",
                (method, path, config_id),
            )
            if dup:
                raise AppError(ERROR_CONFLICT, f"路由 {method} {path} 已存在", status_code=409)

        now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        await self._dal.persist.execute(
            """UPDATE api_configs SET
               name = ?, group_name = ?, enabled = ?, method = ?, path = ?,
               auth = ?, data_source = ?, query = ?, response = ?, fault = ?,
               updated_at = ?
               WHERE id = ?""",
            (
                data.get("name", existing["name"]),
                data.get("group", data.get("group_name", existing["group_name"])),
                1 if data.get("enabled", bool(existing["enabled"])) else 0,
                method, path,
                json.dumps(data["auth"], ensure_ascii=False) if "auth" in data else existing["auth"],
                json.dumps(data["dataSource"], ensure_ascii=False) if "dataSource" in data else existing["data_source"],
                json.dumps(data["query"], ensure_ascii=False) if "query" in data else existing["query"],
                json.dumps(data["response"], ensure_ascii=False) if "response" in data else existing["response"],
                json.dumps(data["fault"], ensure_ascii=False) if "fault" in data else existing["fault"],
                now,
                config_id,
            ),
        )
        await self._dal.persist.commit()

        config = await self.get_config(config_id)
        await event_bus.emit("config.api.updated", action="updated", configId=config_id)
        return config

    async def delete_config(self, config_id: str) -> bool:
        existing = await self.get_config(config_id)
        if not existing:
            raise AppError(ERROR_NOT_FOUND, f"配置 '{config_id}' 不存在", status_code=404)

        await self._dal.persist.execute("DELETE FROM api_configs WHERE id = ?", (config_id,))
        await self._dal.persist.commit()
        await event_bus.emit("config.api.updated", action="deleted", configId=config_id)
        logger.info(f"ConfigManager: deleted api config '{config_id}'")
        return True

    async def set_enabled(self, config_id: str, enabled: bool) -> dict:
        existing = await self.get_config(config_id)
        if not existing:
            raise AppError(ERROR_NOT_FOUND, f"配置 '{config_id}' 不存在", status_code=404)

        await self._dal.persist.execute(
            "UPDATE api_configs SET enabled = ?, updated_at = ? WHERE id = ?",
            (1 if enabled else 0, datetime.now(timezone.utc).replace(tzinfo=None).isoformat(), config_id),
        )
        await self._dal.persist.commit()
        await event_bus.emit("config.api.updated", action="toggled", configId=config_id, enabled=enabled)
        return await self.get_config(config_id)

    async def list_groups(self) -> list[dict]:
        rows = await self._dal.persist.fetch_all(
            "SELECT group_name, COUNT(*) as count FROM api_configs GROUP BY group_name ORDER BY group_name"
        )
        return [{"name": r["group_name"], "count": r["count"]} for r in rows]

    def get_default_sql(self, collection: str) -> dict | None:
        info = DEFAULT_SQLS.get(collection)
        if not info:
            return None
        return {"collection": collection, "sql": info["sql"], "description": info["description"]}

    async def export_configs(self, group: str | None = None) -> list[dict]:
        configs = await self.list_configs(group=group)
        return configs

    async def import_configs(self, configs: list[dict], overwrite: bool = False) -> dict:
        imported = 0
        skipped = 0
        for cfg in configs:
            config_id = cfg.get("id")
            if config_id:
                existing = await self.get_config(config_id)
                if existing:
                    if overwrite:
                        await self.update_config(config_id, cfg)
                        imported += 1
                    else:
                        skipped += 1
                    continue
            await self.create_config(cfg)
            imported += 1
        return {"imported": imported, "skipped": skipped}
