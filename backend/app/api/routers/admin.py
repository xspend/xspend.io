from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Transaction, TransactionRule, UploadedFile as UploadedFileModel

router = APIRouter()


# ── Privacy: delete all ──

@router.delete("/data/all")
def delete_all_data(confirm: str = "no", db: Session = Depends(get_db)):
    if confirm != "yes":
        raise HTTPException(status_code=400, detail="Pass ?confirm=yes to delete all data")
    db.query(Transaction).delete()
    db.query(TransactionRule).delete()
    db.query(UploadedFileModel).delete()
    db.commit()
    return {"success": True, "message": "All data deleted"}
