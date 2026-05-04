"""LEGACY-07 e2e: 拓扑删除时自动解绑 api_configs，不再返回 40103.

后端测试矩阵（docs/开发方案.md §2.14 §测试方案）：
  1. 删无引用拓扑 → 200 + unboundApiCount=0
  2. 删有 N 引用拓扑 → 200 + unboundApiCount=N + api_configs.topology_id=NULL + updated_at 已变
  3. 批删混合（有/无引用）→ 200 + 全部删除 + 总解绑数正确
  4. delete-impact 返回 affectedApiCount + affectedApis 列表
  5. delete-impact 拓扑不存在 → 404 + 40101
  6. 解绑后 SQL 接口调用 → 400 + 40001（已有 _step5_execute 兜底）
  7. 静态接口在拓扑被删后仍正常响应（不依赖 topology_id）
  8. 回归：原 40103 错误码不再出现

Run: backend on 127.0.0.1:8080；`python test_scripts/test_topology_delete_unbind.py`.
"""
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8080"
ADMIN = f"{BASE}/admin/api"

# 取 mock 路径前缀（M3-01 设置）
_conn = sqlite3.connect("backend/data/app.db")
_row = _conn.execute(
    "SELECT value FROM settings WHERE key = 'mock_path_prefix'"
).fetchone()
MOCK_PREFIX = _row[0] if _row else ""
_conn.close()
del _conn, _row

PATH_PREFIX = "/legacy07_topo_del"
TOPO_NAME_PREFIX = "legacy07-topo"


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
    """删本测试可能残留的 api_configs 与 topologies."""
    st, pl = _request("GET", f"{ADMIN}/apis?path=legacy07_topo_del&pageSize=50")
    if st == 200:
        for item in pl.get("data", {}).get("items", []):
            if item.get("path", "").startswith(PATH_PREFIX):
                _request("DELETE", f"{ADMIN}/apis/{item['id']}")
    st, pl = _request("GET", f"{ADMIN}/topologies?name=legacy07&pageSize=50")
    if st == 200:
        for item in pl.get("data", {}).get("items", []):
            if (item.get("name", "")).startswith(TOPO_NAME_PREFIX):
                _request("DELETE", f"{ADMIN}/topologies/{item['id']}")


def _create_topology(name):
    st, pl = _request("POST", f"{ADMIN}/topologies", {"name": name, "description": ""})
    if st != 200:
        _fail(f"create topology {name}: {st} {pl}")
    return pl["data"]["id"]


def _create_api(*, topology_id=None, suffix="x", data_source="static", sql_text=""):
    body = {
        "name": f"legacy07 api {suffix}",
        "method": "GET",
        "path": f"{PATH_PREFIX}_{suffix}_{int(time.time() * 1000)}",
        "enabled": True,
        "dataSource": data_source,
        "topologyId": topology_id,
        "sqlText": sql_text or None,
        "config": {"staticBody": {"code": 0, "data": {"ok": suffix}}}
        if data_source == "static"
        else {},
    }
    st, pl = _request("POST", f"{ADMIN}/apis", body)
    if st != 200:
        _fail(f"create api: {st} {pl}")
    return pl["data"]["id"], body["path"]


def main():
    print("=== Setup: cleanup ===")
    cleanup()

    # ---- 测试 1: 删无引用拓扑 ----
    topo_alone = _create_topology(f"{TOPO_NAME_PREFIX}-alone")
    st, pl = _request("DELETE", f"{ADMIN}/topologies/{topo_alone}")
    if st != 200 or pl.get("code") != 0:
        _fail(f"[1] delete: {st} {pl}")
    if pl.get("data", {}).get("unboundApiCount") != 0:
        _fail(f"[1] expected unboundApiCount=0, got {pl}")
    _pass("[1] 删无引用拓扑 → 200 + unboundApiCount=0")

    # ---- 测试 2: 删有 N=2 引用拓扑 ----
    topo_with_refs = _create_topology(f"{TOPO_NAME_PREFIX}-refs")
    api_id_1, _ = _create_api(topology_id=topo_with_refs, suffix="ref1")
    api_id_2, _ = _create_api(topology_id=topo_with_refs, suffix="ref2", data_source="sql", sql_text="SELECT * FROM nodes")
    # 取删前 updated_at
    _, pl_before = _request("GET", f"{ADMIN}/apis/{api_id_1}")
    updated_at_before = pl_before["data"]["updatedAt"]
    time.sleep(1.1)  # ensure timestamp difference at second precision

    st, pl = _request("DELETE", f"{ADMIN}/topologies/{topo_with_refs}")
    if st != 200 or pl.get("code") != 0:
        _fail(f"[2] delete: {st} {pl}")
    if pl.get("data", {}).get("unboundApiCount") != 2:
        _fail(f"[2] expected unboundApiCount=2, got {pl}")

    # 验证 api_configs.topology_id 已 NULL + updated_at 已变
    _, pl_after = _request("GET", f"{ADMIN}/apis/{api_id_1}")
    if pl_after["data"]["topologyId"] is not None:
        _fail(f"[2] api_id_1 topology_id should be NULL: {pl_after}")
    if pl_after["data"]["updatedAt"] == updated_at_before:
        _fail(f"[2] api_id_1 updated_at should have changed")
    _, pl2 = _request("GET", f"{ADMIN}/apis/{api_id_2}")
    if pl2["data"]["topologyId"] is not None:
        _fail(f"[2] api_id_2 topology_id should be NULL: {pl2}")
    _pass("[2] 删有 2 引用拓扑 → 200 + unboundApiCount=2 + api_configs 已解绑 + updated_at 已变")

    # ---- 测试 3: 批删混合 ----
    # 注意：DELETE /topologies 是"全删"端点，会一并删除 DB 中预存的拓扑与解绑预存接口；
    # 因此这里用 >= 断言（确保至少我的测试数据被处理），而不是精确匹配。
    cleanup()  # 重置我的测试数据
    topo_a = _create_topology(f"{TOPO_NAME_PREFIX}-batch-a")
    topo_b = _create_topology(f"{TOPO_NAME_PREFIX}-batch-b")
    topo_c_alone = _create_topology(f"{TOPO_NAME_PREFIX}-batch-c-alone")
    api_x, _ = _create_api(topology_id=topo_a, suffix="batchx")
    api_y, _ = _create_api(topology_id=topo_b, suffix="batchy")
    # 提交批删
    st, pl = _request("DELETE", f"{ADMIN}/topologies")
    if st != 200 or pl.get("code") != 0:
        _fail(f"[3] batch delete: {st} {pl}")
    data = pl.get("data", {})
    if data.get("deletedCount", 0) < 3:  # 至少删了 a/b/c_alone
        _fail(f"[3] deletedCount should be >= 3, got {data}")
    if data.get("unboundApiCount", 0) < 2:  # 至少 api_x + api_y 被解绑（预存接口可能也算入）
        _fail(f"[3] expected unboundApiCount>=2, got {data}")
    # 解绑后 api_x / api_y 仍存在且 topology_id=NULL
    _, plx = _request("GET", f"{ADMIN}/apis/{api_x}")
    if plx.get("code") != 0 or plx["data"]["topologyId"] is not None:
        _fail(f"[3] api_x should remain with topology_id=NULL: {plx}")
    _, ply = _request("GET", f"{ADMIN}/apis/{api_y}")
    if ply.get("code") != 0 or ply["data"]["topologyId"] is not None:
        _fail(f"[3] api_y should remain with topology_id=NULL: {ply}")
    _pass("[3] 批删混合 → 200 + deletedCount>=3 + unboundApiCount>=2 + 接口仍存在已解绑")

    # 清理批删后剩下的 api_configs
    _request("DELETE", f"{ADMIN}/apis/{api_x}")
    _request("DELETE", f"{ADMIN}/apis/{api_y}")

    # ---- 测试 4: delete-impact 返回受影响接口 ----
    topo_imp = _create_topology(f"{TOPO_NAME_PREFIX}-impact")
    api_i1, _ = _create_api(topology_id=topo_imp, suffix="imp1")
    api_i2, _ = _create_api(topology_id=topo_imp, suffix="imp2")
    api_i3, _ = _create_api(topology_id=topo_imp, suffix="imp3")
    st, pl = _request("GET", f"{ADMIN}/topologies/{topo_imp}/delete-impact")
    if st != 200:
        _fail(f"[4] delete-impact: {st} {pl}")
    data = pl.get("data", {})
    if data.get("affectedApiCount") != 3:
        _fail(f"[4] expected affectedApiCount=3, got {data}")
    affected = data.get("affectedApis", [])
    if len(affected) != 3:
        _fail(f"[4] expected 3 affectedApis, got {len(affected)}: {affected}")
    api_ids_in_response = {a["id"] for a in affected}
    if not {api_i1, api_i2, api_i3}.issubset(api_ids_in_response):
        _fail(f"[4] affectedApis missing some ids: {api_ids_in_response}")
    if data.get("topologyName") != f"{TOPO_NAME_PREFIX}-impact":
        _fail(f"[4] topologyName mismatch: {data}")
    _pass("[4] delete-impact 返回 affectedApiCount=3 + affectedApis 含全部 3 个接口")

    # ---- 测试 5: delete-impact 拓扑不存在 ----
    st, pl = _request("GET", f"{ADMIN}/topologies/topo_nonexistent_xxx/delete-impact")
    if st != 404 or pl.get("detail", {}).get("code") != 40101:
        _fail(f"[5] expected 404+40101, got {st} {pl}")
    _pass("[5] delete-impact 拓扑不存在 → 404 + 40101")

    # ---- 测试 6: 解绑后 SQL 接口调用 → 40001 ----
    # 先删拓扑（解绑 api_i1/i2/i3，但它们都是静态的，需要新建一个 SQL 的）
    _request("DELETE", f"{ADMIN}/apis/{api_i1}")
    _request("DELETE", f"{ADMIN}/apis/{api_i2}")
    _request("DELETE", f"{ADMIN}/apis/{api_i3}")
    api_sql, sql_path = _create_api(
        topology_id=topo_imp, suffix="sql6",
        data_source="sql", sql_text="SELECT * FROM nodes",
    )
    _request("DELETE", f"{ADMIN}/topologies/{topo_imp}")  # 解绑 api_sql
    # 现在调 mock 路由
    st, pl = _request("GET", f"{BASE}{MOCK_PREFIX}{sql_path}")
    if st != 400:
        _fail(f"[6] expected HTTP 400, got {st} {pl}")
    if pl.get("code") != 40001:
        _fail(f"[6] expected code 40001, got {pl}")
    _pass("[6] 解绑后 SQL 接口调用 → 400 + 40001（_step5_execute 兜底）")

    # ---- 测试 7: 静态接口在拓扑被删后仍正常响应 ----
    topo_static = _create_topology(f"{TOPO_NAME_PREFIX}-static")
    api_static, static_path = _create_api(topology_id=topo_static, suffix="static7", data_source="static")
    _request("DELETE", f"{ADMIN}/topologies/{topo_static}")  # 解绑
    st, pl = _request("GET", f"{BASE}{MOCK_PREFIX}{static_path}")
    if st != 200 or pl.get("code") != 0:
        _fail(f"[7] static api after topo delete: {st} {pl}")
    if pl.get("data", {}).get("ok") != "static7":
        _fail(f"[7] static body wrong: {pl}")
    _pass("[7] 静态接口在拓扑被删后仍正常响应（不依赖 topology_id）")

    # ---- 测试 8: 回归 — 不应再出现 40103 ----
    # 通过完整流程验证：创建有引用拓扑、调 DELETE、断言响应中 code=0 而非 40103
    topo_reg = _create_topology(f"{TOPO_NAME_PREFIX}-regression")
    api_reg, _ = _create_api(topology_id=topo_reg, suffix="reg8")
    st, pl = _request("DELETE", f"{ADMIN}/topologies/{topo_reg}")
    if pl.get("code") == 40103:
        _fail(f"[8] regression: 40103 should not appear anymore, got {pl}")
    if st != 200 or pl.get("code") != 0:
        _fail(f"[8] regression: expected 200+code 0, got {st} {pl}")
    _pass("[8] 回归 — 删拓扑成功，错误码 40103 不再触发")
    _request("DELETE", f"{ADMIN}/apis/{api_reg}")
    _request("DELETE", f"{ADMIN}/apis/{api_sql}")
    _request("DELETE", f"{ADMIN}/apis/{api_static}")

    print("\n=== Cleanup ===")
    cleanup()
    print("\nALL 8 TESTS PASSED")


if __name__ == "__main__":
    main()
