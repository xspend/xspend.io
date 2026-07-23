"""Alembic migration 0010_user_profiles_soft_delete — splits the financial/
goal-planning columns off `users` into a new `user_profiles` table, and adds
`users.is_deleted` for the soft-delete flow (see app/services/auth_service.py:
delete_account()).

Builds the pre-0010 (post-0009) schema via the real migration chain, seeds a
user with non-default financial values, runs 0010, and asserts the backfill —
SQLite for CI portability (also hand-verified against a real local Postgres
during dev).

This migration is DELIBERATELY additive-only: the 11 old financial columns
stay on `users` until a separate follow-up migration (0011) drops them, per
this repo's destructive-changes-are-a-separate-migration discipline. That
means `alembic check` at head is EXPECTED to report those 11 columns as
removable right now — see test_alembic_check_reports_the_expected_drift
below, which asserts that specific expected state rather than "no drift".
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
    """A SQLite DB built via the real migration chain up to 0009, seeded with
    a user with non-default financial values, then upgraded to 0010."""
    tmpdir = tempfile.mkdtemp(prefix="xspend-user-profiles-test-")
    db_path = os.path.join(tmpdir, "post0009.db")
    db_url = f"sqlite:///{db_path}"

    r = _run_alembic(db_url, "upgrade", "0009_password_reset_tokens")
    assert r.returncode == 0, r.stderr

    engine = create_engine(db_url)
    with engine.begin() as c:
        c.execute(text(
            "INSERT INTO users (email, full_name, income_amount, income_frequency, "
            "savings_goal_weekly, savings_goal_monthly, debt_payoff_goal, financial_goal, "
            "selected_goals, other_goals, currency_code, monthly_budget, payday_day) "
            "VALUES ('alice@test.com', 'Alice', 5000, 'biweekly', 100, 400, 20000, "
            "'Buy a house', 'travel,car', 'none', 'EUR', 1200, '15')"
        ))
    engine.dispose()

    r = _run_alembic(db_url, "upgrade", "0010_user_profiles_soft_delete")
    assert r.returncode == 0, r.stderr

    yield db_url


def test_user_profiles_table_exists_with_expected_columns(migrated_db):
    insp = inspect(create_engine(migrated_db))
    assert "user_profiles" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("user_profiles")}
    assert cols == {
        "id", "user_id", "income_amount", "income_frequency", "savings_goal_weekly",
        "savings_goal_monthly", "debt_payoff_goal", "financial_goal", "selected_goals",
        "other_goals", "currency_code", "monthly_budget", "payday_day",
    }


def test_user_profiles_fk_targets_users_with_cascade_and_is_unique(migrated_db):
    insp = inspect(create_engine(migrated_db))
    fks = insp.get_foreign_keys("user_profiles")
    matching = [fk for fk in fks if "user_id" in fk["constrained_columns"]]
    assert matching, "no FK found on user_profiles.user_id"
    fk = matching[0]
    assert fk["referred_table"] == "users"
    assert fk["referred_columns"] == ["id"]
    assert fk["options"].get("ondelete") == "CASCADE"
    assert any(uq["column_names"] == ["user_id"] for uq in insp.get_unique_constraints("user_profiles"))


def test_backfill_copies_existing_financial_data(migrated_db):
    e = create_engine(migrated_db)
    with e.connect() as c:
        row = c.execute(text(
            "SELECT income_amount, income_frequency, savings_goal_weekly, savings_goal_monthly, "
            "debt_payoff_goal, financial_goal, selected_goals, other_goals, currency_code, "
            "monthly_budget, payday_day FROM user_profiles WHERE user_id = 1"
        )).fetchone()
    assert row == (5000, "biweekly", 100, 400, 20000, "Buy a house", "travel,car", "none", "EUR", 1200, "15")


def test_users_is_deleted_added_and_defaults_false(migrated_db):
    insp = inspect(create_engine(migrated_db))
    assert "is_deleted" in {c["name"] for c in insp.get_columns("users")}
    e = create_engine(migrated_db)
    with e.connect() as c:
        assert bool(c.execute(text("SELECT is_deleted FROM users WHERE email = 'alice@test.com'")).scalar()) is False


def test_alembic_check_reports_the_expected_drift(migrated_db):
    # 0010 deliberately does NOT drop the 11 old columns yet (that's 0011,
    # a separate follow-up) — so `alembic check` at head is expected to
    # flag exactly those as removable, not report a clean state.
    r = _run_alembic(migrated_db, "check")
    assert r.returncode != 0
    output = r.stdout + r.stderr
    for col in (
        "income_amount", "income_frequency", "savings_goal_weekly", "savings_goal_monthly",
        "debt_payoff_goal", "financial_goal", "selected_goals", "other_goals",
        "currency_code", "monthly_budget", "payday_day",
    ):
        assert f"users.{col}" in output, f"expected {col} to be flagged as drift, wasn't found in: {output}"


def test_downgrade_and_reupgrade_round_trip(migrated_db):
    r = _run_alembic(migrated_db, "downgrade", "0009_password_reset_tokens")
    assert r.returncode == 0, r.stdout + r.stderr

    insp = inspect(create_engine(migrated_db))
    assert "user_profiles" not in insp.get_table_names()
    assert "is_deleted" not in {c["name"] for c in insp.get_columns("users")}

    # data survives the round trip
    e = create_engine(migrated_db)
    with e.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM users")).scalar() == 1

    r = _run_alembic(migrated_db, "upgrade", "0010_user_profiles_soft_delete")
    assert r.returncode == 0, r.stderr

    insp = inspect(create_engine(migrated_db))
    assert "user_profiles" in insp.get_table_names()
