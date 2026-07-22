"""auth tables

Adds the schema for the auth overhaul: email verification, refresh tokens,
and the logout blacklist.

- `users.email_verified` (Boolean, NOT NULL). Existing users are grandfathered
  to `true` on upgrade — the new email-verification gate on login must not
  lock out accounts that signed up before this migration.
- `email_verification_tokens`, `refresh_tokens`, `token_blacklist` — all new
  tables. `email_verification_tokens.user_id` and `refresh_tokens.user_id` are
  `ON DELETE CASCADE` from `users.id`, same as every other user-owned table.
  `token_blacklist` has no FK to `users` here — it's keyed by JWT `jti` alone.
  (`0006_token_blacklist_user_id` adds `user_id` to it afterward.)

Revision ID: 0005_auth_tables
Revises: 0004_pk_columns_to_id
"""
from alembic import op
import sqlalchemy as sa


revision = "0005_auth_tables"
down_revision = "0004_pk_columns_to_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute("UPDATE users SET email_verified = true")

    op.create_table(
        "email_verification_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_email_verification_tokens_token", "email_verification_tokens", ["token"], unique=True
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("jti", sa.String(36), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_refresh_tokens_jti", "refresh_tokens", ["jti"], unique=True)

    op.create_table(
        "token_blacklist",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("jti", sa.String(36), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_token_blacklist_jti", "token_blacklist", ["jti"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_token_blacklist_jti", table_name="token_blacklist")
    op.drop_table("token_blacklist")

    op.drop_index("ix_refresh_tokens_jti", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_index("ix_email_verification_tokens_token", table_name="email_verification_tokens")
    op.drop_table("email_verification_tokens")

    op.drop_column("users", "email_verified")
