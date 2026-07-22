"""login otps

Adds `login_otps` for 2FA on login: after email+password check out, a 6-digit
OTP is emailed and login_token is returned to the client; POST
/auth/verify-otp exchanges (login_token, otp) for the actual access/refresh
pair. See app/services/auth_service.py.

user_id is ON DELETE CASCADE from users.id, same as every other user-owned
auth table.

Revision ID: 0007_login_otps
Revises: 0006_token_blacklist_user_id
"""
from alembic import op
import sqlalchemy as sa


revision = "0007_login_otps"
down_revision = "0006_token_blacklist_user_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_otps",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("login_token", sa.String(64), nullable=False),
        sa.Column("otp_hash", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_login_otps_login_token", "login_otps", ["login_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_login_otps_login_token", table_name="login_otps")
    op.drop_table("login_otps")
