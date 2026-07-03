from sqlalchemy import Column, String, Float, Date, DateTime, Boolean, Text, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import uuid

def gen_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"
    user_id = Column(String, primary_key=True, default=gen_uuid)
    full_name = Column(String(150))
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=True)
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
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

# Legacy alias
UserProfile = User

class Account(Base):
    __tablename__ = "accounts"
    account_id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, nullable=True)
    account_name = Column(String(150))
    account_type = Column(String(50), default="checking")
    institution_name = Column(String(150), nullable=True)
    last4_masked = Column(String(10), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())

class UploadedFile(Base):
    __tablename__ = "uploaded_files"
    uploaded_file_id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, nullable=True)
    account_id = Column(String, nullable=True)
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

class Category(Base):
    __tablename__ = "categories"
    category_id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, nullable=True)
    category_name = Column(String(100), nullable=False)
    category_group = Column(String(50), default="expense")
    is_system_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=True)
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
    __tablename__ = "transactions"
    transaction_id = Column(String, primary_key=True, default=gen_uuid)
    id = Column(Integer, unique=True, autoincrement=True)
    user_id = Column(String, nullable=True)
    account_id = Column(String, nullable=True)
    uploaded_file_id = Column(String, nullable=True)
    external_transaction_id = Column(String, nullable=True)
    raw_date = Column(String, nullable=True)
    raw_description = Column(String, nullable=True)
    raw_amount = Column(String, nullable=True)
    raw_category = Column(String, nullable=True)
    transaction_date = Column(Date, nullable=True)
    posted_date = Column(Date, nullable=True)
    amount = Column(Float, nullable=True)
    currency_code = Column(String(3), default="USD")
    currency = Column(String(3), default="USD")
    description_raw = Column(String(500), nullable=True)
    description_clean = Column(String(255), nullable=True)
    description = Column(String, nullable=True)
    original_description = Column(String, nullable=True)
    merchant_name = Column(String(255), nullable=True)
    bank_name_raw = Column(String(255), nullable=True)
    bank_source = Column(String, default="Unknown Bank")
    account_name = Column(String, nullable=True)
    transaction_type = Column(String(50), default="unknown")
    category_id = Column(String, nullable=True)
    category = Column(String, default="Other")
    subcategory = Column(String, nullable=True)
    notes = Column(String(500), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    project = relationship("Project", back_populates="transactions")
    project_review_pending = Column(Boolean, default=False)  # auto-added, awaiting review
    fingerprint = Column(String, index=True, nullable=True)  # NOT globally unique — see __table_args__ (unique per user)
    fingerprint_hash = Column(String(255), nullable=True)
    __table_args__ = (UniqueConstraint('fingerprint', 'user_id', name='uq_txn_fingerprint_user'),)
    is_duplicate = Column(Boolean, default=False)
    is_pending = Column(Boolean, default=False)
    status = Column(String, default="posted")
    is_user_edited = Column(Boolean, default=False)
    is_edited = Column(Boolean, default=False)
    review_status = Column(String(30), default="pending_review")
    needs_review = Column(Boolean, default=False)
    exclusion_reason = Column(String(100), nullable=True)
    classification_confidence = Column(String, default="low")
    classification_source = Column(String, default="auto")
    import_source = Column(String, nullable=True)
    is_fixed = Column(Boolean, default=False)
    fixed_confidence = Column(Float, default=0.0)
    fixed_source = Column(String, default="auto")
    fixed_suggestion_dismissed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

class TransactionRule(Base):
    __tablename__ = "transaction_rules"
    rule_id = Column(String, primary_key=True, default=gen_uuid)
    user_id = Column(String, nullable=True)
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
    user_id    = Column(String, nullable=True)

class ManualFixedExpense(Base):
    __tablename__ = "manual_fixed_expenses"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(Text, nullable=False)
    amount     = Column(Float, nullable=False)
    frequency  = Column(Text, default="monthly")
    created_at = Column(Text, server_default=func.now())
    user_id    = Column(String, nullable=True)

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
            category_id=gen_uuid(),
            category_name=name,
            category_group=group,
            is_system_default=True,
            is_active=True,
            display_order=i,
        ))
    db.commit()
