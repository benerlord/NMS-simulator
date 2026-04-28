import json
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import HTTPException, Query

from app.db.connection import connect, transaction
from app.admin.schemas.token import (
    TokenCreate,
    TokenItem,
    TokenItemResponse,
    TokenListData,
    TokenListResponse,
)
from fastapi import APIRouter

router = APIRouter(prefix="/admin/api", tags=["Token"])


def _new_id() -> str:
    return f"tok_{uuid.uuid4().hex[:12]}"


def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_dt(val: Any) -> datetime:
    if isinstance(val, str):
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    return val


def _row_to_item(row) -> TokenItem:
    try:
        meta = json.loads(row["meta"]) if row["meta"] else {}
    except json.JSONDecodeError:
        meta = {}
    return TokenItem(
        token=row["token"],
        issued_at=_parse_dt(row["issued_at"]),
        expires_at=_parse_dt(row["expires_at"]),
        revoked=bool(row["revoked"]),
        issued_by_api=row["issued_by_api"],
        meta=meta if isinstance(meta, dict) else {},
    )


def _ensure_token_exists(conn, token: str):
    row = conn.execute(
        "SELECT * FROM tokens WHERE token = ?", (token,)
    ).fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail={"code": 40401, "message": "Token 不存在", "details": {"token": token}},
        )
    return row


# GET /admin/api/tokens
@router.get("/tokens", response_model=TokenListResponse)
def list_tokens(
    revoked: Optional[bool] = Query(None),
    not_expired: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
) -> dict:
    conditions = []
    params: list[Any] = []
    if revoked is not None:
        conditions.append("revoked = ?")
        params.append(1 if revoked else 0)
    if not_expired:
        conditions.append("expires_at > datetime('now')")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    offset = (page - 1) * page_size

    with connect() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM tokens {where}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT * FROM tokens {where}
            ORDER BY issued_at DESC
            LIMIT ? OFFSET ?
            """,
            params + [page_size, offset],
        ).fetchall()

    items = [_row_to_item(r) for r in rows]
    return {
        "code": 0,
        "data": {
            "items": [m.model_dump(mode="json") for m in items],
            "total": total,
            "page": page,
            "pageSize": page_size,
        },
        "message": "ok",
    }


# POST /admin/api/tokens
@router.post("/tokens", response_model=TokenItemResponse)
def create_token(body: TokenCreate) -> dict:
    issued_at = _now()
    expires_at = body.expires_at.strftime("%Y-%m-%dT%H:%M:%SZ")

    with connect() as conn:
        dup = conn.execute(
            "SELECT token FROM tokens WHERE token = ?", (body.token,)
        ).fetchone()
        if dup:
            raise HTTPException(
                status_code=409,
                detail={"code": 40901, "message": "Token 已存在", "details": {"token": body.token}},
            )

    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO tokens (token, issued_at, expires_at, revoked, issued_by_api, meta)
            VALUES (?, ?, ?, 0, ?, ?)
            """,
            (
                body.token,
                issued_at,
                expires_at,
                body.issued_by_api,
                json.dumps(body.meta or {}, ensure_ascii=False),
            ),
        )
        row = conn.execute(
            "SELECT * FROM tokens WHERE token = ?", (body.token,)
        ).fetchone()
        item = _row_to_item(row)

    return {
        "code": 0,
        "data": item.model_dump(mode="json"),
        "message": "ok",
    }


# POST /admin/api/tokens/{token}/revoke
@router.post("/tokens/{token}/revoke", response_model=TokenItemResponse)
def revoke_token(token: str) -> dict:
    with transaction() as conn:
        row = _ensure_token_exists(conn, token)
        conn.execute(
            "UPDATE tokens SET revoked = 1 WHERE token = ?",
            (token,),
        )
        row = conn.execute(
            "SELECT * FROM tokens WHERE token = ?", (token,)
        ).fetchone()
        item = _row_to_item(row)

    return {
        "code": 0,
        "data": item.model_dump(mode="json"),
        "message": "ok",
    }


# DELETE /admin/api/tokens/expired
@router.delete("/tokens/expired")
def delete_expired_tokens() -> dict:
    with transaction() as conn:
        result = conn.execute(
            "DELETE FROM tokens WHERE expires_at <= datetime('now')"
        )
    return {
        "code": 0,
        "data": {"deleted": result.rowcount},
        "message": "ok",
    }
