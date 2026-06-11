import asyncio
import json
import random
import time
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.db.connection import connect, transaction
from app.admin.schemas._base import CamelModel
from app.admin.schemas.node_group import (
    AttrStrategyItem,
    EdgeStrategyItem,
    NodeGroupCreate,
    NodeGroupUpdate,
    NodeGroupItem,
    MacroNode,
    MacroNodeStatus,
    MacroEdge,
    GroupGraphData,
)

router = APIRouter(prefix="/admin/api", tags=["节点组"])

# Per-group concurrency lock: only one materialize per group at a time
_materialize_locks: dict[str, bool] = {}

NODE_FLUSH_SIZE = 5000
MAX_CARTESIAN_EDGES = 1_000_000


def _new_id() -> str:
    return f"grp_{uuid.uuid4().hex[:12]}"


def _parse_attr_strategies(raw: str) -> list[AttrStrategyItem]:
    data = json.loads(raw)
    return [AttrStrategyItem(**item) for item in data]


def _parse_edge_strategies(raw: Optional[str]) -> Optional[list[EdgeStrategyItem]]:
    if raw is None:
        return None
    data = json.loads(raw)
    return [EdgeStrategyItem(**item) for item in data] if data else None


def _is_materialized(conn, group_id: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM nodes WHERE group_id = ?", (group_id,)
    ).fetchone()
    return row["cnt"] > 0


def _row_to_item(conn, row) -> NodeGroupItem:
    return NodeGroupItem(
        id=row["id"],
        topology_id=row["topology_id"],
        node_type_id=row["node_type_id"],
        group_name=row["group_name"],
        node_count=row["node_count"],
        name_template=row["name_template"],
        attr_strategies=_parse_attr_strategies(row["attr_strategies"]),
        edge_strategies=_parse_edge_strategies(row["edge_strategies"]),
        is_materialized=_is_materialized(conn, row["id"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ============== node_groups CRUD ==============


@router.get("/topologies/{topology_id}/node-groups")
def list_node_groups(topology_id: str) -> dict:
    with connect() as conn:
        topo = conn.execute(
            "SELECT id FROM topologies WHERE id = ?", (topology_id,)
        ).fetchone()
        if not topo:
            raise HTTPException(
                status_code=404,
                detail={"code": 40501, "message": "拓扑不存在"},
            )
        rows = conn.execute(
            "SELECT * FROM node_groups WHERE topology_id = ? ORDER BY created_at",
            (topology_id,),
        ).fetchall()
        items = [_row_to_item(conn, r) for r in rows]
        return {
            "code": 0,
            "data": {"items": [m.model_dump(mode="json", by_alias=True) for m in items]},
            "message": "ok",
        }


@router.get("/node-groups/{group_id}")
def get_node_group(group_id: str) -> dict:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM node_groups WHERE id = ?", (group_id,)
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=404,
                detail={"code": 40502, "message": "节点组不存在"},
            )
        item = _row_to_item(conn, row)
        return {"code": 0, "data": item.model_dump(mode="json", by_alias=True), "message": "ok"}


@router.post("/topologies/{topology_id}/node-groups")
def create_node_group(topology_id: str, data: NodeGroupCreate) -> dict:
    group_id = _new_id()
    with transaction() as conn:
        topo = conn.execute(
            "SELECT id FROM topologies WHERE id = ?", (topology_id,)
        ).fetchone()
        if not topo:
            raise HTTPException(
                status_code=404,
                detail={"code": 40501, "message": "拓扑不存在"},
            )
        ntype = conn.execute(
            "SELECT id FROM node_types WHERE id = ?", (data.node_type_id,)
        ).fetchone()
        if not ntype:
            raise HTTPException(
                status_code=400,
                detail={"code": 40503, "message": "节点类型不存在"},
            )
        conn.execute(
            """INSERT INTO node_groups
               (id, topology_id, node_type_id, group_name, node_count, name_template,
                attr_strategies, edge_strategies)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                group_id,
                topology_id,
                data.node_type_id,
                data.group_name,
                data.node_count,
                data.name_template,
                json.dumps(
                    [s.model_dump() for s in data.attr_strategies], ensure_ascii=False
                ),
                json.dumps(
                    [s.model_dump() for s in data.edge_strategies], ensure_ascii=False
                )
                if data.edge_strategies
                else None,
            ),
        )
    return {"code": 0, "data": {"id": group_id}, "message": "ok"}


@router.put("/node-groups/{group_id}")
def update_node_group(group_id: str, data: NodeGroupUpdate) -> dict:
    fields = data.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(
            status_code=400,
            detail={"code": 40504, "message": "无更新字段"},
        )
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM node_groups WHERE id = ?", (group_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(
                status_code=404,
                detail={"code": 40502, "message": "节点组不存在"},
            )

        # Serialize list fields to JSON strings
        if "attr_strategies" in fields:
            fields["attr_strategies"] = json.dumps(
                [s.model_dump() for s in data.attr_strategies], ensure_ascii=False
            )
        if "edge_strategies" in fields:
            fields["edge_strategies"] = json.dumps(
                [s.model_dump() for s in data.edge_strategies], ensure_ascii=False
            ) if data.edge_strategies else None

        set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
        conn.execute(
            f"UPDATE node_groups SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            (*fields.values(), group_id),
        )
    return {"code": 0, "data": {"id": group_id}, "message": "ok"}


@router.delete("/node-groups/{group_id}")
def delete_node_group(group_id: str) -> dict:
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM node_groups WHERE id = ?", (group_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(
                status_code=404,
                detail={"code": 40502, "message": "节点组不存在"},
            )
        # Cascade: delete all materialized nodes (cascades to node_attrs, canvas_nodes, edges)
        conn.execute("DELETE FROM nodes WHERE group_id = ?", (group_id,))
        conn.execute("DELETE FROM node_groups WHERE id = ?", (group_id,))
    return {"code": 0, "data": {"id": group_id}, "message": "删除成功"}


# ============== Materialize Engine ==============


def _render_name(template: str, group_name: str, index: int, width: int) -> str:
    """Render node name from template: {group} -> group_name, {i:0Nd} -> zero-padded index."""
    name = template.replace("{group}", group_name)
    name = name.replace(f"{{i:0{width}d}}", str(index).zfill(width))
    return name


def _parse_name_template(template: str) -> int:
    """Extract the zero-padding width from name template, default 5."""
    import re

    m = re.search(r"\{i:0(\d+)d\}", template)
    if m:
        return int(m.group(1))
    return 5


def _generate_attr_value(strategy: AttrStrategyItem, index: int, rng: random.Random) -> str:
    """Generate a single attribute value for the i-th node (0-indexed)."""
    if strategy.strategy == "fixed":
        return strategy.fixed_value
    elif strategy.strategy == "random":
        return rng.choice(strategy.pool)
    elif strategy.strategy == "increment":
        return _increment_value(strategy.base, strategy.step, index)
    elif strategy.strategy == "range":
        return str(rng.randint(strategy.min, strategy.max))
    return ""


def _increment_value(base: str, step: str, idx: int) -> str:
    """base + idx * step, preserving leading zeros and handling IP-like values."""
    # Integer with leading-zero preservation
    try:
        b = int(base)
        s = int(step)
        result = b + idx * s
        if base.startswith("0") and len(base) > 1:
            return str(result).zfill(len(base))
        return str(result)
    except ValueError:
        pass
    # IP-like: increment last octet
    parts = base.rsplit(".", 1)
    if len(parts) == 2:
        try:
            last = int(parts[1])
            s = int(step)
            return f"{parts[0]}.{last + idx * s}"
        except ValueError:
            pass
    # Fallback
    try:
        return f"{base}{idx * int(step)}"
    except ValueError:
        return f"{base}_{idx}"


def _generate_edges(
    conn,
    topology_id: str,
    source_ids: list[str],
    target_ids: list[str],
    edge_type_id: str,
    mode: str,
    ratio_k: Optional[int],
) -> list[str]:
    """Generate edge (source, target) pairs according to mode."""
    pairs: list[tuple[str, str]] = []
    n_src = len(source_ids)
    n_tgt = len(target_ids)

    if mode == "modulo":
        k = ratio_k or 1
        for i, src in enumerate(source_ids):
            tgt_idx = min(i // k, n_tgt - 1)
            pairs.append((src, target_ids[tgt_idx]))
    elif mode == "one_to_n":
        k = ratio_k or 1
        for i, src in enumerate(source_ids):
            for j in range(k):
                tgt_idx = (i * k + j) % n_tgt
                pairs.append((src, target_ids[tgt_idx]))
    elif mode == "all_to_all":
        for src in source_ids:
            for tgt in target_ids:
                pairs.append((src, tgt))
    elif mode == "dense":
        for i in range(min(n_src, n_tgt)):
            pairs.append((source_ids[i], target_ids[i]))

    # Insert in batch
    edge_ids = []
    for src, tgt in pairs:
        eid = f"edge_{uuid.uuid4().hex[:12]}"
        edge_ids.append(eid)
        conn.execute(
            """INSERT INTO edges (id, topology_id, edge_type_id, source_id, target_id, status)
               VALUES (?, ?, ?, ?, ?, 'up')""",
            (eid, topology_id, edge_type_id, src, tgt),
        )
    return edge_ids


def _resolve_edge_type_id(conn, edge_type_code: str) -> Optional[str]:
    row = conn.execute(
        "SELECT id FROM edge_types WHERE code = ?", (edge_type_code,)
    ).fetchone()
    return row["id"] if row else None


# ============== Materialize Endpoint ==============


@router.post("/node-groups/{group_id}/materialize")
async def materialize_node_group(group_id: str) -> dict:
    # 1. Concurrency check
    if _materialize_locks.get(group_id):
        raise HTTPException(
            status_code=409,
            detail={"code": 40505, "message": "该节点组正在展开中，请稍后重试"},
        )
    _materialize_locks[group_id] = True
    t_start = time.time()

    try:
        # 2. Validate group
        with connect() as conn:
            group = conn.execute(
                "SELECT * FROM node_groups WHERE id = ?", (group_id,)
            ).fetchone()
            if not group:
                raise HTTPException(
                    status_code=404,
                    detail={"code": 40502, "message": "节点组不存在"},
                )
            if _is_materialized(conn, group_id):
                raise HTTPException(
                    status_code=409,
                    detail={"code": 40506, "message": "节点组已展开，不可重复展开"},
                )

            topology_id = group["topology_id"]
            node_type_id = group["node_type_id"]
            node_count = group["node_count"]
            name_template = group["name_template"]
            attr_strategies = _parse_attr_strategies(group["attr_strategies"])
            edge_strategies = _parse_edge_strategies(group["edge_strategies"])

        # 3. Pre-validate edge strategies
        hybrid_target_nodes: dict[str, str] = {}  # target_group_id -> normal node_id (for hybrid)
        if edge_strategies:
            for es in edge_strategies:
                n_src = node_count
                with connect() as conn:
                    tgt_group = conn.execute(
                        "SELECT node_count FROM node_groups WHERE id = ? AND topology_id = ?",
                        (es.target_group_id, topology_id),
                    ).fetchone()
                    if tgt_group:
                        # Regular group-to-group edge strategy
                        if not _is_materialized(conn, es.target_group_id):
                            raise HTTPException(
                                status_code=400,
                                detail={
                                    "code": 40508,
                                    "message": f"目标节点组 {es.target_group_id} 尚未展开，请先展开目标组",
                                },
                            )
                        n_tgt = tgt_group["node_count"]
                        if es.mode == "all_to_all":
                            if n_src * n_tgt > MAX_CARTESIAN_EDGES:
                                raise HTTPException(
                                    status_code=400,
                                    detail={
                                        "code": 40509,
                                        "message": f"笛卡尔积边数 {n_src * n_tgt} 超过上限 {MAX_CARTESIAN_EDGES}",
                                    },
                                )
                    else:
                        # Hybrid: target_group_id references a normal node, not a group
                        tgt_node = conn.execute(
                            "SELECT id FROM nodes WHERE id = ? AND topology_id = ?",
                            (es.target_group_id, topology_id),
                        ).fetchone()
                        if not tgt_node:
                            raise HTTPException(
                                status_code=400,
                                detail={
                                    "code": 40507,
                                    "message": f"边策略引用的目标 {es.target_group_id} 不存在",
                                },
                            )
                        hybrid_target_nodes[es.target_group_id] = tgt_node["id"]

        # 4. Generate nodes
        width = _parse_name_template(name_template)

        # Pre-query alarm schema for the topology (used per-node in flush)
        alarm_schema_id: Optional[str] = None
        alarm_default_fields: list[tuple] = []  # [(field_key, default_value), ...]
        with connect() as _ac:
            _row = _ac.execute(
                "SELECT alarm_schema_id FROM topologies WHERE id = ?", (topology_id,)
            ).fetchone()
            if _row and _row["alarm_schema_id"]:
                alarm_schema_id = _row["alarm_schema_id"]
                _fields = _ac.execute(
                    "SELECT field_key, default_value FROM alarm_schema_fields "
                    "WHERE alarm_schema_id = ? AND default_value IS NOT NULL "
                    "ORDER BY sort_order, id",
                    (alarm_schema_id,),
                ).fetchall()
                alarm_default_fields = [(f["field_key"], f["default_value"]) for f in _fields]

        rng = random.Random(group_id)  # Seeded random for reproducibility
        total_nodes = node_count
        node_ids: list[str] = []
        generated_nodes = 0

        def _flush_nodes(conn, buffer: list[tuple], base_idx: int):
            """Flush buffered nodes + attrs to DB. base_idx is the global index of buffer[0]."""
            for j, (nid, nname) in enumerate(buffer):
                idx = base_idx + j
                conn.execute(
                    """INSERT INTO nodes (id, topology_id, node_type_id, name, dn, status, group_id)
                       VALUES (?, ?, ?, ?, ?, 'online', ?)""",
                    (nid, topology_id, node_type_id, nname, nname, group_id),
                )
                node_ids.append(nid)
                for s in attr_strategies:
                    val = _generate_attr_value(s, idx, rng)
                    conn.execute(
                        "INSERT INTO node_attrs (node_id, field_key, value) VALUES (?, ?, ?)",
                        (nid, s.field_key, val),
                    )
                # Auto-insert 1 default alarm per node when topology has alarm_schema bound
                if alarm_schema_id:
                    aid = f"alm_{uuid.uuid4().hex[:12]}"
                    conn.execute(
                        "INSERT INTO node_alarms (id, node_id, alarm_index) VALUES (?, ?, 1)",
                        (aid, nid),
                    )
                    for fk, fv in alarm_default_fields:
                        conn.execute(
                            "INSERT INTO node_alarm_attrs (alarm_id, field_key, value) VALUES (?, ?, ?)",
                            (aid, fk, fv),
                        )

        buffer: list[tuple] = []  # (node_id, name)
        with transaction() as conn:
            for i in range(node_count):
                nid = f"node_{uuid.uuid4().hex[:12]}"
                name = _render_name(name_template, group["group_name"], i + 1, width)
                buffer.append((nid, name))

                if len(buffer) >= NODE_FLUSH_SIZE:
                    base_idx = generated_nodes
                    _flush_nodes(conn, buffer, base_idx)
                    generated_nodes += len(buffer)
                    buffer.clear()
                    elapsed = int((time.time() - t_start) * 1000)
                    await _broadcast(group_id, topology_id, "nodes", generated_nodes, total_nodes, elapsed)
                    await asyncio.sleep(0)

            if buffer:
                base_idx = generated_nodes
                _flush_nodes(conn, buffer, base_idx)
                generated_nodes += len(buffer)

        # 5. Generate edges
        total_edges = 0
        if edge_strategies:
            with connect() as conn:
                target_node_cache: dict[str, list[str]] = {}
                for es in edge_strategies:
                    edge_type_id = _resolve_edge_type_id(conn, es.edge_type_code)
                    if not edge_type_id:
                        raise HTTPException(
                            status_code=400,
                            detail={
                                "code": 40510,
                                "message": f"边类型 {es.edge_type_code} 不存在",
                            },
                        )

                    if es.target_group_id not in target_node_cache:
                        if es.target_group_id in hybrid_target_nodes:
                            # Hybrid: single normal node as target
                            target_node_cache[es.target_group_id] = [hybrid_target_nodes[es.target_group_id]]
                        else:
                            # Regular: all nodes belonging to the target group
                            tgt_rows = conn.execute(
                                "SELECT id FROM nodes WHERE group_id = ? ORDER BY rowid",
                                (es.target_group_id,),
                            ).fetchall()
                            target_node_cache[es.target_group_id] = [r["id"] for r in tgt_rows]

                    tgt_ids = target_node_cache[es.target_group_id]

                    with transaction() as tx:
                        edge_ids = _generate_edges(
                            tx, topology_id, node_ids, tgt_ids, edge_type_id, es.mode, es.ratio_k,
                        )
                        total_edges += len(edge_ids)

                    elapsed = int((time.time() - t_start) * 1000)
                    await _broadcast(group_id, topology_id, "edges", total_edges, total_edges, elapsed)
                    await asyncio.sleep(0)

        # 6. Done
        elapsed_ms = int((time.time() - t_start) * 1000)
        await _broadcast(group_id, topology_id, "done", max(generated_nodes, total_edges), max(generated_nodes, total_edges), elapsed_ms)

        return {
            "code": 0,
            "data": {
                "materializedNodes": generated_nodes,
                "materializedEdges": total_edges,
                "elapsedMs": elapsed_ms,
            },
            "message": "ok",
        }
    finally:
        _materialize_locks.pop(group_id, None)


async def _broadcast(group_id: str, topology_id: str, phase: str, current: int, total: int, elapsed_ms: int):
    from app.core.ws_hub import broadcast_group_progress

    await broadcast_group_progress(topology_id, group_id, {
        "phase": phase,
        "current": current,
        "total": total,
        "pct": round(current / total * 100) if total > 0 else 100,
        "elapsedMs": elapsed_ms,
    })


# ============== Macro Node Position ==============


class MacroNodePositionUpdate(CamelModel):
    x: float
    y: float


@router.patch("/node-groups/{group_id}/position")
def update_macro_node_position(group_id: str, data: MacroNodePositionUpdate) -> dict:
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM node_groups WHERE id = ?", (group_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(
                status_code=404,
                detail={"code": 40502, "message": "节点组不存在"},
            )
        conn.execute(
            "UPDATE node_groups SET canvas_x = ?, canvas_y = ?, updated_at = datetime('now') WHERE id = ?",
            (data.x, data.y, group_id),
        )
    return {"code": 0, "data": {"id": group_id, "x": data.x, "y": data.y}, "message": "ok"}


# ============== Group Graph ==============


@router.get("/topologies/{topology_id}/group-graph")
def get_group_graph(topology_id: str) -> dict:
    with connect() as conn:
        topo = conn.execute(
            "SELECT id FROM topologies WHERE id = ?", (topology_id,)
        ).fetchone()
        if not topo:
            raise HTTPException(
                status_code=404,
                detail={"code": 40501, "message": "拓扑不存在"},
            )

        groups = conn.execute(
            "SELECT * FROM node_groups WHERE topology_id = ?", (topology_id,)
        ).fetchall()

        macro_nodes: list[MacroNode] = []
        for g in groups:
            materialized = _is_materialized(conn, g["id"])
            if materialized:
                online = conn.execute(
                    "SELECT COUNT(*) FROM nodes WHERE group_id = ? AND status = 'online'",
                    (g["id"],),
                ).fetchone()[0]
                offline = conn.execute(
                    "SELECT COUNT(*) FROM nodes WHERE group_id = ? AND status = 'offline'",
                    (g["id"],),
                ).fetchone()[0]
                status_breakdown = MacroNodeStatus(online=online, offline=offline)
            else:
                status_breakdown = MacroNodeStatus(
                    online=g["node_count"], offline=0
                )
            macro_nodes.append(
                MacroNode(
                    id=g["id"],
                    topology_id=g["topology_id"],
                    node_type_id=g["node_type_id"],
                    group_name=g["group_name"],
                    node_count=g["node_count"],
                    is_materialized=materialized,
                    status_breakdown=status_breakdown,
                    x=g["canvas_x"] if "canvas_x" in g.keys() else None,
                    y=g["canvas_y"] if "canvas_y" in g.keys() else None,
                )
            )

        macro_edges: list[MacroEdge] = []
        for g in groups:
            if g["edge_strategies"]:
                for es in json.loads(g["edge_strategies"]):
                    # Count actual edges
                    total_edge_count = 0
                    tgt_is_group = conn.execute(
                        "SELECT COUNT(*) FROM node_groups WHERE id = ?",
                        (es["target_group_id"],),
                    ).fetchone()[0] > 0
                    source_materialized = _is_materialized(conn, g["id"])

                    if source_materialized:
                        if tgt_is_group:
                            if _is_materialized(conn, es["target_group_id"]):
                                total_edge_count = conn.execute(
                                    """
                                    SELECT COUNT(*) FROM edges
                                    WHERE source_id IN (SELECT id FROM nodes WHERE group_id = ?)
                                      AND target_id IN (SELECT id FROM nodes WHERE group_id = ?)
                                    """,
                                    (g["id"], es["target_group_id"]),
                                ).fetchone()[0]
                        else:
                            # Hybrid: target is a normal node
                            total_edge_count = conn.execute(
                                """
                                SELECT COUNT(*) FROM edges
                                WHERE source_id IN (SELECT id FROM nodes WHERE group_id = ?)
                                  AND target_id = ?
                                """,
                                (g["id"], es["target_group_id"]),
                            ).fetchone()[0]

                    macro_edges.append(
                        MacroEdge(
                            source_group_id=g["id"],
                            target_group_id=es["target_group_id"],
                            edge_type_code=es["edge_type_code"],
                            mode=es["mode"],
                            ratio_k=es.get("ratio_k"),
                            total_edge_count=total_edge_count,
                            visual_source_is_macro=es.get("visual_source_is_macro"),
                        )
                    )

    result = GroupGraphData(macro_nodes=macro_nodes, macro_edges=macro_edges)
    return {
        "code": 0,
        "data": result.model_dump(mode="json", by_alias=True),
        "message": "ok",
    }
