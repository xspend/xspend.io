"""Alembic migration 0006_token_blacklist_user_id — adds a user_id FK to
token_blacklist (0005_auth_tables shipped it with no FK at all; see 0006's
docstring for why this had to be a follow-up rather than an edit to 0005).

Builds the pre-0006 (post-0005) schema via the real migration chain and
confirms the NOT NULL user_id add is safe under that migration's assumption
that token_blacklist is always empty at this point — SQLite for CI
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
    """A SQLite DB built via the real migration chain up to 0005, then 0006."""
    tmpdir = tempfile.mkdtemp(prefix="xspend-token-blacklist-user-id-test-")
    db_path = os.path.join(tmpdir, "post0005.db")
    db_url = f"sqlite:///{db_path}"

    r = _run_alembic(db_url, "upgrade", "0005_auth_tables")
    assert r.returncode == 0, r.stderr

    engine = create_engine(db_url)
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (email, full_name) VALUES ('alice@test.com', 'Alice')"))
    engine.dispose()

    r = _run_alembic(db_url, "upgrade", "head")
    assert r.returncode == 0, r.stderr

    yield db_url


def test_token_blacklist_is_empty_at_0005():
    # Sanity check on the migration's core assumption: nothing writes to
    # token_blacklist before this migration ships, so a NOT NULL add with no
    # server_default and no backfill is safe. If this ever fails, 0006 needs
    # a two-step (nullable -> backfill -> not null) instead.
    tmpdir = tempfile.mkdtemp(prefix="xspend-token-blacklist-precheck-")
    db_path = os.path.join(tmpdir, "pre0006.db")
    db_url = f"sqlite:///{db_path}"
    r = _run_alembic(db_url, "upgrade", "0005_auth_tables")
    assert r.returncode == 0, r.stderr
    e = create_engine(db_url)
    with e.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM token_blacklist")).scalar() == 0


def test_user_id_column_and_fk_added(migrated_db):
    insp = inspect(create_engine(migrated_db))
    cols = {c["name"] for c in insp.get_columns("token_blacklist")}
    assert cols == {"id", "user_id", "jti", "expires_at", "created_at"}

    fks = insp.get_foreign_keys("token_blacklist")
    matching = [fk for fk in fks if "user_id" in fk["constrained_columns"]]
    assert matching, "no FK found on token_blacklist.user_id"
    fk = matching[0]
    assert fk["referred_table"] == "users"
    assert fk["referred_columns"] == ["id"]
    assert fk["options"].get("ondelete") == "CASCADE"


def test_alembic_check_reports_no_drift(migrated_db):
    r = _run_alembic(migrated_db, "check")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "No new upgrade operations detected" in (r.stdout + r.stderr)


def test_downgrade_and_reupgrade_round_trip(migrated_db):
    r = _run_alembic(migrated_db, "downgrade", "-1")
    assert r.returncode == 0, r.stdout + r.stderr

    insp = inspect(create_engine(migrated_db))
    assert "user_id" not in {c["name"] for c in insp.get_columns("token_blacklist")}

    r = _run_alembic(migrated_db, "upgrade", "head")
    assert r.returncode == 0, r.stderr

    insp = inspect(create_engine(migrated_db))
    assert "user_id" in {c["name"] for c in insp.get_columns("token_blacklist")}
