import pytest
from pydantic import ValidationError
from app.admin.schemas import (
    AlarmSchemaCreate,
    AlarmSchemaFieldCreate,
    TopologyAlarmSchemaPatch,
)


def test_field_text_requires_max_length():
    with pytest.raises(ValidationError):
        AlarmSchemaFieldCreate(
            field_key="x", field_label="X", field_type="text"
        )


def test_field_non_text_no_max_length_needed():
    f = AlarmSchemaFieldCreate(
        field_key="x", field_label="X", field_type="number"
    )
    assert f.max_length is None


def test_alarm_schema_create_camel_alias():
    a = AlarmSchemaCreate(code="huawei", name="华为告警")
    dump = a.model_dump(by_alias=True)
    assert "code" in dump and "name" in dump


def test_topology_alarm_schema_patch_clear_existing_default_false():
    p = TopologyAlarmSchemaPatch(alarmSchemaId="as_1")
    assert p.clear_existing is False
    assert p.alarm_schema_id == "as_1"
