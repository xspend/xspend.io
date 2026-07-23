"""Auth business logic: signup, email verification, login, token refresh,
logout. Coordinates app/repositories/auth_repository.py (DB) and
app/core/security.py (hashing/JWTs) and app/services/email_service.py
(sending mail) — the router just calls these and translates AuthError into
the right HTTP status.
"""
import math
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.models import User
from app.repositories import auth_repository
from . import email_service


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


class InvalidResetToken(AuthError):
    status_code = 400


class InvalidRefreshToken(AuthError):
    status_code = 401


class InvalidOtp(AuthError):
    status_code = 401


class TooManyOtpAttempts(AuthError):
    status_code = 429


def _create_verification_token(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS)
    auth_repository.create_verification_token(db, user.id, token, expires_at)
    return token


def _lockout_message(locked_until: datetime) -> str:
    remaining_seconds = (locked_until - datetime.utcnow()).total_seconds()
    remaining_minutes = max(1, math.ceil(remaining_seconds / 60))
    return f"Too many incorrect attempts. Try again in {remaining_minutes} minute(s)."


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


async def forgot_password(db: Session, email: str) -> None:
    """Deliberately silent on an unknown email — unlike resend_verification,
    this endpoint must not reveal whether an address is registered. The
    router always returns the same generic message regardless of what
    happens here."""
    email = email.lower().strip()
    user = auth_repository.get_user_by_email(db, email)
    if not user:
        return
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES)
    auth_repository.create_password_reset_token(db, user.id, token, expires_at)
    await email_service.send_password_reset_email(user.email, token, user.id)


def reset_password(db: Session, token: str, new_password: str, eid: Optional[str] = None) -> User:
    row = auth_repository.get_password_reset_token(db, token)
    if not row:
        raise InvalidResetToken("Invalid or expired reset link")
    if row.used:
        raise InvalidResetToken("This reset link has already been used")
    if row.expires_at < datetime.utcnow():
        raise InvalidResetToken("This reset link has expired — request a new one")
    if eid is not None and security.decode_id(eid) != row.user_id:
        raise InvalidResetToken("Invalid or expired reset link")
    user = auth_repository.get_user_by_id(db, row.user_id)
    if not user:
        raise InvalidResetToken("Invalid or expired reset link")

    auth_repository.mark_password_reset_token_used(db, row)
    auth_repository.update_user_password(db, user, security.hash_password(new_password))
    # a changed password should end every other session, not just this request
    auth_repository.revoke_all_refresh_tokens_for_user(db, user.id)
    return user


def change_password(db: Session, user_id: int, current_password: str, new_password: str) -> None:
    """For an already-logged-in user changing their password on purpose
    (knows the current one) — as opposed to reset_password(), which is the
    forgot-password recovery path via an emailed token. Also revokes every
    refresh token, same as a reset: the current access token still works
    until it naturally expires, but nothing can mint a new one off the old
    password's sessions."""
    user = auth_repository.get_user_by_id(db, user_id)
    if not user:
        raise UserNotFound("User not found")
    if not security.verify_password(current_password, user.password_hash or ""):
        raise InvalidCredentials("Current password is incorrect")
    auth_repository.update_user_password(db, user, security.hash_password(new_password))
    auth_repository.revoke_all_refresh_tokens_for_user(db, user.id)


async def login(db: Session, email: str, password: str) -> str:
    """Checks email+password (factor 1), then emails a fresh OTP (factor 2)
    and returns the login_token the client must present, along with that
    OTP, to verify_login_otp(). No access/refresh tokens are issued here —
    that only happens once the OTP checks out.

    Only one challenge exists per user at a time — a fresh login overwrites
    whatever OTP was already pending. If the previous challenge was locked
    out from too many wrong attempts, login is refused until that lock
    expires, so a wrong-password guesser can't just call /login again to
    reset their own OTP attempt counter."""
    email = email.lower().strip()
    user = auth_repository.get_user_by_email(db, email)
    if not user or not security.verify_password(password, user.password_hash or ""):
        raise InvalidCredentials("Invalid email or password")
    if user.is_deleted:
        # Defense in depth — the mangled email on soft-delete already means
        # this lookup should never match the original address in the first
        # place, but check explicitly in case that ever isn't true.
        raise InvalidCredentials("Invalid email or password")
    if not user.email_verified:
        raise EmailNotVerified("Please verify your email before logging in")

    existing = auth_repository.get_login_otp_by_user_id(db, user.id)
    if existing and existing.locked_until and existing.locked_until > datetime.utcnow():
        raise TooManyOtpAttempts(_lockout_message(existing.locked_until))

    login_token = secrets.token_urlsafe(32)
    otp = security.generate_otp()
    expires_at = datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
    auth_repository.upsert_login_otp(db, user.id, login_token, security.hash_password(otp), expires_at)
    await email_service.send_login_otp_email(user.email, otp)
    return login_token


def verify_login_otp(db: Session, login_token: str, otp: str) -> Tuple[str, str, User]:
    row = auth_repository.get_login_otp_by_token(db, login_token)
    if not row or row.used:
        raise InvalidOtp("Invalid or expired login attempt")
    if row.locked_until and row.locked_until > datetime.utcnow():
        raise TooManyOtpAttempts(_lockout_message(row.locked_until))
    if row.expires_at < datetime.utcnow():
        raise InvalidOtp("This code has expired.")
    if not security.verify_password(otp, row.otp_hash):
        auth_repository.increment_login_otp_attempts(db, row)
        if row.attempts >= settings.MAX_OTP_ATTEMPTS:
            locked_until = datetime.utcnow() + timedelta(minutes=settings.OTP_LOCKOUT_MINUTES)
            auth_repository.lock_login_otp(db, row, locked_until)
            raise TooManyOtpAttempts(_lockout_message(locked_until))
        raise InvalidOtp("Incorrect code")

    user = auth_repository.get_user_by_id(db, row.user_id)
    if not user:
        raise InvalidOtp("Invalid or expired login attempt")

    auth_repository.mark_login_otp_used(db, row)
    access_token, refresh_token = _issue_token_pair(db, user)
    return access_token, refresh_token, user


async def resend_otp(db: Session, login_token: str) -> str:
    """Re-sends a fresh OTP for a pending login challenge, without making the
    caller re-enter their password. Reuses the same upsert path as login()
    (same user_id row, new login_token/OTP/expiry, attempts reset) — the old
    login_token stops working once this succeeds."""
    row = auth_repository.get_login_otp_by_token(db, login_token)
    if not row or row.used:
        raise InvalidOtp("Invalid or expired login attempt")
    if row.locked_until and row.locked_until > datetime.utcnow():
        raise TooManyOtpAttempts(_lockout_message(row.locked_until))
    user = auth_repository.get_user_by_id(db, row.user_id)
    if not user:
        raise InvalidOtp("Invalid or expired login attempt")

    new_login_token = secrets.token_urlsafe(32)
    otp = security.generate_otp()
    expires_at = datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)
    auth_repository.upsert_login_otp(db, user.id, new_login_token, security.hash_password(otp), expires_at)
    await email_service.send_login_otp_email(user.email, otp)
    return new_login_token


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
    """Soft delete — flags the account and mangles its email (frees the
    address for a new signup) but keeps every row of data. Revokes every
    refresh token immediately; the current access token (if any) gets
    rejected right away too, via the is_deleted check in app/core/deps.py."""
    user = auth_repository.get_user_by_id(db, user_id)
    if not user:
        raise UserNotFound("User not found")
    auth_repository.soft_delete_user(db, user)
    auth_repository.revoke_all_refresh_tokens_for_user(db, user.id)
