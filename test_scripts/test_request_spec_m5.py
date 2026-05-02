"""M5-05 E2E test: 请求契约 + 鉴权 集成验收.

Pipeline step order (docs §2.10):
  [2] check_enabled → [3] authenticate → [3.5] validate_request → [4] fault → [5] execute → [6] render

M5-05 8 条路径:
  1. 必填 header 缺失 → 400 + 40020
  2. header expectValue 不匹配 → 400 + 40021
  3. 必填 query 缺 → 400 + 40022
  4. query 类型错（声明 int 传 abc）→ 400 + 40023
  5. 严格模式未声明 query 字段 → 400 + 40025
  6. body required=True 但 body 空 → 400 + 40026
  7. xtoken 鉴权通过路径（auth + 全部 request 字段满足）→ 200
     连带验证: 缺 token → 401 (auth 先于 validation, 不泄露字段信息)
  8. M4 老接口（config.request 不存在）调用行为不变

Run: backend on 127.0.0.1:8080；`python test_scripts/test_request_spec_m5.py`.
"""
import json
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8080"
ADMIN = f"{BASE}/admin/api"

# ---------- globals ----------
MOCK_PREFIX = ""
PATH_PREFIX = "/m5_e2e"
TOKEN_VALUE = "m5_e2e_token_probe"
TOKEN_ID = None

_total = 0
_failed = 0


def _request(method, url, body=None, headers=None, raw_body=None):
    data = None
    hdrs = {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    if raw_body is not None:
        data = raw_body
        hdrs.setdefault("Content-Type", "application/json")
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
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
    global _total
    _total += 1
    print(f"[PASS] {msg}")


def _fail(msg):
    global _failed
    _failed += 1
    print(f"[FAIL] {msg}")


# ---------- helpers ----------

def cleanup_stale():
    st, pl = _request("GET", f"{ADMIN}/apis?path={PATH_PREFIX}&pageSize=50")
    if st != 200:
        return
    for item in pl.get("data", {}).get("items", []):
        if item.get("path", "").startswith(PATH_PREFIX):
            _request("DELETE", f"{ADMIN}/apis/{item['id']}")
    # cleanup token from previous run
    st, pl = _request("GET", f"{ADMIN}/tokens?pageSize=200")
    if st == 200:
        for item in pl.get("data", {}).get("items", []):
            if item.get("token") == TOKEN_VALUE:
                _request("POST", f"{ADMIN}/tokens/{TOKEN_VALUE}/revoke")


def _create(suffix, *, method="GET", config=None, data_source="static"):
    body = {
        "name": f"m5-e2e {suffix}",
        "method": method,
        "path": f"{PATH_PREFIX}_{suffix}",
        "enabled": True,
        "dataSource": data_source,
        "config": config if config is not None else {
            "staticBody": {"code": 0, "data": {"ok": suffix}}
        },
    }
    st, pl = _request("POST", f"{ADMIN}/apis", body)
    if st != 200:
        _fail(f"create {suffix}: {st} {pl}")
        return None, None
    return pl["data"]["id"], body["path"]


def _hit(method, path, *, expect_http, expect_code, headers=None, body=None, raw_body=None):
    st, pl = _request(
        method,
        f"{BASE}{MOCK_PREFIX}{path}",
        body=body,
        headers=headers,
        raw_body=raw_body,
    )
    ok = True
    if st != expect_http:
        _fail(f"{method} {path}: http {st} != {expect_http} (body={pl})")
        ok = False
    actual_code = pl.get("code") if isinstance(pl, dict) else None
    if actual_code != expect_code:
        _fail(f"{method} {path}: code {actual_code} != {expect_code} (body={pl})")
        ok = False
    return pl, ok


def setup_token():
    """Create an xtoken token for auth integration testing (path 7)."""
    global TOKEN_ID
    expires = "2099-12-31T23:59:59"
    body = {
        "token": TOKEN_VALUE,
        "expiresAt": expires,
        "authType": "xtoken",
        "meta": {"scope": "m5-e2e"},
    }
    st, pl = _request("POST", f"{ADMIN}/tokens", body)
    if st == 200:
        TOKEN_ID = pl.get("data", {}).get("id")
        print(f"[INFO] token created: {TOKEN_VALUE}")
    elif st == 409:
        # from previous stale run; revoke + recreate
        _request("POST", f"{ADMIN}/tokens/{TOKEN_VALUE}/revoke")
        st, pl = _request("POST", f"{ADMIN}/tokens", body)
        if st == 200:
            TOKEN_ID = pl.get("data", {}).get("id")
            print(f"[INFO] token re-created after revoke: {TOKEN_VALUE}")


def teardown_token():
    if TOKEN_ID:
        _request("POST", f"{ADMIN}/tokens/{TOKEN_VALUE}/revoke")


# ---------- mock prefix ----------

def _load_prefix():
    import sqlite3
    conn = sqlite3.connect("backend/data/app.db")
    row = conn.execute("SELECT value FROM settings WHERE key = 'mock_path_prefix'").fetchone()
    conn.close()
    return (row[0] if row else "") or ""


# ---------- main ----------

def main():
    global MOCK_PREFIX
    MOCK_PREFIX = _load_prefix()

    cleanup_stale()
    setup_token()

    # ===== 路径 1: 必填 header 缺失 → 400 + 40020 =====
    aid, apath = _create("hdr_missing", config={
        "staticBody": {"code": 0, "data": {"ok": True}},
        "request": {
            "headers": [{"name": "X-Tenant-Id", "required": True}],
        },
    })
    _hit("GET", apath, expect_http=400, expect_code=40020)
    _pass("[1] 必填请求头缺失 → 400 + 40020")
    # positive: same API with correct header → 200
    _hit("GET", apath, expect_http=200, expect_code=0,
         headers={"X-Tenant-Id": "t-001"})
    _pass("[1+] 同接口带上请求头 → 200 + 0")
    _request("DELETE", f"{ADMIN}/apis/{aid}")

    # ===== 路径 2: header expectValue 不匹配 → 400 + 40021 =====
    aid, apath = _create("hdr_expect", config={
        "staticBody": {"code": 0, "data": {"ok": True}},
        "request": {
            "headers": [{"name": "X-Env", "required": True, "expectValue": "prod"}],
        },
    })
    _hit("GET", apath, expect_http=400, expect_code=40021,
         headers={"X-Env": "staging"})
    _pass("[2] header expectValue 不匹配 → 400 + 40021")
    # positive: correct value
    _hit("GET", apath, expect_http=200, expect_code=0,
         headers={"X-Env": "prod"})
    _pass("[2+] 同接口期望值匹配 → 200 + 0")
    _request("DELETE", f"{ADMIN}/apis/{aid}")

    # ===== 路径 3: 必填 query 缺 → 400 + 40022 =====
    aid, apath = _create("qry_missing", config={
        "staticBody": {"code": 0, "data": {"ok": True}},
        "request": {
            "query": [{"name": "topologyId", "type": "string", "required": True}],
        },
    })
    _hit("GET", apath, expect_http=400, expect_code=40022)
    _pass("[3] 必填 query 参数缺 → 400 + 40022")
    _hit("GET", apath + "?topologyId=t1", expect_http=200, expect_code=0)
    _pass("[3+] 同接口带上必填 query → 200 + 0")
    _request("DELETE", f"{ADMIN}/apis/{aid}")

    # ===== 路径 4: query 类型错（声明 int 传 abc）→ 400 + 40023 =====
    aid, apath = _create("qry_type", config={
        "staticBody": {"code": 0, "data": {"ok": True}},
        "request": {
            "query": [{"name": "pageNo", "type": "int", "required": False}],
        },
    })
    _hit("GET", apath + "?pageNo=abc", expect_http=400, expect_code=40023)
    _pass("[4] query 类型错（int 传 abc）→ 400 + 40023")
    _hit("GET", apath + "?pageNo=42", expect_http=200, expect_code=0)
    _pass("[4+] 同接口传 pageNo=42 → 200 + 0")
    _request("DELETE", f"{ADMIN}/apis/{aid}")

    # ===== 路径 5: 严格模式未声明 query 字段 → 400 + 40025 =====
    aid, apath = _create("qry_strict", config={
        "staticBody": {"code": 0, "data": {"ok": True}},
        "request": {
            "query": [{"name": "knownParam", "type": "string"}],
        },
    })
    _hit("GET", apath + "?fooBar=1", expect_http=400, expect_code=40025)
    _pass("[5] 严格白名单：未声明 query 字段 → 400 + 40025")
    # mixed: declared + undeclared → still rejected
    _hit("GET", apath + "?knownParam=ok&strange=x",
         expect_http=400, expect_code=40025)
    _pass("[5a] 严格白名单：声明+未声明混合 → 仍然 400 + 40025")
    # only declared → pass
    _hit("GET", apath + "?knownParam=ok", expect_http=200, expect_code=0)
    _pass("[5+] 严格白名单：仅传声明字段 → 200 + 0")
    _request("DELETE", f"{ADMIN}/apis/{aid}")

    # ===== 路径 6: body required=True 但 body 空 → 400 + 40026 =====
    aid, apath = _create("body_empty", method="POST", config={
        "staticBody": {"code": 0, "data": {"ok": True}},
        "request": {
            "body": {"contentType": "application/json", "required": True},
        },
    })
    _hit("POST", apath, expect_http=400, expect_code=40026, raw_body=b"")
    _pass("[6] body required=True 但 body 空 → 400 + 40026")
    _hit("POST", apath, expect_http=200, expect_code=0,
         body={"any": "thing"})
    _pass("[6+] body required=True 带 body → 200 + 0")
    _request("DELETE", f"{ADMIN}/apis/{aid}")

    # ===== 路径 7: xtoken 鉴权通过 + 全 request 字段满足 → 200 =====
    # 7a: auth required + request params wrong + NO token → must be 401 (auth before validation)
    aid, apath = _create("auth_order", config={
        "staticBody": {"code": 0, "data": {"secret": True}},
        "request": {
            "query": [{"name": "topologyId", "type": "string", "required": True}],
        },
        "auth": {"type": "xtoken", "headerName": "X-Auth-Token"},
    })
    # no token, also missing required query → should be 401 (auth first), NOT 400
    _hit("GET", apath, expect_http=401, expect_code=40401)
    _pass("[7a] auth+缺query 但无 token → 401 (auth 优先, 不泄露字段信息)")

    # 7b: wrong token → 401
    _hit("GET", apath, expect_http=401, expect_code=40401,
         headers={"X-Auth-Token": "wrong_token"})
    _pass("[7b] 错误 token → 401 + 40401")

    # 7c: correct token + all request fields satisfied → 200
    pl, ok = _hit("GET", apath + "?topologyId=topo_x",
                  expect_http=200, expect_code=0,
                  headers={"X-Auth-Token": TOKEN_VALUE})
    if ok:
        data = pl.get("data") if isinstance(pl.get("data"), dict) else {}
        if data.get("secret") is not True:
            _fail(f"[7c] body mismatch: {pl}")
        else:
            _pass("[7c] 正确 token + 全部 request 字段满足 → 200 + data.secret")
    _request("DELETE", f"{ADMIN}/apis/{aid}")

    # ===== 路径 8: M4 老接口（无 config.request）行为不变 → 200 =====
    aid, apath = _create("legacy", config={
        "staticBody": {"code": 0, "data": {"ok": "legacy"}},
    })
    pl, _ = _hit("GET", apath, expect_http=200, expect_code=0)
    data = pl.get("data") if isinstance(pl.get("data"), dict) else {}
    if data.get("ok") != "legacy":
        _fail(f"[8] legacy body wrong: {pl}")
    else:
        _pass("[8] M4 老接口（无 config.request）→ 200 + code 0（向后兼容）")
    _request("DELETE", f"{ADMIN}/apis/{aid}")

    teardown_token()

    print(f"\n{'='*50}")
    if _failed:
        print(f"[RESULT] {_total - _failed}/{_total} PASS, {_failed} FAIL")
        sys.exit(1)
    else:
        print(f"[RESULT] {_total}/{_total} ALL PASS")


if __name__ == "__main__":
    main()
