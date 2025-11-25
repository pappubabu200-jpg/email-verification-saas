# backend/app/middleware/cors.py

"""
CORS Middleware (Final Version)

Provides a safe, configurable CORS setup compatible with:
- Development (localhost)
- Production (your domain)
- API clients (API keys via JS)
- Preflight OPTIONS requests

Environment variable:
    CORS_ALLOW_ORIGINS="http://localhost:3000,https://yourdomain.com"

If not set, defaults to:
    http://localhost:3000
    *
"""

import os
from fastapi.middleware.cors import CORSMiddleware


def add_cors(app):
    """
    Attach CORS middleware to FastAPI app.
    This should be called BEFORE all other middleware.
    """

    # Allow frontend + optional multi-domain setup
    raw_origins = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000,*")
    allow_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

    # Minimum secure defaults
    if not allow_origins:
        allow_origins = ["http://localhost:3000"]

    # Add middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],  # For API keys & Authorization
        expose_headers=["X-Request-Id", "X-RateLimit-Remaining"],
        max_age=86400,  # cache preflight
    )
