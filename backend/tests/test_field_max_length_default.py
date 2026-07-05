"""三处字段 Schema 的 text max_length 兜底测试。

user story: 用户新增 text 字段忘填 MaxLen —— 应自动填 255 而不是报 400。
"""
import pytest
from pydantic import ValidationError

from app.admin.schemas.node_type import NodeTypeFieldInput, EdgeTypeFieldInput
from app.admin.schemas.alarm import AlarmSchemaFieldCreate


def test_node_type_field_text_maxlen_none_defaults_to_255():
    """NodeTypeFieldInput: text 类型 max_length=None → 255。"""
    f = NodeTypeFieldInput(fieldKey="ip", fieldLabel="IP", fieldType="text")
    assert f.max_length == 255


def test_node_type_field_text_maxlen_explicit_preserved():
    """NodeTypeFieldInput: 显式 max_length=100 → 保留 100。"""
    f = NodeTypeFieldInput(fieldKey="ip", fieldLabel="IP", fieldType="text", maxLength=100)
    assert f.max_length == 100


def test_node_type_field_text_maxlen_zero_still_rejected():
    """NodeTypeFieldInput: max_length=0 仍拒绝（Field ge=1 兜底）。"""
    with pytest.raises(ValidationError):
        NodeTypeFieldInput(fieldKey="ip", fieldLabel="IP", fieldType="text", maxLength=0)


def test_node_type_field_number_maxlen_none_stays_none():
    """NodeTypeFieldInput: number 类型 max_length=None 不动 —— 只对 text 兜底。"""
    f = NodeTypeFieldInput(fieldKey="p", fieldLabel="端口", fieldType="number")
    assert f.max_length is None


def test_edge_type_field_text_maxlen_none_defaults_to_255():
    """EdgeTypeFieldInput: text 类型 max_length=None → 255。"""
    f = EdgeTypeFieldInput(fieldKey="bw", fieldLabel="带宽", fieldType="text")
    assert f.max_length == 255


def test_alarm_schema_field_text_maxlen_none_defaults_to_255():
    """AlarmSchemaFieldCreate: text 类型 max_length=None → 255。"""
    f = AlarmSchemaFieldCreate(fieldKey="msg", fieldLabel="告警文本", fieldType="text")
    assert f.max_length == 255
