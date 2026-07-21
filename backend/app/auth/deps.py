from fastapi import Depends, HTTPException

from .security import decode_token, security


def get_current_user(credentials=Depends(security)) -> int:
    """Resolve the authenticated user's id from the bearer token.
    Raises 401 if missing/invalid. Returns the integer user_id.

    users.id was migrated from a UUID string to an integer PK. A token
    issued before that migration carries a UUID `sub` — reject it with 401
    (not 500) so the client cleanly re-prompts login instead of erroring.
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(credentials.credentials)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        return int(payload["sub"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Session expired, please log in again")
