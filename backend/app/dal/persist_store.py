"""Persistent SQLite database store."""

import os
from pathlib import Path

import aiosqlite
from loguru import logger

from app.config import settings

# ---------------------------------------------------------------------------
# DDL: All 12 persistent tables + schema_migrations
# ---------------------------------------------------------------------------

SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    description TEXT DEFAULT '',
    applied_at  TEXT DEFAULT (datetime('now'))
);
"""

TABLES_DDL = [
    # 1. topologies
    """
    CREATE TABLE IF NOT EXISTS topologies (
        id          TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        description TEXT DEFAULT '',
        data        TEXT NOT NULL DEFAULT '{}',
        version     INTEGER DEFAULT 1,
        is_active   INTEGER DEFAULT 0,
        created_at  TEXT DEFAULT (datetime('now')),
        updated_at  TEXT DEFAULT (datetime('now'))
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_topologies_active ON topologies(is_active);",
    "CREATE INDEX IF NOT EXISTS idx_topologies_updated ON topologies(updated_at);",

    # 2. topology_history
    """
    CREATE TABLE IF NOT EXISTS topology_history (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        topology_id  TEXT NOT NULL,
        version      INTEGER NOT NULL,
        data         TEXT NOT NULL,
        device_count INTEGER DEFAULT 0,
        port_count   INTEGER DEFAULT 0,
        link_count   INTEGER DEFAULT 0,
        created_at   TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (topology_id) REFERENCES topologies(id) ON DELETE CASCADE
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_topo_history_tid_ver ON topology_history(topology_id, version DESC);",

    # 3. device_types
    """
    CREATE TABLE IF NOT EXISTS device_types (
        id           TEXT PRIMARY KEY,
        name         TEXT NOT NULL,
        icon         TEXT DEFAULT 'default',
        color        TEXT DEFAULT '#1890ff',
        shape        TEXT DEFAULT 'rect',
        built_in     INTEGER DEFAULT 0,
        capabilities TEXT DEFAULT '{}',
        fields       TEXT DEFAULT '[]',
        created_at   TEXT DEFAULT (datetime('now')),
        updated_at   TEXT DEFAULT (datetime('now'))
    );
    """,

    # 4. api_configs
    """
    CREATE TABLE IF NOT EXISTS api_configs (
        id              TEXT PRIMARY KEY,
        name            TEXT NOT NULL,
        group_name      TEXT DEFAULT '',
        enabled         INTEGER DEFAULT 1,
        method          TEXT NOT NULL,
        path            TEXT NOT NULL,
        auth            TEXT DEFAULT '{"type":"none"}',
        data_source     TEXT NOT NULL,
        query           TEXT DEFAULT '{"params":[],"pagination":{"enabled":false}}',
        response        TEXT DEFAULT '{"contentType":"application/json","template":{}}',
        fault           TEXT DEFAULT '{"delay":0,"errorRate":0,"errorStatus":500}',
        created_at      TEXT DEFAULT (datetime('now')),
        updated_at      TEXT DEFAULT (datetime('now'))
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_api_configs_group ON api_configs(group_name);",
    "CREATE INDEX IF NOT EXISTS idx_api_configs_enabled ON api_configs(enabled);",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_api_configs_route ON api_configs(method, path);",

    # 5. session_config
    """
    CREATE TABLE IF NOT EXISTS session_config (
        id              TEXT PRIMARY KEY DEFAULT 'default',
        token_expiry    INTEGER DEFAULT 1800,
        credentials     TEXT DEFAULT '[]',
        updated_at      TEXT DEFAULT (datetime('now'))
    );
    """,

    # 6. protocol_configs
    """
    CREATE TABLE IF NOT EXISTS protocol_configs (
        name         TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        enabled      INTEGER DEFAULT 0,
        config       TEXT NOT NULL DEFAULT '{}',
        updated_at   TEXT DEFAULT (datetime('now'))
    );
    """,

    # 7. snmp_oid_configs
    """
    CREATE TABLE IF NOT EXISTS snmp_oid_configs (
        id            TEXT PRIMARY KEY,
        oid           TEXT NOT NULL,
        name          TEXT DEFAULT '',
        group_name    TEXT DEFAULT 'default',
        device_type   TEXT DEFAULT '',
        data_type     TEXT NOT NULL,
        value_source  TEXT DEFAULT 'static',
        value_config  TEXT NOT NULL DEFAULT '{}',
        description   TEXT DEFAULT '',
        enabled       INTEGER DEFAULT 1,
        created_at    TEXT DEFAULT (datetime('now')),
        updated_at    TEXT DEFAULT (datetime('now'))
    );
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_snmp_oid ON snmp_oid_configs(oid);",
    "CREATE INDEX IF NOT EXISTS idx_snmp_oid_group ON snmp_oid_configs(group_name);",
    "CREATE INDEX IF NOT EXISTS idx_snmp_oid_device_type ON snmp_oid_configs(device_type);",

    # 8. snmp_trap_config
    """
    CREATE TABLE IF NOT EXISTS snmp_trap_config (
        id              TEXT PRIMARY KEY DEFAULT 'default',
        destinations    TEXT DEFAULT '[]',
        templates       TEXT DEFAULT '[]',
        updated_at      TEXT DEFAULT (datetime('now'))
    );
    """,

    # 9. sftp_templates
    """
    CREATE TABLE IF NOT EXISTS sftp_templates (
        id                TEXT PRIMARY KEY,
        name              TEXT NOT NULL,
        device_types      TEXT DEFAULT '[]',
        file_type         TEXT NOT NULL DEFAULT 'csv',
        name_template     TEXT NOT NULL,
        generate_interval INTEGER DEFAULT 300,
        enabled           INTEGER DEFAULT 1,
        headers           TEXT DEFAULT '[]',
        created_at        TEXT DEFAULT (datetime('now')),
        updated_at        TEXT DEFAULT (datetime('now'))
    );
    """,

    # 10. kafka_topic_configs
    """
    CREATE TABLE IF NOT EXISTS kafka_topic_configs (
        id              TEXT PRIMARY KEY,
        topic           TEXT NOT NULL,
        message_type    TEXT NOT NULL,
        format          TEXT DEFAULT 'json',
        send_mode       TEXT DEFAULT 'manual',
        send_interval   INTEGER DEFAULT 300,
        enabled         INTEGER DEFAULT 1,
        template        TEXT NOT NULL DEFAULT '{}',
        created_at      TEXT DEFAULT (datetime('now')),
        updated_at      TEXT DEFAULT (datetime('now'))
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_kafka_topic ON kafka_topic_configs(topic);",

    # 11. request_logs
    """
    CREATE TABLE IF NOT EXISTS request_logs (
        id              TEXT PRIMARY KEY,
        timestamp       TEXT NOT NULL,
        method          TEXT NOT NULL,
        path            TEXT NOT NULL,
        query_string    TEXT DEFAULT '',
        headers         TEXT DEFAULT '{}',
        request_body    TEXT DEFAULT NULL,
        status_code     INTEGER NOT NULL,
        response_body   TEXT DEFAULT NULL,
        duration        INTEGER NOT NULL,
        config_id       TEXT DEFAULT NULL,
        config_name     TEXT DEFAULT NULL,
        client_ip       TEXT DEFAULT '',
        error           TEXT DEFAULT NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_req_logs_timestamp ON request_logs(timestamp DESC);",
    "CREATE INDEX IF NOT EXISTS idx_req_logs_method_path ON request_logs(method, path);",
    "CREATE INDEX IF NOT EXISTS idx_req_logs_status ON request_logs(status_code);",
    "CREATE INDEX IF NOT EXISTS idx_req_logs_config ON request_logs(config_id);",

    # 12. system_settings
    """
    CREATE TABLE IF NOT EXISTS system_settings (
        key         TEXT PRIMARY KEY,
        value       TEXT NOT NULL,
        category    TEXT DEFAULT 'general',
        description TEXT DEFAULT '',
        updated_at  TEXT DEFAULT (datetime('now'))
    );
    """,
]

# ---------------------------------------------------------------------------
# Preset data (INSERT OR IGNORE to avoid duplicates on restart)
# ---------------------------------------------------------------------------

PRESET_DATA = [
    # device_types
    """INSERT OR IGNORE INTO device_types (id, name, icon, color, shape, built_in, capabilities) VALUES
       ('switch',   '网络交换机', 'switch',   '#1890ff', 'rect', 1, '{"hasPorts":true,"canConnectNetwork":true,"canConnectServer":true}'),
       ('router',   '路由器',     'router',   '#52c41a', 'rect', 1, '{"hasPorts":true,"canConnectNetwork":true,"canConnectServer":false}'),
       ('server',   '物理服务器', 'server',   '#722ed1', 'rect', 1, '{"hasPorts":true,"canConnectNetwork":true,"canConnectServer":false}'),
       ('storage',  '存储设备',   'storage',  '#fa8c16', 'rect', 1, '{"hasPorts":true,"canConnectNetwork":true,"canConnectServer":true}'),
       ('firewall', '防火墙',     'firewall', '#f5222d', 'rect', 1, '{"hasPorts":true,"canConnectNetwork":true,"canConnectServer":false}');""",

    # protocol_configs
    """INSERT OR IGNORE INTO protocol_configs (name, display_name, enabled, config) VALUES
       ('http-mock',      'HTTP Mock Server', 0, '{"host":"0.0.0.0","port":8080}'),
       ('snmp-agent',     'SNMP Agent',       0, '{"host":"0.0.0.0","port":161,"versions":["v2c"],"v2c":{"community":"public"},"v3":{"users":[]}}'),
       ('sftp-server',    'SFTP Server',      0, '{"host":"0.0.0.0","port":2222,"users":[],"rootPath":"./data/sftp_files"}'),
       ('kafka-producer', 'Kafka Producer',   0, '{"bootstrapServers":"localhost:9092","acks":"all","retries":3,"batchSize":16384,"security":{"protocol":"PLAINTEXT"}}');""",

    # session_config
    """INSERT OR IGNORE INTO session_config (id, token_expiry, credentials) VALUES
       ('default', 1800, '[{"username":"IMOCTest","password":"Imoc@12345"},{"username":"admin","password":"admin123"}]');""",

    # snmp_trap_config
    """INSERT OR IGNORE INTO snmp_trap_config (id, destinations, templates) VALUES
       ('default', '[]', '[]');""",

    # system_settings
    """INSERT OR IGNORE INTO system_settings (key, value, category, description) VALUES
       ('app_port',           '8000',     'general',   '管理 API 监听端口'),
       ('log_level',          '"info"',   'general',   '日志级别: debug / info / warn / error'),
       ('data_dir',           '"./data"', 'general',   '数据存储目录'),
       ('max_devices',        '50000',    'general',   '最大设备数限制'),
       ('auto_save_enabled',  'true',     'auto_save', '是否启用自动保存'),
       ('auto_save_debounce', '3',        'auto_save', '防抖自动保存间隔（秒）'),
       ('auto_save_interval', '60',       'auto_save', '定时保存间隔（秒）'),
       ('max_versions',       '10',       'history',   '拓扑最大版本保留数'),
       ('max_request_logs',   '10000',    'history',   '请求日志最大保留数'),
       ('log_response_body',  'true',     'log',       '是否记录响应体'),
       ('log_body_max_size',  '10240',    'log',       '响应体记录最大大小（字节）');""",
]

# Current schema version
CURRENT_SCHEMA_VERSION = 1


class PersistStore:
    """Manages the persistent SQLite file database."""

    def __init__(self) -> None:
        self._db: aiosqlite.Connection | None = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("PersistStore not started")
        return self._db

    async def start(self) -> None:
        """Open DB connection, apply PRAGMAs, run migrations, insert presets."""
        db_path = settings.db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

        self._db = await aiosqlite.connect(db_path)
        self._db.row_factory = aiosqlite.Row
        logger.info(f"PersistStore: opened database at {db_path}")

        # Apply PRAGMAs
        await self._db.execute("PRAGMA journal_mode = WAL")
        await self._db.execute("PRAGMA synchronous = NORMAL")
        await self._db.execute("PRAGMA cache_size = -8000")
        await self._db.execute("PRAGMA temp_store = MEMORY")
        await self._db.execute("PRAGMA mmap_size = 134217728")
        await self._db.execute("PRAGMA foreign_keys = ON")

        # Run migrations
        await self._migrate()

        # Insert preset data
        await self._insert_presets()

        logger.info("PersistStore: initialization complete")

    async def stop(self) -> None:
        """Close DB connection."""
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("PersistStore: closed database")

    async def _migrate(self) -> None:
        """Run schema migrations."""
        await self._db.executescript(SCHEMA_MIGRATIONS_DDL)

        # Check current version
        async with self._db.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ) as cursor:
            row = await cursor.fetchone()
            current = row[0] if row and row[0] is not None else 0

        if current >= CURRENT_SCHEMA_VERSION:
            logger.info(f"PersistStore: schema is up to date (v{current})")
            return

        # Apply v1: initial schema
        if current < 1:
            logger.info("PersistStore: applying migration v1 (initial schema)")
            for ddl in TABLES_DDL:
                await self._db.executescript(ddl)
            await self._db.execute(
                "INSERT INTO schema_migrations (version, description) VALUES (1, 'initial schema')"
            )
            await self._db.commit()
            logger.info("PersistStore: migration v1 applied")

    async def _insert_presets(self) -> None:
        """Insert preset data (idempotent via INSERT OR IGNORE)."""
        for sql in PRESET_DATA:
            await self._db.executescript(sql)
        await self._db.commit()
        logger.debug("PersistStore: preset data ensured")

    # ------------------------------------------------------------------
    # Generic query helpers
    # ------------------------------------------------------------------

    async def execute(self, sql: str, params: tuple | dict = ()) -> aiosqlite.Cursor:
        """Execute a single SQL statement."""
        return await self.db.execute(sql, params)

    async def executemany(self, sql: str, params_seq: list) -> None:
        """Execute a SQL statement with multiple parameter sets."""
        await self.db.executemany(sql, params_seq)

    async def commit(self) -> None:
        """Commit the current transaction."""
        await self.db.commit()

    async def fetch_one(self, sql: str, params: tuple | dict = ()) -> dict | None:
        """Fetch a single row as dict."""
        async with self.db.execute(sql, params) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return dict(row)

    async def fetch_all(self, sql: str, params: tuple | dict = ()) -> list[dict]:
        """Fetch all rows as list of dicts."""
        async with self.db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def fetch_count(self, sql: str, params: tuple | dict = ()) -> int:
        """Execute a COUNT query and return the integer result."""
        async with self.db.execute(sql, params) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0
