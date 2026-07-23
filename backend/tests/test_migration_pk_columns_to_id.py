"""Alembic migration 0004_pk_columns_to_id — renames 5 primary-key columns from
`<table>_id` to plain `id` (users.user_id, accounts.account_id,
uploaded_files.uploaded_file_id, categories.category_id, transaction_rules.rule_id).

This is a pure rename (no type change), verified manually against a real Postgres
16 instance during development (plain `op.alter_column(..., new_column_name=...)`
works on both dialects without `batch_alter_table`, and every dependent FK
constraint auto-updates to the new column name with no separate step). This test
builds the pre-0004 (post-0003) schema via the real migration chain, seeds
cross-referenced data, runs the migration, and asserts nothing was lost or
mistargeted — SQLite here for CI portability.
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
    uuid_to_integer_pks -> (seed post-0003 data) -> pk_columns_to_id."""
    tmpdir = tempfile.mkdtemp(prefix="xspend-pk-rename-test-")
    db_path = os.path.join(tmpdir, "post0003.db")
    db_url = f"sqlite:///{db_path}"

    r = _run_alembic(db_url, "upgrade", "0003_uuid_to_integer_pks")
    assert r.returncode == 0, r.stderr

    engine = create_engine(db_url)
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (email, full_name) VALUES ('alice@test.com', 'Alice')"))
        c.execute(text("INSERT INTO users (email, full_name) VALUES ('bob@test.com', 'Bob')"))
        c.execute(text("INSERT INTO accounts (user_id, account_name) VALUES (1, 'Chase Checking')"))
        c.execute(text("INSERT INTO accounts (user_id, account_name) VALUES (2, 'Amex')"))
        c.execute(text(
            "INSERT INTO uploaded_files (user_id, account_id, file_name, file_type) "
            "VALUES (1, 1, 'march.csv', 'csv')"
        ))
        c.execute(text("INSERT INTO categories (user_id, category_name) VALUES (1, 'Custom Cat')"))
        c.execute(text("INSERT INTO projects (user_id, name) VALUES (1, 'Vacation Fund')"))
        c.execute(text(
            "INSERT INTO transactions (id, user_id, account_id, uploaded_file_id, transaction_date, "
            "amount, description, transaction_type, category, fingerprint) "
            "VALUES (1, 1, 1, 1, '2026-03-02', -50.0, 'UBER TRIP', 'expense', 'Travel', 'fp-1')"
        ))
        c.execute(text(
            "INSERT INTO transactions (id, user_id, account_id, transaction_date, amount, description, "
            "transaction_type, category, fingerprint) "
            "VALUES (2, 2, 2, '2026-03-04', -20.0, 'GROCERIES', 'expense', 'Groceries', 'fp-2')"
        ))
        c.execute(text(
            "INSERT INTO transaction_rules (user_id, match_value, output_category) "
            "VALUES (1, 'netflix', 'Subscriptions')"
        ))
        c.execute(text("INSERT INTO budget_history (amount, month, user_id) VALUES (2000.0, '2026-03', 1)"))
        c.execute(text("INSERT INTO manual_fixed_expenses (name, amount, user_id) VALUES ('Rent', 1500.0, 1)"))
        c.execute(text("INSERT INTO chat_log (user_id, prompt_id) VALUES (1, 'p1')"))
        c.execute(text(
            "INSERT INTO credit_offsets (user_id, credit_transaction_id, applied_amount, is_active, "
            "statement_period) VALUES (1, 1, 30.0, 1, '2026-03')"
        ))
        c.execute(text(
            "INSERT INTO merchant_rules (merchant_keyword, is_fixed, user_id, match_value, category) "
            "VALUES ('uber', 0, 1, 'uber', 'Travel')"
        ))
    engine.dispose()

    r = _run_alembic(db_url, "upgrade", "0004_pk_columns_to_id")
    assert r.returncode == 0, r.stderr

    yield db_url


def test_all_five_pks_renamed_to_id(migrated_db):
    insp = inspect(create_engine(migrated_db))
    for table in ("users", "accounts", "uploaded_files", "categories", "transaction_rules"):
        pk = insp.get_pk_constraint(table)
        assert pk["constrained_columns"] == ["id"], f"{table} PK is {pk['constrained_columns']}, expected ['id']"
        cols = {c["name"] for c in insp.get_columns(table)}
        assert "id" in cols


def test_old_pk_column_names_gone(migrated_db):
    insp = inspect(create_engine(migrated_db))
    old_names = {
        "users": "user_id",
        "accounts": "account_id",
        "uploaded_files": "uploaded_file_id",
        "categories": "category_id",
        "transaction_rules": "rule_id",
    }
    for table, old_col in old_names.items():
        cols = {c["name"] for c in insp.get_columns(table)}
        assert old_col not in cols, f"{table} still has old PK column {old_col}"


def test_fk_column_names_unchanged_but_target_id(migrated_db):
    # FK column NAMES (user_id, account_id, uploaded_file_id) must be unchanged —
    # only what they point at changes.
    insp = inspect(create_engine(migrated_db))
    expected = [
        ("accounts", "user_id", "users"),
        ("uploaded_files", "user_id", "users"),
        ("uploaded_files", "account_id", "accounts"),
        ("categories", "user_id", "users"),
        ("projects", "user_id", "users"),
        ("transactions", "user_id", "users"),
        ("transactions", "account_id", "accounts"),
        ("transactions", "uploaded_file_id", "uploaded_files"),
        ("transaction_rules", "user_id", "users"),
        ("budget_history", "user_id", "users"),
        ("manual_fixed_expenses", "user_id", "users"),
        ("chat_log", "user_id", "users"),
        ("credit_offsets", "user_id", "users"),
        ("credit_offsets", "credit_transaction_id", "transactions"),
        ("merchant_rules", "user_id", "users"),
    ]
    for table, col, parent in expected:
        fks = insp.get_foreign_keys(table)
        matching = [fk for fk in fks if col in fk["constrained_columns"]]
        assert matching, f"no FK found on {table}.{col}"
        fk = matching[0]
        assert fk["referred_table"] == parent
        assert fk["referred_columns"] == ["id"], (
            f"{table}.{col} targets {fk['referred_table']}.{fk['referred_columns']}, expected ['id']"
        )


def test_no_data_lost_and_values_correct(migrated_db):
    e = create_engine(migrated_db)
    c = e.connect()

    users = {row.email: row.id for row in c.execute(text("SELECT id, email FROM users"))}
    alice_id, bob_id = users["alice@test.com"], users["bob@test.com"]

    accounts = {row.account_name: (row.id, row.user_id)
                for row in c.execute(text("SELECT id, account_name, user_id FROM accounts"))}
    assert accounts["Chase Checking"][1] == alice_id
    assert accounts["Amex"][1] == bob_id

    assert c.execute(text("SELECT COUNT(*) FROM users")).scalar() == 2
    assert c.execute(text("SELECT COUNT(*) FROM accounts")).scalar() == 2
    assert c.execute(text("SELECT COUNT(*) FROM transactions")).scalar() == 2
    assert c.execute(text("SELECT COUNT(*) FROM categories WHERE category_name = 'Custom Cat'")).scalar() == 1
    assert c.execute(text("SELECT COUNT(*) FROM transaction_rules")).scalar() == 1
    assert c.execute(text("SELECT COUNT(*) FROM credit_offsets")).scalar() == 1


def test_autoincrement_continues_after_rename(migrated_db):
    e = create_engine(migrated_db)
    with e.begin() as c:
        c.execute(text("INSERT INTO users (email, full_name) VALUES ('carol@test.com', 'Carol')"))
        new_id = c.execute(text("SELECT id FROM users WHERE email='carol@test.com'")).scalar()
    assert new_id == 3  # after alice(1), bob(2)


def test_downgrade_and_reupgrade_round_trip(migrated_db):
    # Target the migration by name, not "-1" — later migrations (e.g. 0005)
    # get added after this one, so "head" isn't always one step past 0004.
    r = _run_alembic(migrated_db, "downgrade", "0003_uuid_to_integer_pks")
    assert r.returncode == 0, r.stdout + r.stderr

    insp = inspect(create_engine(migrated_db))
    assert insp.get_pk_constraint("users")["constrained_columns"] == ["user_id"]
    assert insp.get_pk_constraint("accounts")["constrained_columns"] == ["account_id"]

    # data survives the round trip
    e = create_engine(migrated_db)
    with e.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM users")).scalar() == 2

    r = _run_alembic(migrated_db, "upgrade", "0004_pk_columns_to_id")
    assert r.returncode == 0, r.stderr

    insp = inspect(create_engine(migrated_db))
    assert insp.get_pk_constraint("users")["constrained_columns"] == ["id"]
