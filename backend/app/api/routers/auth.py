from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import limiter
from app.db import get_db
from app.core.deps import get_current_user, get_current_access_payload
from app.models import User
from app.services import auth_service
from app.schemas.auth import (
    SignupRequest,
    LoginRequest, LoginPendingData,
    VerifyOtpRequest, ResendOtpRequest, LoginResponse,
    VerifyEmailRequest,
    ResendVerificationRequest,
    ForgotPasswordRequest, ResetPasswordRequest,
    ChangePasswordRequest,
    RefreshRequest, TokenPairResponse,
    LogoutRequest,
    UserResponse,
    ApiResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.full_name or "",
        monthly_budget=(user.profile.monthly_budget if user.profile else 0) or 0,
        email_verified=user.email_verified,
    )


def ok(message: str, data=None):
    return {"status": "success", "message": message, "data": data}


@router.post("/signup", response_model=ApiResponse[UserResponse], status_code=201, summary="Create an account")
@limiter.limit(settings.RATE_LIMIT_SIGNUP)
async def signup(request: Request, data: SignupRequest, db: Session = Depends(get_db)):
    try:
        user = await auth_service.signup(db, data.email, data.password, data.name)
    except auth_service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return ok(
        "Account created. Check your email to verify your address before logging in.",
        _user_response(user),
    )


@router.post("/verify-email", response_model=ApiResponse, summary="Verify an email address")
def verify_email(data: VerifyEmailRequest, db: Session = Depends(get_db)):
    try:
        auth_service.verify_email(db, data.token, data.eid)
    except auth_service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return ok("Email verified — you can now log in.")


@router.post("/resend-verification", response_model=ApiResponse, summary="Resend the verification email")
@limiter.limit(settings.RATE_LIMIT_SENSITIVE)
async def resend_verification(request: Request, data: ResendVerificationRequest, db: Session = Depends(get_db)):
    try:
        await auth_service.resend_verification(db, data.email)
    except auth_service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return ok("Verification email sent.")


@router.post("/forgot-password", response_model=ApiResponse,
             summary="Request a password reset email")
@limiter.limit(settings.RATE_LIMIT_SENSITIVE)
async def forgot_password(request: Request, data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    await auth_service.forgot_password(db, data.email)
    # Always the same response, whether or not the email is registered —
    # anything else would let an attacker enumerate accounts by email.
    return ok("If that email is registered, we've sent a password reset link.")


@router.post("/reset-password", response_model=ApiResponse,
             summary="Reset a password using the emailed token")
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    try:
        auth_service.reset_password(db, data.token, data.new_password, data.eid)
    except auth_service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return ok("Password reset — you can now log in with your new password.")


@router.post("/login", response_model=ApiResponse[LoginPendingData],
             summary="Log in with email+password (step 1 of 2) — emails an OTP")
@limiter.limit(settings.RATE_LIMIT_LOGIN)
async def login(request: Request, data: LoginRequest, db: Session = Depends(get_db)):
    try:
        login_token = await auth_service.login(db, data.email, data.password)
    except auth_service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return ok("Check your email for a login code.", LoginPendingData(login_token=login_token))


@router.post("/verify-otp", response_model=ApiResponse[LoginResponse],
             summary="Verify the emailed OTP (step 2 of 2) — returns an access/refresh token pair")
@limiter.limit(settings.RATE_LIMIT_OTP_VERIFY)
def verify_otp(request: Request, data: VerifyOtpRequest, db: Session = Depends(get_db)):
    try:
        access_token, refresh_token, user = auth_service.verify_login_otp(db, data.login_token, data.otp)
    except auth_service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return ok("Logged in.", LoginResponse(
        access_token=access_token, refresh_token=refresh_token,
        user=_user_response(user),
    ))


@router.post("/resend-otp", response_model=ApiResponse[LoginPendingData],
             summary="Resend the login OTP for a pending login attempt")
@limiter.limit(settings.RATE_LIMIT_SENSITIVE)
async def resend_otp(request: Request, data: ResendOtpRequest, db: Session = Depends(get_db)):
    try:
        login_token = await auth_service.resend_otp(db, data.login_token)
    except auth_service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return ok("Check your email for a new login code.", LoginPendingData(login_token=login_token))


@router.post("/refresh", response_model=ApiResponse[TokenPairResponse], summary="Exchange a refresh token for a new pair")
def refresh(data: RefreshRequest, db: Session = Depends(get_db)):
    try:
        access_token, refresh_token = auth_service.refresh(db, data.refresh_token)
    except auth_service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return ok("Token refreshed.", TokenPairResponse(access_token=access_token, refresh_token=refresh_token))


@router.post("/logout", response_model=ApiResponse, summary="Log out (blacklists the access token)")
def logout(
    data: LogoutRequest,
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_access_payload),
):
    auth_service.logout(db, int(payload["sub"]), payload.get("jti"), payload.get("exp"), data.refresh_token)
    return ok("Logged out.")


@router.delete("/user", response_model=ApiResponse,
               summary="Deactivate the current account (soft delete)")
def delete_account(db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    """Soft delete: flags the account and frees its email for reuse, but keeps
    every row of data (transactions, accounts, profile, ...) untouched."""
    auth_service.delete_account(db, current_user)
    return ok("Account deactivated.")


@router.post("/change-password", response_model=ApiResponse,
             summary="Change password while logged in (requires the current password)")
def change_password(
    data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: int = Depends(get_current_user),
):
    try:
        auth_service.change_password(db, current_user, data.current_password, data.new_password)
    except auth_service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return ok("Password changed.")


@router.get("/me", response_model=ApiResponse[UserResponse], summary="Get the current user")
def me(db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    try:
        user = auth_service.get_profile(db, current_user)
    except auth_service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return ok("OK", _user_response(user))
