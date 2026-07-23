"""Alembic migration 0009_password_reset_tokens — adds the table backing the
forgot-password flow (see app/services/auth_service.py: forgot_password() /
reset_password()).

Builds the pre-0009 (post-0008) schema via the real migration chain, seeds a
user, runs 0009, and asserts the new table's shape — SQLite for CI
portability (also hand-verified against a real local Postgres during dev).

Stops at 0009 specifically (not "head") since 0010 lands afterward — same
reasoning as test_migration_auth_tables.py / test_migration_login_otps.py.
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
    """A SQLite DB built via the real migration chain up to 0008, then 0009."""
    tmpdir = tempfile.mkdtemp(prefix="xspend-password-reset-tokens-test-")
    db_path = os.path.join(tmpdir, "post0008.db")
    db_url = f"sqlite:///{db_path}"

    r = _run_alembic(db_url, "upgrade", "0008_login_otps_single_row")
    assert r.returncode == 0, r.stderr

    engine = create_engine(db_url)
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (email, full_name) VALUES ('alice@test.com', 'Alice')"))
    engine.dispose()

    r = _run_alembic(db_url, "upgrade", "0009_password_reset_tokens")
    assert r.returncode == 0, r.stderr

    yield db_url


def test_password_reset_tokens_table_exists_with_expected_columns(migrated_db):
    insp = inspect(create_engine(migrated_db))
    assert "password_reset_tokens" in insp.get_table_names()

    cols = {c["name"] for c in insp.get_columns("password_reset_tokens")}
    assert cols == {"id", "user_id", "token", "expires_at", "used", "created_at"}


def test_password_reset_tokens_fk_targets_users_with_cascade(migrated_db):
    insp = inspect(create_engine(migrated_db))
    fks = insp.get_foreign_keys("password_reset_tokens")
    matching = [fk for fk in fks if "user_id" in fk["constrained_columns"]]
    assert matching, "no FK found on password_reset_tokens.user_id"
    fk = matching[0]
    assert fk["referred_table"] == "users"
    assert fk["referred_columns"] == ["id"]
    assert fk["options"].get("ondelete") == "CASCADE"


def test_token_column_is_unique(migrated_db):
    insp = inspect(create_engine(migrated_db))
    indexes = insp.get_indexes("password_reset_tokens")
    assert any(ix["unique"] and ix["column_names"] == ["token"] for ix in indexes)


def test_downgrade_and_reupgrade_round_trip(migrated_db):
    r = _run_alembic(migrated_db, "downgrade", "0008_login_otps_single_row")
    assert r.returncode == 0, r.stdout + r.stderr

    insp = inspect(create_engine(migrated_db))
    assert "password_reset_tokens" not in insp.get_table_names()

    r = _run_alembic(migrated_db, "upgrade", "0009_password_reset_tokens")
    assert r.returncode == 0, r.stderr

    insp = inspect(create_engine(migrated_db))
    assert "password_reset_tokens" in insp.get_table_names()
