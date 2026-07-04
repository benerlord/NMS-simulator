import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS topologies (
  id              TEXT PRIMARY KEY,
  name            TEXT NOT NULL UNIQUE,
  description     TEXT,
  version         INTEGER NOT NULL DEFAULT 1,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS node_types (
  id              TEXT PRIMARY KEY,
  code            TEXT NOT NULL UNIQUE,
  name            TEXT NOT NULL,
  category        TEXT NOT NULL,
  icon            TEXT,
  color           TEXT,
  shape           TEXT,
  render_mode     TEXT NOT NULL DEFAULT 'none'
                  CHECK (render_mode IN ('none','flat')),
  dn_template     TEXT,
  description     TEXT,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS node_type_fields (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  node_type_id    TEXT NOT NULL,
  field_key       TEXT NOT NULL,
  field_label     TEXT NOT NULL,
  field_type      TEXT NOT NULL CHECK (field_type IN ('text','number','select','boolean','array')),
  default_value   TEXT,
  options         TEXT,
  required        INTEGER NOT NULL DEFAULT 0,
  sort_order      INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (node_type_id) REFERENCES node_types(id) ON DELETE CASCADE,
  UNIQUE (node_type_id, field_key)
);

CREATE TABLE IF NOT EXISTS edge_types (
  id                      TEXT PRIMARY KEY,
  code                    TEXT NOT NULL UNIQUE,
  name                    TEXT NOT NULL,
  semantic                TEXT NOT NULL DEFAULT 'connect'
                          CHECK (semantic IN ('connect','contain')),
  directed                INTEGER NOT NULL DEFAULT 1,
  exclusive_target        INTEGER NOT NULL DEFAULT 0,
  allow_source_type_codes TEXT,
  allow_target_type_codes TEXT,
  line_style              TEXT,
  color                   TEXT,
  description             TEXT,
  created_at              TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS edge_type_fields (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  edge_type_id    TEXT NOT NULL,
  field_key       TEXT NOT NULL,
  field_label     TEXT NOT NULL,
  field_type      TEXT NOT NULL CHECK (field_type IN ('text','number','select','boolean','array')),
  default_value   TEXT,
  options         TEXT,
  required        INTEGER NOT NULL DEFAULT 0,
  sort_order      INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (edge_type_id) REFERENCES edge_types(id) ON DELETE CASCADE,
  UNIQUE (edge_type_id, field_key)
);

CREATE TABLE IF NOT EXISTS nodes (
  id              TEXT PRIMARY KEY,
  topology_id     TEXT NOT NULL,
  node_type_id    TEXT NOT NULL,
  name            TEXT NOT NULL,
  dn              TEXT,
  status          TEXT NOT NULL DEFAULT 'online',
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (topology_id)  REFERENCES topologies(id) ON DELETE CASCADE,
  FOREIGN KEY (node_type_id) REFERENCES node_types(id)
);
CREATE INDEX IF NOT EXISTS idx_nodes_topo          ON nodes(topology_id);
CREATE INDEX IF NOT EXISTS idx_nodes_type          ON nodes(node_type_id);
CREATE INDEX IF NOT EXISTS idx_nodes_topo_type     ON nodes(topology_id, node_type_id);
CREATE INDEX IF NOT EXISTS idx_nodes_status        ON nodes(status);
CREATE UNIQUE INDEX IF NOT EXISTS uq_nodes_topo_dn ON nodes(topology_id, dn) WHERE dn IS NOT NULL;

CREATE TABLE IF NOT EXISTS node_attrs (
  node_id         TEXT NOT NULL,
  field_key       TEXT NOT NULL,
  value           TEXT,
  PRIMARY KEY (node_id, field_key),
  FOREIGN KEY (node_id) REFERENCES nodes(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_node_attrs_key ON node_attrs(field_key);

CREATE TABLE IF NOT EXISTS edges (
  id              TEXT PRIMARY KEY,
  topology_id     TEXT NOT NULL,
  edge_type_id    TEXT NOT NULL,
  source_id       TEXT NOT NULL,
  target_id       TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'up',
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (topology_id)  REFERENCES topologies(id) ON DELETE CASCADE,
  FOREIGN KEY (edge_type_id) REFERENCES edge_types(id),
  FOREIGN KEY (source_id)    REFERENCES nodes(id) ON DELETE CASCADE,
  FOREIGN KEY (target_id)    REFERENCES nodes(id) ON DELETE CASCADE,
  CHECK (source_id <> target_id)
);
CREATE INDEX IF NOT EXISTS idx_edges_topo      ON edges(topology_id);
CREATE INDEX IF NOT EXISTS idx_edges_type      ON edges(edge_type_id);
CREATE INDEX IF NOT EXISTS idx_edges_src       ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_tgt       ON edges(target_id);
CREATE INDEX IF NOT EXISTS idx_edges_topo_type ON edges(topology_id, edge_type_id);

CREATE TABLE IF NOT EXISTS edge_attrs (
  edge_id         TEXT NOT NULL,
  field_key       TEXT NOT NULL,
  value           TEXT,
  PRIMARY KEY (edge_id, field_key),
  FOREIGN KEY (edge_id) REFERENCES edges(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_edge_attrs_key ON edge_attrs(field_key);

CREATE TABLE IF NOT EXISTS canvas_nodes (
  node_id         TEXT PRIMARY KEY,
  topology_id     TEXT NOT NULL,
  x               REAL NOT NULL DEFAULT 0,
  y               REAL NOT NULL DEFAULT 0,
  FOREIGN KEY (node_id)     REFERENCES nodes(id) ON DELETE CASCADE,
  FOREIGN KEY (topology_id) REFERENCES topologies(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_canvas_topo ON canvas_nodes(topology_id);

CREATE TABLE IF NOT EXISTS api_configs (
  id              TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  method          TEXT NOT NULL,
  path            TEXT NOT NULL,
  enabled         INTEGER NOT NULL DEFAULT 1,
  group_name      TEXT,
  data_source     TEXT NOT NULL CHECK (data_source IN ('sql','static')),
  topology_id     TEXT,
  sql_text        TEXT,
  config          TEXT NOT NULL,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (topology_id) REFERENCES topologies(id),
  UNIQUE (method, path)
);
CREATE INDEX IF NOT EXISTS idx_apis_enabled ON api_configs(enabled);
CREATE INDEX IF NOT EXISTS idx_apis_topo    ON api_configs(topology_id);
CREATE INDEX IF NOT EXISTS idx_apis_group   ON api_configs(group_name);

CREATE TABLE IF NOT EXISTS tokens (
  token           TEXT PRIMARY KEY,
  issued_at       TEXT NOT NULL DEFAULT (datetime('now')),
  expires_at      TEXT NOT NULL,
  revoked         INTEGER NOT NULL DEFAULT 0,
  issued_by_api   TEXT,
  meta            TEXT
);
CREATE INDEX IF NOT EXISTS idx_tokens_exp ON tokens(expires_at);

CREATE TABLE IF NOT EXISTS request_logs (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  ts              TEXT NOT NULL DEFAULT (datetime('now')),
  api_id          TEXT,
  method          TEXT NOT NULL,
  path            TEXT NOT NULL,
  query           TEXT,
  status_code     INTEGER NOT NULL,
  duration_ms     INTEGER NOT NULL,
  client_ip       TEXT,
  error_message   TEXT
);
CREATE INDEX IF NOT EXISTS idx_logs_ts     ON request_logs(ts DESC);
CREATE INDEX IF NOT EXISTS idx_logs_api    ON request_logs(api_id);
CREATE INDEX IF NOT EXISTS idx_logs_status ON request_logs(status_code);

CREATE TABLE IF NOT EXISTS settings (
  key             TEXT PRIMARY KEY,
  value           TEXT NOT NULL,
  updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS node_groups (
  id              TEXT PRIMARY KEY,
  topology_id     TEXT NOT NULL,
  node_type_id    TEXT NOT NULL,
  group_name      TEXT NOT NULL,
  node_count      INTEGER NOT NULL CHECK (node_count > 0),
  name_template   TEXT NOT NULL DEFAULT '{group}-{i:05d}',
  attr_strategies TEXT NOT NULL DEFAULT '[]',
  edge_strategies TEXT,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (topology_id) REFERENCES topologies(id) ON DELETE CASCADE,
  FOREIGN KEY (node_type_id) REFERENCES node_types(id)
);
CREATE INDEX IF NOT EXISTS idx_node_groups_topo ON node_groups(topology_id);

CREATE TABLE IF NOT EXISTS domains (
  id              TEXT PRIMARY KEY,
  name            TEXT NOT NULL UNIQUE,
  description     TEXT,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS domain_node_types (
  domain_id       TEXT NOT NULL,
  node_type_id    TEXT NOT NULL,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (domain_id, node_type_id),
  FOREIGN KEY (domain_id) REFERENCES domains(id) ON DELETE CASCADE,
  FOREIGN KEY (node_type_id) REFERENCES node_types(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_dnt_domain ON domain_node_types(domain_id);
CREATE INDEX IF NOT EXISTS idx_dnt_type   ON domain_node_types(node_type_id);

CREATE TABLE IF NOT EXISTS mock_instances (
  id              TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  topology_id     TEXT NOT NULL,
  port            INTEGER NOT NULL,
  description     TEXT,
  enabled         INTEGER NOT NULL DEFAULT 1,
  status          TEXT NOT NULL DEFAULT 'running',
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (topology_id) REFERENCES topologies(id) ON DELETE CASCADE,
  UNIQUE (port)
);
CREATE INDEX IF NOT EXISTS idx_instances_topo ON mock_instances(topology_id);

CREATE TABLE IF NOT EXISTS alarm_schemas (
  id              TEXT PRIMARY KEY,
  code            TEXT NOT NULL UNIQUE,
  name            TEXT NOT NULL,
  description     TEXT,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS alarm_schema_fields (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  alarm_schema_id TEXT NOT NULL,
  field_key       TEXT NOT NULL,
  field_label     TEXT NOT NULL,
  field_type      TEXT NOT NULL CHECK (field_type IN ('text','number','select','boolean','array')),
  default_value   TEXT,
  options         TEXT,
  required        INTEGER NOT NULL DEFAULT 0,
  max_length      INTEGER,
  sort_order      INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (alarm_schema_id) REFERENCES alarm_schemas(id) ON DELETE CASCADE,
  UNIQUE (alarm_schema_id, field_key)
);

CREATE TABLE IF NOT EXISTS node_alarms (
  id              TEXT PRIMARY KEY,
  node_id         TEXT NOT NULL,
  alarm_index     INTEGER NOT NULL,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (node_id) REFERENCES nodes(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_node_alarms_node ON node_alarms(node_id);

CREATE TABLE IF NOT EXISTS node_alarm_attrs (
  alarm_id        TEXT NOT NULL,
  field_key       TEXT NOT NULL,
  value           TEXT,
  PRIMARY KEY (alarm_id, field_key),
  FOREIGN KEY (alarm_id) REFERENCES node_alarms(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_node_alarm_attrs_key ON node_alarm_attrs(field_key);

CREATE TABLE IF NOT EXISTS node_group_alarms (
  id              TEXT PRIMARY KEY,
  node_group_id   TEXT NOT NULL,
  alarm_index     INTEGER NOT NULL,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (node_group_id) REFERENCES node_groups(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_group_alarms_grp ON node_group_alarms(node_group_id);

CREATE TABLE IF NOT EXISTS node_group_alarm_attrs (
  alarm_id        TEXT NOT NULL,
  field_key       TEXT NOT NULL,
  value           TEXT,
  PRIMARY KEY (alarm_id, field_key),
  FOREIGN KEY (alarm_id) REFERENCES node_group_alarms(id) ON DELETE CASCADE
);
"""


def _expand_field_type_check(
    conn: sqlite3.Connection,
    table: str,
    fk_clause: str,
    unique_clause: str,
) -> None:
    """幂等地将 field_type CHECK 约束扩展为包含 'array'。

    SQLite 不支持 ALTER TABLE MODIFY CONSTRAINT，因此采用
    rename → create new → copy → drop old 模式。
    若当前表的 SQL 定义已包含 'array'，则跳过。
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if row is None:
        return  # 表不存在，等 SCHEMA_SQL 创建
    table_sql = row[0] or ""
    if "'array'" in table_sql or "\"array\"" in table_sql:
        return  # 已是新约束，无需重建

    # 暂时关闭外键约束以允许重命名
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        # 确定实际列（通过 PRAGMA）
        cols_info = conn.execute(f"PRAGMA table_info({table})").fetchall()
        col_names = [c[1] for c in cols_info]  # c[1] = name
        cols_csv = ", ".join(col_names)

        tmp = f"{table}_bak_array_migration"
        conn.execute(f"ALTER TABLE {table} RENAME TO {tmp}")

        # 从 SCHEMA_SQL 中找到新建表语句（已包含 'array'）已更新
        # 直接内联建表，使用已知列结构
        if table == "node_type_fields":
            conn.execute(f"""
                CREATE TABLE {table} (
                  id              INTEGER PRIMARY KEY AUTOINCREMENT,
                  node_type_id    TEXT NOT NULL,
                  field_key       TEXT NOT NULL,
                  field_label     TEXT NOT NULL,
                  field_type      TEXT NOT NULL
                                  CHECK (field_type IN ('text','number','select','boolean','array')),
                  default_value   TEXT,
                  options         TEXT,
                  required        INTEGER NOT NULL DEFAULT 0,
                  sort_order      INTEGER NOT NULL DEFAULT 0,
                  max_length      INTEGER,
                  {fk_clause},
                  {unique_clause}
                )
            """)
        elif table == "edge_type_fields":
            conn.execute(f"""
                CREATE TABLE {table} (
                  id              INTEGER PRIMARY KEY AUTOINCREMENT,
                  edge_type_id    TEXT NOT NULL,
                  field_key       TEXT NOT NULL,
                  field_label     TEXT NOT NULL,
                  field_type      TEXT NOT NULL
                                  CHECK (field_type IN ('text','number','select','boolean','array')),
                  default_value   TEXT,
                  options         TEXT,
                  required        INTEGER NOT NULL DEFAULT 0,
                  sort_order      INTEGER NOT NULL DEFAULT 0,
                  max_length      INTEGER,
                  {fk_clause},
                  {unique_clause}
                )
            """)
        elif table == "alarm_schema_fields":
            conn.execute(f"""
                CREATE TABLE {table} (
                  id              INTEGER PRIMARY KEY AUTOINCREMENT,
                  alarm_schema_id TEXT NOT NULL,
                  field_key       TEXT NOT NULL,
                  field_label     TEXT NOT NULL,
                  field_type      TEXT NOT NULL
                                  CHECK (field_type IN ('text','number','select','boolean','array')),
                  default_value   TEXT,
                  options         TEXT,
                  required        INTEGER NOT NULL DEFAULT 0,
                  max_length      INTEGER,
                  sort_order      INTEGER NOT NULL DEFAULT 0,
                  mapping_target  TEXT,
                  {fk_clause},
                  {unique_clause}
                )
            """)

        conn.execute(f"INSERT INTO {table} ({cols_csv}) SELECT {cols_csv} FROM {tmp}")
        conn.execute(f"DROP TABLE {tmp}")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def _rebuild_api_configs_domain_unique(conn: sqlite3.Connection) -> None:
    """把 api_configs 的 UNIQUE(method, path) 放宽成 UNIQUE(domain_id, method, path)。

    幂等：通过读取 sqlite_master 里的 CREATE TABLE 语句判断当前是老约束还是新约束。
    仅当仍是老约束（UNIQUE(method, path)）时才重建表。

    原子性：整个 rebuild 走 SAVEPOINT，中途任何异常都能回滚到原状。
    这可以防止将来新增列但忘记同步这里时留下"表已 rename、新表空壳"的半迁移态。
    """
    import re

    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='api_configs'"
    ).fetchone()
    if row is None:
        return
    table_sql = row[0] or ""
    # 用正则匹配新约束，兼容手工格式化（如 "UNIQUE ( domain_id , method , path )"）
    if re.search(r"UNIQUE\s*\(\s*domain_id\s*,\s*method\s*,\s*path\s*\)", table_sql):
        return

    # 关外键、SAVEPOINT 包裹重建、迁数据、切回
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("SAVEPOINT rebuild_api_configs")
        try:
            cols_info = conn.execute("PRAGMA table_info(api_configs)").fetchall()
            col_names = [c[1] for c in cols_info]
            cols_csv = ", ".join(col_names)

            conn.execute("ALTER TABLE api_configs RENAME TO api_configs_bak_domain_unique")

            conn.execute("""
                CREATE TABLE api_configs (
                  id              TEXT PRIMARY KEY,
                  name            TEXT NOT NULL,
                  method          TEXT NOT NULL,
                  path            TEXT NOT NULL,
                  enabled         INTEGER NOT NULL DEFAULT 1,
                  group_name      TEXT,
                  data_source     TEXT NOT NULL CHECK (data_source IN ('sql','static')),
                  topology_id     TEXT,
                  sql_text        TEXT,
                  config          TEXT NOT NULL,
                  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                  updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
                  domain_id       TEXT,
                  category        TEXT,
                  FOREIGN KEY (topology_id) REFERENCES topologies(id),
                  UNIQUE (domain_id, method, path)
                )
            """)

            conn.execute(
                f"INSERT INTO api_configs ({cols_csv}) SELECT {cols_csv} FROM api_configs_bak_domain_unique"
            )
            conn.execute("DROP TABLE api_configs_bak_domain_unique")

            # 重建原有索引（rename 会带着索引一起丢，这里显式补齐）
            conn.execute("CREATE INDEX IF NOT EXISTS idx_apis_enabled ON api_configs(enabled)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_apis_topo    ON api_configs(topology_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_apis_group   ON api_configs(group_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_apis_domain  ON api_configs(domain_id)")
            conn.execute("RELEASE SAVEPOINT rebuild_api_configs")
        except Exception:
            conn.execute("ROLLBACK TO SAVEPOINT rebuild_api_configs")
            conn.execute("RELEASE SAVEPOINT rebuild_api_configs")
            raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def run_migrations(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    # Idempotent column addition for nodes.group_id
    try:
        conn.execute("ALTER TABLE nodes ADD COLUMN group_id TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_group ON nodes(group_id)")
    # Idempotent column addition for node_groups canvas position
    try:
        conn.execute("ALTER TABLE node_groups ADD COLUMN canvas_x REAL")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE node_groups ADD COLUMN canvas_y REAL")
    except sqlite3.OperationalError:
        pass
    # Idempotent column addition for node_type_fields.max_length
    try:
        conn.execute("ALTER TABLE node_type_fields ADD COLUMN max_length INTEGER")
    except sqlite3.OperationalError:
        pass
    # Idempotent column addition for edge_type_fields.max_length
    try:
        conn.execute("ALTER TABLE edge_type_fields ADD COLUMN max_length INTEGER")
    except sqlite3.OperationalError:
        pass
    # 域作用域：topologies 新增 domain_id 列（NULL = 全局，无域限制）
    try:
        conn.execute("ALTER TABLE topologies ADD COLUMN domain_id TEXT")
    except sqlite3.OperationalError:
        pass
    conn.execute("CREATE INDEX IF NOT EXISTS idx_topologies_domain ON topologies(domain_id)")
    # 接口分类：api_configs 新增 domain_id 和 category 列
    try:
        conn.execute("ALTER TABLE api_configs ADD COLUMN domain_id TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE api_configs ADD COLUMN category TEXT")
    except sqlite3.OperationalError:
        pass
    conn.execute("CREATE INDEX IF NOT EXISTS idx_apis_domain ON api_configs(domain_id)")
    # 实例状态：mock_instances 新增 status 列
    try:
        conn.execute("ALTER TABLE mock_instances ADD COLUMN status TEXT NOT NULL DEFAULT 'running'")
    except sqlite3.OperationalError:
        pass
    # 实例协议：mock_instances 新增 ssl_enabled 列
    try:
        conn.execute("ALTER TABLE mock_instances ADD COLUMN ssl_enabled INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    # 请求日志：request_logs 新增 instance_id 列
    try:
        conn.execute("ALTER TABLE request_logs ADD COLUMN instance_id TEXT")
    except sqlite3.OperationalError:
        pass
    conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_instance ON request_logs(instance_id)")
    # Idempotent column addition for topologies.alarm_schema_id
    try:
        conn.execute("ALTER TABLE topologies ADD COLUMN alarm_schema_id TEXT")
    except sqlite3.OperationalError:
        pass
    # Idempotent column addition for alarm_schema_fields.mapping_target
    try:
        conn.execute("ALTER TABLE alarm_schema_fields ADD COLUMN mapping_target TEXT")
    except sqlite3.OperationalError:
        pass
    # Idempotent column addition for alarm_schemas.display_field_key
    try:
        conn.execute("ALTER TABLE alarm_schemas ADD COLUMN display_field_key TEXT")
    except sqlite3.OperationalError:
        pass
    # 扩展 field_type CHECK 约束以支持 'array'（SQLite 须重建表）
    # node_type_fields
    _expand_field_type_check(conn, "node_type_fields",
                             "FOREIGN KEY (node_type_id) REFERENCES node_types(id) ON DELETE CASCADE",
                             "UNIQUE (node_type_id, field_key)")
    # edge_type_fields
    _expand_field_type_check(conn, "edge_type_fields",
                             "FOREIGN KEY (edge_type_id) REFERENCES edge_types(id) ON DELETE CASCADE",
                             "UNIQUE (edge_type_id, field_key)")
    # alarm_schema_fields
    _expand_field_type_check(conn, "alarm_schema_fields",
                             "FOREIGN KEY (alarm_schema_id) REFERENCES alarm_schemas(id) ON DELETE CASCADE",
                             "UNIQUE (alarm_schema_id, field_key)")
    # 跨网管同名接口：api_configs 的 UNIQUE(method, path) 放宽为 UNIQUE(domain_id, method, path)
    _rebuild_api_configs_domain_unique(conn)
