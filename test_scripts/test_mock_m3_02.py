"""M3-02 end-to-end test: RouteRegistry 运行时增删改同步 <200ms.

M3-01 proved correctness of register/update/unregister; M3-02 is the
*timing* acceptance: every runtime mutation must propagate to /mock/**
within 200ms (docs §4.2 M3-02 row).

Matrix (each measured independently, admin ack → first /mock/** hit):
  1. CREATE (POST /admin/api/apis)                 → /mock path returns 200
  2. DISABLE (PATCH /apis/{id}/enabled false)       → /mock path returns 404
  3. RE-ENABLE (PATCH /apis/{id}/enabled true)      → /mock path returns 200
  4. PATH CHANGE (PUT /apis/{id})                   → new /mock path 200, old 404
  5. METHOD CHANGE (PUT /apis/{id})                 → new method 200, old 405
  6. DELETE (DELETE /apis/{id})                     → /mock path returns 404

Uses 127.0.0.1 (Windows IPv6→IPv4 fallback costs ~2s on localhost).
Assumes backend already running on 8080 and api_configs reachable.
"""
import json
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8080"
ADMIN = f"{BASE}/admin/api"
BUDGET_MS = 200

import sqlite3 as _sqlite3
_conn = _sqlite3.connect("backend/data/app.db")
_row = _conn.execute(
    "SELECT value FROM settings WHERE key = 'mock_path_prefix'"
).fetchone()
MOCK_PREFIX = _row[0] if _row else "/mock"
_conn.close()
del _sqlite3, _conn, _row

PATH_A = "/m3_02_probe"
PATH_B = "/m3_02_probe_renamed"
BODY = {"hello": "m3-02"}


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
    status, payload = _request("GET", f"{ADMIN}/apis?path=m3_02_probe&pageSize=50")
    if status != 200:
        return
    for item in payload.get("data", {}).get("items", []):
        if item.get("path", "").startswith("/m3_02_probe"):
            _request("DELETE", f"{ADMIN}/apis/{item['id']}")


def _warmup():
    """JIT whole pipeline so the first measured transition doesn't eat cold-start cost."""
    _request("GET", f"{ADMIN}/apis?pageSize=1")
    st, pl = _request(
        "POST",
        f"{ADMIN}/apis",
        {
            "name": "m3-02 warmup",
            "method": "GET",
            "path": "/m3_02_warmup",
            "enabled": True,
            "dataSource": "static",
            "config": {"staticBody": {"w": 1}},
        },
    )
    if st == 200:
        wid = pl["data"]["id"]
        _request("GET", f"{BASE}{MOCK_PREFIX}/m3_02_warmup")
        _request("DELETE", f"{ADMIN}/apis/{wid}")


def _timed_hit(method, path, expect_status, expect_body=None, t_start=None):
    """Hit /mock<path>, measure latency from t_start (or from now) to response.

    Returns elapsed_ms. Fails the test if status/body mismatch or budget exceeded.
    """
    if t_start is None:
        t_start = time.perf_counter()
    status, payload = _request(method, f"{BASE}{MOCK_PREFIX}{path}", {} if method != "GET" else None)
    elapsed_ms = int((time.perf_counter() - t_start) * 1000)
    if status != expect_status:
        _fail(f"{method} /mock{path}: expected {expect_status}, got {status} {payload}")
    if expect_body is not None and payload != expect_body:
        _fail(f"{method} /mock{path}: body mismatch: {payload!r} != {expect_body!r}")
    if elapsed_ms > BUDGET_MS:
        _fail(f"{method} /mock{path}: {elapsed_ms}ms > {BUDGET_MS}ms budget")
    return elapsed_ms


def main():
    cleanup_stale()
    _warmup()

    results = {}

    # --- 1. CREATE ---
    t0 = time.perf_counter()
    st, pl = _request(
        "POST",
        f"{ADMIN}/apis",
        {
            "name": "M3-02 probe",
            "method": "GET",
            "path": PATH_A,
            "enabled": True,
            "dataSource": "static",
            "config": {"staticBody": BODY},
        },
    )
    if st != 200:
        _fail(f"create failed: {st} {pl}")
    api_id = pl["data"]["id"]
    ms = _timed_hit("GET", PATH_A, 200, BODY, t_start=t0)
    results["create → 200"] = ms
    _pass(f"CREATE → GET {PATH_A} 200 in {ms}ms")

    # --- 2. DISABLE ---
    t0 = time.perf_counter()
    st, _ = _request("PATCH", f"{ADMIN}/apis/{api_id}/enabled", {"enabled": False})
    if st != 200:
        _fail("disable failed")
    ms = _timed_hit("GET", PATH_A, 404, t_start=t0)
    results["disable → 404"] = ms
    _pass(f"DISABLE → GET {PATH_A} 404 in {ms}ms")

    # --- 3. RE-ENABLE ---
    t0 = time.perf_counter()
    st, _ = _request("PATCH", f"{ADMIN}/apis/{api_id}/enabled", {"enabled": True})
    if st != 200:
        _fail("re-enable failed")
    ms = _timed_hit("GET", PATH_A, 200, BODY, t_start=t0)
    results["re-enable → 200"] = ms
    _pass(f"RE-ENABLE → GET {PATH_A} 200 in {ms}ms")

    # --- 4. PATH CHANGE ---
    t0 = time.perf_counter()
    st, _ = _request("PUT", f"{ADMIN}/apis/{api_id}", {"path": PATH_B})
    if st != 200:
        _fail("path change failed")
    ms_new = _timed_hit("GET", PATH_B, 200, BODY, t_start=t0)
    results["path change → new 200"] = ms_new
    _pass(f"PATH CHANGE → GET {PATH_B} 200 in {ms_new}ms")
    # old path should already be 404 (not timed — registered state)
    st, _ = _request("GET", f"{BASE}{MOCK_PREFIX}{PATH_A}")
    if st != 404:
        _fail(f"old path expected 404, got {st}")
    _pass(f"old path {PATH_A} → 404")

    # --- 5. METHOD CHANGE (GET → POST) ---
    t0 = time.perf_counter()
    st, _ = _request("PUT", f"{ADMIN}/apis/{api_id}", {"method": "POST"})
    if st != 200:
        _fail("method change failed")
    ms_new = _timed_hit("POST", PATH_B, 200, BODY, t_start=t0)
    results["method change → new 200"] = ms_new
    _pass(f"METHOD CHANGE → POST {PATH_B} 200 in {ms_new}ms")
    st, _ = _request("GET", f"{BASE}{MOCK_PREFIX}{PATH_B}")
    if st != 405:
        _fail(f"old method expected 405, got {st}")
    _pass(f"old method GET {PATH_B} → 405")

    # --- 6. DELETE ---
    t0 = time.perf_counter()
    st, _ = _request("DELETE", f"{ADMIN}/apis/{api_id}")
    if st != 200:
        _fail("delete failed")
    ms = _timed_hit("POST", PATH_B, 404, t_start=t0)
    results["delete → 404"] = ms
    _pass(f"DELETE → POST {PATH_B} 404 in {ms}ms")

    print("\nLATENCY MATRIX (budget {}ms):".format(BUDGET_MS))
    for label, ms in results.items():
        print(f"  {label:30s} {ms:>5d}ms")

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
