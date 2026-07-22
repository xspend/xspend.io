from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.deps import get_current_user, get_current_access_payload
from app.models import User
from app.services import auth_service
from app.schemas.auth import (
    SignupRequest, SignupResponse,
    LoginRequest, LoginResponse,
    VerifyEmailRequest, MessageResponse,
    ResendVerificationRequest,
    RefreshRequest, TokenPairResponse,
    LogoutRequest,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.full_name or "",
        monthly_budget=user.monthly_budget or 0,
        email_verified=user.email_verified,
    )


@router.post("/signup", response_model=SignupResponse, status_code=201, summary="Create an account")
async def signup(data: SignupRequest, db: Session = Depends(get_db)):
    try:
        user = await auth_service.signup(db, data.email, data.password, data.name)
    except auth_service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return SignupResponse(
        message="Account created. Check your email to verify your address before logging in.",
        user=_user_response(user),
    )


@router.post("/verify-email", response_model=MessageResponse, summary="Verify an email address")
def verify_email(data: VerifyEmailRequest, db: Session = Depends(get_db)):
    try:
        auth_service.verify_email(db, data.token, data.eid)
    except auth_service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return MessageResponse(message="Email verified — you can now log in.")


@router.post("/resend-verification", response_model=MessageResponse, summary="Resend the verification email")
async def resend_verification(data: ResendVerificationRequest, db: Session = Depends(get_db)):
    try:
        await auth_service.resend_verification(db, data.email)
    except auth_service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return MessageResponse(message="Verification email sent.")


@router.post("/login", response_model=LoginResponse, summary="Log in and get an access/refresh token pair")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    try:
        access_token, refresh_token, user = auth_service.login(db, data.email, data.password)
    except auth_service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return LoginResponse(
        access_token=access_token, refresh_token=refresh_token,
        user=_user_response(user),
    )


@router.post("/refresh", response_model=TokenPairResponse, summary="Exchange a refresh token for a new pair")
def refresh(data: RefreshRequest, db: Session = Depends(get_db)):
    try:
        access_token, refresh_token = auth_service.refresh(db, data.refresh_token)
    except auth_service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return TokenPairResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout", response_model=MessageResponse, summary="Log out (blacklists the access token)")
def logout(
    data: LogoutRequest,
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_access_payload),
):
    auth_service.logout(db, int(payload["sub"]), payload.get("jti"), payload.get("exp"), data.refresh_token)
    return MessageResponse(message="Logged out.")


@router.delete("/account", response_model=MessageResponse, summary="Delete the current user and all their data")
def delete_account(db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    """Delete the current user and ALL of their data. Irreversible."""
    auth_service.delete_account(db, current_user)
    return MessageResponse(message="Account deleted.")


@router.get("/me", response_model=UserResponse, summary="Get the current user")
def me(db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    try:
        user = auth_service.get_profile(db, current_user)
    except auth_service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return _user_response(user)
