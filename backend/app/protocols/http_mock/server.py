"""HTTP Mock Server plugin — runs a standalone FastAPI app on a separate port."""

import asyncio
import json
import time
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from loguru import logger

from app.protocols.base import ProtocolPlugin
from app.protocols.http_mock.middleware import AuthMiddleware, FaultInjector
from app.protocols.http_mock.query_pipeline import QueryPipeline
from app.protocols.http_mock.response_renderer import ResponseRenderer
from app.protocols.http_mock.request_logger import RequestLogger
from app.protocols.http_mock.route_dispatcher import RouteDispatcher

from app.services.config_manager import ConfigManager
from app.services.session_manager import SessionManager
from app.dal.base import DAL
from app.dal.memory_store import MemoryStore


class HttpMockServer(ProtocolPlugin):
    """HTTP Mock Server that runs on a configurable port."""

    def __init__(
        self,
        dal: DAL,
        memory: MemoryStore,
        config_manager: ConfigManager,
        session_manager: SessionManager,
        host: str = "0.0.0.0",
        port: int = 8080,
    ):
        self._dal = dal
        self._host = host
        self._port = port
        self._running = False
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task | None = None
        self._started_at: str | None = None
        self._total_requests = 0

        # Components
        self._dispatcher = RouteDispatcher(config_manager)
        self._auth = AuthMiddleware(session_manager)
        self._fault = FaultInjector()
        self._pipeline = QueryPipeline(memory)
        self._renderer = ResponseRenderer()
        self._logger = RequestLogger(dal)
        self._session_manager = session_manager

        # Build FastAPI app
        self._app = self._build_app()

    def _build_app(self) -> FastAPI:
        app = FastAPI(title="NMS Mock Server", docs_url=None, redoc_url=None)

        @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
        async def catch_all(request: Request, path: str):
            return await self._handle_request(request, f"/{path}")

        # Login endpoint (special: issues tokens)
        @app.post("/")
        async def root_post(request: Request):
            return await self._handle_request(request, "/")

        @app.get("/")
        async def root_get(request: Request):
            return await self._handle_request(request, "/")

        return app

    async def _handle_request(self, request: Request, path: str) -> JSONResponse:
        """Process a mock server request."""
        start_time = time.time()
        method = request.method.upper()
        query_string = str(request.url.query) if request.url.query else ""
        headers = dict(request.headers)
        client_ip = request.client.host if request.client else ""

        # Read request body
        try:
            body_bytes = await request.body()
            request_body = body_bytes.decode("utf-8") if body_bytes else None
        except Exception:
            request_body = None

        self._total_requests += 1

        # Check for login request (special token issuance)
        config = self._dispatcher.match(method, path)
        if not config:
            # Check if this is a login-like request (POST with credentials)
            # Try to handle as token issuance
            if method == "POST" and request_body:
                token_response = await self._try_login(request_body, headers)
                if token_response:
                    duration = int((time.time() - start_time) * 1000)
                    resp_str = json.dumps(token_response, ensure_ascii=False)
                    await self._logger.log(
                        method=method, path=path, query_string=query_string,
                        headers=headers, request_body=request_body,
                        status_code=200, response_body=resp_str,
                        duration=duration, client_ip=client_ip,
                    )
                    return JSONResponse(content=token_response)

            duration = int((time.time() - start_time) * 1000)
            await self._logger.log(
                method=method, path=path, query_string=query_string,
                headers=headers, request_body=request_body,
                status_code=404, duration=duration, client_ip=client_ip,
                error="No matching route",
            )
            return JSONResponse(status_code=404, content={"error": "Not found"})

        config_id = config.get("id")
        config_name = config.get("name")

        # Auth check
        auth_ok, auth_status, auth_error = self._auth.check(config, headers)
        if not auth_ok:
            duration = int((time.time() - start_time) * 1000)
            await self._logger.log(
                method=method, path=path, query_string=query_string,
                headers=headers, request_body=request_body,
                status_code=auth_status, duration=duration,
                config_id=config_id, config_name=config_name,
                client_ip=client_ip, error=auth_error,
            )
            return JSONResponse(status_code=auth_status, content={"error": auth_error})

        # Fault injection
        should_error, error_status = await self._fault.apply(config)
        if should_error:
            duration = int((time.time() - start_time) * 1000)
            error_body = {"error": "Simulated error", "status": error_status}
            resp_str = json.dumps(error_body, ensure_ascii=False)
            await self._logger.log(
                method=method, path=path, query_string=query_string,
                headers=headers, request_body=request_body,
                status_code=error_status, response_body=resp_str,
                duration=duration, config_id=config_id, config_name=config_name,
                client_ip=client_ip, error="Fault injection",
            )
            return JSONResponse(status_code=error_status, content=error_body)

        # Build params from query string + body
        params = dict(request.query_params)
        if request_body:
            try:
                body_json = json.loads(request_body)
                if isinstance(body_json, dict):
                    params.update(body_json)
            except json.JSONDecodeError:
                pass

        # Execute query pipeline
        try:
            query_result = await self._pipeline.execute(config, params)
        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            await self._logger.log(
                method=method, path=path, query_string=query_string,
                headers=headers, request_body=request_body,
                status_code=500, duration=duration,
                config_id=config_id, config_name=config_name,
                client_ip=client_ip, error=str(e),
            )
            return JSONResponse(status_code=500, content={"error": str(e)})

        # Render response
        rendered, content_type = self._renderer.render(config, query_result)
        duration = int((time.time() - start_time) * 1000)
        resp_str = json.dumps(rendered, ensure_ascii=False) if isinstance(rendered, (dict, list)) else str(rendered)

        await self._logger.log(
            method=method, path=path, query_string=query_string,
            headers=headers, request_body=request_body,
            status_code=200, response_body=resp_str,
            duration=duration, config_id=config_id, config_name=config_name,
            client_ip=client_ip,
        )

        return JSONResponse(
            content=rendered,
            headers={"Content-Type": content_type},
        )

    async def _try_login(self, body: str, headers: dict) -> dict | None:
        """Try to handle request as a login attempt."""
        try:
            data = json.loads(body)
            username = data.get("userName") or data.get("username")
            password = data.get("password")
            if username and password:
                token = self._session_manager.authenticate(username, password)
                if token:
                    return {"accessSession": token, "roaRand": "", "expires": 1800}
        except Exception:
            pass
        return None

    # ---- ProtocolPlugin interface ----

    async def start(self) -> None:
        if self._running:
            return
        await self._dispatcher.load_all()
        config = uvicorn.Config(
            app=self._app, host=self._host, port=self._port,
            log_level="warning",
        )
        self._server = uvicorn.Server(config)
        self._task = asyncio.create_task(self._server.serve())
        self._running = True
        self._started_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        self._total_requests = 0
        logger.info(f"HttpMockServer: started on {self._host}:{self._port}")

    async def stop(self) -> None:
        if not self._running:
            return
        self._dispatcher.unload()
        if self._server:
            self._server.should_exit = True
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            self._task = None
        self._server = None
        self._running = False
        self._started_at = None
        logger.info("HttpMockServer: stopped")

    async def restart(self) -> None:
        await self.stop()
        await self.start()

    def status(self) -> dict:
        return {
            "displayName": "HTTP Mock Server",
            "status": "running" if self._running else "stopped",
            "port": self._port,
            "startedAt": self._started_at,
            "stats": {
                "totalRequests": self._total_requests,
                "activeRoutes": len(self._dispatcher.list_routes()),
            } if self._running else None,
        }

    def health_check(self) -> dict:
        return {
            "healthy": self._running,
            "uptime": None,
            "lastError": None,
            "checks": {
                "port_available": self._running,
                "memory_ok": True,
            },
        }

    async def reload_config(self) -> None:
        if self._running:
            await self._dispatcher.load_all()

    # ---- Accessors ----

    @property
    def dispatcher(self) -> RouteDispatcher:
        return self._dispatcher

    @property
    def request_logger(self) -> RequestLogger:
        return self._logger

    @property
    def pipeline(self) -> QueryPipeline:
        return self._pipeline
