from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from .security import decode_token, security
from app.db import get_db
from app.repositories import auth_repository


def get_current_access_payload(credentials=Depends(security), db: Session = Depends(get_db)) -> dict:
    """Decode + fully validate the bearer token: signature, `type == "access"`,
    and not blacklisted (logged out). Returns the raw JWT payload (sub, email,
    jti, exp) so callers that need the jti (logout) don't have to re-decode."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(credentials.credentials)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token")
    jti = payload.get("jti")
    if jti and auth_repository.is_jti_blacklisted(db, jti):
        raise HTTPException(status_code=401, detail="Session has been logged out")
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError):
        return payload  # malformed sub — get_current_user() below raises its own clean 401
    user = auth_repository.get_user_by_id(db, user_id)
    if user and user.is_deleted:
        # An already-issued access token shouldn't keep working just because
        # it hasn't naturally expired yet — deletion should be immediate, not
        # "wait a few minutes" (unlike the password-change case, which relies
        # on natural expiry since it's less final than an account deletion).
        raise HTTPException(status_code=401, detail="This account no longer exists")
    return payload


def get_current_user(payload: dict = Depends(get_current_access_payload)) -> int:
    """Resolve the authenticated user's id from the bearer token.
    Raises 401 if missing/invalid/expired/blacklisted. Returns the integer user_id.

    users.id was migrated from a UUID string to an integer PK. A token
    issued before that migration carries a UUID `sub` — reject it with 401
    (not 500) so the client cleanly re-prompts login instead of erroring.
    """
    try:
        return int(payload["sub"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Session expired, please log in again")
