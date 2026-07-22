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
