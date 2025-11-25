# backend/app/middleware/request_logger.py
import logging
import time
import re
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger("request")
# configure a sensible default handler if the app hasn't configured logging yet
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


_EMAIL_RE = re.compile(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)")
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _redact_pii(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    # redact email-like tokens
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    # optional: redact IPv4-looking tokens
    text = _IP_RE.sub("[REDACTED_IP]", text)
    return text


def _client_ip_from_request(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    """
    Structured request logger.

    Adds:
    - request timing
    - client_ip
    - request_id propagation (reads X-Request-Id or request.state.request_id)
    - redacts simple PII (emails, ipv4) from path/query when logging
    """

    async def dispatch(self, request: Request, call_next):
        start = time.time()

        # prefer request.state.request_id (set by request_id middleware) or header
        request_id = getattr(request.state, "request_id", None) or request.headers.get("X-Request-Id")
        # gather lightweight context for logs
        context = {
            "request_id": request_id,
            "method": request.method,
            "path": _redact_pii(request.url.path),
            "query": _redact_pii(request.url.query) or None,
            "client_ip": _client_ip_from_request(request),
            "user_id": None,
            "team_id": None,
            "api_key_id": None,
        }

        # best-effort pull user/team/api_key metadata (if earlier middleware attached them)
        try:
            if hasattr(request.state, "user") and getattr(request.state.user, "id", None):
                context["user_id"] = getattr(request.state.user, "id")
        except Exception:
            pass
        try:
            if getattr(request.state, "api_user_id", None):
                context["user_id"] = getattr(request.state, "api_user_id")
        except Exception:
            pass
        try:
            if getattr(request.state, "team", None) and getattr(request.state.team, "id", None):
                context["team_id"] = getattr(request.state.team, "id")
            elif getattr(request.state, "team_id", None):
                context["team_id"] = getattr(request.state, "team_id")
        except Exception:
            pass
        try:
            if getattr(request.state, "api_key_row", None) and getattr(request.state.api_key_row, "id", None):
                context["api_key_id"] = getattr(request.state.api_key_row, "id")
        except Exception:
            pass

        try:
            response: Response = await call_next(request)
        except Exception as exc:
            duration_ms = int((time.time() - start) * 1000)
            # log the exception with structured context
            logger.exception(
                "request_error",
                extra={
                    **context,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                    "error": str(exc)[:1000],
                },
            )
            raise

        duration_ms = int((time.time() - start) * 1000)
        status_code = getattr(response, "status_code", 0)

        # ensure X-Request-Id is present in response headers
        try:
            if request_id:
                response.headers.setdefault("X-Request-Id", request_id)
        except Exception:
            pass

        # final structured log
        try:
            logger.info(
                "request",
                extra={
                    **context,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
        except Exception:
            # never raise from the logging middleware
            try:
                logger.info(f"{request.method} {context['path']} {status_code} {duration_ms}ms req_id={request_id}")
            except Exception:
                pass

        return response
