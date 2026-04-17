from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.admin.routes import router as admin_router
from app.core.config import settings
from app.db.connection import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="NMS Mock", lifespan=lifespan)
app.include_router(admin_router)


def main() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
