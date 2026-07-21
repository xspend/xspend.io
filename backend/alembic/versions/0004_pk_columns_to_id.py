"""pk columns to id

Renames 5 primary-key columns that still used the `<table>_id` naming convention
to plain `id`, matching every other table (`Transaction.id`, `Project.id`,
`BudgetHistory.id`, etc.):
  - users.user_id            -> users.id
  - accounts.account_id      -> accounts.id
  - uploaded_files.uploaded_file_id -> uploaded_files.id
  - categories.category_id   -> categories.id
  - transaction_rules.rule_id -> transaction_rules.id

This is a PURE RENAME — no type change, no data transformation — unlike
`0003_uuid_to_integer_pks`. Verified directly (both SQLite and a real local
Postgres) that a plain `op.alter_column(table, old, new_column_name="id")`
works WITHOUT `batch_alter_table`'s reflect-and-rebuild machinery on either
dialect, and that every dependent FK constraint auto-updates to reference the
renamed column with NO separate `drop_constraint`/`create_foreign_key` step:
  - SQLite (3.25+) natively supports `ALTER TABLE ... RENAME COLUMN` and
    rewrites the stored DDL of every table with a FK pointing at the renamed
    column.
  - Postgres tracks FK targets by column OID, not name, so a rename never
    invalidates or requires touching the constraint.
Foreign-key COLUMN NAMES on child tables (`user_id`, `account_id`,
`uploaded_file_id`) are unchanged — only what they point at changes name.

Revision ID: 0004_pk_columns_to_id
Revises: 0003_uuid_to_integer_pks
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_pk_columns_to_id"
down_revision = "0003_uuid_to_integer_pks"
branch_labels = None
depends_on = None


# (table, old_pk_column_name)
RENAMES = [
    ("users", "user_id"),
    ("accounts", "account_id"),
    ("uploaded_files", "uploaded_file_id"),
    ("categories", "category_id"),
    ("transaction_rules", "rule_id"),
]


def upgrade() -> None:
    for table, old_col in RENAMES:
        op.alter_column(table, old_col, new_column_name="id", existing_type=sa.Integer())


def downgrade() -> None:
    for table, old_col in RENAMES:
        op.alter_column(table, "id", new_column_name=old_col, existing_type=sa.Integer())
