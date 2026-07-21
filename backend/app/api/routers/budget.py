from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth import get_current_user

router = APIRouter()


@router.get("/budget-history")
def get_budget_history(db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    import sqlalchemy as _sa
    rows = db.execute(_sa.text(
        "SELECT month, amount FROM budget_history WHERE user_id = :u ORDER BY month DESC"
    ), {'u': current_user}).fetchall()
    return {row[0]: row[1] for row in rows}
