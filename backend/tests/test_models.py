"""Schema regression tests — lock in the dedup so redundant columns can't creep back."""
from sqlalchemy import inspect

from app.db import engine

# The 20 columns removed in the dedup migration. If any reappears, a change
# regressed the schema cleanup.
DROPPED_TRANSACTION_COLUMNS = {
    "raw_date", "raw_description", "raw_amount", "raw_category",
    "description_raw", "description_clean", "original_description",
    "currency_code", "merchant_name", "bank_name_raw", "fingerprint_hash",
    "category_id", "subcategory", "posted_date", "project_review_pending",
    "is_duplicate", "status", "review_status", "classification_source",
    "is_user_edited",
}

CANONICAL_TRANSACTION_COLUMNS = {
    "id", "user_id", "transaction_date", "amount",
    "currency", "description", "category", "fingerprint", "is_edited",
}

# Tables that got a brand-new integer autoincrement PK in the UUID->int migration
# (transactions reused its existing integer `id` instead of adding a new column).
# All PKs are now named plain `id` (see the pk_columns_to_id migration) — the dict
# values are kept (not collapsed to a bare set) so a future PK-name regression on
# any one table is still caught per-table.
INT_PK_TABLES = {
    "users": "id",
    "accounts": "id",
    "uploaded_files": "id",
    "categories": "id",
    "transaction_rules": "id",
    "transactions": "id",
}


def _cols(table):
    return {c["name"] for c in inspect(engine).get_columns(table)}


def _col_types(table):
    return {c["name"]: c["type"] for c in inspect(engine).get_columns(table)}


def test_no_dropped_columns_remain():
    cols = _cols("transactions")
    assert not (DROPPED_TRANSACTION_COLUMNS & cols)


def test_no_uuid_transaction_id_column():
    # transaction_id (the old UUID PK) was removed; `id` is now the real PK.
    assert "transaction_id" not in _cols("transactions")


def test_canonical_columns_present():
    cols = _cols("transactions")
    assert CANONICAL_TRANSACTION_COLUMNS.issubset(cols)


def test_credit_offsets_and_merchant_rules_are_managed_tables():
    tables = set(inspect(engine).get_table_names())
    assert {"credit_offsets", "merchant_rules"}.issubset(tables)


def test_merchant_rules_has_full_column_set():
    # The migrate.py copy was missing 11 columns; the ORM model is the full one.
    cols = _cols("merchant_rules")
    for required in ("match_value", "category", "is_active", "user_id", "priority", "source"):
        assert required in cols


def test_fingerprint_unique_per_user_constraint_exists():
    uniques = inspect(engine).get_unique_constraints("transactions")
    cols_sets = [set(u["column_names"]) for u in uniques]
    assert {"fingerprint", "user_id"} in cols_sets


def test_all_primary_keys_are_integer():
    import sqlalchemy as sa
    for table, pk_col in INT_PK_TABLES.items():
        col_type = _col_types(table)[pk_col]
        assert isinstance(col_type, sa.Integer), f"{table}.{pk_col} is {col_type}, expected Integer"


def test_real_foreign_keys_exist():
    insp = inspect(engine)
    # (table, constrained_column, referred_table) for every relation that used to
    # be a loose untyped string column.
    expected = {
        ("accounts", "user_id", "users"),
        ("uploaded_files", "user_id", "users"),
        ("uploaded_files", "account_id", "accounts"),
        ("categories", "user_id", "users"),
        ("projects", "user_id", "users"),
        ("transactions", "user_id", "users"),
        ("transactions", "account_id", "accounts"),
        ("transactions", "uploaded_file_id", "uploaded_files"),
        ("transactions", "project_id", "projects"),
        ("transaction_rules", "user_id", "users"),
        ("budget_history", "user_id", "users"),
        ("manual_fixed_expenses", "user_id", "users"),
        ("chat_log", "user_id", "users"),
        ("credit_offsets", "user_id", "users"),
        ("credit_offsets", "credit_transaction_id", "transactions"),
        ("credit_offsets", "matched_expense_id", "transactions"),
        ("merchant_rules", "user_id", "users"),
    }
    actual = set()
    for table in {t for t, _, _ in expected}:
        for fk in insp.get_foreign_keys(table):
            for col in fk["constrained_columns"]:
                actual.add((table, col, fk["referred_table"]))
    assert expected.issubset(actual)


def test_foreign_keys_target_id_not_table_prefixed_column():
    # Every FK's referred column must be the parent's plain `id` PK (the point of
    # the pk_columns_to_id migration) — not a leftover `user_id`/`account_id`/etc.
    insp = inspect(engine)
    for table in ("accounts", "uploaded_files", "categories", "projects",
                  "transactions", "transaction_rules", "budget_history",
                  "manual_fixed_expenses", "chat_log", "credit_offsets", "merchant_rules"):
        for fk in insp.get_foreign_keys(table):
            assert fk["referred_columns"] == ["id"], (
                f"{table} FK on {fk['constrained_columns']} targets "
                f"{fk['referred_table']}.{fk['referred_columns']}, expected ['id']"
            )
