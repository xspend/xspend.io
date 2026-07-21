from contextlib import asynccontextmanager

from fastapi import FastAPI
import os
from dotenv import load_dotenv
load_dotenv()
from fastapi.middleware.cors import CORSMiddleware
from app.db import SessionLocal
from app.models import seed_default_categories

from app.api.routers import (
    profile, accounts, categories, upload, transactions, rules, admin,
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

app = FastAPI(title="FinanceAI API", lifespan=lifespan)

# Allowed origins: localhost for dev + any production domains from the
# FRONTEND_ORIGINS env var (comma-separated). Set this in Render to your Vercel
# domain so the deployed frontend isn't blocked by CORS.
_default_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
_prod_origins = [o.strip() for o in os.getenv("FRONTEND_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_default_origins + _prod_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profile.router)
app.include_router(accounts.router)
app.include_router(categories.router)
app.include_router(upload.router)
app.include_router(transactions.router)
app.include_router(rules.router)
app.include_router(admin.router)
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
