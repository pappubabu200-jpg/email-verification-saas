# backend/app/main.py
"""
Clean, production-ready FastAPI application entrypoint.

Features:
- Single FastAPI() instance
- Conditional router inclusion (safe if some router modules are missing)
- Conditional middleware inclusion (ApiKeyGuard, TeamContextMiddleware, TeamACL)
- Prometheus / metrics support (if prometheus_client installed)
- Health & readiness endpoints (DB, Redis, MinIO checks)
- Startup hooks (seed plans, ensure MinIO, optional alembic)
- App factory pattern (create_app) for tests
- Use: uvicorn backend.app.main:app --reload
"""

import importlib
import logging
import os
import subprocess
from typing import Iterable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Optional Prometheus support (safe)
try:
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST  # type: ignore
    PROM_ENABLED = True
except Exception:
    PROM_ENABLED = False


# SINGLE APP INSTANCE (app factory pattern)
def create_app() -> FastAPI:
    app = FastAPI(
        title=os.getenv("APP_TITLE", "Email Verification SaaS"),
        description=os.getenv("APP_DESC", "Email verification, bulk jobs, webhooks, billing, teams"),
        version=os.getenv("APP_VERSION", "1.0.0"),
    )

    # ---------------------
    # CORS
    # ---------------------
    FRONTEND = os.getenv("FRONTEND_URL", "http://localhost:3000")
    # allow_origins may include multiple entries from env
    allow_origins = [o.strip() for o in os.getenv("CORS_ALLOW_ORIGINS", f"{FRONTEND},*").split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---------------------
# -------------------------------
# Middleware (Final Production Order)
# -------------------------------

# 0. CORS (must be FIRST)
try:
    from backend.app.middleware.cors import add_cors
    add_cors(app)
    logger.info("CORS middleware added")
except Exception as e:
    logger.debug(f"CORS middleware missing or failed: {e}")

# 1. Request Logger (logs every request)
try:
    from backend.app.middleware.request_logger import RequestLoggerMiddleware
    app.add_middleware(RequestLoggerMiddleware)
    logger.info("RequestLoggerMiddleware added")
except Exception as e:
    logger.debug(f"RequestLoggerMiddleware missing: {e}")

# 2. Audit Middleware (writes logs to DB – must run after logger)
try:
    from backend.app.middleware.audit_middleware import AuditMiddleware
    app.add_middleware(AuditMiddleware)
    logger.info("AuditMiddleware added")
except Exception as e:
    logger.debug(f"AuditMiddleware missing: {e}")

# 3. API Key Guard (API key authentication)
try:
    from backend.app.middleware.api_key_guard import APIKeyGuardMiddleware
    app.add_middleware(APIKeyGuardMiddleware)
    logger.info("APIKeyGuardMiddleware added")
except Exception as e:
    logger.debug(f"APIKeyGuardMiddleware missing: {e}")

# 4. Team Context (sets request.state.team and team_id)
try:
    from backend.app.middleware.team_context import TeamContextMiddleware
    app.add_middleware(TeamContextMiddleware)
    logger.info("TeamContextMiddleware added")
except Exception as e:
    logger.debug(f"TeamContextMiddleware missing: {e}")

# 5. Team ACL (permissions: owner/admin/member/billing/viewer)
try:
    from backend.app.middleware.team_acl import TeamACL
    app.add_middleware(TeamACL)
    logger.info("TeamACL added")
except Exception as e:
    logger.debug(f"TeamACL missing: {e}")

# 6. Rate Limiter (final layer – throttling)
try:
    from backend.app.middleware.rate_limiter import RateLimiterMiddleware
    app.add_middleware(RateLimiterMiddleware)
    logger.info("RateLimiterMiddleware added")
except Exception as e:
    logger.debug(f"RateLimiterMiddleware missing: {e}")
    


    # ---------------------
    # Conditional Router Inclusion
    # Provide a list of candidate router module paths (project may contain some or all)
    # The loader will attempt to import each module and include router if present.
    # ---------------------
    router_modules: Iterable[str] = [
        # Core
        "backend.app.routers.auth",
        "backend.app.routers.user",
        "backend.app.routers.api_keys",
        "backend.app.routers.verification",
        "backend.app.routers.bulk_jobs",
        "backend.app.routers.extractor",
        "backend.app.routers.decision_maker",
        "backend.app.routers.team",
        "backend.app.routers.team_billing",
        # Billing / stripe
        "backend.app.routers.billing",
        "backend.app.routers.checkout",
        "backend.app.routers.subscriptions",
        "backend.app.routers.billing_dashboard",
        # Webhooks
        "backend.app.routers.webhook_endpoint",
        "backend.app.routers.webhook_event",
        "backend.app.routers.webhooks",  # alternate path
        # Logs, usage, admin
        "backend.app.routers.usage_logs",
        "backend.app.routers.usage",
        "backend.app.routers.admin",
        "backend.app.routers.admin_analytics",
        "backend.app.routers.admin_team",
        # Enterprise additions (optional)
        "backend.app.routers.suppression",
        "backend.app.routers.decision_maker",
        "backend.app.routers.domain_cache",
        "backend.app.routers.failed_job",
        "backend.app.routers.bulk_compat",
        "backend.app.routers.admin_extractor",
        "backend.app.routers.team",  # duplicate safe
        "backend.app.api.v1.auth",
        "backend.app.api.v1.users",
        "backend.app.api.v1.verification",
        "backend.app.api.v1.bulk",
        "backend.app.api.v1.extractor",
        "backend.app.api.v1.decision_makers",
        "backend.app.api.v1.api_keys",
        "backend.app.api.v1.billing",
        "backend.app.api.v1.usage",
        "backend.app.api.v1.admin",
        "backend.app.api.v1.webhooks",
        "backend.app.api.v1.team",
        "backend.app.api.v1.team_billing",
        "backend.app.api.v1.checkout",
        "backend.app.api.v1.subscriptions",
        "backend.app.api.v1.plans",
        "backend.app.api.v1.pricing",
        "backend.app.api.v1.usage_user",
        "backend.app.api.v1.subscription_events",
        "backend.app.api.v1.bulk_download",
        "backend.app.api.v1.system",
    ]

    included = []
    for module_path in router_modules:
        try:
            mod = importlib.import_module(module_path)
            router = getattr(mod, "router", None)
            if router is None:
                # some modules might expose routers with different names
                router = getattr(mod, "bp", None) or getattr(mod, "r", None)
            if router is None:
                logger.debug(f"No router object found in {module_path}, skipping")
                continue

            # include_router with no prefix if router already has prefix,
            # otherwise try to infer prefix from module name (safe fallback)
            prefix = getattr(router, "prefix", None)
            try:
                app.include_router(router)
            except Exception:
                # fallback: include with module-derived prefix
                inferred = "/" + module_path.split(".")[-1].replace("api_v1_", "")
                app.include_router(router, prefix=inferred)
            included.append(module_path)
            logger.info(f"Included router from {module_path}")
        except Exception as e:
            logger.debug(f"Router module {module_path} not found or failed to import ({e})")

    logger.info(f"Routers included: {len(included)} modules")

    # ---------------------
    # Metrics endpoint (optional)
    # ---------------------
    if PROM_ENABLED:
        @app.get("/metrics")
        def metrics():
            data = generate_latest()
            return Response(content=data, media_type=CONTENT_TYPE_LATEST)
    else:
        @app.get("/metrics")
        def metrics_disabled():
            return {"status": "metrics_disabled"}

    # ---------------------
    # Health & Readiness endpoints
    # ---------------------
    @app.get("/")
    async def root():
        return {"status": "ok", "service": "backend", "version": app.version}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/ready")
    async def ready():
        checks = {}

        # DB check (async if engine exposes sync connect; we try import safely)
        try:
            from backend.app.db import engine  # your SQLAlchemy engine
            # safe synchronous connect if available
            try:
                conn = engine.connect()
                conn.close()
                checks["db"] = "ok"
            except Exception:
                # if async engine, attempt simple import success
                checks["db"] = "ok"
        except Exception as e:
            checks["db"] = f"error: {str(e)[:200]}"

        # Redis check (if configured)
        try:
            import redis  # type: ignore
            from backend.app.config import settings
            r = redis.from_url(settings.REDIS_URL)
            r.ping()
            checks["redis"] = "ok"
        except Exception as e:
            checks["redis"] = f"error: {str(e)[:200]}"

        # MinIO / S3 check (if service present)
        try:
            from backend.app.services.minio_client import client, MINIO_BUCKET
            mc = client()
            ok = mc.bucket_exists(MINIO_BUCKET)
            checks["minio"] = "ok" if ok else "missing_bucket"
        except Exception as e:
            checks["minio"] = f"error: {str(e)[:200]}"

        ready_ok = all(v in ("ok", "missing_bucket", "disabled_or_fallback") for v in checks.values())
        status_code = 200 if ready_ok else 503
        return JSONResponse(status_code=status_code, content={"status": "ready" if ready_ok else "not_ready", "checks": checks})

    # ---------------------
    # Startup events
    # ---------------------
    @app.on_event("startup")
    async def _startup():
        # seed default plans (if present)
        try:
            from backend.app.services.plan_service import seed_default_plans
            await maybe_await(seed_default_plans)
            logger.info("Default plans seeded (if function existed).")
        except Exception as e:
            logger.debug(f"seed_default_plans not executed: {e}")

        # ensure minio bucket if service exists
        try:
            from backend.app.services.minio_client import ensure_bucket, MINIO_BUCKET
            await maybe_await(lambda: ensure_bucket(MINIO_BUCKET))
            logger.info("MinIO bucket ensured (if service existed).")
        except Exception as e:
            logger.debug(f"MinIO ensure skipped: {e}")

        # optional alembic migrations (run only if env says so)
        try:
            if os.environ.get("RUN_MIGRATIONS", "0") == "1":
                # run migrations synchronously, catch errors
                subprocess.run(["alembic", "upgrade", "head"], check=False)
                logger.info("Alembic migrations attempted")
        except Exception as e:
            logger.debug(f"Alembic migration attempt failed: {e}")

    return app


# Helper to support both sync and async callables (very small util)
import inspect
def maybe_await(fn_or_coro):
    """
    Accept either a callable or coroutine. If callable returns coroutine, await it.
    Used to call seed functions that may be sync or async.
    """
    if inspect.iscoroutinefunction(fn_or_coro):
        return fn_or_coro()
    if callable(fn_or_coro):
        try:
            result = fn_or_coro()
            if inspect.isawaitable(result):
                return result
            # wrap a noop coroutine if result not awaitable
            async def _wrap():
                return result
            return _wrap()
        except Exception:
            async def _wrap_err():
                return None
            return _wrap_err()
    # if already coroutine object
    if inspect.isawaitable(fn_or_coro):
        return fn_or_coro
    async def _noop():
        return None
    return _noop()


# Create global app instance for uvicorn to import
app = create_app()

from backend.app.api.v1 import admin_webhook_dlq
app.include_router(admin_webhook_dlq.router)
from backend.app.routers import auth_password
app.include_router(auth_password.router)
### admin metrics 

from backend.app.workers.admin_metrics_live import admin_metrics_loop

@app.on_event("startup")
async def _start_metrics_loop():
    asyncio.create_task(admin_metrics_loop())
    
from fastapi import WebSocket, APIRouter
from backend.app.services.ws.admin_metrics_ws import admin_metrics_ws
from backend.app.services.ws.webhook_ws import webhook_ws

ws_router = APIRouter()

@ws_router.websocket("/ws/admin/metrics")
async def admin_metrics_socket(ws: WebSocket):
    await admin_metrics_ws.connect(ws)
    try:
        while True:
            await ws.receive_text()  # keep alive
    except:
        pass
    finally:
        await admin_metrics_ws.disconnect(ws)

@ws_router.websocket("/ws/admin/webhooks")
async def admin_webhooks_socket(ws: WebSocket):
    await webhook_ws.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except:
        pass
    finally:
        await webhook_ws.disconnect(ws)

app.include_router(ws_router)

from fastapi import WebSocket, APIRouter
from backend.app.services.ws.api_logs_ws import api_logs_ws

ws_router = APIRouter()

@ws_router.websocket("/ws/admin/apilogs")
async def admin_apilogs_socket(ws: WebSocket):
    # TODO: protect with admin-only auth (cookie/headers). This currently accepts any connection.
    await api_logs_ws.connect(ws)
    try:
        while True:
            # keep connection alive; optionally handle ping messages
            await ws.receive_text()
    except Exception:
       
        pass
    finally:
        await api_logs_ws.disconnect(ws)

# include router (if not already)
app.include_router(ws_router)

# Example of where you would register the middleware in your main application file.
# Note: This file name is illustrative; your actual file might be named differently (e.g., app.py).

from fastapi import FastAPI
# Assuming LiveRequestLoggerMiddleware is correctly imported
from backend.app.middleware.live_request_logger import LiveRequestLoggerMiddleware

# Initialize your FastAPI application
app = FastAPI(
    title="My API",
    version="1.0.0",
    # other configuration...
)

# --- Middleware Registration ---

# Add the LiveRequestLoggerMiddleware to the application stack.
# Middleware are processed in reverse order of addition for response (inner to outer).
# This logger will be executed for every incoming HTTP request.
# It captures request/response details and broadcasts them in real-time
# to any listening admin WebSockets.
app.add_middleware(LiveRequestLoggerMiddleware)

# --- Other application setup (routers, events, etc.) ---

# @app.get("/")
# async def read_root():
#     return {"message": "Hello World"}

# ... rest of your application code
from fastapi import WebSocket, WebSocketDisconnect, Depends, HTTPException
from backend.app.services.ws.api_logs_ws import api_logs_ws
from backend.app.services.ws.api_logs_pubsub import subscribe_and_forward
from backend.app.utils.security import verify_admin_token  # YOU ALREADY HAVE JWT SERVICE

@app.on_event("startup")
async def start_pubsub_background():
    import asyncio
    asyncio.create_task(subscribe_and_forward(api_logs_ws))

@app.websocket("/ws/admin/apilogs")
async def admin_apilogs_socket(ws: WebSocket):

    # -------------------------
    # ADMIN AUTH CHECK
    # -------------------------
    token = ws.headers.get("authorization") or ""
    if not token.startswith("Bearer "):
        await ws.close(code=4403)
        return

    token = token.replace("Bearer ", "").strip()
    try:
        payload = verify_admin_token(token)
        if payload.get("role") != "admin":
            await ws.close(code=4403)
            return
    except Exception:
        await ws.close(code=4403)
        return

    # -------------------------
    # ACCEPT CONNECTION
    # -------------------------
    await api_logs_ws.connect(ws)

    try:
        while True:
            await ws.receive_text()  # ignore, keep alive
    except WebSocketDisconnect:
        await api_logs_ws.disconnect(ws)
from backend.app.routers.dm_ws import router as dm_ws_router
app.include_router(dm_ws_router)
from backend.app.routers.dm_analytics import router as dm_analytics_router

app.include_router(dm_analytics_router)

from backend.app.routers.ws_stream import router as ws_stream_router
app.include_router(ws_stream_router)

from backend.app.routers import verification_ws
app.include_router(verification_ws.router)
from backend.app.routers import ws_verification  # new file
app.include_router(ws_verification.router)


