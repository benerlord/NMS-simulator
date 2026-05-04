"""LEGACY-06 e2e: 接口拓扑绑定可修改（PATCH /topology 加固 + 预扫描端点）.

后端测试矩阵（docs/开发方案.md §2.13 §测试方案）：
  1. PATCH 切到新拓扑 → 200 + topology_id 已更新 + updated_at 已变
  2. PATCH 切到不存在拓扑 → 404 + 40101
  3. PATCH 切到 null（解绑）→ 200 + topology_id=null
  4. PATCH 同值跳过 → 200 + updated_at 不变（5.1 加固）
  5. preview SQL 含原拓扑独有视图 → missingViews 非空 + warning 非 null
  6. preview SQL 引用都在新拓扑里 → missingViews=[] + warning=null
  7. preview targetTopologyId 不存在 → 404 + 40101
  8. preview sqlText 为空 → missingViews=[]，正常 200

Run: backend on 127.0.0.1:8080；`python test_scripts/test_api_topology_switch.py`.
"""
import json
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8080"
ADMIN = f"{BASE}/admin/api"

PATH_PREFIX = "/legacy06_topo_switch"


def _request(method, url, body=None):
    data = None
    hdrs = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
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


def cleanup():
    """删掉本测试创建的所有 api_configs 与 topologies."""
    st, pl = _request("GET", f"{ADMIN}/apis?path=legacy06_topo_switch&pageSize=50")
    if st == 200:
        for item in pl.get("data", {}).get("items", []):
            if item.get("path", "").startswith(PATH_PREFIX):
                _request("DELETE", f"{ADMIN}/apis/{item['id']}")
    st, pl = _request("GET", f"{ADMIN}/topologies?name=legacy06&pageSize=50")
    if st == 200:
        for item in pl.get("data", {}).get("items", []):
            if (item.get("name", "")).startswith("legacy06-topo"):
                _request("DELETE", f"{ADMIN}/topologies/{item['id']}")


def _create_topology(name):
    st, pl = _request("POST", f"{ADMIN}/topologies", {"name": name, "description": ""})
    if st != 200:
        _fail(f"create topology {name}: {st} {pl}")
    return pl["data"]["id"]


def _create_api(*, topology_id, sql_text=""):
    body = {
        "name": "legacy06 api",
        "method": "GET",
        "path": f"{PATH_PREFIX}_{int(time.time() * 1000)}",
        "enabled": True,
        "dataSource": "sql" if sql_text else "static",
        "topologyId": topology_id,
        "sqlText": sql_text,
        "config": {} if sql_text else {"staticBody": {"code": 0, "data": None}},
    }
    st, pl = _request("POST", f"{ADMIN}/apis", body)
    if st != 200:
        _fail(f"create api: {st} {pl}")
    return pl["data"]["id"]


def main():
    print("=== Setup: cleanup + create 2 topologies ===")
    cleanup()
    topo_a = _create_topology("legacy06-topo-A")
    topo_b = _create_topology("legacy06-topo-B")
    _pass(f"created topo_a={topo_a[:16]}... topo_b={topo_b[:16]}...")

    # ---- 测试 1: PATCH 切到新拓扑 ----
    api_id = _create_api(topology_id=topo_a, sql_text="SELECT * FROM nodes")
    st, pl = _request("GET", f"{ADMIN}/apis/{api_id}")
    if st != 200:
        _fail(f"GET api: {st} {pl}")
    updated_at_before = pl["data"]["updatedAt"]

    time.sleep(1.1)  # ensure updated_at second-precision will tick
    st, pl = _request("PATCH", f"{ADMIN}/apis/{api_id}/topology", {"topologyId": topo_b})
    if st != 200:
        _fail(f"[1] PATCH switch: {st} {pl}")
    if pl["data"]["topologyId"] != topo_b:
        _fail(f"[1] topology_id not updated: {pl['data']}")
    if pl["data"]["updatedAt"] == updated_at_before:
        _fail(f"[1] updated_at should change: {pl['data']}")
    _pass("[1] PATCH 切到新拓扑 → 200 + topology_id 已更新 + updated_at 已变")

    # ---- 测试 2: PATCH 切到不存在拓扑 ----
    st, pl = _request("PATCH", f"{ADMIN}/apis/{api_id}/topology", {"topologyId": "topo_nonexistent_xxx"})
    if st != 404 or pl.get("detail", {}).get("code") != 40101:
        _fail(f"[2] expected 404+40101, got {st} {pl}")
    _pass("[2] PATCH 切到不存在拓扑 → 404 + 40101")

    # ---- 测试 3: PATCH 切到 null ----
    st, pl = _request("PATCH", f"{ADMIN}/apis/{api_id}/topology", {"topologyId": None})
    if st != 200 or pl["data"]["topologyId"] is not None:
        _fail(f"[3] PATCH null: {st} {pl}")
    _pass("[3] PATCH 切到 null（解绑）→ 200 + topology_id=null")

    # 重新切回 topo_b 准备测试 4
    time.sleep(1.1)
    _request("PATCH", f"{ADMIN}/apis/{api_id}/topology", {"topologyId": topo_b})

    # ---- 测试 4: PATCH 同值跳过 ----
    st, pl = _request("GET", f"{ADMIN}/apis/{api_id}")
    updated_at_b1 = pl["data"]["updatedAt"]
    time.sleep(1.1)
    st, pl = _request("PATCH", f"{ADMIN}/apis/{api_id}/topology", {"topologyId": topo_b})
    if st != 200:
        _fail(f"[4] same-value PATCH: {st} {pl}")
    if pl["data"]["updatedAt"] != updated_at_b1:
        _fail(f"[4] updated_at should NOT change on same-value PATCH: before={updated_at_b1} after={pl['data']['updatedAt']}")
    _pass("[4] PATCH 同值跳过 → 200 + updated_at 不变")

    # ---- 测试 5: preview SQL 含视图在新拓扑下不存在 ----
    api_id_5 = _create_api(
        topology_id=topo_a,
        sql_text="SELECT * FROM nonexistent_view JOIN ports ON 1=1",
    )
    st, pl = _request(
        "GET",
        f"{ADMIN}/apis/{api_id_5}/topology-switch-preview?targetTopologyId={topo_b}",
    )
    if st != 200:
        _fail(f"[5] preview: {st} {pl}")
    data = pl.get("data", {})
    missing = data.get("missingViews", [])
    if "nonexistent_view" not in missing or "ports" not in missing:
        _fail(f"[5] expected nonexistent_view+ports in missingViews, got {missing}")
    if data.get("warning") is None:
        _fail(f"[5] expected non-null warning when missing views exist: {data}")
    _pass("[5] preview SQL 含原拓扑独有视图 → missingViews 非空 + warning 非 null")

    # ---- 测试 6: preview SQL 引用都存在 ----
    api_id_6 = _create_api(topology_id=topo_a, sql_text="SELECT * FROM nodes JOIN edges ON 1=1")
    st, pl = _request(
        "GET",
        f"{ADMIN}/apis/{api_id_6}/topology-switch-preview?targetTopologyId={topo_b}",
    )
    if st != 200:
        _fail(f"[6] preview: {st} {pl}")
    data = pl.get("data", {})
    if data.get("missingViews", ["x"]) != []:
        _fail(f"[6] expected missingViews=[], got {data.get('missingViews')}")
    if data.get("warning") is not None:
        _fail(f"[6] expected warning=null, got {data.get('warning')}")
    if "nodes" not in data.get("availableViews", []):
        _fail(f"[6] expected 'nodes' in availableViews, got {data.get('availableViews')}")
    _pass("[6] preview SQL 引用都在新拓扑里 → missingViews=[] + warning=null")

    # ---- 测试 7: preview targetTopologyId 不存在 ----
    st, pl = _request(
        "GET",
        f"{ADMIN}/apis/{api_id_6}/topology-switch-preview?targetTopologyId=topo_nonexistent_xxx",
    )
    if st != 404 or pl.get("detail", {}).get("code") != 40101:
        _fail(f"[7] expected 404+40101, got {st} {pl}")
    _pass("[7] preview targetTopologyId 不存在 → 404 + 40101")

    # ---- 测试 8: preview sqlText 为空 ----
    api_id_8 = _create_api(topology_id=topo_a)  # static, no sqlText
    st, pl = _request(
        "GET",
        f"{ADMIN}/apis/{api_id_8}/topology-switch-preview?targetTopologyId={topo_b}",
    )
    if st != 200:
        _fail(f"[8] preview: {st} {pl}")
    data = pl.get("data", {})
    if data.get("missingViews", ["x"]) != []:
        _fail(f"[8] expected missingViews=[], got {data.get('missingViews')}")
    if data.get("currentSqlReferences", ["x"]) != []:
        _fail(f"[8] expected currentSqlReferences=[], got {data.get('currentSqlReferences')}")
    _pass("[8] preview sqlText 为空 → missingViews=[]，正常 200")

    print("\n=== Cleanup ===")
    cleanup()
    print("\nALL 8 TESTS PASSED")


if __name__ == "__main__":
    main()
