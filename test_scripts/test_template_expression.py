"""M6-02 LEGACY-05 Phase 2 unit tests: expression engine inside `{{ }}`.

Test categories (docs/开发方案.md §2.12 §14.2)：
    A. 正向矩阵       (10 条)：基础算术、函数调用、混合表达式
    B. 安全矩阵       (15 条)：禁用语法、未授权函数、未定义变量、资源上限
    C. 类型保留矩阵   (3 条)：whole-string int / in-string str / float 保留
    D. 回归矩阵       (3 条)：未声明占位符透传、含空白单标识符仍替换、
                              旧路径与新路径 dispatch 边界
    E. 集成测试       (3 条)：与 Phase 1 派生变量结果一致 / 除零冒泡 /
                              ManageOne 风格纯表达式版本
"""
import sys

sys.path.insert(0, "backend")

from app.core.response_template import (
    TemplateRenderError,
    _eval_expression,
    _build_context,
    render_template,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(total=28, page=1, page_size=100, items=None):
    if items is None:
        items = [{"id": i} for i in range(min(total, page_size))]
    return _build_context(items, total, page, page_size)


def _expect_error(expr, ctx=None, contains=None):
    """Run expr in ctx, assert TemplateRenderError; optionally assert msg contains substring."""
    ctx = ctx or _ctx()
    try:
        _eval_expression(expr, ctx)
    except TemplateRenderError as exc:
        if contains is not None:
            assert contains in str(exc), f"msg {exc!r} 不含 {contains!r}"
        return
    raise AssertionError(f"expr {expr!r} 应抛 TemplateRenderError")


# ---------------------------------------------------------------------------
# A. 正向矩阵 (10)
# ---------------------------------------------------------------------------

def test_A1_const_add():
    assert _eval_expression("1 + 1", _ctx()) == 2


def test_A2_var_arith():
    # total=28, pageSize=100 → 128
    assert _eval_expression("total + pageSize", _ctx()) == 128


def test_A3_ceil_div():
    # ceil(28/100) = 1
    assert _eval_expression("ceil(total / pageSize)", _ctx()) == 1


def test_A4_offset_formula():
    # (2-1)*100 = 100
    assert _eval_expression("(pageNo - 1) * pageSize", _ctx(page=2)) == 100


def test_A5_min_clamp():
    # min(1*100, 28) = 28 (last-page clamp)
    assert _eval_expression("min(pageNo * pageSize, total)", _ctx()) == 28


def test_A6_max_remaining():
    # max(0, 28 - 1*100) = max(0, -72) = 0
    assert _eval_expression("max(0, total - pageNo * pageSize)", _ctx()) == 0


def test_A7_round_div():
    # round(28/100) = 0 (banker's rounding to even, 0.28 → 0)
    assert _eval_expression("round(total / pageSize)", _ctx()) == 0


def test_A8_abs_neg():
    assert _eval_expression("abs(0 - pageSize)", _ctx()) == 100


def test_A9_int_truncate_plus_one():
    # int(28/100)+1 = 0+1 = 1
    assert _eval_expression("int(total / pageSize) + 1", _ctx()) == 1


def test_A10_bool_to_int_arith():
    # hasNext=False, hasPrev=False on first page of small data
    # 0*10 + 0*1 = 0
    assert _eval_expression("hasNext * 10 + hasPrev * 1", _ctx()) == 0
    # 多页中间页：hasNext=True, hasPrev=True → 10+1 = 11
    ctx2 = _ctx(total=250, page=2, page_size=100, items=[{"id": i} for i in range(100)])
    assert _eval_expression("hasNext * 10 + hasPrev * 1", ctx2) == 11


# ---------------------------------------------------------------------------
# B. 安全矩阵 (15)
# ---------------------------------------------------------------------------

def test_B1_dunder_import():
    # __import__('os') → 字符串字面量先被拒（'os' 是 Constant str）
    _expect_error("__import__('os')", contains="字面量")


def test_B2_open_unauthorized():
    # open 不在函数白名单
    _expect_error("open(123)", contains="未授权函数")


def test_B3_div_zero():
    _expect_error("1 / 0", contains="除零")


def test_B4_pow_disabled():
    # ** 未在 _BINOP_TABLE 中 → 在 _check_whitelist Pow 节点拒
    _expect_error("2 ** 100", contains="禁用")


def test_B5_attribute_access():
    _expect_error("(1).real", contains="禁用")


def test_B6_subscript():
    _expect_error("items[0]", contains="禁用")


def test_B7_lambda():
    _expect_error("(lambda: 1)()", contains="禁用")


def test_B8_ifexp():
    _expect_error("1 if total else 0", contains="禁用")


def test_B9_compare():
    _expect_error("total > 10", contains="禁用")


def test_B10_undefined_var():
    _expect_error("nonExistentVar + 1", contains="未定义变量")


def test_B11_func_arity_too_few():
    # ceil() 元数错（应 1 个，实 0 个）
    _expect_error("ceil()", contains="参数数错")


def test_B12_func_arity_too_many():
    # min(1,2,3) 元数错（应 2 个，实 3 个）
    _expect_error("min(1, 2, 3)", contains="参数数错")


def test_B13_too_long():
    # 长度 > 200
    long_expr = "1+" * 120 + "1"
    assert len(long_expr) > 200
    _expect_error(long_expr, contains="表达式过长")


def test_B14_too_many_nodes():
    # 长度 ≤ 200 但节点数 > 50
    # 用 "1+1+1+...+1" 形式：每个 "+1" 加 2 个节点（BinOp + Constant）
    # 30 个 +1 → 1 + 30*2 + 1 (Expression + Load 等) ~ 70 nodes，长度 62
    expr = "1" + "+1" * 30
    assert len(expr) <= 200
    _expect_error(expr, contains="过于复杂")


def test_B15_overflow():
    # 1e20 + 1e20 > 1e15
    _expect_error("1000000000000 * 1000000000000", contains="溢出")


# ---------------------------------------------------------------------------
# C. 类型保留矩阵 (3)
# ---------------------------------------------------------------------------

def test_C1_whole_string_returns_int():
    """whole-string `"{{total+1}}"` → JSON int (not string)."""
    tpl = {"x": "{{total + 1}}"}
    result = render_template(tpl, [], total=28, page=1, page_size=100)
    assert result["x"] == 29
    assert isinstance(result["x"], int)


def test_C2_in_string_stringified():
    """in-string `"Total: {{total+1}}"` → JSON string with substituted text."""
    tpl = {"x": "Total: {{total + 1}}"}
    result = render_template(tpl, [], total=28, page=1, page_size=100)
    assert result["x"] == "Total: 29"


def test_C3_float_preserved():
    """`{{pageNo + 0.5}}` → JSON float 1.5 (not stringified, not int-truncated)."""
    tpl = {"x": "{{pageNo + 0.5}}"}
    result = render_template(tpl, [], total=0, page=1, page_size=10)
    assert result["x"] == 1.5
    assert isinstance(result["x"], float)


# ---------------------------------------------------------------------------
# D. 回归矩阵 (3)
# ---------------------------------------------------------------------------

def test_D1_unknown_bare_identifier_passthrough():
    """单标识符 + 未在 ctx 中 → 透传字面量（不抛错）。"""
    tpl = {"x": "{{nonExistent}}"}
    result = render_template(tpl, [], total=0, page=1, page_size=10)
    assert result["x"] == "{{nonExistent}}"


def test_D2_whitespace_around_identifier_still_lookup():
    """`{{ items }}`（含空白）仍走单标识符路径，整串占位时返回原 list。"""
    tpl = {"x": "{{ items }}"}
    items = [{"a": 1}]
    result = render_template(tpl, items, total=1, page=1, page_size=10)
    assert result["x"] == items
    assert isinstance(result["x"], list)


def test_D3_dispatch_boundary_identifier_vs_expr():
    """同一模板里既有单标识符占位又有表达式占位，互不干扰。"""
    tpl = {
        "id_lookup": "{{total}}",
        "expr": "{{total + 1}}",
        "unknown": "{{xyz}}",
    }
    result = render_template(tpl, [], total=10, page=1, page_size=5)
    assert result["id_lookup"] == 10
    assert result["expr"] == 11
    assert result["unknown"] == "{{xyz}}"


# ---------------------------------------------------------------------------
# E. 集成测试 (3)
# ---------------------------------------------------------------------------

def test_E1_expression_matches_phase1_derived_var():
    """`{{ceil(total/pageSize)}}` 应与 Phase 1 派生变量 `{{totalPageNo}}` 结果完全一致。"""
    tpl = {"a": "{{totalPageNo}}", "b": "{{ceil(total / pageSize)}}"}
    # 跨多个边界场景
    for total, page, page_size in [
        (0, 1, 100),       # 空数据
        (28, 1, 100),      # 末页非满
        (100, 1, 100),     # 整除
        (250, 2, 100),     # 中间页
        (250, 3, 100),     # 末页
    ]:
        items = [{"id": i} for i in range(min(total - (page - 1) * page_size, page_size))] if total > 0 else []
        result = render_template(tpl, items, total, page, page_size)
        assert result["a"] == result["b"], (
            f"派生变量 {result['a']} ≠ 表达式 {result['b']} "
            f"(total={total}, page={page}, pageSize={page_size})"
        )


def test_E2_render_template_propagates_div_zero():
    """模板写 `{{1/0}}` → render_template 抛 TemplateRenderError(消息含"除零")。"""
    try:
        render_template({"x": "{{1 / 0}}"}, [], 0, 1, 10)
    except TemplateRenderError as exc:
        assert "除零" in str(exc), f"消息 {exc!r} 不含'除零'"
        return
    raise AssertionError("应抛 TemplateRenderError")


def test_E3_manageone_pure_expression_template():
    """ManageOne 风格模板用纯表达式版（不依赖 Phase 1 派生变量）应产出相同结果。"""
    items = [{"id": i} for i in range(28)]
    tpl_phase1 = {  # 用 Phase 1 派生变量
        "objList": "{{items}}",
        "totalNum": "{{total}}",
        "pageSize": "{{pageSize}}",
        "totalPageNo": "{{totalPageNo}}",
        "currentPage": "{{pageNo}}",
    }
    tpl_phase2 = {  # 用 Phase 2 表达式
        "objList": "{{items}}",
        "totalNum": "{{total}}",
        "pageSize": "{{pageSize}}",
        "totalPageNo": "{{ceil(total / pageSize)}}",
        "currentPage": "{{page}}",
    }
    r1 = render_template(tpl_phase1, items, 28, 1, 100)
    r2 = render_template(tpl_phase2, items, 28, 1, 100)
    assert r1 == r2, f"Phase1 {r1} ≠ Phase2 {r2}"


# ---------------------------------------------------------------------------
# Test runner (pytest-free)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Running M6-02 LEGACY-05 Phase 2 expression-engine unit tests...\n")
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print(f"  [PASS] {name}")
            except AssertionError as exc:
                print(f"  [FAIL] {name}: {exc}")
                failures += 1
            except Exception as exc:
                print(f"  [ERROR] {name}: {type(exc).__name__}: {exc}")
                failures += 1
    if failures:
        print(f"\n{failures} TEST(S) FAILED")
        sys.exit(1)
    print("\nALL TESTS PASSED")
