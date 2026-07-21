from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date as date_type

from app.db import get_db
from app.auth import get_current_user
from app.models import Project, Transaction

router = APIRouter()


class ProjectCreate(BaseModel):
    name: str
    type: str = "custom"  # savings | debt | custom
    target_amount: Optional[float] = None
    target_date: Optional[str] = None
    # Auto-populate filter (Slice 2). All optional; omit => manual project.
    filter_accounts: Optional[list] = None      # list of account_name strings
    filter_start_date: Optional[str] = None     # "YYYY-MM-DD"
    filter_end_date: Optional[str] = None       # "YYYY-MM-DD"
    filter_categories: Optional[list] = None    # list of category strings

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    target_amount: Optional[float] = None
    target_date: Optional[str] = None
    is_archived: Optional[bool] = None

class TransactionProjectUpdate(BaseModel):
    project_id: Optional[int] = None

@router.get("/projects")
def get_projects(include_archived: bool = False, db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    q = db.query(Project).filter(Project.user_id == current_user)
    if not include_archived:
        q = q.filter(Project.is_archived == False)
    projects = q.order_by(Project.created_at.desc()).all()
    result = []
    for p in projects:
        progress = calculate_project_progress(p)
        result.append({
            "id": p.id,
            "name": p.name,
            "type": p.type,
            "target_amount": p.target_amount,
            "target_date": str(p.target_date) if p.target_date else None,
            "is_archived": p.is_archived,
            "created_at": str(p.created_at),
            **progress
        })
    return result

def _match_project_transactions(db, user_id, accounts=None, start_date=None,
                                end_date=None, categories=None, only_unassigned=False):
    """Single source of truth for project filter matching. Returns a Transaction query.
    Matches money-out / money-back rows only: expense, refund, transfer, cash.
    Each filter clause is applied only if that filter is provided."""
    import sqlalchemy as _sa
    q = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.is_pending == False,
        Transaction.transaction_type.in_(['expense', 'refund', 'transfer', 'cash']),
    )
    if accounts:
        q = q.filter(Transaction.bank_source.in_(accounts))
    if start_date:
        q = q.filter(Transaction.transaction_date >= start_date)
    if end_date:
        q = q.filter(Transaction.transaction_date <= end_date)
    if categories:
        q = q.filter(Transaction.category.in_(categories))
    if only_unassigned:
        q = q.filter(Transaction.project_id == None)  # noqa: E711
    return q


def _has_project_filter(p):
    return bool(p.filter_accounts or p.filter_start_date or p.filter_end_date or p.filter_categories)


@router.post("/projects")
def create_project(data: ProjectCreate, db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    import json as _json
    _has_filter = bool(data.filter_accounts or data.filter_start_date
                       or data.filter_end_date or data.filter_categories)
    p = Project(
        user_id=current_user,
        name=data.name,
        type=data.type,
        target_amount=data.target_amount,
        target_date=datetime.strptime(data.target_date, "%Y-%m-%d").date() if data.target_date else None,
        filter_accounts=_json.dumps(data.filter_accounts) if data.filter_accounts else None,
        filter_start_date=datetime.strptime(data.filter_start_date, "%Y-%m-%d").date() if data.filter_start_date else None,
        filter_end_date=datetime.strptime(data.filter_end_date, "%Y-%m-%d").date() if data.filter_end_date else None,
        filter_categories=_json.dumps(data.filter_categories) if data.filter_categories else None,
        is_auto=_has_filter,
    )
    db.add(p)
    db.commit()
    db.refresh(p)

    # Populate matching transactions immediately (only unassigned ones, so we
    # never steal a transaction already belonging to another project).
    added = 0
    if _has_filter:
        matches = _match_project_transactions(
            db, current_user,
            accounts=data.filter_accounts,
            start_date=p.filter_start_date,
            end_date=p.filter_end_date,
            categories=data.filter_categories,
            only_unassigned=True,
        ).all()
        for t in matches:
            t.project_id = p.id
            # created-with-filter matches are NOT flagged for review — the user
            # explicitly defined this filter. Only later auto-adds (Slice 3) flag.
        added = len(matches)
        db.commit()

    return {"id": p.id, "name": p.name, "type": p.type,
            "target_amount": p.target_amount, "transactions_added": added}

@router.patch("/projects/{pid}")
def update_project(pid: int, data: ProjectUpdate, db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    p = db.query(Project).filter(Project.id == pid, Project.user_id == current_user).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    if data.name is not None: p.name = data.name
    if data.type is not None: p.type = data.type
    if data.target_amount is not None: p.target_amount = data.target_amount
    if data.target_date is not None: p.target_date = datetime.strptime(data.target_date, "%Y-%m-%d").date()
    if data.is_archived is not None: p.is_archived = data.is_archived
    db.commit()
    return {"success": True}

@router.delete("/projects/{pid}")
def delete_project(pid: int, db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    p = db.query(Project).filter(Project.id == pid, Project.user_id == current_user).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    # Unlink transactions
    db.query(Transaction).filter(Transaction.project_id == pid, Transaction.user_id == current_user).update({"project_id": None})
    db.delete(p)
    db.commit()
    return {"success": True}

@router.get("/projects/{pid}/progress")
def get_project_progress(pid: int, db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    p = db.query(Project).filter(Project.id == pid, Project.user_id == current_user).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"id": p.id, "name": p.name, **calculate_project_progress(p)}

@router.patch("/transactions/{tid}/project")
def update_transaction_project(tid: int, data: TransactionProjectUpdate, db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    t = db.query(Transaction).filter(Transaction.id == tid).first()
    if not t:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if t.user_id != current_user:
        raise HTTPException(status_code=403, detail="Not authorized")
    t.project_id = data.project_id
    db.commit()
    return {"success": True}

def calculate_project_progress(p: Project) -> dict:
    txns = p.transactions if p.transactions else []
    if p.type == "debt":
        current = sum(abs(t.amount) for t in txns if t.amount and t.amount < 0)
    else:
        current = sum(t.amount for t in txns if t.amount and t.amount > 0)
    target = p.target_amount or 0
    pct = min(round((current / target * 100), 1), 100) if target > 0 else 0
    remaining = max(target - current, 0) if target > 0 else None
    on_track = None
    if p.target_date and target > 0 and p.created_at:
        days_total = (p.target_date - p.created_at.date()).days
        days_elapsed = (date_type.today() - p.created_at.date()).days
        if days_total > 0:
            expected = (days_elapsed / days_total) * target
            on_track = current >= expected * 0.9
    return {
        "current_amount": round(current, 2),
        "percentage": pct,
        "remaining": round(remaining, 2) if remaining is not None else None,
        "on_track": on_track,
        "transaction_count": len(txns),
    }
