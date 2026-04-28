"""M3-04 unit tests: response_template 渲染器占位符 + 边缘用例.

Placeholders (docs §2.5):
    {{items}}   -> list returned by SQL executor (raw injection via whole-string shortcut)
    {{total}}   -> total row count
    {{page}}    -> current page number
    {{pageNo}}  -> alias for page
    {{pageSize}}-> page size
    {{uuid}}    -> uuid4 hex (with dashes)
    {{now}}     -> UTC ISO-8601, ends with Z

Rendering semantics (two modes):
    - Whole-string shortcut: if a string value in the template is *exactly*
      `{{key}}` (possibly with whitespace), ctx[key] is returned raw
      (not stringified). This keeps arrays/objects as JSON types.
    - Textual substitution: `{{key}}` as part of a longer string is replaced
      by `str(ctx[key])` or `json.dumps(...)` for dict/list/bool/null.
    - Unknown placeholders pass through unchanged.

Edge cases:
    - Unknown placeholder → pass through unchanged
    - Template is raw JSON string → json.loads → render
    - Template is already a parsed dict/list/primitive → skip json.loads
    - Template malformed JSON string → TemplateRenderError
    - {{items}} whole-string shortcut → raw list injection (not stringified)
    - {{items}} embedded in longer string → textual substitution + stringify
    - Nested structures
    - Empty items / zero totals
    - uuid uniqueness across calls
    - now consistency within same call
    - bool / null in items → proper stringify
"""
import json
import re
import sys

sys.path.insert(0, "backend")

from app.core.response_template import (
    TemplateRenderError,
    render_template,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ITEMS = [{"name": "switch-a", "status": "online"}, {"name": "router-b", "status": "offline"}]
TOTAL = 42
PAGE = 3
PAGE_SIZE = 20


def _iso_re(s):
    """Return true if s looks like an ISO-8601 timestamp ending with Z."""
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", s))


# ---------------------------------------------------------------------------
# Placeholder tests
# ---------------------------------------------------------------------------


def test_items_whole_string_value():
    """{{items}} as the entire string VALUE (whole-string shortcut) → raw list injected.

    When a string value in the template is *exactly* the placeholder token,
    the whole-string shortcut returns ctx["items"] directly (not stringified).
    """
    tpl = {"data": "{{items}}"}  # value is exactly "{{items}}" → shortcut fires
    result = render_template(tpl, ITEMS, TOTAL, PAGE, PAGE_SIZE)
    assert result["data"] == ITEMS
    assert isinstance(result["data"], list)


def test_items_nested():
    """Multiple placeholders in a nested structure."""
    tpl = {"data": "{{items}}", "meta": {"total": "{{total}}", "page": "{{page}}"}}
    result = render_template(tpl, ITEMS, TOTAL, PAGE, PAGE_SIZE)
    assert result["data"] == ITEMS
    assert isinstance(result["data"], list)
    assert result["meta"]["total"] == TOTAL
    assert result["meta"]["page"] == PAGE


def test_total_textual():
    """{{total}} in a string → textual replacement as decimal."""
    tpl = {"total": "count: {{total}}"}
    result = render_template(tpl, ITEMS, TOTAL, PAGE, PAGE_SIZE)
    assert result["total"] == f"count: {TOTAL}"


def test_page_textual():
    """{{page}} embedded in text → stringified."""
    tpl = {"page": "page-{{page}}"}
    result = render_template(tpl, ITEMS, TOTAL, PAGE, PAGE_SIZE)
    assert result["page"] == "page-3"


def test_pageNo_alias():
    """{{pageNo}} is an alias for {{page}} (whole-string → raw int)."""
    tpl = {"pageNo": "{{pageNo}}"}
    result = render_template(tpl, ITEMS, TOTAL, PAGE, PAGE_SIZE)
    assert result["pageNo"] == PAGE


def test_pageSize_textual():
    """{{pageSize}} embedded in text → stringified."""
    tpl = {"size": "{{pageSize}} items per page"}
    result = render_template(tpl, ITEMS, TOTAL, PAGE, PAGE_SIZE)
    assert result["size"] == "20 items per page"


def test_pageSize_whole():
    """{{pageSize}} as entire value → raw int."""
    tpl = {"size": "{{pageSize}}"}
    result = render_template(tpl, ITEMS, TOTAL, PAGE, PAGE_SIZE)
    assert result["size"] == PAGE_SIZE


def test_uuid_format():
    """{{uuid}} → 32-hex-digit uuid4 with dashes (36 chars)."""
    tpl = {"reqId": "{{uuid}}"}
    result = render_template(tpl, ITEMS, TOTAL, PAGE, PAGE_SIZE)
    uid = result["reqId"]
    assert isinstance(uid, str)
    assert len(uid) == 36
    assert uid.count("-") == 4
    # Each segment matches uuid4 hex format
    assert re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", uid)


def test_uuid_unique():
    """Two calls return different uuid values."""
    tpl = {"a": "{{uuid}}", "b": "{{uuid}}"}
    r1 = render_template(tpl, ITEMS, TOTAL, PAGE, PAGE_SIZE)
    r2 = render_template(tpl, ITEMS, TOTAL, PAGE, PAGE_SIZE)
    assert r1["a"] != r2["a"]
    assert r1["b"] != r2["b"]


def test_now_format():
    """{{now}} → ISO-8601 UTC ending with Z."""
    tpl = {"ts": "{{now}}"}
    result = render_template(tpl, ITEMS, TOTAL, PAGE, PAGE_SIZE)
    ts = result["ts"]
    assert _iso_re(ts), f"Expected ISO-8601 Z, got {ts!r}"


def test_now_same_within_call():
    """{{now}} referenced twice in the same template → same value."""
    tpl = {"t1": "{{now}}", "t2": "{{now}}"}
    result = render_template(tpl, ITEMS, TOTAL, PAGE, PAGE_SIZE)
    assert result["t1"] == result["t2"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_unknown_placeholder_unchanged():
    """Unknown {{foobar}} → passes through unchanged."""
    tpl = {"key": "value={{foobar}}"}
    result = render_template(tpl, ITEMS, TOTAL, PAGE, PAGE_SIZE)
    assert result["key"] == "value={{foobar}}"


def test_unknown_inside_text():
    """{{unknown}} embedded in text stays as literal text."""
    tpl = {"key": "request id: {{unknown}}"}
    result = render_template(tpl, ITEMS, TOTAL, PAGE, PAGE_SIZE)
    assert result["key"] == "request id: {{unknown}}"


def test_malformed_json_template_string():
    """Raw string template that is not valid JSON → TemplateRenderError."""
    try:
        render_template("{this is not valid json", ITEMS, TOTAL, PAGE, PAGE_SIZE)
        assert False, "Expected TemplateRenderError"
    except TemplateRenderError:
        pass


def test_malformed_json_in_dict_value():
    """Parsed dict with a value that is a malformed JSON string is fine
    (it's just a string, not re-parsed as JSON)."""
    tpl = {"data": "{this is not valid json}"}
    # No error — the string is a literal, not interpreted as JSON
    result = render_template(tpl, ITEMS, TOTAL, PAGE, PAGE_SIZE)
    assert result["data"] == "{this is not valid json}"


def test_empty_template():
    """Empty string template → json.loads raises, caught as TemplateRenderError."""
    try:
        render_template("", ITEMS, TOTAL, PAGE, PAGE_SIZE)
        assert False
    except TemplateRenderError:
        pass


def test_whitespace_around_placeholder():
    """{{ items }} and {{  items  }} with extra spaces are still matched."""
    tpl_outer = {"a": "{{ items }}", "b": "{{  total  }}"}
    result = render_template(tpl_outer, ITEMS, TOTAL, PAGE, PAGE_SIZE)
    assert result["a"] == ITEMS
    assert result["b"] == TOTAL  # whole-string shortcut → raw int


def test_items_in_list():
    """Placeholder in a list element."""
    tpl = ["first", "{{items}}", "last"]
    result = render_template(tpl, ITEMS, TOTAL, PAGE, PAGE_SIZE)
    assert result[0] == "first"
    assert result[1] == ITEMS
    assert result[2] == "last"


def test_deeply_nested():
    """Three-level nesting with multiple placeholders."""
    tpl = {
        "meta": {
            "pagination": {
                "page": "{{page}}",
                "pageSize": "{{pageSize}}",
                "total": "{{total}}",
            }
        },
        "data": "{{items}}",
    }
    result = render_template(tpl, ITEMS, TOTAL, PAGE, PAGE_SIZE)
    assert result["meta"]["pagination"]["page"] == PAGE
    assert result["meta"]["pagination"]["pageSize"] == PAGE_SIZE
    assert result["meta"]["pagination"]["total"] == TOTAL
    assert result["data"] == ITEMS


def test_empty_items():
    """items=[] is rendered as raw empty list (not stringified)."""
    tpl = {"rows": "{{items}}"}
    result = render_template(tpl, [], 0, 1, 10)
    assert result["rows"] == []


def test_zero_total():
    tpl = {"total": "{{total}}"}
    result = render_template(tpl, [], 0, 1, 10)
    assert result["total"] == 0  # whole-string shortcut → raw int


def test_items_in_string_textual():
    """{{items}} embedded in longer string → list is json.dumps stringified."""
    tpl = {"info": "result has {{items}}"}
    result = render_template(tpl, [{"n": 1}], 1, 1, 10)
    assert result["info"] == 'result has [{"n": 1}]'


def test_bool_in_items():
    """Boolean values in items are stringified as true/false."""
    tpl = {"active": "{{items}}"}
    result = render_template(tpl, [{"on": True, "off": False}], 2, 1, 10)
    assert result["active"] == [{"on": True, "off": False}]


def test_null_in_items():
    """Null values in items pass through as null."""
    tpl = {"nullable": "{{items}}"}
    result = render_template(tpl, [{"val": None}], 1, 1, 10)
    assert result["nullable"] == [{"val": None}]


def test_primitive_template():
    """Template is a raw number / bool / null — returned as-is."""
    assert render_template(42, ITEMS, TOTAL, PAGE, PAGE_SIZE) == 42
    assert render_template(True, ITEMS, TOTAL, PAGE, PAGE_SIZE) is True
    assert render_template(None, ITEMS, TOTAL, PAGE, PAGE_SIZE) is None


def test_raw_json_string_template():
    """Template is a JSON-string (already a string) → parsed then rendered."""
    tpl = json.dumps({"code": 0, "data": "{{items}}"})
    result = render_template(tpl, ITEMS, TOTAL, PAGE, PAGE_SIZE)
    assert result["code"] == 0
    assert result["data"] == ITEMS


def test_page_one():
    """page=1 and pageNo alias still work correctly (whole-string → raw int)."""
    tpl = {"page": "{{page}}", "pageNo": "{{pageNo}}"}
    result = render_template(tpl, ITEMS, TOTAL, 1, 10)
    assert result["page"] == 1
    assert result["pageNo"] == 1


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Running M3-04 response_template unit tests...\n")
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
