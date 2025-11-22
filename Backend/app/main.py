from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from backend.app.middleware.api_key_guard import ApiKeyGuard
from backend.app.config import settings

# PROMETHEUS (optional)
try:
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    PROM_ENABLED = True
except Exception:
    PROM_ENABLED = False

# ---------------------------------------------------------
# FASTAPI APP
# ---------------------------------------------------------
app = FastAPI(
    title="Email Verification SaaS",
    version="1.0.0",
    description="Full backend: email verification, bulk jobs, extractor, decision makers, billing, API keys"
)

# ---------------------------------------------------------
# MIDDLEWARE
# ---------------------------------------------------------
# API Key Middleware (required for decision maker throttling)
app.add_middleware(ApiKeyGuard)

# CORS (Frontend -> Backend communication)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # change to your domain later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# ROUTERS
# ---------------------------------------------------------
from backend.app.api.v1 import (
    auth,
    users,
    verification,
    bulk,
    extractor,
    decision_makers,
    api_keys,
    billing,
    usage,
    admin,
    webhooks,
)

# Public + Protected routes
app.include_router(auth.router, prefix="/api/v1/auth")
app.include_router(users.router, prefix="/api/v1/users")
app.include_router(verification.router, prefix="/api/v1/verify")
app.include_router(bulk.router, prefix="/api/v1/bulk")
app.include_router(extractor.router, prefix="/api/v1/extractor")
app.include_router(decision_makers.router)
app.include_router(api_keys.router)
app.include_router(billing.router)
app.include_router(usage.router)
app.include_router(admin.router)
app.include_router(webhooks.router)

# ---------------------------------------------------------
# METRICS ENDPOINT
# ---------------------------------------------------------
if PROM_ENABLED:
    @app.get("/metrics")
    def metrics():
        data = generate_latest()
        return Response(content=data, media_type=CONTENT_TYPE_LATEST)
else:
    @app.get("/metrics")
    def metrics_disabled():
        return {"status": "metrics_disabled"}

# ---------------------------------------------------------
# HEALTH CHECK
# ---------------------------------------------------------
@app.get("/")
def root():
    return {"status": "ok", "service": "backend", "version": "1.0.0"}


from backend.app.api.v1 import admin_analytics
app.include_router(admin_analytics.router)


from backend.app.api.v1 import admin_analytics
app.include_router(admin_analytics.router)

from backend.app.api.v1 import bulk_compat
app.include_router(bulk_compat.router)

from backend.app.middleware.team_context import TeamContextMiddleware
app.add_middleware(TeamContextMiddleware)


from backend.app.middleware.team_acl import TeamACL
app.add_middleware(TeamACL)

from backend.app.api.v1 import team
app.include_router(team.router)



from backend.app.api.v1 import team_billing
app.include_router(team_billing.router)





from backend.app.api.v1 import admin_team
app.include_router(admin_team.router)



from backend.app.api.v1 import admin_team
app.include_router(admin_team.router)
