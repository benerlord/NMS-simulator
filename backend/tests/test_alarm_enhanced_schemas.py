import pytest
from pydantic import ValidationError
from app.admin.schemas import (
    AlarmSchemaFieldCreate,
    AlarmSchemaCreate,
)


def test_field_mapping_target_accepts_valid_ident():
    f = AlarmSchemaFieldCreate(
        field_key="x", field_label="X", field_type="number",
        mapping_target="ip",
    )
    assert f.mapping_target == "ip"


def test_field_mapping_target_accepts_none():
    f = AlarmSchemaFieldCreate(
        field_key="x", field_label="X", field_type="number",
    )
    assert f.mapping_target is None


def test_field_mapping_target_rejects_invalid_chars():
    with pytest.raises(ValidationError):
        AlarmSchemaFieldCreate(
            field_key="x", field_label="X", field_type="number",
            mapping_target="bad-key!",
        )


def test_field_mapping_target_rejects_leading_digit():
    with pytest.raises(ValidationError):
        AlarmSchemaFieldCreate(
            field_key="x", field_label="X", field_type="number",
            mapping_target="1invalid",
        )


def test_alarm_schema_create_with_display_field_key():
    a = AlarmSchemaCreate(
        code="c1", name="C1", display_field_key="alarm_id",
    )
    assert a.display_field_key == "alarm_id"


def test_alarm_schema_create_display_field_key_defaults_none():
    a = AlarmSchemaCreate(code="c1", name="C1")
    assert a.display_field_key is None


def test_camel_alias_for_mapping_target_and_display_field_key():
    f = AlarmSchemaFieldCreate(
        fieldKey="x", fieldLabel="X", fieldType="number",
        mappingTarget="ip",
    )
    dump = f.model_dump(by_alias=True)
    assert "mappingTarget" in dump
    assert dump["mappingTarget"] == "ip"
