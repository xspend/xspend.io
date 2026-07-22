"""All SQLAlchemy queries for the auth flow. No business rules here — just
CRUD against User, EmailVerificationToken, RefreshToken, TokenBlacklist,
LoginOtp, and PasswordResetToken. app/services/auth_service.py is the
caller; it decides what the results mean.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    User, EmailVerificationToken, RefreshToken, TokenBlacklist, LoginOtp, PasswordResetToken,
)


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


def update_user_password(db: Session, user: User, password_hash: str) -> None:
    user.password_hash = password_hash
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


def revoke_all_refresh_tokens_for_user(db: Session, user_id: int) -> None:
    """Kills every other session on password reset — a stolen/old password
    shouldn't leave existing refresh tokens usable to mint new access
    tokens forever. Access tokens already issued still run out their normal
    (short) expiry; there's no registry of live access-token jtis to
    blacklist en masse."""
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id, RefreshToken.revoked == False  # noqa: E712
    ).update({"revoked": True})
    db.commit()


def is_jti_blacklisted(db: Session, jti: str) -> bool:
    return db.query(TokenBlacklist).filter(TokenBlacklist.jti == jti).first() is not None


def blacklist_jti(db: Session, jti: str, expires_at: datetime, user_id: int) -> None:
    if is_jti_blacklisted(db, jti):
        return
    db.add(TokenBlacklist(user_id=user_id, jti=jti, expires_at=expires_at))
    db.commit()


def get_login_otp_by_user_id(db: Session, user_id: int) -> Optional[LoginOtp]:
    return db.query(LoginOtp).filter(LoginOtp.user_id == user_id).first()


def get_login_otp_by_token(db: Session, login_token: str) -> Optional[LoginOtp]:
    return db.query(LoginOtp).filter(LoginOtp.login_token == login_token).first()


def upsert_login_otp(db: Session, user_id: int, login_token: str, otp_hash: str, expires_at: datetime) -> LoginOtp:
    """One row per user (see the unique constraint on user_id) — a fresh
    login overwrites whatever challenge, used or not, was already there."""
    row = get_login_otp_by_user_id(db, user_id)
    if row:
        row.login_token = login_token
        row.otp_hash = otp_hash
        row.expires_at = expires_at
        row.used = False
        row.attempts = 0
        row.locked_until = None
    else:
        row = LoginOtp(user_id=user_id, login_token=login_token, otp_hash=otp_hash, expires_at=expires_at)
        db.add(row)
    db.commit()
    return row


def increment_login_otp_attempts(db: Session, row: LoginOtp) -> None:
    row.attempts += 1
    db.commit()


def lock_login_otp(db: Session, row: LoginOtp, locked_until: datetime) -> None:
    row.locked_until = locked_until
    db.commit()


def mark_login_otp_used(db: Session, row: LoginOtp) -> None:
    row.used = True
    db.commit()


def create_password_reset_token(db: Session, user_id: int, token: str, expires_at: datetime) -> PasswordResetToken:
    row = PasswordResetToken(user_id=user_id, token=token, expires_at=expires_at)
    db.add(row)
    db.commit()
    return row


def get_password_reset_token(db: Session, token: str) -> Optional[PasswordResetToken]:
    return db.query(PasswordResetToken).filter(PasswordResetToken.token == token).first()


def mark_password_reset_token_used(db: Session, row: PasswordResetToken) -> None:
    row.used = True
    db.commit()
