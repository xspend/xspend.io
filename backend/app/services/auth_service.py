"""Auth business logic: signup, email verification, login, token refresh,
logout. Coordinates app/repositories/auth_repository.py (DB) and
app/core/security.py (hashing/JWTs) and app/services/email_service.py
(sending mail) — the router just calls these and translates AuthError into
the right HTTP status.
"""
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.core import security
from app.models import User
from app.repositories import auth_repository
from . import email_service

EMAIL_VERIFICATION_EXPIRE_HOURS = 24


class AuthError(Exception):
    """Base for auth failures. `status_code` is the HTTP status the router
    should respond with — keeps the router's error handling to one clause."""
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class EmailAlreadyRegistered(AuthError):
    status_code = 400


class InvalidCredentials(AuthError):
    status_code = 401


class EmailNotVerified(AuthError):
    status_code = 403


class UserNotFound(AuthError):
    status_code = 404


class AlreadyVerified(AuthError):
    status_code = 400


class InvalidVerificationToken(AuthError):
    status_code = 400


class InvalidRefreshToken(AuthError):
    status_code = 401


def _create_verification_token(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=EMAIL_VERIFICATION_EXPIRE_HOURS)
    auth_repository.create_verification_token(db, user.id, token, expires_at)
    return token


def _issue_token_pair(db: Session, user: User) -> Tuple[str, str]:
    access_token, _jti, _exp = security.create_access_token(user.id, user.email)
    refresh_token, refresh_jti, refresh_exp = security.create_refresh_token(user.id)
    auth_repository.create_refresh_token(db, user.id, refresh_jti, refresh_exp)
    return access_token, refresh_token


async def signup(db: Session, email: str, password: str, name: str) -> User:
    email = email.lower().strip()
    if auth_repository.get_user_by_email(db, email):
        raise EmailAlreadyRegistered("Email already registered")
    # monthly_budget isn't collected at signup — it starts at 0 and gets set
    # later via the budget/profile flow.
    user = auth_repository.create_user(db, email, security.hash_password(password), name, monthly_budget=0)
    token = _create_verification_token(db, user)
    await email_service.send_verification_email(user.email, token, user.id)
    return user


def verify_email(db: Session, token: str, eid: Optional[str] = None) -> User:
    row = auth_repository.get_verification_token(db, token)
    if not row:
        raise InvalidVerificationToken("Invalid verification token")
    if row.used:
        raise InvalidVerificationToken("This verification link has already been used")
    if row.expires_at < datetime.utcnow():
        raise InvalidVerificationToken("This verification link has expired — request a new one")
    # `eid` (encoded id) is a cheap sanity check carried on the link, not the
    # source of truth — the token lookup above already proves ownership. A
    # mismatch here means the link got tampered with or copy-pasted wrong.
    if eid is not None and security.decode_id(eid) != row.user_id:
        raise InvalidVerificationToken("Invalid verification token")
    user = auth_repository.get_user_by_id(db, row.user_id)
    if not user:
        raise InvalidVerificationToken("Invalid verification token")
    auth_repository.mark_verification_token_used(db, row)
    auth_repository.mark_user_verified(db, user)
    return user


async def resend_verification(db: Session, email: str) -> None:
    email = email.lower().strip()
    user = auth_repository.get_user_by_email(db, email)
    if not user:
        raise UserNotFound("No account found with that email")
    if user.email_verified:
        raise AlreadyVerified("This email is already verified")
    token = _create_verification_token(db, user)
    await email_service.send_verification_email(user.email, token, user.id)


def login(db: Session, email: str, password: str) -> Tuple[str, str, User]:
    email = email.lower().strip()
    user = auth_repository.get_user_by_email(db, email)
    if not user or not security.verify_password(password, user.password_hash or ""):
        raise InvalidCredentials("Invalid email or password")
    if not user.email_verified:
        raise EmailNotVerified("Please verify your email before logging in")
    access_token, refresh_token = _issue_token_pair(db, user)
    return access_token, refresh_token, user


def refresh(db: Session, refresh_token: str) -> Tuple[str, str]:
    payload = security.decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise InvalidRefreshToken("Invalid refresh token")

    jti = payload.get("jti")
    row = auth_repository.get_refresh_token_by_jti(db, jti) if jti else None
    if not row or row.revoked or row.expires_at < datetime.utcnow():
        raise InvalidRefreshToken("Refresh token has been revoked or is invalid")
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError, KeyError):
        raise InvalidRefreshToken("Refresh token has been revoked or is invalid")
    user = auth_repository.get_user_by_id(db, user_id)
    if not user:
        raise InvalidRefreshToken("Refresh token has been revoked or is invalid")

    auth_repository.revoke_refresh_token(db, row)
    return _issue_token_pair(db, user)


def logout(db: Session, user_id: int, access_jti: str, access_exp, refresh_token: str = None) -> None:
    if access_jti:
        expires_at = datetime.utcfromtimestamp(access_exp) if isinstance(access_exp, (int, float)) else access_exp
        auth_repository.blacklist_jti(db, access_jti, expires_at, user_id)
    if refresh_token:
        payload = security.decode_token(refresh_token)
        if payload and payload.get("type") == "refresh" and payload.get("jti"):
            row = auth_repository.get_refresh_token_by_jti(db, payload["jti"])
            if row:
                auth_repository.revoke_refresh_token(db, row)


def get_profile(db: Session, user_id: int) -> User:
    user = auth_repository.get_user_by_id(db, user_id)
    if not user:
        raise UserNotFound("User not found")
    return user


def delete_account(db: Session, user_id: int) -> None:
    auth_repository.delete_user_cascade(db, user_id)
