from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth import get_current_user, hash_password, verify_password, create_token, decode_token, security
from app.models import User

router = APIRouter()


# ── Auth Endpoints ──

@router.post("/auth/signup")
def auth_signup(data: dict, db: Session = Depends(get_db)):
    import sqlalchemy as _sa
    email = (data.get("email") or "").lower().strip()
    password = data.get("password") or ""
    name = data.get("name") or ""
    budget = float(data.get("monthly_budget") or 0)
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")
    # Basic email format + password strength checks.
    import re as _re_v
    if not _re_v.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address")
    # Common domain-typo guard (gmai.com, yaho.com, etc.) with a suggestion.
    _COMMON_TYPOS = {
        "gmai.com": "gmail.com", "gmial.com": "gmail.com", "gmal.com": "gmail.com",
        "gmail.co": "gmail.com", "gnail.com": "gmail.com", "gmaill.com": "gmail.com",
        "yaho.com": "yahoo.com", "yahooo.com": "yahoo.com", "yahoo.co": "yahoo.com",
        "hotmial.com": "hotmail.com", "hotmai.com": "hotmail.com", "hotmil.com": "hotmail.com",
        "outlok.com": "outlook.com", "outloo.com": "outlook.com",
        "iclod.com": "icloud.com", "icloud.co": "icloud.com",
    }
    _dom = email.split("@")[1] if "@" in email else ""
    if _dom in _COMMON_TYPOS:
        _user = email.split("@")[0]
        raise HTTPException(status_code=400, detail=f"Did you mean {_user}@{_COMMON_TYPOS[_dom]}? Please check your email address.")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    existing = db.execute(_sa.text("SELECT id FROM users WHERE email = :e"), {"e": email}).fetchone()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = hash_password(password)
    # Always create a NEW user (each signup is a distinct account). user_id is
    # an autoincrement integer PK — the DB assigns it, not the app.
    new_user = User(email=email, password_hash=hashed, full_name=name, monthly_budget=budget)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    user_id = new_user.id
    token = create_token(user_id, email)
    return {"token": token, "user": {"id": user_id, "email": email, "name": name, "monthly_budget": budget}}

@router.post("/auth/login")
def auth_login(data: dict, db: Session = Depends(get_db)):
    import sqlalchemy as _sa
    email = (data.get("email") or "").lower().strip()
    password = data.get("password") or ""
    user = db.execute(_sa.text(
        "SELECT id, email, password_hash, full_name, monthly_budget FROM users WHERE email = :e"
    ), {"e": email}).fetchone()
    if not user or not verify_password(password, user[2]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_token(user[0], user[1])
    return {"token": token, "user": {"id": user[0], "email": user[1], "name": user[3], "monthly_budget": user[4]}}

@router.delete("/auth/account")
def delete_account(db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    """Delete the current user and ALL of their data. Irreversible."""
    import sqlalchemy as _sa
    uid = current_user
    for tbl in ("transactions", "uploaded_files", "accounts", "merchant_rules",
                "projects"):
        try:
            db.execute(_sa.text(f"DELETE FROM {tbl} WHERE user_id = :uid"), {"uid": uid})
        except Exception:
            pass
    try:
        db.execute(_sa.text("DELETE FROM users WHERE id = :uid"), {"uid": uid})
    except Exception:
        pass
    db.commit()
    return {"success": True}


@router.get("/auth/me")
def auth_me(credentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload
