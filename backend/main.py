from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.middleware import setup_cors, setup_security_headers, setup_trusted_hosts
from app.core.rate_limit import limiter
from app.db import SessionLocal
from app.models import seed_default_categories

from app.api.routers import (
    profile, accounts, categories, upload, transactions, rules,
    chat, budget, projects, dashboard, fixed_expenses, insights, auth,
    credit_offsets,
)

# Schema is managed exclusively by Alembic (see alembic/versions/) — run
# `alembic upgrade head` before starting the app. No create_all here: that would
# let a table/column exist without ever going through a reviewed migration,
# silently diverging from what `alembic upgrade head` produces elsewhere.

@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        seed_default_categories(db)
    finally:
        db.close()
    yield

app = FastAPI(
    title="FinanceAI API",
    version="1.0.0",
    description="xspend backend: statement upload, categorized spending, cash-flow insights, savings projects.",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "auth", "description": "Signup, email verification, login, token refresh, logout."},
    ],
)

def _is_auth_path(request: Request) -> bool:
    return request.url.path.startswith("/auth")


def _validation_message(exc: RequestValidationError) -> str:
    msgs = []
    for err in exc.errors():
        msg = err.get("msg", "")
        if msg.startswith("Value error, "):
            msg = msg[len("Value error, "):]
        if msg:
            msgs.append(msg)
    return ". ".join(msgs) if msgs else "Invalid request."


@app.exception_handler(HTTPException)
async def _auth_scoped_http_exception_handler(request: Request, exc: HTTPException):
    # Auth responses use a {status, message, data} envelope; every other
    # router keeps FastAPI's default {"detail": ...} body.
    if not _is_auth_path(request):
        return await http_exception_handler(request, exc)
    message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "message": message, "data": None},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def _auth_scoped_validation_exception_handler(request: Request, exc: RequestValidationError):
    if not _is_auth_path(request):
        return await request_validation_exception_handler(request, exc)
    return JSONResponse(
        status_code=422,
        content={"status": "error", "message": _validation_message(exc), "data": None},
    )


@app.exception_handler(RateLimitExceeded)
async def _auth_scoped_rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    if not _is_auth_path(request):
        return _rate_limit_exceeded_handler(request, exc)
    response = JSONResponse(
        status_code=429,
        content={"status": "error", "message": f"Rate limit exceeded: {exc.detail}", "data": None},
    )
    return request.app.state.limiter._inject_headers(response, request.state.view_rate_limit)


app.state.limiter = limiter

# Middleware order matters: Starlette runs the LAST-added middleware
# outermost, so CORS goes after security headers/rate limiting — that way
# even a 429 (rate limit) or 5xx still carries CORS headers, instead of the
# browser treating it as an opaque network error the frontend JS can't read.
# Trusted-host checking goes last of all (outermost/first-checked): a request
# with a forged Host header shouldn't get as far as CORS/rate-limit handling.
setup_security_headers(app)
app.add_middleware(SlowAPIMiddleware)
setup_cors(app)
setup_trusted_hosts(app)

app.include_router(profile.router)
app.include_router(accounts.router)
app.include_router(categories.router)
app.include_router(upload.router)
app.include_router(transactions.router)
app.include_router(rules.router)
app.include_router(chat.router)
app.include_router(budget.router)
app.include_router(projects.router)
app.include_router(dashboard.router)
app.include_router(fixed_expenses.router)
app.include_router(insights.router)
app.include_router(auth.router)
app.include_router(credit_offsets.router)


@app.get("/")
def root():
    return {"status": "FinanceAI API running"}
