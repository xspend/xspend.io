"""Pydantic request/response models for the auth API. Kept separate from the
router so the shapes are easy to find and reuse, and so FastAPI can build
proper Swagger schemas for every auth endpoint instead of the old `data: dict`.
"""
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

# Common domain-typo guard (gmai.com, yaho.com, etc.) — carried over from the
# original hand-rolled check in main.py, just relocated into the schema.
_COMMON_TYPOS = {
    "gmai.com": "gmail.com", "gmial.com": "gmail.com", "gmal.com": "gmail.com",
    "gmail.co": "gmail.com", "gnail.com": "gmail.com", "gmaill.com": "gmail.com",
    "yaho.com": "yahoo.com", "yahooo.com": "yahoo.com", "yahoo.co": "yahoo.com",
    "hotmial.com": "hotmail.com", "hotmai.com": "hotmail.com", "hotmil.com": "hotmail.com",
    "outlok.com": "outlook.com", "outloo.com": "outlook.com",
    "iclod.com": "icloud.com", "icloud.co": "icloud.com",
}

def _check_typo(email: str) -> str:
    domain = email.split("@")[1] if "@" in email else ""
    if domain in _COMMON_TYPOS:
        user = email.split("@")[0]
        raise ValueError(
            f"Did you mean {user}@{_COMMON_TYPOS[domain]}? Please check your email address."
        )
    return email

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = ""

    @field_validator("email")
    @classmethod
    def no_common_typo(cls, v: str) -> str:
        return _check_typo(v)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class ResendVerificationRequest(BaseModel):
    email: EmailStr

class VerifyEmailRequest(BaseModel):
    token: str
    eid: Optional[str] = None

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    eid: Optional[str] = None
    new_password: str = Field(min_length=8)

class LoginOtpRequiredResponse(BaseModel):
    message: str
    login_token: str

class VerifyOtpRequest(BaseModel):
    login_token: str
    otp: str

class ResendOtpRequest(BaseModel):
    login_token: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)

class RefreshRequest(BaseModel):
    refresh_token: str

class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    monthly_budget: float
    email_verified: bool

class SignupResponse(BaseModel):
    message: str
    user: UserResponse

class MessageResponse(BaseModel):
    message: str

class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class LoginResponse(TokenPairResponse):
    user: UserResponse
