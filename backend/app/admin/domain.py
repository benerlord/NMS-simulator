import uuid

from fastapi import APIRouter, HTTPException

from app.db.connection import connect, transaction
from app.admin.schemas.domain import DomainCreate, DomainUpdate, DomainItem

router = APIRouter(prefix="/admin/api", tags=["域"])


def _new_id() -> str:
    return f"dom_{uuid.uuid4().hex[:12]}"


@router.get("/domains")
def list_domains() -> dict:
    with connect() as conn:
        rows = conn.execute("""
            SELECT d.*, COUNT(t.id) AS topology_count
            FROM domains d
            LEFT JOIN topologies t ON t.domain_id = d.id
            GROUP BY d.id
            ORDER BY d.name
        """).fetchall()
        items = [
            DomainItem(
                id=r["id"],
                name=r["name"],
                description=r["description"],
                topology_count=r["topology_count"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            ).model_dump(mode="json", by_alias=True)
            for r in rows
        ]
    return {"code": 0, "data": {"items": items, "total": len(items)}, "message": "ok"}


@router.post("/domains")
def create_domain(data: DomainCreate) -> dict:
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM domains WHERE name = ?", (data.name,)
        ).fetchone()
        if existing:
            raise HTTPException(
                status_code=409,
                detail={"code": 40301, "message": "域名称已存在"},
            )
        dom_id = _new_id()
        conn.execute(
            "INSERT INTO domains (id, name, description) VALUES (?, ?, ?)",
            (dom_id, data.name, data.description),
        )
    return {"code": 0, "data": {"id": dom_id}, "message": "ok"}


@router.put("/domains/{dom_id}")
def update_domain(dom_id: str, data: DomainUpdate) -> dict:
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM domains WHERE id = ?", (dom_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(
                status_code=404,
                detail={"code": 40302, "message": "域不存在"},
            )
        if data.name is not None:
            dup = conn.execute(
                "SELECT id FROM domains WHERE name = ? AND id != ?",
                (data.name, dom_id),
            ).fetchone()
            if dup:
                raise HTTPException(
                    status_code=409,
                    detail={"code": 40301, "message": "域名称已存在"},
                )
        updates, params = [], []
        if data.name is not None:
            updates.append("name = ?")
            params.append(data.name)
        if data.description is not None:
            updates.append("description = ?")
            params.append(data.description)
        if updates:
            updates.append("updated_at = datetime('now')")
            set_clause = ", ".join(updates)
            params.append(dom_id)
            conn.execute(f"UPDATE domains SET {set_clause} WHERE id = ?", params)
    return {"code": 0, "data": {"id": dom_id}, "message": "ok"}


@router.delete("/domains/{dom_id}")
def delete_domain(dom_id: str) -> dict:
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM domains WHERE id = ?", (dom_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(
                status_code=404,
                detail={"code": 40302, "message": "域不存在"},
            )
        conn.execute(
            "UPDATE topologies SET domain_id = NULL WHERE domain_id = ?",
            (dom_id,),
        )
        conn.execute("DELETE FROM domains WHERE id = ?", (dom_id,))
    return {"code": 0, "data": {"id": dom_id}, "message": "ok"}
