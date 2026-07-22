from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.db import get_db
from app.core.deps import get_current_user
from app.models import User

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


@router.get("/profile")
def get_profile(db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    p = db.query(User).filter(User.id == current_user).first()
    if not p:
        return {"exists": False}
    return {
        "exists": True,
        "full_name": p.full_name,
        "email": p.email,
        "income_amount": p.income_amount,
        "monthly_income": p.income_amount,
        "income_frequency": p.income_frequency,
        "currency_code": p.currency_code,
        "preferred_currency": p.currency_code,
        "payday_day": p.payday_day,
        "selected_goals": p.selected_goals,
        "other_goals": p.other_goals,
        "savings_goal_monthly": p.savings_goal_monthly,
        "monthly_savings_goal": p.savings_goal_monthly,
        "savings_goal_weekly": p.savings_goal_weekly,
        "debt_payoff_goal": p.debt_payoff_goal,
        "monthly_budget": p.monthly_budget,
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
    if data.income_amount is not None: p.income_amount = data.income_amount
    if data.monthly_income is not None: p.income_amount = data.monthly_income
    if data.income_frequency is not None: p.income_frequency = data.income_frequency
    if data.currency_code is not None: p.currency_code = data.currency_code
    if data.preferred_currency is not None: p.currency_code = data.preferred_currency
    if data.payday_day is not None: p.payday_day = data.payday_day
    if data.selected_goals is not None: p.selected_goals = data.selected_goals
    if data.other_goals is not None: p.other_goals = data.other_goals
    if data.savings_goal_monthly is not None: p.savings_goal_monthly = data.savings_goal_monthly
    if data.monthly_savings_goal is not None: p.savings_goal_monthly = data.monthly_savings_goal
    if data.savings_goal_weekly is not None: p.savings_goal_weekly = data.savings_goal_weekly
    if data.weekly_savings_goal is not None: p.savings_goal_weekly = data.weekly_savings_goal
    if data.debt_payoff_goal is not None: p.debt_payoff_goal = data.debt_payoff_goal
    if data.monthly_budget is not None: p.monthly_budget = data.monthly_budget
    db.commit()
    return {"success": True}
