"""M4-02 end-to-end test: topology JSON import/export.

Verifies (docs/开发方案.md §M4-02 acceptance):
  - 导出文件可在另一实例导入还原；节点/边/属性完整

Test matrix:
  1. Build a source topology with 2 nodes (router + switch) + 2 attrs each + canvas
     positions + 1 edge (physical_link) + 1 edge attr.
  2. GET /export → assert envelope shape: schemaVersion="1.0", topology.name,
     2 nodes (with attrs+canvas), 1 edge (with attrs), original ids preserved.
  3. POST /import with that doc → 200, returns new topology_id, name auto-suffixed
     because base name collides with the source.
  4. GET /graph on imported topology → 2 nodes, 1 edge, canvas restored.
  5. Verify per-node attrs: ip/vendor/model values match source 1:1.
  6. Verify edge endpoints remap correctly (sourceId/targetId point to NEW node ids).
  7. Error paths:
     - schemaVersion mismatch → 400/40010
     - duplicate node id → 400/40011
     - self-loop → 400/40013
     - edge points to undeclared node → 400/40014
     - missing nodeTypeCode → 400/40015
     - missing edgeTypeCode → 400/40016
  8. Cleanup: delete both topologies.

Assumes backend on http://127.0.0.1:8080.
"""
from __future__ import annotations

import copy
import json
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8080"
ADMIN = f"{BASE}/admin/api"


def _request(method, url, body=None):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
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


def _ok(status, payload, label):
    if status != 200:
        _fail(f"{label} → {status} {payload}")
    if isinstance(payload, dict) and payload.get("code", 0) != 0:
        _fail(f"{label} non-zero code: {payload}")


def main():
    # ---------- 0. Discover seeded type ids ----------
    status, payload = _request("GET", f"{ADMIN}/node-types")
    _ok(status, payload, "GET /node-types")
    node_types = {nt["code"]: nt["id"] for nt in payload["data"]["items"]}
    if "router" not in node_types or "switch" not in node_types:
        _fail(f"seeded node types missing 'router'/'switch': {list(node_types)}")

    status, payload = _request("GET", f"{ADMIN}/edge-types")
    _ok(status, payload, "GET /edge-types")
    edge_types = {et["code"]: et["id"] for et in payload["data"]["items"]}
    if "physical_link" not in edge_types:
        _fail(f"seeded edge type 'physical_link' missing: {list(edge_types)}")

    # ---------- 1. Build source topology ----------
    src_topo_name = "M4-02 源拓扑"
    status, payload = _request("POST", f"{ADMIN}/topologies",
                               {"name": src_topo_name, "description": "import/export e2e"})
    _ok(status, payload, f"create source topology {src_topo_name}")
    src_topo_id = payload["data"]["id"]
    print(f"[INFO] source topology: {src_topo_id}")

    # 2 nodes
    node_ids = []
    for code, name, dn, attrs, x, y in [
        ("router", "R1", "ne=R1", {"ip": "10.0.0.1", "vendor": "Cisco", "model": "ASR-9000"}, 100.0, 200.0),
        ("switch", "S1", "ne=S1", {"ip": "10.0.0.2", "vendor": "Huawei", "model": "S5700"}, 300.0, 200.0),
    ]:
        status, payload = _request(
            "POST", f"{ADMIN}/topologies/{src_topo_id}/nodes",
            {"nodeTypeId": node_types[code], "name": name, "dn": dn, "status": "online"},
        )
        _ok(status, payload, f"create node {name}")
        node_id = payload["data"]["id"]
        node_ids.append(node_id)

        # attrs
        attr_body = [{"fieldKey": k, "value": v} for k, v in attrs.items()]
        status, payload = _request("PUT", f"{ADMIN}/nodes/{node_id}/attrs", attr_body)
        _ok(status, payload, f"set attrs on {name}")

        # canvas
        status, payload = _request("PATCH", f"{ADMIN}/topologies/{src_topo_id}/canvas",
                                   {"nodes": [{"node_id": node_id, "x": x, "y": y}]})
        _ok(status, payload, f"set canvas for {name}")

    _pass(f"built source topology with 2 nodes + 6 attrs + 2 canvas points")

    # 1 edge
    status, payload = _request(
        "POST", f"{ADMIN}/topologies/{src_topo_id}/edges",
        {"edgeTypeId": edge_types["physical_link"],
         "sourceId": node_ids[0], "targetId": node_ids[1], "status": "up"},
    )
    _ok(status, payload, "create edge R1—S1")
    edge_id = payload["data"]["id"]

    status, payload = _request("PUT", f"{ADMIN}/edges/{edge_id}/attrs",
                               [{"fieldKey": "bandwidth", "value": "10Gbps"}])
    _ok(status, payload, "set edge attr")
    _pass("source edge + 1 attr added")

    # ---------- 2. GET /export ----------
    status, payload = _request("GET", f"{ADMIN}/topologies/{src_topo_id}/export")
    _ok(status, payload, "GET /export")
    doc = payload["data"]
    if doc["schemaVersion"] != "1.0":
        _fail(f"unexpected schemaVersion: {doc['schemaVersion']}")
    if doc["topology"]["name"] != src_topo_name:
        _fail(f"export name mismatch: {doc['topology']['name']!r}")
    if len(doc["nodes"]) != 2 or len(doc["edges"]) != 1:
        _fail(f"export counts wrong: {len(doc['nodes'])} nodes, {len(doc['edges'])} edges")

    # Verify export details
    exported_nodes_by_name = {n["name"]: n for n in doc["nodes"]}
    if "R1" not in exported_nodes_by_name or "S1" not in exported_nodes_by_name:
        _fail(f"export missing node names: {list(exported_nodes_by_name)}")
    r1 = exported_nodes_by_name["R1"]
    if r1["nodeTypeCode"] != "router":
        _fail(f"R1 nodeTypeCode wrong: {r1['nodeTypeCode']}")
    if r1["attrs"].get("ip") != "10.0.0.1":
        _fail(f"R1 attr ip not preserved: {r1['attrs']}")
    if not r1.get("canvas") or r1["canvas"].get("x") != 100.0:
        _fail(f"R1 canvas missing/wrong: {r1.get('canvas')}")
    e0 = doc["edges"][0]
    if e0["edgeTypeCode"] != "physical_link" or e0["attrs"].get("bandwidth") != "10Gbps":
        _fail(f"edge export wrong: {e0}")
    _pass(f"export envelope: schemaVersion=1.0, 2 nodes (with attrs+canvas), 1 edge (with attrs)")

    # ---------- 3. POST /import (re-import same doc) ----------
    # Round-trip the doc: remove fields that import doesn't own (id at topo level
    # is generated server-side; export doesn't include it).
    import_body = copy.deepcopy(doc)
    status, payload = _request("POST", f"{ADMIN}/topologies/import", import_body)
    _ok(status, payload, "POST /topologies/import")
    result = payload["data"]
    imported_topo_id = result["topologyId"]
    if imported_topo_id == src_topo_id:
        _fail("imported topology id should differ from source")
    if not result["name"].startswith(src_topo_name):
        _fail(f"imported name should start with source name: {result['name']!r}")
    if "(导入" not in result["name"]:
        _fail(f"imported name should carry 导入 suffix: {result['name']!r}")
    if result["nodeCount"] != 2 or result["edgeCount"] != 1 or result["canvasCount"] != 2:
        _fail(f"import counts wrong: {result}")
    _pass(f"imported as new topology {imported_topo_id} name={result['name']!r}")

    # ---------- 4. GET /graph on imported topology ----------
    status, payload = _request("GET", f"{ADMIN}/topologies/{imported_topo_id}/graph")
    _ok(status, payload, "GET imported /graph")
    graph = payload["data"]
    if len(graph["nodes"]) != 2 or len(graph["edges"]) != 1:
        _fail(f"imported graph counts wrong: {len(graph['nodes'])}/{len(graph['edges'])}")
    if len(graph["canvasNodes"]) != 2:
        _fail(f"imported canvas count wrong: {len(graph['canvasNodes'])}")

    new_node_ids_by_name = {n["name"]: n["id"] for n in graph["nodes"]}
    if "R1" not in new_node_ids_by_name or "S1" not in new_node_ids_by_name:
        _fail(f"imported nodes missing names: {list(new_node_ids_by_name)}")
    # IDs must be NEW (different from source)
    src_node_ids = set(node_ids)
    new_node_ids = set(new_node_ids_by_name.values())
    if src_node_ids & new_node_ids:
        _fail(f"imported nodes reused source ids: {src_node_ids & new_node_ids}")
    _pass("imported graph: 2 nodes / 1 edge / 2 canvas points; node ids regenerated")

    # ---------- 5. Verify per-node attrs round-trip ----------
    # Use detail endpoint to fetch attrs of imported R1
    new_r1_id = new_node_ids_by_name["R1"]
    status, payload = _request("GET", f"{ADMIN}/nodes/{new_r1_id}")
    _ok(status, payload, f"GET imported R1 detail")
    r1_detail = payload["data"]
    if r1_detail["attrs"].get("ip") != "10.0.0.1" or r1_detail["attrs"].get("vendor") != "Cisco":
        _fail(f"imported R1 attrs not restored: {r1_detail['attrs']}")
    if r1_detail.get("x") != 100.0:
        _fail(f"imported R1 canvas x not restored: {r1_detail.get('x')}")
    _pass("imported R1 attrs+canvas match source 1:1")

    # ---------- 6. Verify edge endpoints remapped to NEW ids ----------
    new_edge = graph["edges"][0]
    if new_edge["sourceId"] not in new_node_ids or new_edge["targetId"] not in new_node_ids:
        _fail(f"imported edge endpoints not remapped: {new_edge}")
    if new_edge["sourceId"] in src_node_ids or new_edge["targetId"] in src_node_ids:
        _fail(f"imported edge still points to source ids: {new_edge}")
    _pass("imported edge endpoints remapped to new node ids")

    # ---------- 7. Error paths ----------
    bad_version = copy.deepcopy(doc)
    bad_version["schemaVersion"] = "9.9"
    status, payload = _request("POST", f"{ADMIN}/topologies/import", bad_version)
    if status != 400 or payload.get("detail", {}).get("code") != 40010:
        _fail(f"schemaVersion mismatch should 400/40010, got {status} {payload}")
    _pass("schemaVersion mismatch → 400/40010")

    dup_nodes = copy.deepcopy(doc)
    dup_nodes["nodes"][1]["id"] = dup_nodes["nodes"][0]["id"]  # same id twice
    status, payload = _request("POST", f"{ADMIN}/topologies/import", dup_nodes)
    if status != 400 or payload.get("detail", {}).get("code") != 40011:
        _fail(f"duplicate node id should 400/40011, got {status} {payload}")
    _pass("duplicate node id → 400/40011")

    self_loop = copy.deepcopy(doc)
    self_loop["edges"][0]["targetId"] = self_loop["edges"][0]["sourceId"]
    status, payload = _request("POST", f"{ADMIN}/topologies/import", self_loop)
    if status != 400 or payload.get("detail", {}).get("code") != 40013:
        _fail(f"self-loop should 400/40013, got {status} {payload}")
    _pass("self-loop edge → 400/40013")

    dangling = copy.deepcopy(doc)
    dangling["edges"][0]["sourceId"] = "node_does_not_exist"
    status, payload = _request("POST", f"{ADMIN}/topologies/import", dangling)
    if status != 400 or payload.get("detail", {}).get("code") != 40014:
        _fail(f"dangling edge should 400/40014, got {status} {payload}")
    _pass("edge references undeclared node → 400/40014")

    bad_node_type = copy.deepcopy(doc)
    bad_node_type["nodes"][0]["nodeTypeCode"] = "no_such_type_xyz"
    status, payload = _request("POST", f"{ADMIN}/topologies/import", bad_node_type)
    if status != 400 or payload.get("detail", {}).get("code") != 40015:
        _fail(f"missing node type code should 400/40015, got {status} {payload}")
    _pass("missing nodeTypeCode → 400/40015")

    bad_edge_type = copy.deepcopy(doc)
    bad_edge_type["edges"][0]["edgeTypeCode"] = "no_such_edge_type"
    status, payload = _request("POST", f"{ADMIN}/topologies/import", bad_edge_type)
    if status != 400 or payload.get("detail", {}).get("code") != 40016:
        _fail(f"missing edge type code should 400/40016, got {status} {payload}")
    _pass("missing edgeTypeCode → 400/40016")

    # ---------- 8. Cleanup ----------
    _request("DELETE", f"{ADMIN}/topologies/{src_topo_id}")
    _request("DELETE", f"{ADMIN}/topologies/{imported_topo_id}")

    print("\nALL CHECKS PASSED")


if __name__ == "__main__":
    main()
