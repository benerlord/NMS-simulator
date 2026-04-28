"""M3-03 end-to-end test: RequestPipeline 六步管道 — 错误码短路矩阵.

Pipeline step map (docs §5.1):
  [1] route_match      — FastAPI routing (covered by M3-01/02, not re-tested)
  [2] check_enabled    — enabled=false → HTTP 404 + {code:40404}
  [3] authenticate     — stub (M3-06) — config.auth={type:'xtoken'} → 40401
  [4] inject_fault     — stub (M3-05) — pass-through, not exercised
  [5] execute (SQL)    — 无 topology → 40001；sqlText 空 → 40001；
                         非 SELECT → 40303；SQL 运行期异常 → 40302
  [5] execute (static) — no-op (body resolution deferred to step 6)
  [6] render           — 模板 JSON 解析失败 → 40303；默认分支返回 {code:0,data:null}

Each assertion targets ONE documented error code. Positive-path regression
for the successful static/sql flows is already covered by M3-01/02.

Run: backend on 127.0.0.1:8080; `python test_scripts/test_mock_m3_03.py`.
"""
import json
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8080"
ADMIN = f"{BASE}/admin/api"

import sqlite3 as _sqlite3
_conn = _sqlite3.connect("backend/data/app.db")
_row = _conn.execute(
    "SELECT value FROM settings WHERE key = 'mock_path_prefix'"
).fetchone()
MOCK_PREFIX = _row[0] if _row else "/mock"
_conn.close()
del _sqlite3, _conn, _row

PATH_PREFIX = "/m3_03_pipe"


def _request(method, url, body=None):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8") or "{}"
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}


def _pass(msg):
    print(f"[PASS] {msg}")


def _fail(msg):
    print(f"[FAIL] {msg}")
    sys.exit(1)


def cleanup_stale():
    status, payload = _request("GET", f"{ADMIN}/apis?path=m3_03_pipe&pageSize=50")
    if status != 200:
        return
    for item in payload.get("data", {}).get("items", []):
        if item.get("path", "").startswith(PATH_PREFIX):
            _request("DELETE", f"{ADMIN}/apis/{item['id']}")


def _get_or_create_topology():
    """Return (topo_id, created_here) — reuse the first existing topology,
    or create a dedicated one for the whitelist test if DB is empty.
    """
    st, pl = _request("GET", f"{ADMIN}/topologies?pageSize=1")
    items = pl.get("data", {}).get("items", []) if st == 200 else []
    if items:
        return items[0]["id"], False
    st, pl = _request(
        "POST", f"{ADMIN}/topologies", {"name": "m3-03 pipeline probe topo"}
    )
    if st != 200:
        _fail(f"create topology failed: {st} {pl}")
    return pl["data"]["id"], True


def _create(suffix, **overrides):
    body = {
        "name": f"m3-03 {suffix}",
        "method": "GET",
        "path": f"{PATH_PREFIX}_{suffix}",
        "enabled": True,
        "dataSource": "static",
        "config": {"staticBody": {"ok": suffix}},
    }
    body.update(overrides)
    st, pl = _request("POST", f"{ADMIN}/apis", body)
    if st != 200:
        _fail(f"create {suffix}: {st} {pl}")
    return pl["data"]["id"], body["path"]


def _assert_mock(method, path, expect_http, expect_code):
    st, pl = _request(method, f"{BASE}{MOCK_PREFIX}{path}", {} if method != "GET" else None)
    if st != expect_http:
        _fail(f"{method} /mock{path}: http {st} != {expect_http} (body={pl})")
    body_code = pl.get("code") if isinstance(pl, dict) else None
    if body_code != expect_code:
        _fail(f"{method} /mock{path}: code={body_code} != {expect_code} (body={pl})")
    return pl


def main():
    cleanup_stale()

    # Warmup to amortise first-hit cost.
    wid, wpath = _create("warmup", config={"staticBody": {"w": 1}})
    _request("GET", f"{BASE}{MOCK_PREFIX}{wpath}")
    _request("DELETE", f"{ADMIN}/apis/{wid}")

    # ---------- [2] enabled=false ----------
    aid, apath = _create("disabled")
    _request("PATCH", f"{ADMIN}/apis/{aid}/enabled", {"enabled": False})
    _assert_mock("GET", apath, 404, 40404)
    _pass("[2] disabled → 404 + code 40404")
    _request("DELETE", f"{ADMIN}/apis/{aid}")

    # ---------- [3] auth stub (config.auth.type='xtoken' without M3-06) ----------
    aid, apath = _create(
        "auth",
        config={"staticBody": {"x": 1}, "auth": {"type": "xtoken"}},
    )
    _assert_mock("GET", apath, 401, 40401)
    _pass("[3] auth.type=xtoken (stub) → 401 + code 40401")
    _request("DELETE", f"{ADMIN}/apis/{aid}")

    # ---------- [5] SQL 无 topology ----------
    aid, apath = _create(
        "sql_no_topo",
        dataSource="sql",
        sqlText="SELECT 1 AS x",
        config={},
    )
    _assert_mock("GET", apath, 400, 40001)
    _pass("[5] SQL no topology → 400 + code 40001")
    _request("DELETE", f"{ADMIN}/apis/{aid}")

    # ---------- [5] SQL 白名单（非 SELECT） ----------
    # Need a real topology id so step 5 gets past the topology check. Then PUT
    # sqlText to DROP → execute_paged.validate_readonly raises before any DB.
    topo_id, _ = _get_or_create_topology()
    aid, apath = _create(
        "sql_whitelist",
        dataSource="sql",
        sqlText="SELECT 1 AS x",
        topologyId=topo_id,
        config={},
    )
    _request("PUT", f"{ADMIN}/apis/{aid}", {"sqlText": "DROP TABLE nodes"})
    _assert_mock("GET", apath, 400, 40303)
    _pass("[5] SQL whitelist (non-SELECT) → 400 + code 40303")
    _request("DELETE", f"{ADMIN}/apis/{aid}")

    # ---------- [6] render (static + malformed template, no staticBody) ----------
    # Start as static with staticBody, then PUT to strip staticBody and inject a
    # malformed template string — step 6 calls json.loads on it → 40303.
    aid, apath = _create("render_err")
    _request(
        "PUT",
        f"{ADMIN}/apis/{aid}",
        {"config": {"response": {"template": "{this is not valid json"}}},
    )
    _assert_mock("GET", apath, 400, 40303)
    _pass("[6] template JSON parse error → 400 + code 40303")
    _request("DELETE", f"{ADMIN}/apis/{aid}")

    # ---------- Positive path (static) ----------
    aid, apath = _create("happy")
    st, pl = _request("GET", f"{BASE}{MOCK_PREFIX}{apath}")
    if st != 200 or pl != {"ok": "happy"}:
        _fail(f"positive static: {st} {pl}")
    _pass("positive static → 200 + exact body")
    _request("DELETE", f"{ADMIN}/apis/{aid}")

    # ---------- Positive path (default render) ----------
    # static + empty config → step 6 falls to {code:0, data:null} floor.
    aid, apath = _create("default", config={})
    st, pl = _request("GET", f"{BASE}{MOCK_PREFIX}{apath}")
    if st != 200 or pl != {"code": 0, "data": None}:
        _fail(f"positive default: {st} {pl}")
    _pass("positive default → 200 + {code:0,data:null}")
    _request("DELETE", f"{ADMIN}/apis/{aid}")

    print("\nPIPELINE ERROR-CODE MATRIX:")
    print("  [2] disabled          → 404 40404  ✓")
    print("  [3] auth (stub)       → 401 40401  ✓")
    print("  [5] SQL no topology   → 400 40001  ✓")
    print("  [5] SQL whitelist     → 400 40303  ✓")
    print("  [6] template parse    → 400 40303  ✓")
    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
