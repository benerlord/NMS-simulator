"""Data Access Layer — unified interface over PersistStore and MemoryStore."""

import json
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from app.dal.memory_store import MemoryStore
from app.dal.persist_store import PersistStore


class DAL:
    """Aggregates PersistStore and MemoryStore into a single data access layer."""

    def __init__(self, persist: PersistStore, memory: MemoryStore) -> None:
        self.persist = persist
        self.memory = memory

    async def start(self) -> None:
        await self.persist.start()
        await self.memory.start()
        logger.info("DAL: started")

    async def stop(self) -> None:
        await self.memory.stop()
        await self.persist.stop()
        logger.info("DAL: stopped")

    # ==================================================================
    # Topology CRUD
    # ==================================================================

    async def list_topologies(self) -> list[dict]:
        """List all topologies (without full data)."""
        rows = await self.persist.fetch_all(
            "SELECT id, name, description, version, is_active, created_at, updated_at FROM topologies ORDER BY updated_at DESC"
        )
        return rows

    async def get_topology(self, topo_id: str) -> dict | None:
        """Get a topology by ID (including data)."""
        return await self.persist.fetch_one(
            "SELECT * FROM topologies WHERE id = ?", (topo_id,)
        )

    async def save_topology(
        self,
        topo_id: str,
        name: str,
        description: str,
        data: dict,
        *,
        is_active: bool = False,
    ) -> dict:
        """Create or update a topology, also creating a history entry."""
        now = datetime.now(timezone.utc).isoformat()
        data_json = json.dumps(data, ensure_ascii=False)

        existing = await self.persist.fetch_one(
            "SELECT version FROM topologies WHERE id = ?", (topo_id,)
        )

        if existing:
            new_version = existing["version"] + 1
            await self.persist.execute(
                """UPDATE topologies
                   SET name = ?, description = ?, data = ?, version = ?, is_active = ?, updated_at = ?
                   WHERE id = ?""",
                (name, description, data_json, new_version, int(is_active), now, topo_id),
            )
        else:
            new_version = 1
            await self.persist.execute(
                """INSERT INTO topologies (id, name, description, data, version, is_active, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (topo_id, name, description, data_json, new_version, int(is_active), now, now),
            )

        # Save history
        await self.save_history(topo_id, new_version, data)

        await self.persist.commit()

        return {
            "id": topo_id,
            "name": name,
            "version": new_version,
            "is_active": is_active,
        }

    async def delete_topology(self, topo_id: str) -> bool:
        """Delete a topology and its history (cascading FK)."""
        cursor = await self.persist.execute(
            "DELETE FROM topologies WHERE id = ?", (topo_id,)
        )
        await self.persist.commit()
        return cursor.rowcount > 0

    async def set_active_topology(self, topo_id: str) -> None:
        """Set a topology as the active one (deactivate others)."""
        await self.persist.execute("UPDATE topologies SET is_active = 0")
        await self.persist.execute(
            "UPDATE topologies SET is_active = 1 WHERE id = ?", (topo_id,)
        )
        await self.persist.commit()

    async def get_active_topology(self) -> dict | None:
        """Get the currently active topology."""
        return await self.persist.fetch_one(
            "SELECT * FROM topologies WHERE is_active = 1"
        )

    async def load_topology(self, topo_id: str) -> dict | None:
        """Load a topology from DB and sync to memory store."""
        topo = await self.get_topology(topo_id)
        if topo is None:
            return None

        data = json.loads(topo["data"]) if isinstance(topo["data"], str) else topo["data"]
        await self.memory.full_sync(data)
        await self.set_active_topology(topo_id)
        logger.info(f"DAL: loaded topology '{topo_id}' into memory")
        return topo

    # ==================================================================
    # Version management
    # ==================================================================

    async def save_history(self, topo_id: str, version: int, data: dict) -> None:
        """Save a topology version snapshot."""
        data_json = json.dumps(data, ensure_ascii=False)
        device_count = len(data.get("devices", []))
        port_count = len(data.get("ports", []))
        link_count = len(data.get("links", []))

        await self.persist.execute(
            """INSERT INTO topology_history (topology_id, version, data, device_count, port_count, link_count)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (topo_id, version, data_json, device_count, port_count, link_count),
        )

    async def list_history(self, topo_id: str) -> list[dict]:
        """List version history for a topology (without data)."""
        return await self.persist.fetch_all(
            """SELECT id, topology_id, version, device_count, port_count, link_count, created_at
               FROM topology_history
               WHERE topology_id = ?
               ORDER BY version DESC""",
            (topo_id,),
        )

    async def restore_version(self, topo_id: str, version: int) -> dict | None:
        """Restore a specific version of a topology."""
        history = await self.persist.fetch_one(
            "SELECT data FROM topology_history WHERE topology_id = ? AND version = ?",
            (topo_id, version),
        )
        if history is None:
            return None

        data = json.loads(history["data"])
        topo = await self.persist.fetch_one(
            "SELECT name, description FROM topologies WHERE id = ?", (topo_id,)
        )
        if topo is None:
            return None

        result = await self.save_topology(
            topo_id, topo["name"], topo["description"], data, is_active=True
        )
        await self.memory.full_sync(data)
        return result

    async def cleanup_history(self, topo_id: str, max_versions: int = 10) -> int:
        """Delete old versions beyond max_versions. Returns count deleted."""
        cursor = await self.persist.execute(
            """DELETE FROM topology_history
               WHERE topology_id = ?
                 AND id NOT IN (
                     SELECT id FROM topology_history
                     WHERE topology_id = ?
                     ORDER BY version DESC
                     LIMIT ?
                 )""",
            (topo_id, topo_id, max_versions),
        )
        await self.persist.commit()
        deleted = cursor.rowcount
        if deleted:
            logger.info(f"DAL: cleaned up {deleted} old versions for topology '{topo_id}'")
        return deleted

    # ==================================================================
    # Generic config CRUD
    # ==================================================================

    async def save_config(self, table: str, data: dict) -> None:
        """Insert or replace a config row."""
        columns = list(data.keys())
        placeholders = ", ".join("?" for _ in columns)
        col_names = ", ".join(columns)
        values = tuple(
            json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
            for v in data.values()
        )
        await self.persist.execute(
            f"INSERT OR REPLACE INTO {table} ({col_names}) VALUES ({placeholders})",
            values,
        )
        await self.persist.commit()

    async def get_config(self, table: str, config_id: str) -> dict | None:
        """Get a config row by ID."""
        return await self.persist.fetch_one(
            f"SELECT * FROM {table} WHERE id = ?", (config_id,)
        )

    async def delete_config(self, table: str, config_id: str) -> bool:
        """Delete a config row."""
        cursor = await self.persist.execute(
            f"DELETE FROM {table} WHERE id = ?", (config_id,)
        )
        await self.persist.commit()
        return cursor.rowcount > 0
