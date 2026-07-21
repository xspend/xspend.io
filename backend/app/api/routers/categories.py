from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Category

router = APIRouter()


@router.get("/categories")
def get_categories(db: Session = Depends(get_db)):
    cats = db.query(Category).filter(Category.is_active == True).order_by(Category.display_order).all()
    return [{"id": c.id, "name": c.category_name, "group": c.category_group, "is_default": c.is_system_default} for c in cats]
