"""Alembic migration 0007_login_otps — adds the login_otps table backing
2FA on login (see app/services/auth_service.py: login() / verify_login_otp()).

Builds the pre-0007 (post-0006) schema via the real migration chain, seeds a
user, runs 0007, and asserts the new table's shape — SQLite for CI
portability (also hand-verified against a real local Postgres during dev).

Stops at 0007 specifically (not "head") since 0008 changes login_otps'
shape afterward — see test_migration_login_otps_single_row.py.
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
    """A SQLite DB built via the real migration chain up to 0006, then 0007."""
    tmpdir = tempfile.mkdtemp(prefix="xspend-login-otps-test-")
    db_path = os.path.join(tmpdir, "post0006.db")
    db_url = f"sqlite:///{db_path}"

    r = _run_alembic(db_url, "upgrade", "0006_token_blacklist_user_id")
    assert r.returncode == 0, r.stderr

    engine = create_engine(db_url)
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (email, full_name) VALUES ('alice@test.com', 'Alice')"))
    engine.dispose()

    r = _run_alembic(db_url, "upgrade", "0007_login_otps")
    assert r.returncode == 0, r.stderr

    yield db_url


def test_login_otps_table_exists_with_expected_columns(migrated_db):
    insp = inspect(create_engine(migrated_db))
    assert "login_otps" in insp.get_table_names()

    cols = {c["name"] for c in insp.get_columns("login_otps")}
    assert cols == {"id", "user_id", "login_token", "otp_hash", "expires_at", "used", "attempts", "created_at"}


def test_login_otps_fk_targets_users_with_cascade(migrated_db):
    insp = inspect(create_engine(migrated_db))
    fks = insp.get_foreign_keys("login_otps")
    matching = [fk for fk in fks if "user_id" in fk["constrained_columns"]]
    assert matching, "no FK found on login_otps.user_id"
    fk = matching[0]
    assert fk["referred_table"] == "users"
    assert fk["referred_columns"] == ["id"]
    assert fk["options"].get("ondelete") == "CASCADE"


def test_login_token_column_is_unique(migrated_db):
    insp = inspect(create_engine(migrated_db))
    indexes = insp.get_indexes("login_otps")
    assert any(ix["unique"] and ix["column_names"] == ["login_token"] for ix in indexes)


def test_downgrade_and_reupgrade_round_trip(migrated_db):
    r = _run_alembic(migrated_db, "downgrade", "0006_token_blacklist_user_id")
    assert r.returncode == 0, r.stdout + r.stderr

    insp = inspect(create_engine(migrated_db))
    assert "login_otps" not in insp.get_table_names()

    r = _run_alembic(migrated_db, "upgrade", "0007_login_otps")
    assert r.returncode == 0, r.stderr

    insp = inspect(create_engine(migrated_db))
    assert "login_otps" in insp.get_table_names()
