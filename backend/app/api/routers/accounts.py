from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.db import get_db
from app.models import Account

router = APIRouter()


class AccountCreate(BaseModel):
    account_name: str
    account_type: str = "checking"
    institution_name: Optional[str] = None
    last4_masked: Optional[str] = None


def _account_to_dict(a: Account) -> dict:
    # Hand-built to keep the JSON response shape stable across the PK rename
    # (id was `account_id`) — this used to return the raw ORM object, which
    # FastAPI serialized via `vars(obj)`, emitting every column verbatim.
    return {
        "account_id": a.id,
        "user_id": a.user_id,
        "account_name": a.account_name,
        "account_type": a.account_type,
        "institution_name": a.institution_name,
        "last4_masked": a.last4_masked,
        "is_active": a.is_active,
        "created_at": str(a.created_at) if a.created_at else None,
    }


@router.get("/accounts")
def get_accounts(db: Session = Depends(get_db)):
    accts = db.query(Account).filter(Account.is_active == True).all()
    return [_account_to_dict(a) for a in accts]

@router.post("/accounts")
def create_account(data: AccountCreate, db: Session = Depends(get_db)):
    acct = Account(
        account_name=data.account_name,
        account_type=data.account_type,
        institution_name=data.institution_name,
        last4_masked=data.last4_masked,
    )
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return _account_to_dict(acct)
