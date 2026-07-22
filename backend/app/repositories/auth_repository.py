"""All SQLAlchemy queries for the auth flow. No business rules here — just
CRUD against User, EmailVerificationToken, RefreshToken, and TokenBlacklist.
app/services/auth_service.py is the caller; it decides what the results mean.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import User, EmailVerificationToken, RefreshToken, TokenBlacklist


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def create_user(db: Session, email: str, password_hash: str, name: str, monthly_budget: float) -> User:
    user = User(
        email=email,
        password_hash=password_hash,
        full_name=name,
        monthly_budget=monthly_budget,
        email_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def mark_user_verified(db: Session, user: User) -> None:
    user.email_verified = True
    db.commit()


def delete_user_cascade(db: Session, user_id: int) -> None:
    """Raw-SQL cascade delete for the user's data. Auth tables
    (email_verification_tokens, refresh_tokens) clean up on their own via
    ON DELETE CASCADE; token_blacklist has no FK to users, so nothing to do there."""
    import sqlalchemy as sa
    for table in ("transactions", "uploaded_files", "accounts", "merchant_rules", "projects"):
        try:
            db.execute(sa.text(f"DELETE FROM {table} WHERE user_id = :uid"), {"uid": user_id})
        except Exception:
            pass
    try:
        db.execute(sa.text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})
    except Exception:
        pass
    db.commit()


def create_verification_token(db: Session, user_id: int, token: str, expires_at: datetime) -> EmailVerificationToken:
    row = EmailVerificationToken(user_id=user_id, token=token, expires_at=expires_at)
    db.add(row)
    db.commit()
    return row


def get_verification_token(db: Session, token: str) -> Optional[EmailVerificationToken]:
    return db.query(EmailVerificationToken).filter(EmailVerificationToken.token == token).first()


def mark_verification_token_used(db: Session, row: EmailVerificationToken) -> None:
    row.used = True
    db.commit()


def create_refresh_token(db: Session, user_id: int, jti: str, expires_at: datetime) -> RefreshToken:
    row = RefreshToken(user_id=user_id, jti=jti, expires_at=expires_at)
    db.add(row)
    db.commit()
    return row


def get_refresh_token_by_jti(db: Session, jti: str) -> Optional[RefreshToken]:
    return db.query(RefreshToken).filter(RefreshToken.jti == jti).first()


def revoke_refresh_token(db: Session, row: RefreshToken) -> None:
    row.revoked = True
    db.commit()


def is_jti_blacklisted(db: Session, jti: str) -> bool:
    return db.query(TokenBlacklist).filter(TokenBlacklist.jti == jti).first() is not None


def blacklist_jti(db: Session, jti: str, expires_at: datetime, user_id: int) -> None:
    if is_jti_blacklisted(db, jti):
        return
    db.add(TokenBlacklist(user_id=user_id, jti=jti, expires_at=expires_at))
    db.commit()
