"""Alembic migration 0008_login_otps_single_row — adds a unique constraint on
login_otps.user_id (one row per user, not one per login attempt) plus
`locked_until` for the OTP-attempt lockout. See app/services/auth_service.py.

Builds the pre-0008 (post-0007) schema via the real migration chain, seeds a
user with TWO existing login_otps rows (the old one-row-per-attempt shape),
runs 0008, and asserts the dedup + new constraint/column — SQLite for CI
portability (also hand-verified against a real local Postgres during dev).
"""
import os
import subprocess
import sys
import tempfile

import pytest
from sqlalchemy import create_engine, inspect, text

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_alembic(db_url, *args):
    env = {**os.environ, "DATABASE_URL": db_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True,
    )
    return result


@pytest.fixture
def migrated_db():
    """A SQLite DB built via the real migration chain up to 0007, seeded with
    duplicate login_otps rows for one user, then upgraded to 0008."""
    tmpdir = tempfile.mkdtemp(prefix="xspend-login-otps-single-row-test-")
    db_path = os.path.join(tmpdir, "post0007.db")
    db_url = f"sqlite:///{db_path}"

    r = _run_alembic(db_url, "upgrade", "0007_login_otps")
    assert r.returncode == 0, r.stderr

    engine = create_engine(db_url)
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (email, full_name) VALUES ('alice@test.com', 'Alice')"))
        c.execute(text(
            "INSERT INTO login_otps (user_id, login_token, otp_hash, expires_at, used, attempts) "
            "VALUES (1, 'old-token', 'old-hash', '2020-01-01', 0, 0)"
        ))
        c.execute(text(
            "INSERT INTO login_otps (user_id, login_token, otp_hash, expires_at, used, attempts) "
            "VALUES (1, 'newest-token', 'newest-hash', '2020-01-02', 0, 0)"
        ))
    engine.dispose()

    r = _run_alembic(db_url, "upgrade", "head")
    assert r.returncode == 0, r.stderr

    yield db_url


def test_dedup_keeps_only_the_most_recent_row_per_user(migrated_db):
    e = create_engine(migrated_db)
    with e.connect() as c:
        rows = c.execute(text("SELECT login_token FROM login_otps WHERE user_id = 1")).fetchall()
    assert [r[0] for r in rows] == ["newest-token"]


def test_user_id_is_unique_and_locked_until_added(migrated_db):
    insp = inspect(create_engine(migrated_db))
    cols = {c["name"] for c in insp.get_columns("login_otps")}
    assert cols == {
        "id", "user_id", "login_token", "otp_hash", "expires_at",
        "used", "attempts", "locked_until", "created_at",
    }
    assert any(
        uq["column_names"] == ["user_id"] for uq in insp.get_unique_constraints("login_otps")
    )


def test_second_row_for_same_user_now_rejected(migrated_db):
    e = create_engine(migrated_db)
    with pytest.raises(Exception):
        with e.begin() as c:
            c.execute(text(
                "INSERT INTO login_otps (user_id, login_token, otp_hash, expires_at, used, attempts) "
                "VALUES (1, 'another-token', 'another-hash', '2020-01-03', 0, 0)"
            ))


def test_alembic_check_reports_no_drift(migrated_db):
    r = _run_alembic(migrated_db, "check")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "No new upgrade operations detected" in (r.stdout + r.stderr)


def test_downgrade_and_reupgrade_round_trip(migrated_db):
    r = _run_alembic(migrated_db, "downgrade", "-1")
    assert r.returncode == 0, r.stdout + r.stderr

    insp = inspect(create_engine(migrated_db))
    assert "locked_until" not in {c["name"] for c in insp.get_columns("login_otps")}
    assert insp.get_unique_constraints("login_otps") == []

    r = _run_alembic(migrated_db, "upgrade", "head")
    assert r.returncode == 0, r.stderr

    insp = inspect(create_engine(migrated_db))
    assert "locked_until" in {c["name"] for c in insp.get_columns("login_otps")}
