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
