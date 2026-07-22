"""token_blacklist.user_id

Adds a user_id FK to token_blacklist, ON DELETE CASCADE from users.id — same
as every other user-owned table. Without it, a blacklist row can't be tied
back to who it belonged to, so it never cleans up when the account is
deleted and there's no way to query "this user's revoked sessions."

NOT NULL with no server_default: token_blacklist only ever held ephemeral,
short-lived revocation records (rows self-prune once expires_at passes), so
there's no realistic populated-table case to backfill — verify with
`SELECT COUNT(*) FROM token_blacklist` before running this anywhere it might
not be empty.

Revision ID: 0006_token_blacklist_user_id
Revises: 0005_auth_tables
"""
from alembic import op
import sqlalchemy as sa


revision = "0006_token_blacklist_user_id"
down_revision = "0005_auth_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("token_blacklist") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=False))
        batch_op.create_foreign_key(
            "fk_token_blacklist_user_id_users", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )


def downgrade() -> None:
    with op.batch_alter_table("token_blacklist") as batch_op:
        batch_op.drop_constraint("fk_token_blacklist_user_id_users", type_="foreignkey")
        batch_op.drop_column("user_id")
