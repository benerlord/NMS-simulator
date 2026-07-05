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


def test_node_type_create_no_legacy_fields():
    """NodeTypeCreate 不再接受 icon/color/shape/renderMode/dnTemplate。"""
    from app.admin.schemas.node_type import NodeTypeCreate

    # 只能传新字段
    c = NodeTypeCreate(code="sw", name="交换机", category="physical")
    dumped = c.model_dump(by_alias=True)
    for k in ("icon", "color", "shape", "renderMode", "dnTemplate"):
        assert k not in dumped, f"NodeTypeCreate 不应保留死字段 {k}"


def test_node_type_create_accepts_domain_ids():
    """NodeTypeCreate 新增 domainIds 可选字段。"""
    from app.admin.schemas.node_type import NodeTypeCreate

    c = NodeTypeCreate(code="sw", name="交换机", category="physical", domainIds=["dom_a", "dom_b"])
    assert c.domain_ids == ["dom_a", "dom_b"]

    # None 表示不改动关联
    c2 = NodeTypeCreate(code="sw2", name="交换机2", category="physical")
    assert c2.domain_ids is None

    # 空数组表示清空关联
    c3 = NodeTypeCreate(code="sw3", name="交换机3", category="physical", domainIds=[])
    assert c3.domain_ids == []


def test_node_type_update_accepts_domain_ids():
    """NodeTypeUpdate 新增 domainIds 可选字段。"""
    from app.admin.schemas.node_type import NodeTypeUpdate

    u = NodeTypeUpdate(name="新名字", domainIds=["dom_c"])
    assert u.domain_ids == ["dom_c"]
    assert "renderMode" not in u.model_dump(by_alias=True, exclude_unset=True)
