"""CORS + security-header setup, kept out of main.py so it stays a thin
wiring file (see CLAUDE.md's layout notes).
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings


def setup_cors(app: FastAPI) -> None:
    """Allowed origins come entirely from ALLOWED_ORIGINS (comma-separated)
    — no hardcoded localhost fallback. Local dev must list its own origin
    (e.g. http://localhost:5173) in .env just like prod lists its Vercel
    domain; same "no silent default" rule as DATABASE_URL. Methods/headers
    are the actual set this API uses, not a wildcard — allow_credentials=True
    plus a wildcard for either is a common CORS-hardening smell even where
    the spec technically permits it."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Baseline security headers on every response. No Content-Security-Policy
    here on purpose — this is a JSON API, not an HTML app, and a strict CSP
    would just break /docs' Swagger UI (which loads its own JS/CSS from a
    CDN). HSTS only goes out in production — sending it over plain HTTP in
    local dev is meaningless and can make http://localhost testing weird in
    some browsers."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if settings.ENVIRONMENT.lower() == "production":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


def setup_security_headers(app: FastAPI) -> None:
    app.add_middleware(SecurityHeadersMiddleware)
