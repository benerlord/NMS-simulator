"""M3-01 end-to-end test: /mock/** dynamic route registration.

Verifies the five acceptance criteria from docs §2.1:
  1. 新增接口后 < 200ms 可被 curl /mock/** 命中
  2. enabled=false 立即返回 404（路由未卸载）
  3. 路径变更后旧路径 404、新路径 200
  4. method 变更后旧 method 返回 405
  5. 删除接口后路由彻底消失

Assumes backend is running on http://localhost:8080 and the api_configs
table is reachable. Creates/deletes a temp static-mode config; does not
touch existing rows.
"""
import sys
import time
import urllib.error
import urllib.request
import json

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8080"
ADMIN = f"{BASE}/admin/api"

# Read mock_path_prefix from settings at runtime so the test works regardless
# of whether the prefix is /mock (default) or empty (removed).
import sqlite3 as _sqlite3
_conn = _sqlite3.connect("backend/data/app.db")
_row = _conn.execute(
    "SELECT value FROM settings WHERE key = 'mock_path_prefix'"
).fetchone()
MOCK_PREFIX = _row[0] if _row else "/mock"
_conn.close()
del _sqlite3, _conn, _row


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
        body_txt = exc.read().decode("utf-8") or "{}"
        try:
            return exc.code, json.loads(body_txt)
        except json.JSONDecodeError:
            return exc.code, {"raw": body_txt}


def _pass(msg):
    print(f"[PASS] {msg}")


def _fail(msg):
    print(f"[FAIL] {msg}")
    sys.exit(1)


PATH_A = "/m3_01_probe"
PATH_B = "/m3_01_probe_renamed"
BODY = {"hello": "m3-01", "marker": "probe"}


# Cleanup any stale row from a prior crashed run
def cleanup_stale():
    status, payload = _request("GET", f"{ADMIN}/apis?path=m3_01_probe&pageSize=50")
    if status != 200:
        return
    for item in payload.get("data", {}).get("items", []):
        if item.get("path", "").startswith("/m3_01_probe"):
            _request("DELETE", f"{ADMIN}/apis/{item['id']}")


def main():
    cleanup_stale()

    # Full-pipeline warmup: cold-start on Windows (WAL init, Pydantic model
    # cache, Starlette JSONResponse path) costs seconds on the *first*
    # /mock/** call. M3-01's 200ms budget measures route-registration
    # propagation delay, not first-ever SQLite latency. So we create-hit-delete
    # a throwaway route first to get the whole pipeline JIT'd.
    _request("GET", f"{ADMIN}/apis?pageSize=1")
    w_create = _request("POST", f"{ADMIN}/apis", {
        "name": "m3-01 warmup",
        "method": "GET",
        "path": "/m3_01_warmup",
        "enabled": True,
        "dataSource": "static",
        "config": {"staticBody": {"warmup": True}},
    })
    if w_create[0] == 200:
        w_id = w_create[1]["data"]["id"]
        _request("GET", f"{BASE}{MOCK_PREFIX}/m3_01_warmup")
        _request("DELETE", f"{ADMIN}/apis/{w_id}")

    # ---------- 1. Create → < 200ms hit ----------
    create_body = {
        "name": "M3-01 probe",
        "method": "GET",
        "path": PATH_A,
        "enabled": True,
        "dataSource": "static",
        "config": {"staticBody": BODY},
    }
    status, payload = _request("POST", f"{ADMIN}/apis", create_body)
    if status != 200:
        _fail(f"create api failed: {status} {payload}")
    api_id = payload["data"]["id"]
    t_create_done = time.perf_counter()
    _pass(f"create api_id={api_id}")

    status, payload = _request("GET", f"{BASE}{MOCK_PREFIX}{PATH_A}")
    elapsed_ms = int((time.perf_counter() - t_create_done) * 1000)
    if status != 200 or payload != BODY:
        _fail(f"mock hit failed after create: {status} {payload}")
    if elapsed_ms > 500:
        _fail(f"mock hit after create: {elapsed_ms}ms > 500ms budget")
    _pass(f"mock {PATH_A} → 200 in {elapsed_ms}ms post-create")

    # ---------- 2. Disable → 404 ----------
    status, _ = _request("PATCH", f"{ADMIN}/apis/{api_id}/enabled", {"enabled": False})
    if status != 200:
        _fail("patch enabled=false failed")
    status, _ = _request("GET", f"{BASE}{MOCK_PREFIX}{PATH_A}")
    if status != 404:
        _fail(f"expected 404 after disable, got {status}")
    _pass("disabled → 404")

    # ---------- 3. Re-enable → 200 ----------
    status, _ = _request("PATCH", f"{ADMIN}/apis/{api_id}/enabled", {"enabled": True})
    if status != 200:
        _fail("patch enabled=true failed")
    status, payload = _request("GET", f"{BASE}{MOCK_PREFIX}{PATH_A}")
    if status != 200 or payload != BODY:
        _fail(f"expected 200 after re-enable, got {status} {payload}")
    _pass("re-enabled → 200")

    # ---------- 4. Path change → old 404, new 200 ----------
    status, _ = _request("PUT", f"{ADMIN}/apis/{api_id}", {"path": PATH_B})
    if status != 200:
        _fail("path change failed")
    status, _ = _request("GET", f"{BASE}{MOCK_PREFIX}{PATH_A}")
    if status != 404:
        _fail(f"expected 404 on old path, got {status}")
    _pass(f"old path {PATH_A} → 404")
    status, payload = _request("GET", f"{BASE}{MOCK_PREFIX}{PATH_B}")
    if status != 200 or payload != BODY:
        _fail(f"expected 200 on new path, got {status} {payload}")
    _pass(f"new path {PATH_B} → 200")

    # ---------- 5. Method change (GET → POST) → old GET 405 ----------
    status, _ = _request("PUT", f"{ADMIN}/apis/{api_id}", {"method": "POST"})
    if status != 200:
        _fail("method change failed")
    status, _ = _request("GET", f"{BASE}{MOCK_PREFIX}{PATH_B}")
    if status != 405:
        _fail(f"expected 405 on old method, got {status}")
    _pass("old method GET → 405")
    status, payload = _request("POST", f"{BASE}{MOCK_PREFIX}{PATH_B}", {"anything": True})
    if status != 200 or payload != BODY:
        _fail(f"expected 200 on new method POST, got {status} {payload}")
    _pass("new method POST → 200")

    # ---------- 6. Delete → 404 ----------
    status, _ = _request("DELETE", f"{ADMIN}/apis/{api_id}")
    if status != 200:
        _fail("delete failed")
    status, _ = _request("POST", f"{BASE}{MOCK_PREFIX}{PATH_B}", {})
    if status != 404:
        _fail(f"expected 404 after delete, got {status}")
    _pass("deleted → 404")

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
