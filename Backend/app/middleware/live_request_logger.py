
# Backend/app/middleware/live_request_logger.py
import time
import asyncio
import logging
from typing import Callable, Awaitable
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.requests import Request
from starlette.responses import Response
from backend.app.services.ws.api_logs_ws import api_logs_ws

logger = logging.getLogger(__name__)

class LiveRequestLoggerMiddleware:
    """
    ASGI middleware to record request/response metrics and broadcast to admin WS.
    Best-effort: broadcasting errors are swallowed to avoid impacting the request.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            # pass-through non-http
            await self.app(scope, receive, send)
            return

        start = time.time()
        request = Request(scope, receive=receive)

        # call the inner app and capture response
        response = None
        try:
            # run downstream app
            responder = self.app
            # create a helper to capture status code after response finalizes
            sent_status = {"code": None}

            async def send_and_capture(message):
                if message.get("type") == "http.response.start":
                    headers = message.get("headers", [])
                    status = message.get("status")
                    sent_status["code"] = int(status)
                await send(message)

            await responder(scope, receive, send_and_capture)  # type: ignore
            status_code = sent_status["code"] or 200

        except Exception as exc:
            # On exception, starlette/fastapi will convert to 500; capture that
            logger.exception("Unhandled exception in request pipeline: %s", exc)
            status_code = 500
            raise
        finally:
            # compute metadata and broadcast (non-blocking)
            took = time.time() - start
            try:
                # build log event
                client_host = None
                try:
                    client_host = request.client.host if request.client else None
                except Exception:
                    client_host = None

                # Try to extract user or api key info from request.state or headers
                user_id = getattr(request.state, "user_id", None)
                api_key = None
                try:
                    api_key = request.headers.get("x-api-key") or request.headers.get("authorization")
                except Exception:
                    api_key = None

                payload = {
                    "type": "api_log",
                    "ts": time.time(),
                    "ts_iso": request.scope.get("time") if request.scope.get("time") else None,
                    "method": request.method,
                    "path": request.url.path,
                    "query": str(request.url.query),
                    "status": int(status_code),
                    "duration_ms": int(took * 1000),
                    "client_ip": client_host,
                    "user_id": str(user_id) if user_id else None,
                    "api_key_hint": (api_key[:8] + "...") if api_key else None,
                }

                # fire-and-forget broadcast
                asyncio.create_task(self._safe_broadcast(payload))
            except Exception:
                logger.exception("Failed to schedule API log broadcast")

    async def _safe_broadcast(self, payload):
        try:
            await api_logs_ws.broadcast(payload)
        except Exception:
            # swallow — broadcasting should not block requests
            logger.debug("api_logs_ws.broadcast failed (ignored)")
