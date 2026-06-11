"""Endpoint to enumerate available node fields for alarm field mapping UI."""

from fastapi import APIRouter

from app.db.connection import connect
from app.admin._alarm_utils import NODE_SYSTEM_FIELDS

router = APIRouter(prefix="/admin/api", tags=["节点字段"])


@router.get("/node-fields/available")
def list_available_node_fields() -> dict:
    with connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT field_key FROM node_type_fields ORDER BY field_key"
        ).fetchall()
        custom = [r["field_key"] for r in rows]
    return {
        "code": 0,
        "data": {
            "systemFields": sorted(NODE_SYSTEM_FIELDS),
            "customFields": custom,
        },
        "message": "ok",
    }
