"""password reset tokens

Adds `password_reset_tokens` for the forgot-password flow — same shape as
email_verification_tokens (single-use, expiring, emailed token proving
ownership of the account's email), kept as its own table since the two flows
have different expiries and shouldn't cross-affect each other.

user_id is ON DELETE CASCADE from users.id, same as every other user-owned
auth table.

Revision ID: 0009_password_reset_tokens
Revises: 0008_login_otps_single_row
"""
from alembic import op
import sqlalchemy as sa


revision = "0009_password_reset_tokens"
down_revision = "0008_login_otps_single_row"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_password_reset_tokens_token", "password_reset_tokens", ["token"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_password_reset_tokens_token", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
