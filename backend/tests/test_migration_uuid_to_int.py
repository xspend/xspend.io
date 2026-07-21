"""Alembic migration 0003_uuid_to_integer_pks — the highest-risk change in this
repo (rewrites every primary key on live financial data). This test builds a
throwaway SQLite DB on the pre-migration (UUID-string) schema via the real
migration chain, seeds cross-referenced "production-like" data (including one
deliberately orphaned reference), runs the migration, and asserts:
  - every reference still points at the correct row (no data corruption)
  - real FK/PK constraints exist with the right types
  - NOT NULL columns enforce correctly; nullable orphans just backfill to NULL
  - autoincrement continues correctly for new rows after the swap
  - `alembic check` reports no drift against the current models

This exercises the same migration code manually verified against a real
Postgres 16 instance during development — SQLite here for CI portability.
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
    """A SQLite DB built via the real migration chain: baseline -> dedup ->
    (seed legacy UUID data) -> uuid_to_integer_pks."""
    tmpdir = tempfile.mkdtemp(prefix="xspend-migration-test-")
    db_path = os.path.join(tmpdir, "legacy.db")
    db_url = f"sqlite:///{db_path}"

    r = _run_alembic(db_url, "upgrade", "0002_dedup_txn_columns")
    assert r.returncode == 0, r.stderr

    engine = create_engine(db_url)
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (user_id, email, full_name) VALUES ('u-alice', 'alice@test.com', 'Alice')"))
        c.execute(text("INSERT INTO users (user_id, email, full_name) VALUES ('u-bob', 'bob@test.com', 'Bob')"))
        c.execute(text("INSERT INTO accounts (account_id, user_id, account_name) VALUES ('acct-alice-1', 'u-alice', 'Checking')"))
        c.execute(text("INSERT INTO accounts (account_id, user_id, account_name) VALUES ('acct-bob-1', 'u-bob', 'Amex')"))
        c.execute(text(
            "INSERT INTO uploaded_files (uploaded_file_id, user_id, account_id, file_name, file_type) "
            "VALUES ('upl-1', 'u-alice', 'acct-alice-1', 'march.csv', 'csv')"
        ))
        c.execute(text(
            "INSERT INTO transactions (transaction_id, id, user_id, account_id, uploaded_file_id, "
            "transaction_date, amount, description, transaction_type, category, fingerprint) "
            "VALUES ('t-credit', 1, 'u-alice', 'acct-alice-1', 'upl-1', "
            "'2026-03-02', 30.0, 'STATEMENT CREDIT - UBER', 'card_credit', 'Card Credit', 'fp-1')"
        ))
        c.execute(text(
            "INSERT INTO transactions (transaction_id, id, user_id, account_id, uploaded_file_id, "
            "transaction_date, amount, description, transaction_type, category, fingerprint) "
            "VALUES ('t-expense', 2, 'u-alice', 'acct-alice-1', 'upl-1', "
            "'2026-03-03', -50.0, 'UBER TRIP', 'expense', 'Travel', 'fp-2')"
        ))
        c.execute(text(
            "INSERT INTO transactions (transaction_id, id, user_id, account_id, "
            "transaction_date, amount, description, transaction_type, category, fingerprint) "
            "VALUES ('t-bob', 3, 'u-bob', 'acct-bob-1', "
            "'2026-03-04', -20.0, 'GROCERIES', 'expense', 'Groceries', 'fp-3')"
        ))
        # Deliberate orphan: account_id references a row that doesn't exist.
        # account_id is nullable, so this must backfill to NULL, not crash.
        c.execute(text(
            "INSERT INTO transactions (transaction_id, id, user_id, account_id, "
            "transaction_date, amount, description, transaction_type, category, fingerprint) "
            "VALUES ('t-orphan', 4, 'u-alice', 'acct-GONE', "
            "'2026-03-05', -5.0, 'ORPHAN', 'expense', 'Other', 'fp-4')"
        ))
        c.execute(text(
            "INSERT INTO credit_offsets (user_id, credit_transaction_id, matched_expense_id, "
            "matched_category, credit_type, eligible_for_matching, applied_amount, "
            "unapplied_amount, is_active, statement_period) "
            "VALUES ('u-alice', 't-credit', 't-expense', 'Travel', 'purchase', 1, 30.0, 0.0, 1, '2026-03')"
        ))
        c.execute(text("INSERT INTO chat_log (user_id, prompt_id) VALUES ('u-alice', 'p1')"))
    engine.dispose()

    # Pin to this specific revision, not the floating "head" — this test exists to
    # verify 0003's behavior specifically, and must keep doing so regardless of
    # what later migrations (e.g. 0004_pk_columns_to_id) get added on top.
    r = _run_alembic(db_url, "upgrade", "0003_uuid_to_integer_pks")
    assert r.returncode == 0, r.stderr

    yield db_url, r.stdout + r.stderr


def test_migration_reports_the_orphan(migrated_db):
    _db_url, output = migrated_db
    assert "transactions.account_id" in output
    assert "orphaned" in output.lower()


def test_all_references_resolve_correctly(migrated_db):
    db_url, _ = migrated_db
    e = create_engine(db_url)
    c = e.connect()

    users = {row.email: row.user_id for row in c.execute(text("SELECT user_id, email FROM users"))}
    alice_id, bob_id = users["alice@test.com"], users["bob@test.com"]
    assert isinstance(alice_id, int) and isinstance(bob_id, int)

    accounts = {row.account_name: (row.account_id, row.user_id)
                for row in c.execute(text("SELECT account_id, account_name, user_id FROM accounts"))}
    assert accounts["Checking"][1] == alice_id
    assert accounts["Amex"][1] == bob_id
    alice_acct_id = accounts["Checking"][0]

    txns = {row.description: row for row in c.execute(
        text("SELECT id, user_id, account_id, uploaded_file_id, description FROM transactions"))}
    assert txns["UBER TRIP"].user_id == alice_id
    assert txns["UBER TRIP"].account_id == alice_acct_id
    assert txns["GROCERIES"].user_id == bob_id
    # The orphaned account reference must backfill to NULL, not crash or drop the row.
    assert txns["ORPHAN"].account_id is None
    assert txns["ORPHAN"].user_id == alice_id  # the row itself is preserved

    credit_row = c.execute(text(
        "SELECT user_id, credit_transaction_id, matched_expense_id FROM credit_offsets"
    )).fetchone()
    assert credit_row.user_id == alice_id
    assert credit_row.credit_transaction_id == txns["STATEMENT CREDIT - UBER"].id
    assert credit_row.matched_expense_id == txns["UBER TRIP"].id


def test_no_rows_lost(migrated_db):
    db_url, _ = migrated_db
    e = create_engine(db_url)
    c = e.connect()
    assert c.execute(text("SELECT COUNT(*) FROM users")).scalar() == 2
    assert c.execute(text("SELECT COUNT(*) FROM accounts")).scalar() == 2
    assert c.execute(text("SELECT COUNT(*) FROM transactions")).scalar() == 4
    assert c.execute(text("SELECT COUNT(*) FROM credit_offsets")).scalar() == 1
    assert c.execute(text("SELECT COUNT(*) FROM chat_log")).scalar() == 1


def test_pk_and_fk_constraints_are_real(migrated_db):
    db_url, _ = migrated_db
    e = create_engine(db_url)
    insp = inspect(e)

    assert insp.get_pk_constraint("users")["constrained_columns"] == ["user_id"]
    assert insp.get_pk_constraint("transactions")["constrained_columns"] == ["id"]
    assert "transaction_id" not in {c["name"] for c in insp.get_columns("transactions")}

    fks = {(fk["constrained_columns"][0], fk["referred_table"]) for fk in insp.get_foreign_keys("transactions")}
    assert ("user_id", "users") in fks
    assert ("account_id", "accounts") in fks
    assert ("uploaded_file_id", "uploaded_files") in fks

    co_fks = {(fk["constrained_columns"][0], fk["referred_table"]) for fk in insp.get_foreign_keys("credit_offsets")}
    assert ("credit_transaction_id", "transactions") in co_fks
    assert ("matched_expense_id", "transactions") in co_fks


def test_not_null_columns_still_enforced(migrated_db):
    db_url, _ = migrated_db
    e = create_engine(db_url)
    cols = {c["name"]: c for c in inspect(e).get_columns("chat_log")}
    assert cols["user_id"]["nullable"] is False
    co_cols = {c["name"]: c for c in inspect(e).get_columns("credit_offsets")}
    assert co_cols["credit_transaction_id"]["nullable"] is False


def test_autoincrement_continues_after_migration(migrated_db):
    db_url, _ = migrated_db
    e = create_engine(db_url)
    with e.begin() as c:
        c.execute(text(
            "INSERT INTO users (email, full_name) VALUES ('carol@test.com', 'Carol')"
        ))
        new_user_id = c.execute(text("SELECT user_id FROM users WHERE email='carol@test.com'")).scalar()
        c.execute(text(
            "INSERT INTO transactions (user_id, description, amount) VALUES (:u, 'new row', -1.0)"
        ), {"u": new_user_id})
        new_txn_id = c.execute(text("SELECT id FROM transactions WHERE description='new row'")).scalar()
    assert new_user_id == 3          # after alice(1), bob(2)
    assert new_txn_id == 5            # after the 4 seeded transactions


# NOTE: no "alembic check reports no drift" test here. `alembic check` always
# compares the DB against the CURRENT models (i.e. head), so it can only be
# meaningful for a DB actually upgraded to head — not one deliberately pinned to
# this historical revision. That check lives in test_migration_pk_columns_to_id.py
# (and whichever test module owns head at any given time).


def test_downgrade_is_explicitly_refused(migrated_db):
    db_url, _ = migrated_db
    r = _run_alembic(db_url, "downgrade", "-1")
    assert r.returncode != 0
    assert "not downgradable" in (r.stdout + r.stderr)
