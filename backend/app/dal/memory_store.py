"""In-memory SQLite query engine for runtime topology data."""

import sqlite3
from typing import Any

from loguru import logger

# ---------------------------------------------------------------------------
# Memory table DDL (camelCase columns for user-facing SQL)
# ---------------------------------------------------------------------------

MEMORY_TABLES_DDL = """
CREATE TABLE devices (
    id           TEXT PRIMARY KEY,
    name         TEXT,
    type         TEXT,
    dn           TEXT,
    ip           TEXT,
    vendor       TEXT,
    model        TEXT,
    status       TEXT,
    portCount    INTEGER DEFAULT 0,
    customFields TEXT DEFAULT '{}'
);
CREATE INDEX idx_mem_devices_type ON devices(type);
CREATE INDEX idx_mem_devices_dn ON devices(dn);
CREATE INDEX idx_mem_devices_status ON devices(status);

CREATE TABLE ports (
    id         TEXT PRIMARY KEY,
    deviceId   TEXT,
    name       TEXT,
    dn         TEXT,
    type       TEXT,
    speed      TEXT,
    status     TEXT
);
CREATE INDEX idx_mem_ports_device ON ports(deviceId);
CREATE INDEX idx_mem_ports_dn ON ports(dn);
CREATE INDEX idx_mem_ports_status ON ports(status);

CREATE TABLE links (
    id              TEXT PRIMARY KEY,
    sourceDeviceId  TEXT,
    sourcePortId    TEXT,
    targetDeviceId  TEXT,
    targetPortId    TEXT,
    type            TEXT,
    bandwidth       TEXT,
    status          TEXT,
    description     TEXT DEFAULT ''
);
CREATE INDEX idx_mem_links_src_dev ON links(sourceDeviceId);
CREATE INDEX idx_mem_links_tgt_dev ON links(targetDeviceId);
CREATE INDEX idx_mem_links_status ON links(status);

CREATE TABLE alarms (
    id         TEXT PRIMARY KEY,
    deviceId   TEXT,
    level      TEXT,
    type       TEXT,
    content    TEXT,
    status     TEXT,
    occurTime  TEXT,
    clearTime  TEXT DEFAULT NULL
);
CREATE INDEX idx_mem_alarms_device ON alarms(deviceId);
CREATE INDEX idx_mem_alarms_level ON alarms(level);
CREATE INDEX idx_mem_alarms_status ON alarms(status);

CREATE TABLE metrics (
    id              TEXT PRIMARY KEY,
    deviceId        TEXT,
    name            TEXT,
    value           REAL,
    unit            TEXT DEFAULT '',
    collectTime     TEXT,
    collectInterval INTEGER DEFAULT 300
);
CREATE INDEX idx_mem_metrics_device ON metrics(deviceId);
CREATE INDEX idx_mem_metrics_name ON metrics(name);
"""

# Column definitions per table for INSERT statements
TABLE_COLUMNS: dict[str, list[str]] = {
    "devices": ["id", "name", "type", "dn", "ip", "vendor", "model", "status", "portCount", "customFields"],
    "ports": ["id", "deviceId", "name", "dn", "type", "speed", "status"],
    "links": ["id", "sourceDeviceId", "sourcePortId", "targetDeviceId", "targetPortId", "type", "bandwidth", "status", "description"],
    "alarms": ["id", "deviceId", "level", "type", "content", "status", "occurTime", "clearTime"],
    "metrics": ["id", "deviceId", "name", "value", "unit", "collectTime", "collectInterval"],
}


class MemoryStore:
    """Manages the in-memory SQLite database for runtime queries."""

    def __init__(self) -> None:
        self._db: sqlite3.Connection | None = None

    @property
    def db(self) -> sqlite3.Connection:
        if self._db is None:
            raise RuntimeError("MemoryStore not started")
        return self._db

    async def start(self) -> None:
        """Create in-memory database and tables."""
        self._db = sqlite3.connect(":memory:", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(MEMORY_TABLES_DDL)
        logger.info("MemoryStore: in-memory database initialized with 5 tables")

    async def stop(self) -> None:
        """Close in-memory database."""
        if self._db:
            self._db.close()
            self._db = None
            logger.info("MemoryStore: closed")

    # ------------------------------------------------------------------
    # Full sync: clear all tables and bulk insert
    # ------------------------------------------------------------------

    async def full_sync(self, topology_data: dict) -> None:
        """Full sync: clear all tables and bulk insert from topology data."""
        db = self.db
        db.execute("BEGIN")
        try:
            for table in TABLE_COLUMNS:
                db.execute(f"DELETE FROM {table}")

            for table, columns in TABLE_COLUMNS.items():
                rows = topology_data.get(table, [])
                if not rows:
                    continue
                self._bulk_insert(table, columns, rows)

            db.execute("COMMIT")
            counts = {t: self._count(t) for t in TABLE_COLUMNS}
            logger.info(f"MemoryStore: full_sync complete — {counts}")
        except Exception:
            db.execute("ROLLBACK")
            raise

    # ------------------------------------------------------------------
    # Single-table sync
    # ------------------------------------------------------------------

    async def sync_table(self, table_name: str, rows: list[dict]) -> None:
        """Replace all data in a single table."""
        columns = TABLE_COLUMNS.get(table_name)
        if columns is None:
            raise ValueError(f"Unknown table: {table_name}")

        db = self.db
        db.execute("BEGIN")
        try:
            db.execute(f"DELETE FROM {table_name}")
            if rows:
                self._bulk_insert(table_name, columns, rows)
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise

    # ------------------------------------------------------------------
    # Incremental sync
    # ------------------------------------------------------------------

    async def upsert_row(self, table_name: str, row: dict) -> None:
        """Insert or replace a single row."""
        columns = TABLE_COLUMNS.get(table_name)
        if columns is None:
            raise ValueError(f"Unknown table: {table_name}")

        placeholders = ", ".join("?" for _ in columns)
        col_names = ", ".join(columns)
        values = tuple(self._get_value(row, c) for c in columns)

        self.db.execute(
            f"INSERT OR REPLACE INTO {table_name} ({col_names}) VALUES ({placeholders})",
            values,
        )

    async def delete_row(self, table_name: str, row_id: str) -> None:
        """Delete a row by id."""
        if table_name not in TABLE_COLUMNS:
            raise ValueError(f"Unknown table: {table_name}")
        self.db.execute(f"DELETE FROM {table_name} WHERE id = ?", (row_id,))

    # ------------------------------------------------------------------
    # SQL execution
    # ------------------------------------------------------------------

    async def execute_sql(
        self, sql: str, params: dict | None = None
    ) -> tuple[list[str], list[list[Any]]]:
        """Execute a SQL query and return (column_names, rows)."""
        cursor = self.db.execute(sql, params or {})
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = [list(row) for row in cursor.fetchall()]
        return columns, rows

    async def execute_count(self, sql: str, params: dict | None = None) -> int:
        """Execute a COUNT query and return the integer result."""
        cursor = self.db.execute(sql, params or {})
        row = cursor.fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # Table info
    # ------------------------------------------------------------------

    async def get_table_info(self) -> list[dict]:
        """Return column definitions and row count for each table."""
        result = []
        for table_name in TABLE_COLUMNS:
            cursor = self.db.execute(f"PRAGMA table_info({table_name})")
            columns = [
                {"name": row[1], "type": row[2], "nullable": not row[3], "pk": bool(row[5])}
                for row in cursor.fetchall()
            ]
            count = self._count(table_name)
            result.append({"table": table_name, "columns": columns, "rowCount": count})
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _bulk_insert(self, table: str, columns: list[str], rows: list[dict]) -> None:
        """Bulk insert rows using executemany."""
        placeholders = ", ".join("?" for _ in columns)
        col_names = ", ".join(columns)
        values = [tuple(self._get_value(r, c) for c in columns) for r in rows]
        self.db.executemany(
            f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
            values,
        )

    @staticmethod
    def _get_value(row: dict, column: str) -> Any:
        """Get a value from a row dict, handling camelCase keys and JSON serialization."""
        import json

        val = row.get(column)
        if val is None:
            return None
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False)
        return val

    def _count(self, table: str) -> int:
        cursor = self.db.execute(f"SELECT COUNT(*) FROM {table}")
        return cursor.fetchone()[0]
