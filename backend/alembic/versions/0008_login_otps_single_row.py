"""login otps single row + lockout

0007 let login() insert a fresh row per attempt, so login_otps accumulated
one row per login instead of tracking "the current challenge" for a user.
This adds:
  - a unique constraint on user_id — one row per user; a fresh POST
    /auth/login overwrites the existing row instead of adding another.
  - `locked_until` — once MAX_OTP_ATTEMPTS wrong guesses are made, the row
    locks for OTP_LOCKOUT_MINUTES; both retrying that OTP and starting a
    new login are refused until it passes (see app/services/auth_service.py).

Pre-migration cleanup: keeps only the most recent row per user before adding
the unique constraint — login_otps only ever holds ephemeral challenges
(10-minute expiry), nothing there is worth backfilling across duplicates.

Revision ID: 0008_login_otps_single_row
Revises: 0007_login_otps
"""
from alembic import op
import sqlalchemy as sa


revision = "0008_login_otps_single_row"
down_revision = "0007_login_otps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM login_otps WHERE id NOT IN "
        "(SELECT MAX(id) FROM login_otps GROUP BY user_id)"
    )
    with op.batch_alter_table("login_otps") as batch_op:
        batch_op.add_column(sa.Column("locked_until", sa.DateTime(), nullable=True))
        batch_op.create_unique_constraint("uq_login_otps_user_id", ["user_id"])


def downgrade() -> None:
    with op.batch_alter_table("login_otps") as batch_op:
        batch_op.drop_constraint("uq_login_otps_user_id", type_="unique")
        batch_op.drop_column("locked_until")
