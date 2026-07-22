"""Auth-only ORM models — kept in their own module since these tables exist
purely to support the auth flow (email verification, refresh tokens, logout
blacklist), not the app's domain data. Registered on the same Base as
everything else, so Alembic/create_all pick them up automatically once this
module is imported (see app/models/__init__.py).
"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.db import Base

class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=func.now())

class RefreshToken(Base):
    """One row per issued refresh token, keyed by its JWT `jti` — not the raw
    token — so we can revoke/rotate without storing the token itself."""
    __tablename__ = "refresh_tokens"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    jti = Column(String(36), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=func.now())

class LoginOtp(Base):
    """A pending 2FA challenge: login already checked email+password, now
    waiting on the emailed OTP. `login_token` is what the client holds
    between the two requests (POST /auth/login -> POST /auth/verify-otp) —
    the OTP alone isn't enough without it, so guessing OTPs requires having
    already passed the password check for that specific login attempt.
    `otp_hash` is bcrypt via the same hash_password/verify_password used for
    real passwords — never store the OTP itself. `attempts` caps brute-force
    guesses at a fixed limit (see auth_service.MAX_OTP_ATTEMPTS); once hit,
    `locked_until` blocks both retrying this OTP and starting a fresh login
    for OTP_LOCKOUT_MINUTES. `user_id` is unique — one pending/most-recent
    challenge per user, not one row per login attempt; a new login()
    overwrites the existing row instead of piling up old ones."""
    __tablename__ = "login_otps"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    login_token = Column(String(64), unique=True, nullable=False, index=True)
    otp_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, nullable=False, default=False)
    attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())

class TokenBlacklist(Base):
    """Access-token `jti`s revoked at logout. A row here makes that specific
    access token rejected for the rest of its natural expiry — cheap to check
    (one indexed lookup) and self-pruning once expires_at passes. `user_id` is
    who the access token belonged to — not used for the lookup itself (that's
    jti-only), but lets a user's blacklist rows cascade-delete with them and
    supports "revoke all of this user's sessions" later."""
    __tablename__ = "token_blacklist"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    jti = Column(String(36), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=func.now())
