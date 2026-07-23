from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.db import get_db
from app.core.deps import get_current_user
from app.models import User, UserProfile

router = APIRouter()


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    income_amount: Optional[float] = None
    income_frequency: Optional[str] = None
    currency_code: Optional[str] = None
    payday_day: Optional[str] = None
    selected_goals: Optional[str] = None
    other_goals: Optional[str] = None
    savings_goal_monthly: Optional[float] = None
    savings_goal_weekly: Optional[float] = None
    debt_payoff_goal: Optional[float] = None
    monthly_budget: Optional[float] = None
    # Legacy
    monthly_income: Optional[float] = None
    preferred_currency: Optional[str] = None
    monthly_savings_goal: Optional[float] = None
    weekly_savings_goal: Optional[float] = None


def get_or_create_profile(db: Session) -> User:
    p = db.query(User).first()
    if not p:
        p = User(full_name="User")
        db.add(p)
        db.commit()
        db.refresh(p)
    return p


def _get_or_create_user_profile(db: Session, user_id: int) -> UserProfile:
    """Every user should already have one (created at signup, backfilled by
    migration 0010 for pre-existing users) — this is just a defensive
    fallback, not the normal path."""
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


@router.get("/profile")
def get_profile(db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    p = db.query(User).filter(User.id == current_user).first()
    if not p:
        return {"exists": False}
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user).first()
    return {
        "exists": True,
        "full_name": p.full_name,
        "email": p.email,
        "income_amount": profile.income_amount if profile else 0,
        "monthly_income": profile.income_amount if profile else 0,
        "income_frequency": profile.income_frequency if profile else "monthly",
        "currency_code": profile.currency_code if profile else "USD",
        "preferred_currency": profile.currency_code if profile else "USD",
        "payday_day": profile.payday_day if profile else None,
        "selected_goals": profile.selected_goals if profile else None,
        "other_goals": profile.other_goals if profile else None,
        "savings_goal_monthly": profile.savings_goal_monthly if profile else 0,
        "monthly_savings_goal": profile.savings_goal_monthly if profile else 0,
        "savings_goal_weekly": profile.savings_goal_weekly if profile else 0,
        "debt_payoff_goal": profile.debt_payoff_goal if profile else 0,
        "monthly_budget": profile.monthly_budget if profile else 0,
    }

@router.post("/profile")
def save_profile(data: ProfileUpdate, db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    # If budget is being updated, save to history for current month
    if data.monthly_budget is not None:
        from datetime import datetime
        current_month = datetime.now().strftime('%Y-%m')
        import sqlalchemy as _sa
        existing = db.execute(_sa.text(
            "SELECT id FROM budget_history WHERE month = :m AND user_id = :u"
        ), {'m': current_month, 'u': current_user}).fetchone()
        if existing:
            db.execute(_sa.text(
                "UPDATE budget_history SET amount = :a WHERE month = :m AND user_id = :u"
            ), {'a': data.monthly_budget, 'm': current_month, 'u': current_user})
        else:
            db.execute(_sa.text(
                "INSERT INTO budget_history (amount, month, user_id) VALUES (:a, :m, :u)"
            ), {'a': data.monthly_budget, 'm': current_month, 'u': current_user})
        db.commit()
    p = db.query(User).filter(User.id == current_user).first()
    if not p:
        raise HTTPException(status_code=404, detail="User not found")
    if data.full_name is not None: p.full_name = data.full_name
    db.commit()

    profile = _get_or_create_user_profile(db, current_user)
    if data.income_amount is not None: profile.income_amount = data.income_amount
    if data.monthly_income is not None: profile.income_amount = data.monthly_income
    if data.income_frequency is not None: profile.income_frequency = data.income_frequency
    if data.currency_code is not None: profile.currency_code = data.currency_code
    if data.preferred_currency is not None: profile.currency_code = data.preferred_currency
    if data.payday_day is not None: profile.payday_day = data.payday_day
    if data.selected_goals is not None: profile.selected_goals = data.selected_goals
    if data.other_goals is not None: profile.other_goals = data.other_goals
    if data.savings_goal_monthly is not None: profile.savings_goal_monthly = data.savings_goal_monthly
    if data.monthly_savings_goal is not None: profile.savings_goal_monthly = data.monthly_savings_goal
    if data.savings_goal_weekly is not None: profile.savings_goal_weekly = data.savings_goal_weekly
    if data.weekly_savings_goal is not None: profile.savings_goal_weekly = data.weekly_savings_goal
    if data.debt_payoff_goal is not None: profile.debt_payoff_goal = data.debt_payoff_goal
    if data.monthly_budget is not None: profile.monthly_budget = data.monthly_budget
    db.commit()
    return {"success": True}
