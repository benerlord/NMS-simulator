import pytest
from pydantic import ValidationError
from app.admin.schemas import (
    AlarmSchemaCreate,
    AlarmSchemaFieldCreate,
    TopologyAlarmSchemaPatch,
)


def test_field_text_maxlen_none_defaults_to_255():
    """text 类型 max_length=None → 兜底 255（旧行为 raise 已在 2026-07-05 移除）。"""
    f = AlarmSchemaFieldCreate(
        field_key="x", field_label="X", field_type="text"
    )
    assert f.max_length == 255


def test_field_non_text_no_max_length_needed():
    f = AlarmSchemaFieldCreate(
        field_key="x", field_label="X", field_type="number"
    )
    assert f.max_length is None


def test_alarm_schema_create_camel_alias():
    f = AlarmSchemaFieldCreate(
        fieldKey="alarm_id",
        fieldLabel="告警ID",
        fieldType="text",
        maxLength=64,
        sortOrder=1,
    )
    dump = f.model_dump(by_alias=True)
    assert "fieldKey" in dump and "fieldLabel" in dump and "fieldType" in dump
    assert "maxLength" in dump and "sortOrder" in dump
    assert "field_key" not in dump


def test_topology_alarm_schema_patch_clear_existing_default_false():
    p = TopologyAlarmSchemaPatch(alarmSchemaId="as_1")
    assert p.clear_existing is False
    assert p.alarm_schema_id == "as_1"
