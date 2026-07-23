from contextlib import asynccontextmanager

from fastapi import FastAPI
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

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
