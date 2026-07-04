import sqlite3

from app.db.migrations import run_migrations


def _fresh_conn(tmp_path):
    c = sqlite3.connect(str(tmp_path / "t.db"), isolation_level=None)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def _table_columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_migration_creates_node_group_alarms_table(tmp_path):
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    cols = _table_columns(conn, "node_group_alarms")
    assert cols == {"id", "node_group_id", "alarm_index", "created_at", "updated_at"}
    conn.close()


def test_migration_creates_node_group_alarm_attrs_table(tmp_path):
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    cols = _table_columns(conn, "node_group_alarm_attrs")
    assert cols == {"alarm_id", "field_key", "value"}
    conn.close()


def test_migration_cascade_delete_group_removes_alarms(tmp_path):
    """删除 node_group 应级联删除其 alarms + alarm_attrs。"""
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    # 造种子数据
    conn.execute("INSERT INTO topologies (id, name) VALUES ('topo_t', 'T')")
    conn.execute("INSERT INTO node_types (id, code, name, category) VALUES ('nt_t', 'dev', 'D', 'switch')")
    conn.execute(
        "INSERT INTO node_groups (id, topology_id, node_type_id, group_name, node_count) "
        "VALUES ('grp_t', 'topo_t', 'nt_t', 'G', 3)"
    )
    conn.execute(
        "INSERT INTO node_group_alarms (id, node_group_id, alarm_index) VALUES ('ga_1', 'grp_t', 1)"
    )
    conn.execute(
        "INSERT INTO node_group_alarm_attrs (alarm_id, field_key, value) VALUES ('ga_1', 'severity', 'critical')"
    )

    conn.execute("DELETE FROM node_groups WHERE id = 'grp_t'")

    alarms = conn.execute("SELECT COUNT(*) c FROM node_group_alarms").fetchone()
    attrs = conn.execute("SELECT COUNT(*) c FROM node_group_alarm_attrs").fetchone()
    assert alarms["c"] == 0
    assert attrs["c"] == 0
    conn.close()


def test_migration_cascade_delete_alarm_removes_attrs(tmp_path):
    """删除 node_group_alarms 行应级联删除其 attrs。"""
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    conn.execute("INSERT INTO topologies (id, name) VALUES ('topo_t', 'T')")
    conn.execute("INSERT INTO node_types (id, code, name, category) VALUES ('nt_t', 'dev', 'D', 'switch')")
    conn.execute(
        "INSERT INTO node_groups (id, topology_id, node_type_id, group_name, node_count) "
        "VALUES ('grp_t', 'topo_t', 'nt_t', 'G', 3)"
    )
    conn.execute("INSERT INTO node_group_alarms (id, node_group_id, alarm_index) VALUES ('ga_1', 'grp_t', 1)")
    conn.execute(
        "INSERT INTO node_group_alarm_attrs (alarm_id, field_key, value) VALUES ('ga_1', 'severity', 'critical')"
    )

    conn.execute("DELETE FROM node_group_alarms WHERE id = 'ga_1'")

    attrs = conn.execute("SELECT COUNT(*) c FROM node_group_alarm_attrs").fetchone()
    assert attrs["c"] == 0
    conn.close()


def test_migration_is_idempotent(tmp_path):
    conn = _fresh_conn(tmp_path)
    run_migrations(conn)
    run_migrations(conn)  # 二次跑不应报错
    assert _table_columns(conn, "node_group_alarms") == {
        "id", "node_group_id", "alarm_index", "created_at", "updated_at"
    }
    conn.close()
