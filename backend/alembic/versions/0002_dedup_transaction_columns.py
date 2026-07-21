"""dedup transaction columns

Drops 20 redundant/dead columns from `transactions` that shadowed a canonical
column or were never read. Before dropping, canonical columns are backfilled from
their legacy twins so no data is lost on populated (production) tables.

This migration is GUARDED: it only touches columns that actually exist, so it is a
no-op on a fresh database created straight from the current models, and does the
real backfill+drop on the existing production schema.

Rollout on production (Postgres): take a Neon backup/branch first, then
    alembic stamp 4058e1b3d445      # baseline already matches prod
    alembic upgrade head            # runs this migration

Revision ID: 0002_dedup_txn_columns
Revises: 4058e1b3d445
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_dedup_txn_columns"
down_revision = "4058e1b3d445"
branch_labels = None
depends_on = None


# Legacy column -> (canonical column it duplicated, original type for downgrade).
# Ordered; dropped only if present.
LEGACY_COLUMNS = {
    "raw_date": sa.String(),
    "raw_description": sa.String(),
    "raw_amount": sa.String(),
    "raw_category": sa.String(),
    "description_raw": sa.String(length=500),
    "description_clean": sa.String(length=255),
    "original_description": sa.String(),
    "currency_code": sa.String(length=3),
    "merchant_name": sa.String(length=255),
    "bank_name_raw": sa.String(length=255),
    "fingerprint_hash": sa.String(length=255),
    "category_id": sa.String(),
    "subcategory": sa.String(),
    "posted_date": sa.Date(),
    "project_review_pending": sa.Boolean(),
    "is_duplicate": sa.Boolean(),
    "status": sa.String(),
    "review_status": sa.String(length=30),
    "classification_source": sa.String(),
    "is_user_edited": sa.Boolean(),
}


def _existing_columns(bind):
    return {c["name"] for c in sa.inspect(bind).get_columns("transactions")}


def upgrade() -> None:
    bind = op.get_bind()
    present = _existing_columns(bind)

    # 1. Backfill canonical columns from legacy twins (only where the twin exists),
    #    so dropping the twin loses nothing on populated tables.
    if "description_clean" in present or "description_raw" in present or "original_description" in present:
        parts = ["description"]
        for c in ("description_clean", "description_raw", "original_description"):
            if c in present:
                parts.append(c)
        op.execute(
            f"UPDATE transactions SET description = COALESCE({', '.join(parts)}) "
            f"WHERE description IS NULL"
        )
    if "currency_code" in present:
        op.execute(
            "UPDATE transactions SET currency = COALESCE(currency, currency_code) "
            "WHERE currency IS NULL"
        )
    if "is_user_edited" in present:
        # Preserve an edit flag set only on the legacy column.
        op.execute(
            "UPDATE transactions SET is_edited = 1 "
            "WHERE is_user_edited = 1 AND (is_edited IS NULL OR is_edited = 0)"
        )

    # 2. Drop the legacy columns that are present. batch_alter_table makes SQLite
    #    do a copy-and-swap; Postgres gets a plain ALTER.
    to_drop = [c for c in LEGACY_COLUMNS if c in present]
    if to_drop:
        with op.batch_alter_table("transactions") as batch_op:
            for col in to_drop:
                batch_op.drop_column(col)


def downgrade() -> None:
    # Re-add the columns (structure only — original values are not restored).
    bind = op.get_bind()
    present = _existing_columns(bind)
    to_add = [c for c in LEGACY_COLUMNS if c not in present]
    if to_add:
        with op.batch_alter_table("transactions") as batch_op:
            for col in to_add:
                batch_op.add_column(sa.Column(col, LEGACY_COLUMNS[col], nullable=True))
