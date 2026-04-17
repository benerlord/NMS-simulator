from fastapi import APIRouter

router = APIRouter(prefix="/admin/api")


@router.get("/health")
def health() -> dict:
    return {"code": 0, "data": {"status": "ok"}, "message": "ok"}
