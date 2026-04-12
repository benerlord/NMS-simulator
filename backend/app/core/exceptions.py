"""Global exception types and FastAPI exception handlers."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger


class AppError(Exception):
    """Application-level error with structured error code."""

    def __init__(
        self,
        code: int,
        message: str,
        detail: str | None = None,
        status_code: int = 400,
    ) -> None:
        self.code = code
        self.message = message
        self.detail = detail
        self.status_code = status_code
        super().__init__(message)


# Common error codes
ERROR_INVALID_PARAMS = 10001
ERROR_NOT_FOUND = 10002
ERROR_CONFLICT = 10003
ERROR_VALIDATION = 10004
ERROR_INTERNAL = 10005


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app."""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        body: dict[str, Any] = {"code": exc.code, "message": exc.message}
        if exc.detail:
            body["detail"] = exc.detail
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "code": ERROR_VALIDATION,
                "message": "数据校验失败",
                "detail": str(exc.errors()),
            },
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={"code": ERROR_INTERNAL, "message": "服务器内部错误"},
        )
