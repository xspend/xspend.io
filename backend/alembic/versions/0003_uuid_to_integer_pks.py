"""uuid to integer pks

Converts every UUID-string primary key to an integer autoincrement PK, and every
loose, untyped string reference column (user_id, account_id, uploaded_file_id,
credit_transaction_id, matched_expense_id) into a real integer ForeignKey.

This is a STAGED, DATA-PRESERVING migration (no rows are dropped):

  1. Add an integer surrogate key to every UUID-PK table (users, accounts,
     uploaded_files, categories, transaction_rules) — Postgres: SERIAL, which
     backfills a unique sequential value for every existing row and wires a
     sequence for future inserts. SQLite: a plain column backfilled from the
     table's built-in `rowid`.
  2. Backfill every reference column into a sibling `<col>_int` column via a
     correlated subquery against the surrogate/PK — while the parent table
     still holds BOTH the old string value and the new int value side by side.
     `credit_offsets` maps its two transaction references through
     `transactions.transaction_id -> transactions.id` (transactions already
     has a usable integer `id`, so it needs no surrogate of its own).
  3. Any reference that fails to resolve (orphaned data — always possible since
     these were never real foreign keys) backfills to NULL. For columns that
     must be NOT NULL, that is a hard stop: the migration raises with the exact
     orphaned rows rather than silently violating (or silently loosening) the
     constraint. For nullable columns it's a printed warning, not a failure.
  4. Swap: for each parent table, drop the old string PK column and promote the
     surrogate to be the primary key (renamed to the original column name, so
     application code and models are unaffected by name). `transactions` drops
     `transaction_id` and promotes its existing `id` to the primary key,
     attaching a Postgres sequence for future autoincrement (SQLite's INTEGER
     PRIMARY KEY is auto-increment-by-rowid with no extra step needed).
  5. Swap children: drop each old string reference column, rename its `_int`
     sibling to the canonical name, and add the real ForeignKey constraint.

⚠️  This invalidates every existing JWT: `sub` was `users.user_id`, a UUID
string, and now the column (and the token subject) is an integer. Every user
must log in again after this migration ships — see app/auth/deps.py, which
rejects a stale UUID `sub` with a clean 401 instead of erroring.

Revision ID: 0003_uuid_to_integer_pks
Revises: 0002_dedup_txn_columns
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_uuid_to_integer_pks"
down_revision = "0002_dedup_txn_columns"
branch_labels = None
depends_on = None


# Tables whose primary key is a UUID string with no other usable integer column.
# `transactions` is handled separately — it already has a populated integer `id`.
SURROGATE_PK_TABLES = [
    "users",
    "accounts",
    "uploaded_files",
    "categories",
    "transaction_rules",
]

# (child_table, child_column, parent_table, parent_lookup_column, parent_value_column, not_null)
# parent_lookup_column is the OLD string column to match against (still present
# at backfill time); parent_value_column is where the new integer value lives
# (the surrogate `new_id`, or `transactions.id` which pre-exists).
# `not_null` mirrors the target column's nullability in models.py — True ONLY
# for chat_log.user_id and credit_offsets.credit_transaction_id; every other
# reference in this schema is nullable.
REFERENCES = [
    ("accounts", "user_id", "users", "user_id", "new_id", False),
    ("uploaded_files", "user_id", "users", "user_id", "new_id", False),
    ("uploaded_files", "account_id", "accounts", "account_id", "new_id", False),
    ("categories", "user_id", "users", "user_id", "new_id", False),
    ("projects", "user_id", "users", "user_id", "new_id", False),
    ("transactions", "user_id", "users", "user_id", "new_id", False),
    ("transactions", "account_id", "accounts", "account_id", "new_id", False),
    ("transactions", "uploaded_file_id", "uploaded_files", "uploaded_file_id", "new_id", False),
    ("transaction_rules", "user_id", "users", "user_id", "new_id", False),
    ("budget_history", "user_id", "users", "user_id", "new_id", False),
    ("manual_fixed_expenses", "user_id", "users", "user_id", "new_id", False),
    ("chat_log", "user_id", "users", "user_id", "new_id", True),
    ("credit_offsets", "user_id", "users", "user_id", "new_id", False),
    ("credit_offsets", "credit_transaction_id", "transactions", "transaction_id", "id", True),
    ("credit_offsets", "matched_expense_id", "transactions", "transaction_id", "id", False),
    ("merchant_rules", "user_id", "users", "user_id", "new_id", False),
]


def _is_pg(bind):
    return bind.dialect.name == "postgresql"


def _add_surrogate_pk(bind, table):
    """Add an integer surrogate key, backfilled with a unique value per
    existing row, on a table whose current PK is a UUID string."""
    if _is_pg(bind):
        # SERIAL (32-bit) to match the model's plain Integer type — BIGSERIAL
        # would drift from `Column(Integer, ...)` and show up in `alembic check`.
        op.execute(f"ALTER TABLE {table} ADD COLUMN new_id SERIAL")
    else:
        op.add_column(table, sa.Column("new_id", sa.Integer(), nullable=True))
        op.execute(f"UPDATE {table} SET new_id = rowid")


def _backfill_reference(child_table, child_col, parent_table, parent_lookup_col, parent_value_col):
    tmp_col = f"{child_col}_int"
    op.add_column(child_table, sa.Column(tmp_col, sa.Integer(), nullable=True))
    op.execute(
        f"UPDATE {child_table} SET {tmp_col} = ("
        f"  SELECT p.{parent_value_col} FROM {parent_table} p"
        f"  WHERE p.{parent_lookup_col} = {child_table}.{child_col}"
        f")"
    )


def _assert_no_orphans(bind, child_table, child_col):
    tmp_col = f"{child_col}_int"
    rows = bind.execute(sa.text(
        f"SELECT {child_col} FROM {child_table} "
        f"WHERE {tmp_col} IS NULL AND {child_col} IS NOT NULL LIMIT 10"
    )).fetchall()
    if rows:
        sample = ", ".join(repr(r[0]) for r in rows)
        raise RuntimeError(
            f"{child_table}.{child_col} has orphaned references that don't match "
            f"any parent row and this column must be NOT NULL — cannot proceed. "
            f"Sample orphaned values: {sample}. Fix or reassign these rows before "
            f"re-running the migration."
        )


def _warn_orphans(bind, child_table, child_col):
    tmp_col = f"{child_col}_int"
    count = bind.execute(sa.text(
        f"SELECT COUNT(*) FROM {child_table} WHERE {tmp_col} IS NULL AND {child_col} IS NOT NULL"
    )).scalar()
    if count:
        print(f"[0003_uuid_to_integer_pks] WARNING: {child_table}.{child_col} has "
              f"{count} orphaned reference(s) that backfilled to NULL (no matching parent row).")


def _swap_surrogate_pk(table, pk_col):
    # NOTE: within a single batch_alter_table block, constraint-creation calls
    # (create_primary_key/create_foreign_key) must reference the column by its
    # PRE-rename name and run BEFORE the alter_column rename — batch mode's
    # table rebuild resolves constraint columns against the original reflected
    # names, so referencing the post-rename name (or ordering the rename first)
    # silently produces a table with NO constraint at all. Verified against
    # both SQLite (batch/table-recreate path) and Postgres (direct ALTER path).
    with op.batch_alter_table(table) as batch_op:
        batch_op.drop_column(pk_col)
        batch_op.create_primary_key(f"pk_{table}", ["new_id"])
        batch_op.alter_column("new_id", new_column_name=pk_col, existing_type=sa.Integer(), nullable=False)


def _promote_transactions_pk(bind):
    # The baseline schema had a separate `UniqueConstraint('id')` (from back when
    # `id` was just a unique column, not the PK). A PK is inherently unique, so
    # that old constraint is now redundant — drop it, or it drifts against the
    # model (no unique=True on `id`) and `alembic check` flags it forever.
    old_unique_name = None
    for uc in sa.inspect(bind).get_unique_constraints("transactions"):
        if uc["column_names"] == ["id"]:
            old_unique_name = uc["name"]
            break

    with op.batch_alter_table("transactions") as batch_op:
        if old_unique_name:
            batch_op.drop_constraint(old_unique_name, type_="unique")
        batch_op.drop_column("transaction_id")
        batch_op.alter_column("id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_primary_key("pk_transactions", ["id"])
    if _is_pg(bind):
        # `id` was app-assigned (max(id)+1), never sequence-backed. Attach one now
        # so the DB — not the app — generates future ids.
        op.execute("CREATE SEQUENCE transactions_id_seq")
        op.execute("ALTER TABLE transactions ALTER COLUMN id SET DEFAULT nextval('transactions_id_seq')")
        op.execute("ALTER SEQUENCE transactions_id_seq OWNED BY transactions.id")
        # A fresh sequence already starts at 1, which is correct for an empty
        # table — only advance it if rows exist (setval(seq, 0) is out of range).
        max_id = bind.execute(sa.text("SELECT MAX(id) FROM transactions")).scalar()
        if max_id is not None:
            op.execute(f"SELECT setval('transactions_id_seq', {int(max_id)})")


def _swap_reference(child_table, child_col, parent_table, parent_pk_col, not_null, fk_name):
    # `parent_pk_col` is the parent's CANONICAL pk column name (e.g. "user_id"),
    # which the swap preserves across the string->int change — NOT the `new_id`
    # surrogate name used only during backfill lookups. By the time this runs,
    # the parent has already been swapped, so `parent_pk_col` is a real int PK.
    #
    # Same pre-rename-name-and-ordering requirement as _swap_surrogate_pk above.
    tmp_col = f"{child_col}_int"
    with op.batch_alter_table(child_table) as batch_op:
        batch_op.drop_column(child_col)
        batch_op.create_foreign_key(
            fk_name, parent_table, [tmp_col], [parent_pk_col],
            ondelete="CASCADE" if parent_table == "users" else None,
        )
        batch_op.alter_column(tmp_col, new_column_name=child_col, existing_type=sa.Integer(), nullable=not not_null)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Surrogate PKs on the 5 UUID-PK tables.
    for table in SURROGATE_PK_TABLES:
        _add_surrogate_pk(bind, table)

    # 2. Backfill every reference column while parents still hold both the old
    #    string value (lookup key) and the new int value (surrogate, or the
    #    pre-existing `transactions.id`).
    for child_table, child_col, parent_table, parent_lookup_col, parent_value_col, _not_null in REFERENCES:
        _backfill_reference(child_table, child_col, parent_table, parent_lookup_col, parent_value_col)

    # 3. Integrity gate: NOT NULL targets must have resolved for every row that
    #    had a non-null old value. Nullable targets just get a warning.
    for child_table, child_col, *_rest, not_null in REFERENCES:
        if not_null:
            _assert_no_orphans(bind, child_table, child_col)
    for child_table, child_col, *_rest, not_null in REFERENCES:
        if not not_null:
            _warn_orphans(bind, child_table, child_col)

    # 4. Swap parent PK columns (must complete before child FKs are added —
    #    a FK target must already be a primary/unique key).
    for table in SURROGATE_PK_TABLES:
        _swap_surrogate_pk(table, {
            "users": "user_id",
            "accounts": "account_id",
            "uploaded_files": "uploaded_file_id",
            "categories": "category_id",
            "transaction_rules": "rule_id",
        }[table])
    _promote_transactions_pk(bind)

    # 5. Swap child reference columns and add the real FK constraints.
    #    FK target column name, post-swap:
    #      - surrogate-PK parents (users/accounts/uploaded_files/categories/
    #        transaction_rules): the surrogate `new_id` was renamed BACK to
    #        `parent_lookup_col`'s own name in step 4, so that name is the target.
    #      - `transactions` as parent: `id` was never renamed — it's the target
    #        directly, regardless of `parent_lookup_col` ("transaction_id",
    #        which no longer exists after `_promote_transactions_pk`).
    for child_table, child_col, parent_table, parent_lookup_col, _parent_value_col, not_null in REFERENCES:
        parent_final_col = "id" if parent_table == "transactions" else parent_lookup_col
        fk_name = f"fk_{child_table}_{child_col}"
        _swap_reference(child_table, child_col, parent_table, parent_final_col, not_null, fk_name)

    # 6. The transactions.user_id swap above dropped the old string `user_id`
    #    column, which implicitly dropped `uq_txn_fingerprint_user` (it can't
    #    exist on a column that no longer exists). Recreate it on the new int
    #    user_id — dedup must stay unique per (fingerprint, user_id).
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.create_unique_constraint("uq_txn_fingerprint_user", ["fingerprint", "user_id"])


def downgrade() -> None:
    # Structural rollback only — original UUID values are not reconstructed.
    # Restore from a pre-migration backup for a true data rollback.
    raise NotImplementedError(
        "0003_uuid_to_integer_pks is not downgradable: the original UUID primary "
        "keys are not preserved anywhere once this migration completes. Restore "
        "the pre-migration database backup instead of downgrading."
    )
