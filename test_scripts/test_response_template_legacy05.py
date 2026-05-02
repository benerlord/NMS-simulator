"""M6-01 LEGACY-05 Phase 1 unit tests: derived pagination context vars.

Covers `_build_context` 新增的 6 个派生变量：
    {{totalPageNo}}  -> ceil(total / pageSize), pageSize<=0 兜底为 0
    {{totalPages}}   -> totalPageNo 别名
    {{hasNext}}      -> page < totalPageNo
    {{hasPrev}}      -> page > 1 and total > 0
    {{offset}}       -> (page - 1) * pageSize
    {{count}}        -> len(items)

Boundary matrix (docs/开发方案.md §2.12)：
    1. 空数据         (total=0,   pageSize=100, page=1)
    2. 末页非满       (total=28,  pageSize=100, page=1)
    3. 整除           (total=100, pageSize=100, page=1)
    4. 中间页         (total=250, pageSize=100, page=2)
    5. 末页           (total=250, pageSize=100, page=3)
    6. 异常请求       (total=0,   pageSize=100, page=2)
    7. pageSize=0 兜底 (total=任意, pageSize=0)

Rendering layer:
    8. ManageOne CMDB 风格模板端到端
    9. {{totalPages}} 与 {{totalPageNo}} 渲染等价
   10. 未声明占位符（如 {{nonExistent}}）仍透传字面量（回归原 _render_str 行为）
"""
import sys

sys.path.insert(0, "backend")

from app.core.response_template import _build_context, render_template


def _stub_items(n: int) -> list[dict]:
    """Make N stub rows so len(items) == expected count."""
    return [{"id": i} for i in range(n)]


# ---------------------------------------------------------------------------
# 1-7. _build_context 边界矩阵
# ---------------------------------------------------------------------------

def test_empty_data():
    """total=0, pageSize=100, page=1 → totalPageNo=0, all flags false, offset=0, count=0"""
    ctx = _build_context([], total=0, page=1, page_size=100)
    assert ctx["totalPageNo"] == 0
    assert ctx["totalPages"] == 0
    assert ctx["hasNext"] is False
    assert ctx["hasPrev"] is False
    assert ctx["offset"] == 0
    assert ctx["count"] == 0


def test_partial_last_page_only():
    """total=28, pageSize=100, page=1 → 仅 1 页，无前后"""
    ctx = _build_context(_stub_items(28), total=28, page=1, page_size=100)
    assert ctx["totalPageNo"] == 1
    assert ctx["hasNext"] is False
    assert ctx["hasPrev"] is False
    assert ctx["offset"] == 0
    assert ctx["count"] == 28


def test_exact_divide():
    """total=100, pageSize=100, page=1 → ceil(100/100)=1，无下一页"""
    ctx = _build_context(_stub_items(100), total=100, page=1, page_size=100)
    assert ctx["totalPageNo"] == 1
    assert ctx["hasNext"] is False
    assert ctx["hasPrev"] is False
    assert ctx["offset"] == 0
    assert ctx["count"] == 100


def test_middle_page():
    """total=250, pageSize=100, page=2 → 共 3 页，前后都有"""
    ctx = _build_context(_stub_items(100), total=250, page=2, page_size=100)
    assert ctx["totalPageNo"] == 3
    assert ctx["hasNext"] is True
    assert ctx["hasPrev"] is True
    assert ctx["offset"] == 100
    assert ctx["count"] == 100


def test_last_page():
    """total=250, pageSize=100, page=3 → 末页非满，有前页无后页"""
    ctx = _build_context(_stub_items(50), total=250, page=3, page_size=100)
    assert ctx["totalPageNo"] == 3
    assert ctx["hasNext"] is False
    assert ctx["hasPrev"] is True
    assert ctx["offset"] == 200
    assert ctx["count"] == 50


def test_anomalous_page_beyond_data():
    """total=0 但 page=2（异常请求）→ hasPrev 也应 False（因 total=0）"""
    ctx = _build_context([], total=0, page=2, page_size=100)
    assert ctx["totalPageNo"] == 0
    assert ctx["hasNext"] is False
    assert ctx["hasPrev"] is False  # total=0 时 hasPrev 被 and 子句压成 False


def test_pagesize_zero_defended():
    """pageSize=0 不抛除零异常，totalPageNo=0；offset=0 兜底"""
    ctx = _build_context([], total=42, page=1, page_size=0)
    assert ctx["totalPageNo"] == 0
    assert ctx["totalPages"] == 0
    assert ctx["hasNext"] is False
    assert ctx["offset"] == 0
    assert ctx["count"] == 0


# ---------------------------------------------------------------------------
# 8-10. 渲染层
# ---------------------------------------------------------------------------

def test_manageone_style_template():
    """ManageOne CMDB 风格响应模板端到端：
       {"objList":[...],"totalNum":28,"pageSize":100,"totalPageNo":1,"currentPage":1}
    """
    tpl = {
        "objList": "{{items}}",
        "totalNum": "{{total}}",
        "pageSize": "{{pageSize}}",
        "totalPageNo": "{{totalPageNo}}",
        "currentPage": "{{pageNo}}",
    }
    items = _stub_items(28)
    result = render_template(tpl, items, total=28, page=1, page_size=100)
    assert result["objList"] == items
    assert result["totalNum"] == 28
    assert result["pageSize"] == 100
    assert result["totalPageNo"] == 1
    assert result["currentPage"] == 1


def test_totalpages_alias_equivalent():
    """{{totalPages}} 与 {{totalPageNo}} 在同一上下文下渲染结果一致"""
    tpl = {"a": "{{totalPageNo}}", "b": "{{totalPages}}"}
    result = render_template(tpl, _stub_items(100), total=250, page=2, page_size=100)
    assert result["a"] == result["b"] == 3


def test_unknown_placeholder_still_passthrough():
    """回归：未声明占位符仍透传字面量，不因新增变量而改变行为"""
    tpl = {"x": "{{nonExistent}}", "y": "{{totalPageNo}}"}
    result = render_template(tpl, _stub_items(0), total=0, page=1, page_size=10)
    assert result["x"] == "{{nonExistent}}"  # 透传字面
    assert result["y"] == 0                  # 新派生变量正常替换


# ---------------------------------------------------------------------------
# 派生变量在 in-string 模式下的字符串化
# ---------------------------------------------------------------------------

def test_hasnext_in_string_stringified():
    """{{hasNext}} 嵌入更长字符串时按 _stringify 规则转 'true' / 'false'"""
    tpl = {"label": "more={{hasNext}}"}
    result = render_template(tpl, _stub_items(100), total=250, page=2, page_size=100)
    assert result["label"] == "more=true"


def test_offset_whole_string_is_int():
    """{{offset}} whole-string 占位 → JSON int 而非字符串"""
    tpl = {"start": "{{offset}}"}
    result = render_template(tpl, _stub_items(100), total=250, page=2, page_size=100)
    assert result["start"] == 100
    assert isinstance(result["start"], int)


# ---------------------------------------------------------------------------
# Test runner (pytest-free, matches test_response_template.py style)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Running M6-01 LEGACY-05 Phase 1 derived-vars unit tests...\n")
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print(f"  [PASS] {name}")
            except AssertionError as exc:
                print(f"  [FAIL] {name}: {exc}")
                sys.exit(1)
            except Exception as exc:
                print(f"  [ERROR] {name}: {exc}")
                sys.exit(1)
    print("\nALL TESTS PASSED")
