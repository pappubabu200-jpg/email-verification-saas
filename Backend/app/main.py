from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.v1 import auth as auth_router
from backend.app.api.v1 import users as users_router

from backend.app.db import init_db

app = FastAPI(
    title="Email Verification SaaS",
    description="Backend API for email verification, extractor and decision-maker services",
    version="0.1.0",
)

# CORS (adjust origins in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router.router, prefix="/api")
app.include_router(users_router.router, prefix="/api")

@app.on_event("startup")
def on_startup():
    # Initialize DB (creates tables if not present)
    init_db()

@app.get("/", tags=["health"])
def root():
    return {"status": "ok"}
from backend.app.middleware.api_key_guard import ApiKeyGuard
app.add_middleware(ApiKeyGuard)
