from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.db import get_db
from app.auth import get_current_user
from app.models import TransactionRule

router = APIRouter()


class RuleCreate(BaseModel):
    match_field: str = "description"
    match_operator: str = "contains"
    match_value: str
    output_transaction_type: Optional[str] = None
    output_category: Optional[str] = None
    priority: int = 0


@router.get("/rules")
def get_rules(db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    rules = db.query(TransactionRule).filter(TransactionRule.active == True, TransactionRule.user_id == current_user).order_by(TransactionRule.priority.desc()).all()
    return [{"id": r.id, "match_field": r.match_field, "match_operator": r.match_operator, "match_value": r.match_value, "output_transaction_type": r.output_transaction_type, "output_category": r.output_category, "priority": r.priority} for r in rules]

@router.post("/rules")
def create_rule(rule: RuleCreate, db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    new_rule = TransactionRule(
        match_field=rule.match_field,
        match_operator=rule.match_operator,
        match_value=rule.match_value,
        output_transaction_type=rule.output_transaction_type,
        output_category=rule.output_category,
        priority=rule.priority,
        active=True,
        user_id=current_user,
    )
    db.add(new_rule)
    db.commit()
    return {"success": True, "rule_id": new_rule.id}

@router.delete("/rules/{rid}")
def delete_rule(rid: str, db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    rule = db.query(TransactionRule).filter(TransactionRule.id == rid, TransactionRule.user_id == current_user).first()
    if not rule:
        raise HTTPException(404, "Not found")
    db.delete(rule)
    db.commit()
    return {"success": True}
