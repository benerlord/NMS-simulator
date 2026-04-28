"""M4-03 performance benchmark.

Acceptance (docs/开发方案.md §4.1 M4-03):
  - 3 万节点画布加载 < 3s   (GET /admin/api/topologies/{id}/graph)
  - SQL 分页 < 1s            (GET /admin/api/topologies/{id}/nodes?page=K&page_size=50)

Strategy:
  1. Bypass HTTP for fixture build — directly bulk-insert 30000 nodes / 30000 edges
     into SQLite via the same DB file the running backend reads (`backend/data/app.db`).
     Use `executemany` inside one transaction; this dwarfs HTTP-driven seeding.
  2. Measure (over 3 runs, take min):
       - GET /graph                        target < 3000 ms
       - GET /nodes (page 1 / page 100 / page 600)   target each < 1000 ms
  3. Print a result table; exit 1 if any threshold blown.

Run with backend already on http://127.0.0.1:8080.
The fixture topology is created with a fixed name so re-runs reuse it; pass
`--reset` to drop and rebuild.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / "backend" / "data" / "app.db"
BASE = "http://127.0.0.1:8080"
ADMIN = f"{BASE}/admin/api"

NODE_COUNT = 30_000
EDGE_COUNT = 30_000
FIXTURE_NAME = "M4-03 性能基准 30k"


# ---------------------------------------------------------------------------

def _request(method: str, url: str, body=None, timeout=30):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8") or "{}"
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}


def _time_ms(method: str, url: str, runs=3):
    """Return min wall-clock ms over `runs` requests, plus payload size of last run."""
    fastest = float("inf")
    last_size = 0
    for _ in range(runs):
        t0 = time.perf_counter()
        status, payload = _request(method, url)
        dt = (time.perf_counter() - t0) * 1000.0
        if status != 200:
            sys.exit(f"[FAIL] {method} {url} → {status} {payload}")
        size = len(json.dumps(payload))
        last_size = size
        if dt < fastest:
            fastest = dt
    return fastest, last_size


def _ensure_fixture(reset: bool) -> str:
    """Build (or reuse) the 30k-node fixture topology. Returns topology_id."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    if reset:
        # Hard reset: delete topo by name, cascades to nodes/edges/canvas/attrs.
        row = conn.execute(
            "SELECT id FROM topologies WHERE name = ?", (FIXTURE_NAME,)
        ).fetchone()
        if row:
            print(f"[INFO] dropping existing fixture {row['id']}")
            conn.execute("DELETE FROM topologies WHERE id = ?", (row["id"],))
            conn.commit()

    row = conn.execute(
        "SELECT id FROM topologies WHERE name = ?", (FIXTURE_NAME,)
    ).fetchone()
    if row:
        topo_id = row["id"]
        n = conn.execute(
            "SELECT COUNT(*) FROM nodes WHERE topology_id = ?", (topo_id,)
        ).fetchone()[0]
        e = conn.execute(
            "SELECT COUNT(*) FROM edges WHERE topology_id = ?", (topo_id,)
        ).fetchone()[0]
        if n >= NODE_COUNT and e >= EDGE_COUNT:
            print(f"[INFO] reusing fixture {topo_id}: {n} nodes / {e} edges")
            conn.close()
            return topo_id
        print(f"[INFO] fixture {topo_id} incomplete (n={n}, e={e}), rebuilding")
        conn.execute("DELETE FROM topologies WHERE id = ?", (topo_id,))
        conn.commit()

    topo_id = f"topo_{uuid.uuid4().hex[:12]}"
    print(f"[INFO] building fixture {topo_id}: {NODE_COUNT} nodes / {EDGE_COUNT} edges …")
    t0 = time.perf_counter()

    nt_id = conn.execute(
        "SELECT id FROM node_types WHERE code = 'router'"
    ).fetchone()[0]
    et_id = conn.execute(
        "SELECT id FROM edge_types WHERE code = 'physical_link'"
    ).fetchone()[0]

    conn.execute("BEGIN")
    conn.execute(
        """
        INSERT INTO topologies (id, name, description, version, created_at, updated_at)
        VALUES (?, ?, ?, 1, datetime('now'), datetime('now'))
        """,
        (topo_id, FIXTURE_NAME, "perf bench"),
    )

    # Pre-generate node ids
    node_ids = [f"node_{uuid.uuid4().hex[:12]}" for _ in range(NODE_COUNT)]

    # Bulk insert nodes
    node_rows = [
        (nid, topo_id, nt_id, f"R{i}", f"ne=R{i}", "online")
        for i, nid in enumerate(node_ids)
    ]
    conn.executemany(
        """INSERT INTO nodes (id, topology_id, node_type_id, name, dn, status,
                              created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
        node_rows,
    )

    # Bulk insert node attrs (3 per node = 90k rows)
    attr_rows = []
    for i, nid in enumerate(node_ids):
        attr_rows.append((nid, "ip", f"10.0.{(i >> 8) & 255}.{i & 255}"))
        attr_rows.append((nid, "vendor", "Cisco" if i % 2 == 0 else "Huawei"))
        attr_rows.append((nid, "model", f"M-{i % 100}"))
    conn.executemany(
        "INSERT INTO node_attrs (node_id, field_key, value) VALUES (?, ?, ?)",
        attr_rows,
    )

    # Bulk insert canvas positions (every node)
    canvas_rows = [
        (nid, topo_id, float((i % 200) * 80), float((i // 200) * 80))
        for i, nid in enumerate(node_ids)
    ]
    conn.executemany(
        "INSERT INTO canvas_nodes (node_id, topology_id, x, y) VALUES (?, ?, ?, ?)",
        canvas_rows,
    )

    # Edges: chain pattern n[i] -> n[i+1] for i in 0..NODE_COUNT-2, plus a few extras
    edge_rows = []
    for i in range(EDGE_COUNT):
        s = node_ids[i % NODE_COUNT]
        # Avoid self-loop: pick a different target deterministically
        t = node_ids[(i + 1) % NODE_COUNT]
        edge_rows.append(
            (f"edge_{uuid.uuid4().hex[:12]}", topo_id, et_id, s, t, "up")
        )
    conn.executemany(
        """INSERT INTO edges (id, topology_id, edge_type_id, source_id, target_id, status,
                              created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
        edge_rows,
    )

    conn.commit()
    conn.close()
    dt = time.perf_counter() - t0
    print(f"[INFO] fixture built in {dt:.1f}s")
    return topo_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="drop and rebuild fixture")
    args = parser.parse_args()

    if not DB_PATH.exists():
        sys.exit(f"[FAIL] DB not found at {DB_PATH}")

    # Ensure backend is up
    status, _ = _request("GET", f"{ADMIN}/health")
    if status != 200:
        sys.exit(f"[FAIL] backend not reachable at {BASE}")

    topo_id = _ensure_fixture(args.reset)

    print()
    print(f"=== M4-03 performance bench ({NODE_COUNT} nodes / {EDGE_COUNT} edges) ===")
    print(f"topology: {topo_id}")
    print()

    fail = False

    # GET /graph
    graph_url = f"{ADMIN}/topologies/{topo_id}/graph"
    ms, size = _time_ms("GET", graph_url, runs=3)
    label = "GET /graph (full topology)"
    threshold = 3000
    status_str = "PASS" if ms < threshold else "FAIL"
    if ms >= threshold:
        fail = True
    print(f"[{status_str}] {label:<40} {ms:>8.1f} ms   payload={size/1024:>7.1f} KB   target < {threshold} ms")

    # GET /nodes paginated, page 1 / 100 / 600 (last page region)
    for page in (1, 100, 600):
        url = f"{ADMIN}/topologies/{topo_id}/nodes?page={page}&page_size=50"
        ms, size = _time_ms("GET", url, runs=3)
        label = f"GET /nodes page={page} pageSize=50"
        threshold = 1000
        status_str = "PASS" if ms < threshold else "FAIL"
        if ms >= threshold:
            fail = True
        print(f"[{status_str}] {label:<40} {ms:>8.1f} ms   payload={size/1024:>7.1f} KB   target < {threshold} ms")

    # PATCH /canvas — bulk save 30k positions (canvas save path)
    # Pre-fetch node ids via /graph (already measured); reuse the same nodes.
    status, payload = _request("GET", graph_url)
    nodes_payload = payload["data"]["nodes"]
    save_body = {
        "nodes": [
            {"node_id": n["id"], "x": float((i % 200) * 80 + 5), "y": float((i // 200) * 80 + 5)}
            for i, n in enumerate(nodes_payload)
        ]
    }
    save_url = f"{ADMIN}/topologies/{topo_id}/canvas"
    fastest_save = float("inf")
    for _ in range(3):
        t0 = time.perf_counter()
        status, p = _request("PATCH", save_url, save_body, timeout=30)
        dt = (time.perf_counter() - t0) * 1000.0
        if status != 200:
            sys.exit(f"[FAIL] PATCH /canvas → {status} {p}")
        if dt < fastest_save:
            fastest_save = dt
    label = "PATCH /canvas (30k positions)"
    threshold = 3000
    status_str = "PASS" if fastest_save < threshold else "FAIL"
    if fastest_save >= threshold:
        fail = True
    print(f"[{status_str}] {label:<40} {fastest_save:>8.1f} ms                       target < {threshold} ms")

    print()
    if fail:
        print("BENCH FAILED — at least one threshold exceeded")
        sys.exit(1)
    print("BENCH PASSED — all thresholds met")


if __name__ == "__main__":
    main()
