import sqlite3

import pytest

from app.db.migrations import run_migrations


def _fresh_conn(tmp_path):
    c = sqlite3.connect(str(tmp_path / "t.db"), isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def _read_table_sql(conn, table):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row["sql"] if row else ""


def test_migration_rewrites_api_configs_to_domain_unique(tmp_path):
    """迁移后 api_configs 应带 UNIQUE(domain_id, method, path)，且不再有 UNIQUE(method, path)。"""
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    sql = _read_table_sql(conn, "api_configs")
    assert "UNIQUE (domain_id, method, path)" in sql or "UNIQUE(domain_id, method, path)" in sql
    # 旧约束不能残留（用括号形式匹配避免误匹配子串）
    assert "UNIQUE (method, path)" not in sql
    assert "UNIQUE(method, path)" not in sql
    conn.close()


def test_migration_is_idempotent(tmp_path):
    """连续跑两次 run_migrations 不应报错、也不应重复处理。"""
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    sql1 = _read_table_sql(conn, "api_configs")
    run_migrations(conn)
    sql2 = _read_table_sql(conn, "api_configs")
    assert sql1 == sql2
    conn.close()


def test_migration_preserves_cross_domain_rows(tmp_path):
    """老库里跨域同 (method, path) 的合法数据必须保留（本次改动仅"放宽"约束）。"""
    # 模拟一个"仍是老约束"的库：先跑一次拿到新表，再"造老库"
    # 简化：先跑一次拿到新表；两个域下各插一条同名接口，确认可插入 & 迁移是幂等的
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)

    # 造两个域
    conn.execute("INSERT INTO domains (id, name) VALUES ('dA', 'A')")
    conn.execute("INSERT INTO domains (id, name) VALUES ('dB', 'B')")
    # 跨域插两条同 (method, path)
    conn.execute(
        "INSERT INTO api_configs (id, name, method, path, data_source, domain_id, config) "
        "VALUES ('api_a', 'A-token', 'PUT', '/token', 'static', 'dA', '{}')"
    )
    conn.execute(
        "INSERT INTO api_configs (id, name, method, path, data_source, domain_id, config) "
        "VALUES ('api_b', 'B-token', 'PUT', '/token', 'static', 'dB', '{}')"
    )
    # 再跑一次迁移，数据不应丢
    run_migrations(conn)
    rows = conn.execute("SELECT id FROM api_configs ORDER BY id").fetchall()
    assert [r["id"] for r in rows] == ["api_a", "api_b"]
    conn.close()


def test_migration_blocks_same_domain_duplicate(tmp_path):
    """迁移后同域插两条同 (method, path) 应被 UNIQUE 拦下。"""
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    conn.execute("INSERT INTO domains (id, name) VALUES ('dA', 'A')")
    conn.execute(
        "INSERT INTO api_configs (id, name, method, path, data_source, domain_id, config) "
        "VALUES ('api_a1', 'A1', 'PUT', '/token', 'static', 'dA', '{}')"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO api_configs (id, name, method, path, data_source, domain_id, config) "
            "VALUES ('api_a2', 'A2', 'PUT', '/token', 'static', 'dA', '{}')"
        )
    conn.close()


def test_migration_allows_null_domain_duplicate(tmp_path):
    """迁移后 domain_id=NULL 的未归类接口可以有重复 (method, path)——SQLite NULL 语义。"""
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    conn.execute(
        "INSERT INTO api_configs (id, name, method, path, data_source, config) "
        "VALUES ('api_n1', 'N1', 'GET', '/foo', 'static', '{}')"
    )
    conn.execute(
        "INSERT INTO api_configs (id, name, method, path, data_source, config) "
        "VALUES ('api_n2', 'N2', 'GET', '/foo', 'static', '{}')"
    )
    rows = conn.execute("SELECT COUNT(*) c FROM api_configs WHERE path='/foo'").fetchone()
    assert rows["c"] == 2
    conn.close()


def test_migration_idempotence_check_tolerates_whitespace_variants(tmp_path):
    """幂等判断应能识别手工格式化的 UNIQUE 声明（多余空格等），避免无谓 rebuild。"""
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)  # 第一次跑到新约束

    # 手工把 api_configs 的 CREATE SQL 改成含多余空格的等价形态
    # 注意：SQLite 不支持直接改 sqlite_master.sql，所以这里用另一种方式：
    # 手工 rename + 手工 create 一个带"怪异 UNIQUE 空格"的等价表，模拟人工迁移过的库
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("ALTER TABLE api_configs RENAME TO api_configs_ws")
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
          UNIQUE ( domain_id , method , path )
        )
    """)
    conn.execute("INSERT INTO api_configs SELECT * FROM api_configs_ws")
    conn.execute("DROP TABLE api_configs_ws")
    conn.execute("PRAGMA foreign_keys = ON")

    sql_before = _read_table_sql(conn, "api_configs")
    assert "UNIQUE ( domain_id , method , path )" in sql_before  # 现在的怪异形态

    # 再跑一次 run_migrations，_rebuild_api_configs_domain_unique 应识别为"已是新约束"，跳过 rebuild
    run_migrations(conn)
    sql_after = _read_table_sql(conn, "api_configs")
    # 不重建 → SQL 不变
    assert sql_after == sql_before
    conn.close()


def test_migration_atomicity_rollback_on_insert_failure(tmp_path, monkeypatch):
    """如果重建过程中 INSERT 失败，应通过 SAVEPOINT 回滚，不留半迁移态。"""
    import sqlite3
    from app.db import migrations

    conn = _fresh_conn(tmp_path)
    # 先建一个"老约束"的表：把 SCHEMA_SQL 跑一次，此时 api_configs 有 UNIQUE(method, path)
    conn.executescript(migrations.SCHEMA_SQL)
    # 老表初始只有 12 列（没 domain_id / category）；先加上，模拟历史增量列
    try:
        conn.execute("ALTER TABLE api_configs ADD COLUMN domain_id TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE api_configs ADD COLUMN category TEXT")
    except sqlite3.OperationalError:
        pass
    # 再手动加一个新 CREATE 里不存在的"未来"列，触发 INSERT SELECT 时的列不存在错
    conn.execute("ALTER TABLE api_configs ADD COLUMN future_col TEXT")
    # 插一条数据，确保回滚能验证"数据未丢"
    conn.execute(
        "INSERT INTO api_configs (id, name, method, path, data_source, config, future_col) "
        "VALUES ('api_x', 'x', 'GET', '/x', 'static', '{}', 'v')"
    )

    # 跑迁移，应抛异常并回滚
    with pytest.raises(sqlite3.OperationalError):
        migrations._rebuild_api_configs_domain_unique(conn)

    # 表结构必须还是老约束（回滚成功）
    sql = _read_table_sql(conn, "api_configs")
    assert "UNIQUE (method, path)" in sql or "UNIQUE(method, path)" in sql
    # 数据也必须还在
    rows = conn.execute("SELECT id, future_col FROM api_configs").fetchall()
    assert [dict(r) for r in rows] == [{"id": "api_x", "future_col": "v"}]
    # 备份表不能残留
    bak = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='api_configs_bak_domain_unique'"
    ).fetchone()
    assert bak is None
    conn.close()
