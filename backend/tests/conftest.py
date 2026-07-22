"""Shared pytest fixtures.

Tests run against a throwaway **file-based SQLite** database in a temp dir — never
a real DB. DATABASE_URL is set here BEFORE any app module is imported, so
database.py builds its engine against the temp DB.
"""
import os
import sys
import tempfile

# ── Point the app at a temp SQLite DB, before importing anything app-related ──
_TMPDIR = tempfile.mkdtemp(prefix="xspend-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMPDIR, 'test.db')}"
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret")

# Tests must never hit a real SMTP server, even if the developer's .env has
# live credentials for local manual testing. app.core.config.Settings reads
# real os.environ vars with HIGHER priority than .env file values, so blanking
# these — not deleting them — is what actually sticks; email_service treats an
# empty string as "not configured" and falls back to logging the verification
# link instead of sending it.
for _var in ("SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM"):
    os.environ[_var] = ""

# Make the backend package importable regardless of pytest's invocation dir.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import engine, Base, SessionLocal  # noqa: E402
import app.models  # noqa: E402,F401  (registers all models on Base.metadata)
from app.models import seed_default_categories  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db():
    """Fresh schema + seeded categories for every test → full isolation."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_default_categories(db)
    finally:
        db.close()
    yield


@pytest.fixture
def db():
    """A SQLAlchemy session bound to the temp DB."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    """FastAPI TestClient. Using it as a context manager fires startup events."""
    from fastapi.testclient import TestClient
    import main
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def make_user(client):
    """Factory: signs up a user via the real auth flow, verifies their email
    (login is gated on that), logs in, and returns (user_id, auth headers)."""
    def _make(email="a@test.com", password="password123", name="A"):
        r = client.post("/auth/signup", json={"email": email, "password": password, "name": name})
        assert r.status_code == 201, r.text
        user_id = r.json()["user"]["id"]

        db = SessionLocal()
        try:
            from app.models import EmailVerificationToken
            token_row = (
                db.query(EmailVerificationToken)
                .filter(EmailVerificationToken.user_id == user_id)
                .first()
            )
            token = token_row.token
        finally:
            db.close()

        r = client.post("/auth/verify-email", json={"token": token})
        assert r.status_code == 200, r.text

        r = client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        access_token = r.json()["access_token"]
        return user_id, {"Authorization": f"Bearer {access_token}"}
    return _make
