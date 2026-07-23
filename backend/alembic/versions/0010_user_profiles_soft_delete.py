"""user profiles and soft delete

Splits the financial/goal-planning columns off `users` into a new
`user_profiles` table (one row per user), and adds `users.is_deleted` for
soft-deleting an account (DELETE /auth/user no longer removes any data —
see app/services/auth_service.py: delete_account()).

This migration is ADDITIVE ONLY: `user_profiles` is created and backfilled
from the existing `users` columns, and `is_deleted` is added — but the 11
old financial columns are NOT dropped from `users` here. That's a separate,
deliberate follow-up migration (0011) once this one has shipped and been
verified live, per this repo's destructive-changes-are-a-separate-migration
discipline (see .claude/skills/db-migration/SKILL.md).

Revision ID: 0010_user_profiles_soft_delete
Revises: 0009_password_reset_tokens
"""
from alembic import op
import sqlalchemy as sa


revision = "0010_user_profiles_soft_delete"
down_revision = "0009_password_reset_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                   unique=True, nullable=False),
        sa.Column("income_amount", sa.Float(), server_default="0"),
        sa.Column("income_frequency", sa.String(30), server_default="monthly"),
        sa.Column("savings_goal_weekly", sa.Float(), server_default="0"),
        sa.Column("savings_goal_monthly", sa.Float(), server_default="0"),
        sa.Column("debt_payoff_goal", sa.Float(), server_default="0"),
        sa.Column("financial_goal", sa.String(100), nullable=True),
        sa.Column("selected_goals", sa.Text(), nullable=True),
        sa.Column("other_goals", sa.Text(), nullable=True),
        sa.Column("currency_code", sa.String(3), server_default="USD"),
        sa.Column("monthly_budget", sa.Float(), server_default="0"),
        sa.Column("payday_day", sa.String(), nullable=True),
    )

    op.execute("""
        INSERT INTO user_profiles (
            user_id, income_amount, income_frequency, savings_goal_weekly,
            savings_goal_monthly, debt_payoff_goal, financial_goal,
            selected_goals, other_goals, currency_code, monthly_budget, payday_day
        )
        SELECT
            id, income_amount, income_frequency, savings_goal_weekly,
            savings_goal_monthly, debt_payoff_goal, financial_goal,
            selected_goals, other_goals, currency_code, monthly_budget, payday_day
        FROM users
    """)

    op.add_column(
        "users",
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "is_deleted")
    op.drop_table("user_profiles")
