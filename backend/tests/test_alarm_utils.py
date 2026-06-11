import sqlite3
from app.db.migrations import run_migrations
from app.admin._alarm_utils import (
    NODE_SYSTEM_FIELDS,
    build_alarm_attrs,
    resolve_mapping,
)


def _make_db_with_node():
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    run_migrations(conn)
    conn.execute("INSERT INTO topologies (id, name) VALUES ('t1', 'T1')")
    conn.execute("INSERT INTO node_types (id, code, name, category) VALUES ('nt1', 'sw', 'SW', 'switch')")
    conn.execute(
        "INSERT INTO nodes (id, topology_id, node_type_id, name, dn, status) "
        "VALUES ('n1', 't1', 'nt1', 'sw-001', 'dn-001', 'online')"
    )
    conn.execute(
        "INSERT INTO node_attrs (node_id, field_key, value) VALUES ('n1', 'ip', '192.168.1.1')"
    )
    return conn


def test_node_system_fields_contains_expected_columns():
    assert NODE_SYSTEM_FIELDS == {"name", "dn", "id", "status", "group_id"}


def test_resolve_mapping_system_field_name():
    conn = _make_db_with_node()
    assert resolve_mapping(conn, "n1", "name") == "sw-001"


def test_resolve_mapping_system_field_dn():
    conn = _make_db_with_node()
    assert resolve_mapping(conn, "n1", "dn") == "dn-001"


def test_resolve_mapping_system_field_status():
    conn = _make_db_with_node()
    assert resolve_mapping(conn, "n1", "status") == "online"


def test_resolve_mapping_custom_field_found():
    conn = _make_db_with_node()
    assert resolve_mapping(conn, "n1", "ip") == "192.168.1.1"


def test_resolve_mapping_custom_field_not_found():
    conn = _make_db_with_node()
    assert resolve_mapping(conn, "n1", "nonexistent") is None


def test_resolve_mapping_node_not_exist():
    conn = _make_db_with_node()
    assert resolve_mapping(conn, "node_missing", "name") is None


def test_build_alarm_attrs_user_value_wins():
    conn = _make_db_with_node()
    fields = [
        {"field_key": "node_ip", "mapping_target": "ip", "default_value": "0.0.0.0"},
    ]
    result = build_alarm_attrs(conn, "n1", fields, user_provided={"node_ip": "USER"})
    assert result == {"node_ip": "USER"}


def test_build_alarm_attrs_mapping_wins_over_default():
    conn = _make_db_with_node()
    fields = [
        {"field_key": "node_ip", "mapping_target": "ip", "default_value": "0.0.0.0"},
    ]
    result = build_alarm_attrs(conn, "n1", fields)
    assert result == {"node_ip": "192.168.1.1"}


def test_build_alarm_attrs_default_when_no_mapping():
    conn = _make_db_with_node()
    fields = [
        {"field_key": "severity", "mapping_target": None, "default_value": "minor"},
    ]
    result = build_alarm_attrs(conn, "n1", fields)
    assert result == {"severity": "minor"}


def test_build_alarm_attrs_default_when_mapping_target_missing():
    conn = _make_db_with_node()
    fields = [
        {"field_key": "node_x", "mapping_target": "nonexistent_field", "default_value": "DEF"},
    ]
    result = build_alarm_attrs(conn, "n1", fields)
    assert result == {"node_x": "DEF"}


def test_build_alarm_attrs_skip_when_all_null():
    conn = _make_db_with_node()
    fields = [
        {"field_key": "k", "mapping_target": None, "default_value": None},
    ]
    result = build_alarm_attrs(conn, "n1", fields)
    assert result == {}


def test_build_alarm_attrs_user_value_none_falls_through_to_mapping():
    conn = _make_db_with_node()
    fields = [
        {"field_key": "node_ip", "mapping_target": "ip", "default_value": "0.0.0.0"},
    ]
    result = build_alarm_attrs(conn, "n1", fields, user_provided={"node_ip": None})
    assert result == {"node_ip": "192.168.1.1"}


def test_build_alarm_attrs_mixed_fields():
    conn = _make_db_with_node()
    fields = [
        {"field_key": "node_name", "mapping_target": "name", "default_value": None},
        {"field_key": "severity", "mapping_target": None, "default_value": "minor"},
        {"field_key": "user_field", "mapping_target": None, "default_value": "FALLBACK"},
    ]
    result = build_alarm_attrs(conn, "n1", fields, user_provided={"user_field": "USER"})
    assert result == {"node_name": "sw-001", "severity": "minor", "user_field": "USER"}
