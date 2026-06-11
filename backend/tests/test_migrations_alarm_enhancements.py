def test_alarm_schema_fields_has_mapping_target(conn):
    rows = conn.execute("PRAGMA table_info(alarm_schema_fields)").fetchall()
    cols = {r["name"] for r in rows}
    assert "mapping_target" in cols


def test_alarm_schemas_has_display_field_key(conn):
    rows = conn.execute("PRAGMA table_info(alarm_schemas)").fetchall()
    cols = {r["name"] for r in rows}
    assert "display_field_key" in cols


def test_mapping_target_can_be_null(conn):
    conn.execute(
        "INSERT INTO alarm_schemas (id, code, name) VALUES ('as_1', 'a', 'A')"
    )
    conn.execute(
        "INSERT INTO alarm_schema_fields (alarm_schema_id, field_key, field_label, field_type) "
        "VALUES ('as_1', 'k1', 'L1', 'text')"
    )
    r = conn.execute(
        "SELECT mapping_target FROM alarm_schema_fields WHERE field_key = 'k1'"
    ).fetchone()
    assert r["mapping_target"] is None


def test_display_field_key_can_be_null(conn):
    conn.execute(
        "INSERT INTO alarm_schemas (id, code, name) VALUES ('as_2', 'b', 'B')"
    )
    r = conn.execute(
        "SELECT display_field_key FROM alarm_schemas WHERE id = 'as_2'"
    ).fetchone()
    assert r["display_field_key"] is None
