"""M5-01 end-to-end test: 请求契约校验 step (HeaderSpec / QuerySpec / BodySpec).

Pipeline step map (docs §5.1 + §2.10 M5):
  [3.5] validate_request — 新增 step (M5-01):
       headers: required → 40020；expectValue 不匹配 → 40021
       query  : required → 40022；类型错 → 40023；严格白名单 → 40025
       body   : required 且空 → 40026

校验路径（8 条）:
  1. M4 老接口（无 config.request）调用零变化 → 200
  2. 缺必填 header → 400 + 40020
  3. header expectValue 不匹配 → 400 + 40021
  4. 缺必填 query → 400 + 40022
  5. query 类型错（声明 int 传 abc）→ 400 + 40023
  6. 严格白名单：未声明 query 字段 → 400 + 40025
  7. body required=True 但 body 空 → 400 + 40026
  8. 全通过 → 200

Run: backend on 127.0.0.1:8080；`python test_scripts/test_request_spec_m5_01.py`.
"""
import json
import sqlite3
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8080"
ADMIN = f"{BASE}/admin/api"

_conn = sqlite3.connect("backend/data/app.db")
_row = _conn.execute(
    "SELECT value FROM settings WHERE key = 'mock_path_prefix'"
).fetchone()
MOCK_PREFIX = _row[0] if _row else ""
_conn.close()
del _conn, _row

PATH_PREFIX = "/m5_01_reqspec"


def _request(method, url, body=None, headers=None, raw_body=None):
    """raw_body 优先于 body：用于显式发空 body 测 40026。"""
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
    print(f"[PASS] {msg}")


def _fail(msg):
    print(f"[FAIL] {msg}")
    sys.exit(1)


def cleanup_stale():
    st, pl = _request("GET", f"{ADMIN}/apis?path=m5_01_reqspec&pageSize=50")
    if st != 200:
        return
    for item in pl.get("data", {}).get("items", []):
        if item.get("path", "").startswith(PATH_PREFIX):
            _request("DELETE", f"{ADMIN}/apis/{item['id']}")


def _create(suffix, *, method="GET", config=None, data_source="static"):
    body = {
        "name": f"m5-01 {suffix}",
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
    return pl["data"]["id"], body["path"]


def _hit(method, path, *, expect_http, expect_code, headers=None, body=None, raw_body=None):
    st, pl = _request(
        method,
        f"{BASE}{MOCK_PREFIX}{path}",
        body=body,
        headers=headers,
        raw_body=raw_body,
    )
    if st != expect_http:
        _fail(
            f"{method} {path}: http {st} != {expect_http} (body={pl})"
        )
    actual_code = pl.get("code") if isinstance(pl, dict) else None
    if actual_code != expect_code:
        _fail(
            f"{method} {path}: code {actual_code} != {expect_code} (body={pl})"
        )
    return pl


def main():
    cleanup_stale()

    # ---------- 路径 1：M4 老接口（无 config.request）行为不变 ----------
    aid, apath = _create("baseline_legacy")
    pl = _hit("GET", apath, expect_http=200, expect_code=0)
    data = pl.get("data") if isinstance(pl.get("data"), dict) else {}
    if data.get("ok") != "baseline_legacy":
        _fail(f"baseline body wrong: {pl}")
    _pass("[1] M4 老接口（无 config.request）→ 200 + code 0（向后兼容）")
    _request("DELETE", f"{ADMIN}/apis/{aid}")

    # ---------- 路径 2：必填 header 缺失 → 40020 ----------
    aid, apath = _create(
        "header_required_missing",
        config={
            "staticBody": {"code": 0, "data": {"ok": True}},
            "request": {
                "headers": [{"name": "X-Tenant-Id", "required": True}],
            },
        },
    )
    _hit("GET", apath, expect_http=400, expect_code=40020)
    _pass("[2] 必填请求头缺失 → 400 + 40020")
    # 同接口带上正确 header 应通过
    _hit(
        "GET", apath,
        expect_http=200, expect_code=0,
        headers={"X-Tenant-Id": "t-001"},
    )
    _pass("[2-pos] 同接口带上请求头 → 200 + 0")
    _request("DELETE", f"{ADMIN}/apis/{aid}")

    # ---------- 路径 3：header expectValue 不匹配 → 40021 ----------
    aid, apath = _create(
        "header_expect_mismatch",
        config={
            "staticBody": {"code": 0, "data": {"ok": True}},
            "request": {
                "headers": [
                    {"name": "X-Env", "required": True, "expectValue": "prod"}
                ],
            },
        },
    )
    _hit(
        "GET", apath,
        expect_http=400, expect_code=40021,
        headers={"X-Env": "staging"},
    )
    _pass("[3] header expectValue 不匹配 → 400 + 40021")
    _request("DELETE", f"{ADMIN}/apis/{aid}")

    # ---------- 路径 4：必填 query 缺 → 40022 ----------
    aid, apath = _create(
        "query_required_missing",
        config={
            "staticBody": {"code": 0, "data": {"ok": True}},
            "request": {
                "query": [{"name": "topologyId", "type": "string", "required": True}],
            },
        },
    )
    _hit("GET", apath, expect_http=400, expect_code=40022)
    _pass("[4] 必填 query 参数缺 → 400 + 40022")
    _request("DELETE", f"{ADMIN}/apis/{aid}")

    # ---------- 路径 5：query 类型错（int 传 abc）→ 40023 ----------
    aid, apath = _create(
        "query_type_mismatch",
        config={
            "staticBody": {"code": 0, "data": {"ok": True}},
            "request": {
                "query": [{"name": "pageNo", "type": "int", "required": False}],
            },
        },
    )
    _hit("GET", apath + "?pageNo=abc", expect_http=400, expect_code=40023)
    _pass("[5] query 类型错（int 传 abc）→ 400 + 40023")
    # 正向：传合法 int 应通过
    _hit("GET", apath + "?pageNo=42", expect_http=200, expect_code=0)
    _pass("[5-pos] 同接口传 pageNo=42 → 200 + 0")
    _request("DELETE", f"{ADMIN}/apis/{aid}")

    # ---------- 路径 6：严格白名单（未声明 query 字段）→ 40025 ----------
    aid, apath = _create(
        "query_strict_whitelist",
        config={
            "staticBody": {"code": 0, "data": {"ok": True}},
            "request": {
                "query": [{"name": "knownParam", "type": "string"}],
            },
        },
    )
    # 只传未声明的 fooBar
    _hit("GET", apath + "?fooBar=1", expect_http=400, expect_code=40025)
    _pass("[6] 严格白名单：未声明 query 字段 → 400 + 40025")
    # 同时传声明的与未声明的，依然拒绝
    _hit(
        "GET", apath + "?knownParam=ok&strange=x",
        expect_http=400, expect_code=40025,
    )
    _pass("[6-mix] 严格白名单：声明字段+未声明字段 → 仍然 400 + 40025")
    # 仅传声明字段：通过
    _hit("GET", apath + "?knownParam=ok", expect_http=200, expect_code=0)
    _pass("[6-pos] 严格白名单：仅传声明字段 → 200 + 0")
    _request("DELETE", f"{ADMIN}/apis/{aid}")

    # ---------- 路径 7：body required=True 但 body 空 → 40026 ----------
    # 用 POST 接口，因为 GET 不带 body
    aid, apath = _create(
        "body_required_empty",
        method="POST",
        config={
            "staticBody": {"code": 0, "data": {"ok": True}},
            "request": {
                "body": {"contentType": "application/json", "required": True},
            },
        },
    )
    _hit(
        "POST", apath,
        expect_http=400, expect_code=40026,
        raw_body=b"",
    )
    _pass("[7] body required=True 但 body 空 → 400 + 40026")
    # 正向：带任意非空 body 应通过
    _hit(
        "POST", apath,
        expect_http=200, expect_code=0,
        body={"any": "thing"},
    )
    _pass("[7-pos] body required=True 带 body → 200 + 0")
    _request("DELETE", f"{ADMIN}/apis/{aid}")

    # ---------- 路径 8：全通过（headers + query + body 三段都满足）----------
    aid, apath = _create(
        "all_pass",
        method="POST",
        config={
            "staticBody": {"code": 0, "data": {"hello": "world"}},
            "request": {
                "headers": [
                    {"name": "X-Auth-Token", "required": True},
                    {"name": "Content-Type", "expectValue": "application/json"},
                ],
                "query": [
                    {"name": "topologyId", "type": "string", "required": True},
                    {"name": "pageNo", "type": "int", "required": False},
                ],
                "body": {"contentType": "application/json", "required": True},
            },
        },
    )
    pl = _hit(
        "POST", apath + "?topologyId=topo_x&pageNo=2",
        expect_http=200, expect_code=0,
        headers={"X-Auth-Token": "tk_abc", "Content-Type": "application/json"},
        body={"grantType": "password"},
    )
    data = pl.get("data") if isinstance(pl.get("data"), dict) else {}
    if data.get("hello") != "world":
        _fail(f"all_pass body wrong: {pl}")
    _pass("[8] 全通过：headers + query + body 三段满足 → 200 + 0")
    _request("DELETE", f"{ADMIN}/apis/{aid}")

    print("\n[ALL PASS] 8/8 cases")


if __name__ == "__main__":
    main()
