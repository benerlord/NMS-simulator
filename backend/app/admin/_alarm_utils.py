"""Common helpers for alarm attr value resolution.

Precedence: user-provided value > mapping_target > default_value > NULL.
"""

NODE_SYSTEM_FIELDS = {"name", "dn", "id", "status", "group_id"}


def resolve_mapping(conn, node_id, mapping_target):
    """Look up the value for a mapping_target on a node.

    System fields are read from nodes.<column>. Custom fields are read from
    node_attrs by field_key. Returns None if node or field is missing.

    mapping_target is assumed to be a validated identifier (alphanumeric + underscore,
    leading letter or underscore) — enforced by Pydantic at the schema layer.
    For system fields, the value is additionally gated by NODE_SYSTEM_FIELDS set
    membership before any SQL interpolation, so column-name interpolation is safe.
    """
    if mapping_target in NODE_SYSTEM_FIELDS:
        row = conn.execute(
            f"SELECT {mapping_target} AS v FROM nodes WHERE id = ?", (node_id,)
        ).fetchone()
        return row["v"] if row else None
    row = conn.execute(
        "SELECT value FROM node_attrs WHERE node_id = ? AND field_key = ?",
        (node_id, mapping_target),
    ).fetchone()
    return row["value"] if row else None


def build_alarm_attrs(conn, node_id, fields, user_provided=None):
    """Resolve attr values for an alarm using the precedence:
    user_provided > mapping_target > default_value > NULL (skip).

    fields: iterable of dict-like with keys (field_key, mapping_target, default_value).
    user_provided: optional dict[field_key -> value]. None values are treated as
                   "not provided" so they fall through to mapping/default.
    Returns: dict[field_key -> value], omitting fields whose final value is None.
    """
    user_provided = user_provided or {}
    result = {}
    for f in fields:
        key = f["field_key"]
        # 1. user explicit value (non-None)
        if key in user_provided and user_provided[key] is not None:
            result[key] = user_provided[key]
            continue
        # 2. mapping_target
        mapping = f["mapping_target"]
        if mapping:
            val = resolve_mapping(conn, node_id, mapping)
            if val is not None:
                result[key] = val
                continue
        # 3. default_value
        if f["default_value"] is not None:
            result[key] = f["default_value"]
        # 4. else skip (no entry in result)
    return result
