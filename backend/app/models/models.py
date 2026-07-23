from sqlalchemy import Column, String, Float, Date, DateTime, Boolean, Text, Integer, ForeignKey, UniqueConstraint, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(150))
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=True)
    email_verified = Column(Boolean, nullable=False, server_default="false", default=False)
    # Soft delete: on DELETE /auth/user, the row stays (all financial data is kept)
    # but this flips true and the email gets mangled (see auth_repository.soft_delete_user)
    # so the address frees up for a new signup.
    is_deleted = Column(Boolean, nullable=False, server_default="false", default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    accounts = relationship("Account", back_populates="user")
    uploaded_files = relationship("UploadedFile", back_populates="user")
    transactions = relationship("Transaction", back_populates="user")
    profile = relationship("UserProfile", uselist=False, back_populates="user")

class UserProfile(Base):
    """Financial/goal-planning data, split out from `users` so that table holds
    only auth/identity columns. One row per user (see the unique constraint on
    user_id) — created alongside the User row at signup (auth_repository.create_user)."""
    __tablename__ = "user_profiles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    income_amount = Column(Float, default=0)
    income_frequency = Column(String(30), default="monthly")
    savings_goal_weekly = Column(Float, default=0)
    savings_goal_monthly = Column(Float, default=0)
    debt_payoff_goal = Column(Float, default=0)
    financial_goal = Column(String(100), nullable=True)
    selected_goals = Column(Text, nullable=True)
    other_goals = Column(Text, nullable=True)
    currency_code = Column(String(3), default="USD")
    monthly_budget = Column(Float, default=0)
    payday_day = Column(String, nullable=True)

    user = relationship("User", back_populates="profile")

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    account_name = Column(String(150))
    account_type = Column(String(50), default="checking")
    institution_name = Column(String(150), nullable=True)
    last4_masked = Column(String(10), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())

    user = relationship("User", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account")

class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    file_name = Column(String(255))
    file_type = Column(String(30))
    source_type = Column(String(50), nullable=True)
    bank_name = Column(String(150), nullable=True)
    upload_status = Column(String(30), default="uploaded")
    parse_confidence = Column(Float, nullable=True)
    transactions_extracted = Column(Integer, default=0)
    duplicates_skipped = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, default=func.now())
    processed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="uploaded_files")
    transactions = relationship("Transaction", back_populates="uploaded_file")

class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    category_name = Column(String(100), nullable=False)
    category_group = Column(String(50), default="expense")
    is_system_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    name = Column(String(150), nullable=False)
    type = Column(String(30), default="custom")  # savings | debt | custom
    target_amount = Column(Float, nullable=True)
    target_date = Column(Date, nullable=True)
    is_archived = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    # Auto-populate filter (Slice 1). All nullable; empty => manual-only project.
    filter_accounts = Column(Text, nullable=True)    # JSON list of account_name strings
    filter_start_date = Column(Date, nullable=True)
    filter_end_date = Column(Date, nullable=True)
    filter_categories = Column(Text, nullable=True)  # JSON list of category strings
    is_auto = Column(Boolean, default=False)         # True when a filter is set
    transactions = relationship("Transaction", back_populates="project")

# Legacy alias
Goal = Project

class Transaction(Base):
    """A single parsed transaction.

    `id` is the integer primary key (promoted from a plain unique column to the
    real autoincrement PK — see Alembic `uuid_to_integer_pks`). The former UUID
    `transaction_id` column is gone; every reference (credit_offsets, API path
    params) now points at `id`.

    Column set was deduplicated (see Alembic `dedup_transaction_columns`): the many
    write-only / duplicate columns that used to shadow these canonical fields
    (description_raw/clean, currency_code, is_user_edited, ...) were dropped. Keep
    writes going only to the canonical column below.
    """
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    uploaded_file_id = Column(Integer, ForeignKey("uploaded_files.id"), nullable=True)
    external_transaction_id = Column(String, nullable=True)  # OFX FITID, used for dedup
    # Canonical value columns
    transaction_date = Column(Date, nullable=True)
    amount = Column(Float, nullable=True)
    currency = Column(String(3), default="USD")
    description = Column(String, nullable=True)
    bank_source = Column(String, default="Unknown Bank")
    account_name = Column(String, nullable=True)
    transaction_type = Column(String(50), default="unknown")
    category = Column(String, default="Other")
    notes = Column(String(500), nullable=True)
    # Project tagging
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    project = relationship("Project", back_populates="transactions")
    # Dedup: fingerprint is unique PER USER, never global — two users may share a txn.
    fingerprint = Column(String, index=True, nullable=True)
    __table_args__ = (UniqueConstraint('fingerprint', 'user_id', name='uq_txn_fingerprint_user'),)
    # Review / classification state
    is_pending = Column(Boolean, default=False)
    needs_review = Column(Boolean, default=False)
    is_edited = Column(Boolean, default=False)
    exclusion_reason = Column(String(100), nullable=True)
    classification_confidence = Column(String, default="low")  # echoed to UI
    import_source = Column(String, nullable=True)
    # Fixed-vs-variable expense signals
    is_fixed = Column(Boolean, default=False)
    fixed_confidence = Column(Float, default=0.0)
    fixed_source = Column(String, default="auto")
    fixed_suggestion_dismissed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="transactions")
    account = relationship("Account", back_populates="transactions")
    uploaded_file = relationship("UploadedFile", back_populates="transactions")

class TransactionRule(Base):
    __tablename__ = "transaction_rules"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    match_field = Column(String(50), default="description")
    match_operator = Column(String(30), default="contains")
    match_value = Column(String(255), nullable=False)
    output_transaction_type = Column(String(50), nullable=True)
    output_category = Column(String, nullable=True)
    priority = Column(Integer, default=0)
    active = Column(Boolean, default=True)
    apply_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())

# Legacy alias
ClassificationRule = TransactionRule

class BudgetHistory(Base):
    __tablename__ = "budget_history"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    amount     = Column(Float, nullable=False)
    month      = Column(String(7), nullable=False)  # "2026-03"
    created_at = Column(DateTime, default=func.now())
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)

class ManualFixedExpense(Base):
    __tablename__ = "manual_fixed_expenses"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(Text, nullable=False)
    amount     = Column(Float, nullable=False)
    frequency  = Column(Text, default="monthly")
    created_at = Column(Text, server_default=func.now())
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)

def seed_default_categories(db):
    if db.query(Category).filter(Category.is_system_default == True).count() > 0:
        return
    defaults = [
        # Core expense categories
        ("Food & Dining","expense"),("Groceries","expense"),
        ("Transport","expense"),("Bills & Utilities","expense"),
        ("Subscriptions","expense"),("Health","expense"),
        ("Shopping","expense"),("Entertainment","expense"),
        ("Travel","expense"),("Personal Care","expense"),
        ("Pets","expense"),("Education","expense"),
        # Added — match classifier emissions (29 canonical categories total)
        ("Baby & Kids","expense"),
        ("Bank Fees","expense"),("Cash & ATM","expense"),
        ("Gifts & Donations","expense"),("Government & Taxes","expense"),
        ("Home Improvement","expense"),("Insurance","expense"),
        ("Professional Services","expense"),
        # Income / transfers / payments / misc
        ("Salary","income"),
        ("Transfer","transfer"),("Credit Card Payment","transfer"),
        ("Card Credit","transfer"),
        ("Loan Payment","debt"),
        ("Refund","refund"),
        ("Other","expense"),
    ]
    for i,(name,group) in enumerate(defaults):
        db.add(Category(
            category_name=name,
            category_group=group,
            is_system_default=True,
            is_active=True,
            display_order=i,
        ))
    db.commit()



class ChatLog(Base):
    """One row per curated-prompt use. Monthly cap = count of rows this month.
    Doubles as analytics: which prompts do people actually use?"""
    __tablename__ = "chat_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    prompt_id = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=func.now())


class CreditOffset(Base):
    """Card statement credits/rewards netted against expenses. Previously created
    via raw `CREATE TABLE` in database.py; now the single source of truth. Existing
    query code accesses this table via raw SQL — that still works against this schema.
    `credit_transaction_id`/`matched_expense_id` point at `transactions.id` (integer).
    """
    __tablename__ = "credit_offsets"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    credit_transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    matched_expense_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)
    matched_category = Column(String(100), nullable=True)
    credit_type = Column(String(50), nullable=True)
    eligible_for_matching = Column(Integer, default=1)
    applied_amount = Column(Numeric(12, 2), nullable=False)
    unapplied_amount = Column(Numeric(12, 2), nullable=True)
    match_confidence = Column(String(20), nullable=True)
    match_method = Column(String(50), nullable=True)
    statement_period = Column(String(7), nullable=True)
    is_active = Column(Integer, default=1)
    matched_by = Column(String(20), default="system")
    created_at = Column(Text, nullable=True)
    updated_at = Column(Text, nullable=True)


class MerchantRule(Base):
    """User-correction learning rules (merchant -> category / fixed). Was defined
    as raw DDL in BOTH database.py and migrate.py (the migrate.py copy was missing
    11 columns). Consolidated here as the single source of truth. Existing query
    code accesses this table via raw SQL — that still works against this schema.
    """
    __tablename__ = "merchant_rules"
    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_keyword = Column(Text, nullable=False)
    is_fixed = Column(Integer, nullable=False)
    user_confirmed = Column(Integer, default=0)
    confidence = Column(Float, default=0.0)
    created_at = Column(Text, server_default=func.now())
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    match_field = Column(Text, default="merchant")
    match_value = Column(Text, nullable=True)
    match_type = Column(Text, default="contains")
    transaction_type = Column(Text, nullable=True)
    category = Column(Text, nullable=True)
    priority = Column(Integer, default=0)
    source = Column(Text, default="system_default")
    confidence_override = Column(Float, nullable=True)
    is_active = Column(Integer, default=1)
    updated_at = Column(Text, nullable=True)
