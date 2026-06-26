from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

import os as _os
# Read the JWT secret from env. In production it MUST be set — fail loud so we
# never silently fall back to a public default. Local dev keeps a fallback.
SECRET_KEY = _os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    if _os.getenv("ENVIRONMENT", "development").lower() == "production":
        raise RuntimeError("JWT_SECRET_KEY must be set in production")
    SECRET_KEY = "financeai-dev-only-secret-change-me"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode('utf-8'), hashed.encode('utf-8'))
    except:
        return False

def create_token(user_id, email: str) -> str:
    expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": str(user_id), "email": email, "exp": expire},
        SECRET_KEY, algorithm=ALGORITHM
    )

def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
