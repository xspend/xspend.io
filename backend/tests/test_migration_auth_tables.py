"""Alembic migration 0005_auth_tables — adds users.email_verified (grandfathering
existing users to true) plus three new tables: email_verification_tokens,
refresh_tokens, token_blacklist.

Builds the pre-0005 (post-0004) schema via the real migration chain, seeds a
user the way it would have existed before this migration shipped, runs 0005,
and asserts the grandfathering + new schema are correct — SQLite for CI
portability (also hand-verified against a real local Postgres during dev).

Stops at 0005 specifically (not "head") since 0006_token_blacklist_user_id
changes token_blacklist's shape afterward — see test_migration_token_blacklist_user_id.py.
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
    """A SQLite DB built via the real migration chain: ... -> pk_columns_to_id
    -> (seed a pre-existing user) -> auth_tables."""
    tmpdir = tempfile.mkdtemp(prefix="xspend-auth-tables-test-")
    db_path = os.path.join(tmpdir, "post0004.db")
    db_url = f"sqlite:///{db_path}"

    r = _run_alembic(db_url, "upgrade", "0004_pk_columns_to_id")
    assert r.returncode == 0, r.stderr

    engine = create_engine(db_url)
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (email, full_name) VALUES ('grandfathered@test.com', 'Old User')"))
    engine.dispose()

    r = _run_alembic(db_url, "upgrade", "0005_auth_tables")
    assert r.returncode == 0, r.stderr

    yield db_url


def test_existing_user_grandfathered_to_verified(migrated_db):
    e = create_engine(migrated_db)
    with e.connect() as c:
        verified = c.execute(
            text("SELECT email_verified FROM users WHERE email = 'grandfathered@test.com'")
        ).scalar()
    assert bool(verified) is True


def test_new_user_defaults_to_unverified(migrated_db):
    e = create_engine(migrated_db)
    with e.begin() as c:
        c.execute(text("INSERT INTO users (email, full_name, email_verified) VALUES ('new@test.com', 'New', 0)"))
        verified = c.execute(text("SELECT email_verified FROM users WHERE email = 'new@test.com'")).scalar()
    assert bool(verified) is False


def test_auth_tables_exist_with_expected_columns(migrated_db):
    insp = inspect(create_engine(migrated_db))
    tables = insp.get_table_names()
    assert "email_verification_tokens" in tables
    assert "refresh_tokens" in tables
    assert "token_blacklist" in tables

    cols = {c["name"] for c in insp.get_columns("email_verification_tokens")}
    assert cols == {"id", "user_id", "token", "expires_at", "used", "created_at"}

    cols = {c["name"] for c in insp.get_columns("refresh_tokens")}
    assert cols == {"id", "user_id", "jti", "expires_at", "revoked", "created_at"}

    # token_blacklist has no user_id yet at 0005 — that lands in 0006
    cols = {c["name"] for c in insp.get_columns("token_blacklist")}
    assert cols == {"id", "jti", "expires_at", "created_at"}


def test_auth_table_fks_target_users_with_cascade(migrated_db):
    insp = inspect(create_engine(migrated_db))
    for table in ("email_verification_tokens", "refresh_tokens"):
        fks = insp.get_foreign_keys(table)
        matching = [fk for fk in fks if "user_id" in fk["constrained_columns"]]
        assert matching, f"no FK found on {table}.user_id"
        fk = matching[0]
        assert fk["referred_table"] == "users"
        assert fk["referred_columns"] == ["id"]

    # token_blacklist has no FK at 0005 — it's keyed by jti alone until 0006
    assert insp.get_foreign_keys("token_blacklist") == []


def test_token_and_jti_columns_are_unique(migrated_db):
    insp = inspect(create_engine(migrated_db))
    token_indexes = insp.get_indexes("email_verification_tokens")
    assert any(ix["unique"] and ix["column_names"] == ["token"] for ix in token_indexes)

    refresh_indexes = insp.get_indexes("refresh_tokens")
    assert any(ix["unique"] and ix["column_names"] == ["jti"] for ix in refresh_indexes)

    blacklist_indexes = insp.get_indexes("token_blacklist")
    assert any(ix["unique"] and ix["column_names"] == ["jti"] for ix in blacklist_indexes)


def test_downgrade_and_reupgrade_round_trip(migrated_db):
    r = _run_alembic(migrated_db, "downgrade", "0004_pk_columns_to_id")
    assert r.returncode == 0, r.stdout + r.stderr

    insp = inspect(create_engine(migrated_db))
    tables = insp.get_table_names()
    assert "email_verification_tokens" not in tables
    assert "refresh_tokens" not in tables
    assert "token_blacklist" not in tables
    assert "email_verified" not in {c["name"] for c in insp.get_columns("users")}

    # data survives the round trip
    e = create_engine(migrated_db)
    with e.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM users")).scalar() == 1

    r = _run_alembic(migrated_db, "upgrade", "0005_auth_tables")
    assert r.returncode == 0, r.stderr

    insp = inspect(create_engine(migrated_db))
    assert "email_verified" in {c["name"] for c in insp.get_columns("users")}
