"""Dynamic CTE view generation for the SQL mode of API configs.

Runtime behavior (per docs/数据库表设计.md §5):
- Each node_type present in the topology becomes a CTE named after its `code`,
  with columns = fixed node columns + pivoted attrs from node_type_fields.
- Each edge_type present in the topology becomes a CTE named after its `code`,
  with source/target names and dn joined in, plus pivoted attrs.
- Generic CTEs `nodes` / `edges` / `children` are always emitted.
- The bound topology id is referenced via the `:__tid__` placeholder.
"""

import re
import sqlite3
from typing import Any, Optional

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

NODE_FIXED_COLUMNS: list[str] = [
    "id",
    "name",
    "dn",
    "status",
    "group_id",
    "created_at",
    "updated_at",
]

EDGE_FIXED_COLUMNS: list[str] = [
    "id",
    "source_id",
    "target_id",
    "status",
    "created_at",
    "updated_at",
]

EDGE_JOIN_COLUMNS: list[str] = [
    "source_name",
    "source_dn",
    "source_group_id",
    "target_name",
    "target_dn",
    "target_group_id",
]

# CTEs that are always emitted by collect_views() regardless of topology content.
# NOTE: "alarms" is intentionally excluded here — it is only emitted when the
# topology has an alarm_schema_id bound (see _build_alarms_cte / collect_views).
GENERIC_VIEW_NAMES: list[str] = ["gn_seq", "nodes", "edges", "children", "node_groups", "group_nodes", "group_edges", "topology_nodes", "topology_edges"]

# Names that user-defined node_type / edge_type codes must not collide with.
# "alarms" is included here so that even though the alarms CTE is only
# conditionally emitted, user codes can never shadow it when it IS present.
_RESERVED_NAMES: set[str] = {"gn_seq", "nodes", "edges", "children", "node_groups", "group_nodes", "group_edges", "topology_nodes", "topology_edges", "alarms"}


def is_valid_ident(s: str) -> bool:
    """Whether `s` is a safe SQL identifier (no injection surface)."""
    return bool(s) and bool(_IDENT_RE.match(s))


def _fetch_used_node_types(conn: sqlite3.Connection, topology_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT DISTINCT nt.id, nt.code, nt.name
        FROM node_types nt
        WHERE nt.id IN (
            SELECT node_type_id FROM nodes WHERE topology_id = ?
            UNION
            SELECT node_type_id FROM node_groups WHERE topology_id = ?
        )
        ORDER BY nt.code
        """,
        (topology_id, topology_id),
    ).fetchall()
    return [{"id": r["id"], "code": r["code"], "name": r["name"]} for r in rows]


def _fetch_used_edge_types(conn: sqlite3.Connection, topology_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT DISTINCT et.id, et.code, et.name
        FROM edge_types et
        JOIN edges e ON e.edge_type_id = et.id
        WHERE e.topology_id = ?
        ORDER BY et.code
        """,
        (topology_id,),
    ).fetchall()
    return [{"id": r["id"], "code": r["code"], "name": r["name"]} for r in rows]


def _fetch_node_fields(conn: sqlite3.Connection, node_type_id: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT field_key FROM node_type_fields
        WHERE node_type_id = ?
        ORDER BY sort_order, id
        """,
        (node_type_id,),
    ).fetchall()
    return [r["field_key"] for r in rows if is_valid_ident(r["field_key"])]


def _fetch_edge_fields(conn: sqlite3.Connection, edge_type_id: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT field_key FROM edge_type_fields
        WHERE edge_type_id = ?
        ORDER BY sort_order, id
        """,
        (edge_type_id,),
    ).fetchall()
    return [r["field_key"] for r in rows if is_valid_ident(r["field_key"])]


def build_node_type_cte(code: str, type_id: str, field_keys: list[str]) -> dict[str, Any]:
    """Return `{name, columns, sql}` for a node_type CTE.

    Emits SELECT body only (caller wraps with `WITH <name> AS (...)`).
    Includes both physical nodes (from main.nodes) and virtual group nodes
    (from the `gn_seq` + `group_nodes` CTEs) so that type-specific views
    like `switch` can query all nodes of that type.
    """
    columns = list(NODE_FIXED_COLUMNS)
    pivots: list[str] = []
    for key in field_keys:
        if key in columns:
            continue
        columns.append(key)
        pivots.append(f"MAX(CASE WHEN a.field_key = '{key}' THEN a.value END) AS {key}")

    # `group_id` is a column on nodes but can be renamed by pivot — skip pivot for it
    fixed = [f"n.{c}" for c in NODE_FIXED_COLUMNS]
    select_lines = fixed + pivots
    select_body = ",\n         ".join(select_lines)

    # Virtual group nodes: NULL for all pivoted attr columns (no real attrs stored)
    gn_fixed = [f"gn.{c}" for c in NODE_FIXED_COLUMNS]
    gn_nulls = [f"NULL AS {key}" for key in field_keys if key not in NODE_FIXED_COLUMNS]
    gn_select_body = ",\n         ".join(gn_fixed + gn_nulls)

    # type_id is a generated string like `nt_switch` from seed; bind-safe as literal
    # since it comes from DB rows we just read.
    sql = (
        f"SELECT {select_body}\n"
        "  FROM nodes n\n"
        "  LEFT JOIN node_attrs a ON a.node_id = n.id\n"
        "  WHERE n.topology_id = :__tid__\n"
        f"    AND n.node_type_id = '{type_id}'\n"
        "  GROUP BY n.id\n"
        "\n"
        "UNION ALL\n"
        "\n"
        f"SELECT {gn_select_body}\n"
        "  FROM group_nodes gn\n"
        f"  WHERE gn.node_type_id = '{type_id}'\n"
        "  GROUP BY gn.id"
    )
    return {"name": code, "columns": columns, "sql": sql}


def build_edge_type_cte(code: str, type_id: str, field_keys: list[str]) -> dict[str, Any]:
    columns = list(EDGE_FIXED_COLUMNS) + list(EDGE_JOIN_COLUMNS)
    pivots: list[str] = []
    for key in field_keys:
        if key in columns:
            continue
        columns.append(key)
        pivots.append(f"MAX(CASE WHEN a.field_key = '{key}' THEN a.value END) AS {key}")

    fixed = [f"e.{c}" for c in EDGE_FIXED_COLUMNS]
    joins = [
        "s.name AS source_name",
        "s.dn   AS source_dn",
        "s.group_id AS source_group_id",
        "t.name AS target_name",
        "t.dn   AS target_dn",
        "t.group_id AS target_group_id",
    ]
    select_body = ",\n         ".join(fixed + joins + pivots)
    sql = (
        f"SELECT {select_body}\n"
        "  FROM edges e\n"
        "  JOIN nodes s ON s.id = e.source_id\n"
        "  JOIN nodes t ON t.id = e.target_id\n"
        "  LEFT JOIN edge_attrs a ON a.edge_id = e.id\n"
        "  WHERE e.topology_id = :__tid__\n"
        f"    AND e.edge_type_id = '{type_id}'\n"
        "  GROUP BY e.id"
    )
    return {"name": code, "columns": columns, "sql": sql}


def _build_gn_seq_cte() -> dict[str, Any]:
    """Recursive sequence generator for node groups.

    Generates (grp_id, idx) pairs from 1 to node_count for each group.
    Extracted as a standalone CTE so that both `group_nodes` and type-specific
    node views can reference it.  Capped at 100 000 per group.
    """
    sql = (
        "SELECT id AS grp_id, 1 AS idx FROM main.node_groups\n"
        "  WHERE topology_id = :__tid__ AND node_count > 0\n"
        "UNION ALL\n"
        "SELECT s.grp_id, s.idx + 1\n"
        "  FROM gn_seq s\n"
        "  JOIN main.node_groups ng ON ng.id = s.grp_id\n"
        "  WHERE s.idx < ng.node_count AND s.idx < 100000"
    )
    return {
        "name": "gn_seq",
        "columns": ["grp_id", "idx"],
        "sql": sql,
    }


def _build_group_nodes_cte() -> dict[str, Any]:
    """Virtual node generation from node_groups definitions.

    References the `gn_seq` CTE (defined earlier in the same WITH clause)
    to generate rows on-the-fly from name_template and node_count.
    """
    sql = (
        "SELECT\n"
        "    ng.id || '_' || CAST(s.idx AS TEXT) AS id,\n"
        "    ng.topology_id,\n"
        "    ng.node_type_id,\n"
        "    CASE\n"
        "        WHEN INSTR(ng.name_template, '{i:') > 0 THEN\n"
        "            REPLACE(\n"
        "                SUBSTR(ng.name_template, 1, INSTR(ng.name_template, '{i:') - 1),\n"
        "                '{group}', ng.group_name\n"
        "            ) ||\n"
        "            SUBSTR('00000000000000000000', 1,\n"
        "                MAX(0, CAST(SUBSTR(ng.name_template, INSTR(ng.name_template, '{i:0') + 4,\n"
        "                    INSTR(SUBSTR(ng.name_template, INSTR(ng.name_template, '{i:0') + 4), 'd}') - 1) AS INTEGER)\n"
        "                    - LENGTH(CAST(s.idx AS TEXT)))) ||\n"
        "            CAST(s.idx AS TEXT) ||\n"
        "            SUBSTR(ng.name_template, INSTR(ng.name_template, 'd}') + 2)\n"
        "        ELSE REPLACE(ng.name_template, '{group}', ng.group_name)\n"
        "    END AS name,\n"
        "    ng.id AS group_id,\n"
        "    ng.group_name,\n"
        "    s.idx AS node_index,\n"
        "    'online' AS status,\n"
        "    NULL AS dn,\n"
        "    datetime('now') AS created_at,\n"
        "    datetime('now') AS updated_at\n"
        "FROM gn_seq s\n"
        "JOIN main.node_groups ng ON ng.id = s.grp_id"
    )
    return {
        "name": "group_nodes",
        "columns": [
            "id", "topology_id", "node_type_id", "name", "dn", "status",
            "group_id", "group_name", "node_index",
            "created_at", "updated_at",
        ],
        "sql": sql,
    }


def _build_group_edges_cte() -> dict[str, Any]:
    """Edge strategy metadata CTE — shows connection rules between groups.

    Returns one row per edge-strategy entry (not per individual edge).
    Users can multiply by node_count(s) to estimate total edge counts.
    Uses json_extract for SQLite < 3.38 compatibility (no ->> operator).
    """
    sql = (
        "SELECT\n"
        "    ng_src.id || '->' || json_extract(es.value, '$.target_group_id') AS id,\n"
        "    ng_src.topology_id,\n"
        "    (SELECT id FROM main.edge_types WHERE code = json_extract(es.value, '$.edge_type_code')) AS edge_type_id,\n"
        "    ng_src.id AS source_id,\n"
        "    ng_src.group_name AS source_name,\n"
        "    ng_src.id AS source_group_id,\n"
        "    json_extract(es.value, '$.target_group_id') AS target_id,\n"
        "    COALESCE(\n"
        "        (SELECT group_name FROM main.node_groups WHERE id = json_extract(es.value, '$.target_group_id')),\n"
        "        (SELECT name FROM main.nodes WHERE id = json_extract(es.value, '$.target_group_id'))\n"
        "    ) AS target_name,\n"
        "    json_extract(es.value, '$.target_group_id') AS target_group_id,\n"
        "    json_extract(es.value, '$.edge_type_code') AS edge_type_code,\n"
        "    json_extract(es.value, '$.mode') AS mode,\n"
        "    CAST(json_extract(es.value, '$.ratio_k') AS INTEGER) AS ratio_k,\n"
        "    ng_src.node_count AS source_node_count,\n"
        "    COALESCE(\n"
        "        (SELECT node_count FROM main.node_groups WHERE id = json_extract(es.value, '$.target_group_id')),\n"
        "        1\n"
        "    ) AS target_node_count\n"
        "FROM main.node_groups ng_src,\n"
        "     json_each(ng_src.edge_strategies) es\n"
        "WHERE ng_src.topology_id = :__tid__\n"
        "  AND ng_src.edge_strategies IS NOT NULL\n"
        "  AND ng_src.edge_strategies <> '[]'\n"
        "  AND ng_src.edge_strategies <> ''"
    )
    return {
        "name": "group_edges",
        "columns": [
            "id", "topology_id", "edge_type_id", "source_id", "source_name", "source_group_id",
            "target_id", "target_name", "target_group_id",
            "edge_type_code", "mode", "ratio_k",
            "source_node_count", "target_node_count",
        ],
        "sql": sql,
    }


def _build_topology_nodes_cte() -> dict[str, Any]:
    """Unified node view combining physical nodes and virtual group nodes.

    Single CTE for all nodes.  References the `group_nodes` CTE (defined
    earlier in the same WITH clause) for virtual group-node rows.
    Add `WHERE node_category = '...'` to filter.
    """
    sql = (
        # --- Physical nodes ---
        "SELECT\n"
        "    id,\n"
        "    topology_id,\n"
        "    node_type_id,\n"
        "    name,\n"
        "    dn,\n"
        "    status,\n"
        "    group_id,\n"
        "    'physical' AS node_category,\n"
        "    NULL AS group_name,\n"
        "    NULL AS node_index,\n"
        "    1 AS group_node_count,\n"
        "    created_at,\n"
        "    updated_at\n"
        "  FROM main.nodes\n"
        "  WHERE topology_id = :__tid__\n"
        "\n"
        "UNION ALL\n"
        "\n"
        # --- Virtual group nodes (from the already-defined group_nodes CTE) ---
        "SELECT\n"
        "    id,\n"
        "    topology_id,\n"
        "    node_type_id,\n"
        "    name,\n"
        "    dn,\n"
        "    status,\n"
        "    group_id,\n"
        "    'group_node' AS node_category,\n"
        "    group_name,\n"
        "    node_index,\n"
        "    (SELECT node_count FROM main.node_groups WHERE id = group_nodes.group_id) AS group_node_count,\n"
        "    created_at,\n"
        "    updated_at\n"
        "  FROM group_nodes"
    )
    return {
        "name": "topology_nodes",
        "columns": [
            "id", "topology_id", "node_type_id", "name", "dn", "status",
            "group_id",
            "node_category", "group_name", "node_index", "group_node_count",
            "created_at", "updated_at",
        ],
        "sql": sql,
    }


def _build_topology_edges_cte() -> dict[str, Any]:
    """Unified edge view combining physical edges, group strategies, and hybrid connections.

    Single CTE for all relationship types.  Add `WHERE edge_category = '...'` to filter.
    """
    sql = (
        # --- Physical edges ---
        "SELECT\n"
        "    e.id,\n"
        "    e.topology_id,\n"
        "    et.code AS edge_type_code,\n"
        "    e.source_id,\n"
        "    s.name AS source_name,\n"
        "    e.target_id,\n"
        "    t.name AS target_name,\n"
        "    s.group_id AS source_group_id,\n"
        "    t.group_id AS target_group_id,\n"
        "    e.status,\n"
        "    NULL AS mode,\n"
        "    NULL AS ratio_k,\n"
        "    1 AS source_node_count,\n"
        "    1 AS target_node_count,\n"
        "    'physical' AS edge_category,\n"
        "    e.created_at,\n"
        "    e.updated_at\n"
        "  FROM main.edges e\n"
        "  JOIN main.edge_types et ON et.id = e.edge_type_id\n"
        "  JOIN main.nodes s ON s.id = e.source_id\n"
        "  JOIN main.nodes t ON t.id = e.target_id\n"
        "  WHERE e.topology_id = :__tid__\n"
        "\n"
        "UNION ALL\n"
        "\n"
        # --- Group-to-group strategies ---
        "SELECT\n"
        "    ng_src.id || '->' || json_extract(es.value, '$.target_group_id') AS id,\n"
        "    ng_src.topology_id,\n"
        "    json_extract(es.value, '$.edge_type_code') AS edge_type_code,\n"
        "    ng_src.id AS source_id,\n"
        "    ng_src.group_name AS source_name,\n"
        "    json_extract(es.value, '$.target_group_id') AS target_id,\n"
        "    tgt_ng.group_name AS target_name,\n"
        "    ng_src.id AS source_group_id,\n"
        "    json_extract(es.value, '$.target_group_id') AS target_group_id,\n"
        "    'strategy' AS status,\n"
        "    json_extract(es.value, '$.mode') AS mode,\n"
        "    CAST(json_extract(es.value, '$.ratio_k') AS INTEGER) AS ratio_k,\n"
        "    ng_src.node_count AS source_node_count,\n"
        "    tgt_ng.node_count AS target_node_count,\n"
        "    'group_strategy' AS edge_category,\n"
        "    ng_src.created_at,\n"
        "    ng_src.updated_at\n"
        "  FROM main.node_groups ng_src,\n"
        "       json_each(ng_src.edge_strategies) es\n"
        "  JOIN main.node_groups tgt_ng ON tgt_ng.id = json_extract(es.value, '$.target_group_id')\n"
        "  WHERE ng_src.topology_id = :__tid__\n"
        "    AND ng_src.edge_strategies IS NOT NULL\n"
        "    AND ng_src.edge_strategies <> '[]'\n"
        "    AND ng_src.edge_strategies <> ''\n"
        "\n"
        "UNION ALL\n"
        "\n"
        # --- Hybrid strategies (target is a normal node, not a group) ---
        "SELECT\n"
        "    ng_src.id || '->' || json_extract(es.value, '$.target_group_id') AS id,\n"
        "    ng_src.topology_id,\n"
        "    json_extract(es.value, '$.edge_type_code') AS edge_type_code,\n"
        "    ng_src.id AS source_id,\n"
        "    ng_src.group_name AS source_name,\n"
        "    json_extract(es.value, '$.target_group_id') AS target_id,\n"
        "    tgt_node.name AS target_name,\n"
        "    ng_src.id AS source_group_id,\n"
        "    NULL AS target_group_id,\n"
        "    'strategy' AS status,\n"
        "    json_extract(es.value, '$.mode') AS mode,\n"
        "    CAST(json_extract(es.value, '$.ratio_k') AS INTEGER) AS ratio_k,\n"
        "    ng_src.node_count AS source_node_count,\n"
        "    1 AS target_node_count,\n"
        "    'hybrid' AS edge_category,\n"
        "    ng_src.created_at,\n"
        "    ng_src.updated_at\n"
        "  FROM main.node_groups ng_src,\n"
        "       json_each(ng_src.edge_strategies) es\n"
        "  JOIN main.nodes tgt_node ON tgt_node.id = json_extract(es.value, '$.target_group_id')\n"
        "  WHERE ng_src.topology_id = :__tid__\n"
        "    AND ng_src.edge_strategies IS NOT NULL\n"
        "    AND ng_src.edge_strategies <> '[]'\n"
        "    AND ng_src.edge_strategies <> ''\n"
        "    AND json_extract(es.value, '$.target_group_id') NOT IN (\n"
        "        SELECT id FROM main.node_groups WHERE topology_id = :__tid__\n"
        "    )"
    )
    return {
        "name": "topology_edges",
        "columns": [
            "id", "topology_id", "edge_type_code",
            "source_id", "source_name", "target_id", "target_name",
            "source_group_id", "target_group_id",
            "status", "mode", "ratio_k",
            "source_node_count", "target_node_count",
            "edge_category",
            "created_at", "updated_at",
        ],
        "sql": sql,
    }


ALARM_FIXED_COLUMNS: list[str] = [
    "id", "node_id", "node_name", "node_dn",
    "alarm_index", "created_at", "updated_at",
]


def _build_alarms_cte(conn: sqlite3.Connection, topology_id: str) -> Optional[dict[str, Any]]:
    """Alarms CTE — UNION 物理节点告警 + 节点组虚拟告警。

    对使用方透明：同一张 alarms 表既能查到物理告警也能查到虚拟告警，字段列一致。
    """
    row = conn.execute(
        "SELECT alarm_schema_id FROM topologies WHERE id = ?", (topology_id,)
    ).fetchone()
    if not row or not row["alarm_schema_id"]:
        return None
    sid = row["alarm_schema_id"]

    field_rows = conn.execute(
        "SELECT field_key, mapping_target FROM alarm_schema_fields WHERE alarm_schema_id = ? "
        "ORDER BY sort_order, id",
        (sid,),
    ).fetchall()

    columns = list(ALARM_FIXED_COLUMNS)

    phys_fixed = [
        "a.id",
        "a.node_id",
        "n.name AS node_name",
        "n.dn AS node_dn",
        "a.alarm_index",
        "a.created_at",
        "a.updated_at",
    ]
    phys_pivots: list[str] = []
    virt_fixed = [
        "('gna_' || gn.id || '_' || ga.alarm_index) AS id",
        "gn.id AS node_id",
        "gn.name AS node_name",
        "gn.dn AS node_dn",
        "ga.alarm_index",
        "ga.created_at",
        "ga.updated_at",
    ]
    virt_pivots: list[str] = []

    for r in field_rows:
        key = r["field_key"]
        if not is_valid_ident(key):
            continue
        if key in columns:
            continue
        columns.append(key)

        if r["mapping_target"]:
            mt = r["mapping_target"]
            phys_pivots.append(f"MAX(CASE WHEN aa.field_key = '{key}' THEN aa.value END) AS {key}")
            if is_valid_ident(mt) and mt in {"name", "dn", "id", "status"}:
                virt_pivots.append(f"gn.{mt} AS {key}")
            else:
                virt_pivots.append(f"NULL AS {key}")
        else:
            phys_pivots.append(f"MAX(CASE WHEN aa.field_key = '{key}' THEN aa.value END) AS {key}")
            virt_pivots.append(f"MAX(CASE WHEN gaa.field_key = '{key}' THEN gaa.value END) AS {key}")

    phys_select_body = ",\n         ".join(phys_fixed + phys_pivots)
    virt_select_body = ",\n         ".join(virt_fixed + virt_pivots)

    physical_sql = (
        f"SELECT {phys_select_body}\n"
        "  FROM main.node_alarms a\n"
        "  JOIN main.nodes n ON n.id = a.node_id\n"
        "  LEFT JOIN main.node_alarm_attrs aa ON aa.alarm_id = a.id\n"
        "  WHERE n.topology_id = :__tid__\n"
        "  GROUP BY a.id"
    )
    virtual_sql = (
        f"SELECT {virt_select_body}\n"
        "  FROM group_nodes gn\n"
        "  JOIN main.node_groups g ON g.id = gn.group_id\n"
        "  JOIN main.node_group_alarms ga ON ga.node_group_id = g.id\n"
        "  LEFT JOIN main.node_group_alarm_attrs gaa ON gaa.alarm_id = ga.id\n"
        "  WHERE g.topology_id = :__tid__\n"
        "  GROUP BY gn.id, ga.id"
    )
    sql = f"{physical_sql}\nUNION ALL\n{virtual_sql}"

    return {"name": "alarms", "columns": columns, "sql": sql}


def build_generic_ctes() -> list[dict[str, Any]]:
    """Always-available CTEs: nodes / edges / children / node_groups / group_nodes / group_edges / topology_edges.
    """
    nodes_sql = (
        "SELECT id, topology_id, node_type_id, name, dn, status, group_id,\n"
        "         created_at, updated_at\n"
        "  FROM main.nodes\n"
        "  WHERE topology_id = :__tid__"
    )
    edges_sql = (
        "SELECT e.id, e.topology_id, e.edge_type_id, e.source_id, e.target_id, e.status,\n"
        "         e.created_at, e.updated_at,\n"
        "         s.name AS source_name, s.dn AS source_dn, s.group_id AS source_group_id,\n"
        "         t.name AS target_name, t.dn AS target_dn, t.group_id AS target_group_id\n"
        "  FROM main.edges e\n"
        "  JOIN main.nodes s ON s.id = e.source_id\n"
        "  JOIN main.nodes t ON t.id = e.target_id\n"
        "  WHERE e.topology_id = :__tid__"
    )
    children_sql = (
        "SELECT e.source_id AS parent_id,\n"
        "         n.id, n.name, n.dn, n.status, n.node_type_id, n.group_id\n"
        "  FROM main.edges e\n"
        "  JOIN main.edge_types et ON et.id = e.edge_type_id AND et.semantic = 'contain'\n"
        "  JOIN main.nodes n ON n.id = e.target_id\n"
        "  WHERE e.topology_id = :__tid__"
    )
    node_groups_sql = (
        "SELECT id, topology_id, node_type_id, group_name, node_count,\n"
        "         name_template, attr_strategies, edge_strategies,\n"
        "         created_at, updated_at\n"
        "  FROM main.node_groups\n"
        "  WHERE topology_id = :__tid__"
    )
    return [
        # gn_seq must come before group_nodes (which references it) and before
        # type-specific node views (which also reference group_nodes).
        _build_gn_seq_cte(),
        {
            "name": "nodes",
            "columns": [
                "id", "topology_id", "node_type_id", "name", "dn", "status",
                "group_id", "created_at", "updated_at",
            ],
            "sql": nodes_sql,
        },
        {
            "name": "edges",
            "columns": [
                "id", "topology_id", "edge_type_id", "source_id", "target_id",
                "status", "created_at", "updated_at",
                "source_name", "source_dn", "source_group_id",
                "target_name", "target_dn", "target_group_id",
            ],
            "sql": edges_sql,
        },
        {
            "name": "children",
            "columns": [
                "parent_id", "id", "name", "dn", "status", "node_type_id", "group_id",
            ],
            "sql": children_sql,
        },
        {
            "name": "node_groups",
            "columns": [
                "id", "topology_id", "node_type_id", "group_name", "node_count",
                "name_template", "attr_strategies", "edge_strategies",
                "created_at", "updated_at",
            ],
            "sql": node_groups_sql,
        },
        _build_group_nodes_cte(),
        _build_group_edges_cte(),
        _build_topology_nodes_cte(),
        _build_topology_edges_cte(),
    ]


def collect_views(
    conn: sqlite3.Connection, topology_id: str
) -> dict[str, list[dict[str, Any]]]:
    """Return node/edge/generic view metadata for a topology."""
    node_views: list[dict[str, Any]] = []
    for nt in _fetch_used_node_types(conn, topology_id):
        if not is_valid_ident(nt["code"]) or nt["code"] in _RESERVED_NAMES:
            continue
        fields = _fetch_node_fields(conn, nt["id"])
        node_views.append(build_node_type_cte(nt["code"], nt["id"], fields))

    edge_views: list[dict[str, Any]] = []
    existing_names = {v["name"] for v in node_views} | _RESERVED_NAMES
    for et in _fetch_used_edge_types(conn, topology_id):
        if not is_valid_ident(et["code"]) or et["code"] in existing_names:
            continue
        fields = _fetch_edge_fields(conn, et["id"])
        edge_views.append(build_edge_type_cte(et["code"], et["id"], fields))

    generic = build_generic_ctes()
    alarms_cte = _build_alarms_cte(conn, topology_id)
    if alarms_cte is not None:
        generic.append(alarms_cte)

    return {
        # generic first: gn_seq and group_nodes must be defined before
        # type-specific views that reference them via UNION ALL.
        "generic": generic,
        "nodeViews": node_views,
        "edgeViews": edge_views,
    }
