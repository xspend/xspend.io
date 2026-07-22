import base64
import uuid
from datetime import datetime, timedelta
from typing import Optional, Tuple
from jose import JWTError, jwt
import bcrypt
from fastapi.security import HTTPBearer

from .config import settings

SECRET_KEY = settings.jwt_secret_key
ALGORITHM = "HS256"

# Access tokens are short-lived (checked on every request); refresh tokens are
# long-lived and only used to mint a new access token. Each carries its own
# `jti` so the DB-backed refresh/blacklist tables can reference a specific
# token without ever storing the JWT itself.
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
    except:
        return False

def create_access_token(user_id, email: str) -> Tuple[str, str, datetime]:
    """Returns (token, jti, expires_at). Callers don't need to persist access
    tokens anywhere — they're validated by signature + type + blacklist lookup."""
    jti = str(uuid.uuid4())
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    token = jwt.encode(
        {"sub": str(user_id), "email": email, "type": "access", "jti": jti, "exp": expire},
        SECRET_KEY, algorithm=ALGORITHM
    )
    return token, jti, expire

def create_refresh_token(user_id) -> Tuple[str, str, datetime]:
    """Returns (token, jti, expires_at). The jti is what gets stored in the
    refresh_tokens table — the token itself is never persisted."""
    jti = str(uuid.uuid4())
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    token = jwt.encode(
        {"sub": str(user_id), "type": "refresh", "jti": jti, "exp": expire},
        SECRET_KEY, algorithm=ALGORITHM
    )
    return token, jti, expire

def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None

def encode_id(id_: int) -> str:
    """Obfuscates an integer id for use in a URL (e.g. the `eid` on a
    verification link) so it doesn't read as a raw sequential DB id. This is
    NOT a security boundary — it's reversible with no secret involved, just a
    cheap sanity check alongside the real token."""
    return base64.urlsafe_b64encode(str(id_).encode()).decode().rstrip("=")

def decode_id(encoded: str) -> Optional[int]:
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        return int(base64.urlsafe_b64decode(padded).decode())
    except (ValueError, UnicodeDecodeError):
        return None
