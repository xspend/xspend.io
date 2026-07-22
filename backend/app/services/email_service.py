"""Sends the verification email via SMTP (fastapi-mail + Jinja2 templates).
If SMTP isn't configured (no SMTP_* env vars — the default for local dev), the
verification link is printed to stdout instead of sent, so signup works with
zero email setup.
"""
from pathlib import Path
from typing import Optional

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType

from app.core.config import settings
from app.core.security import encode_id

TEMPLATE_FOLDER = Path(__file__).parent.parent / "templates"

# Where verification links point — a frontend route, not this API. Falls back
# to the first FRONTEND_ORIGINS entry, then localhost, if APP_BASE_URL isn't set.
APP_BASE_URL = (
    settings.APP_BASE_URL
    or (settings.frontend_origins_list[0] if settings.frontend_origins_list else None)
    or "http://localhost:5173"
)

_fm: Optional[FastMail] = None
if settings.smtp_configured:
    _config = ConnectionConfig(
        MAIL_USERNAME=settings.SMTP_USERNAME,
        MAIL_PASSWORD=settings.SMTP_PASSWORD,
        MAIL_FROM=settings.SMTP_FROM,
        MAIL_FROM_NAME=settings.SMTP_FROM_NAME,
        MAIL_PORT=int(settings.SMTP_PORT),
        MAIL_SERVER=settings.SMTP_HOST,
        MAIL_STARTTLS=settings.SMTP_STARTTLS.lower() == "true",
        MAIL_SSL_TLS=settings.SMTP_SSL.lower() == "true",
        USE_CREDENTIALS=True,
        VALIDATE_CERTS=True,
        TEMPLATE_FOLDER=TEMPLATE_FOLDER,
    )
    _fm = FastMail(_config)


def verification_link(token: str, user_id: int) -> str:
    # `eid` (encoded id) rides along as a cheap sanity check the frontend/
    # router can use before ever touching the DB — the token is still the
    # actual source of truth, this just lets a mismatched/tampered id get
    # caught early. Encoded rather than a raw int so the link doesn't expose
    # the user's sequential DB id in plain sight.
    return f"{APP_BASE_URL.rstrip('/')}/verify-email?token={token}&eid={encode_id(user_id)}"


async def send_verification_email(to_email: str, token: str, user_id: int) -> None:
    link = verification_link(token, user_id)
    if _fm is None:
        print(f"[email] SMTP not configured — verification link for {to_email}: {link}")
        return
    message = MessageSchema(
        recipients=[to_email],
        subject="Verify your xspend email",
        template_body={"link": link},
        subtype=MessageType.html,
    )
    await _fm.send_message(message, template_name="verify_email.html")


async def send_login_otp_email(to_email: str, otp: str) -> None:
    if _fm is None:
        print(f"[email] SMTP not configured — login OTP for {to_email}: {otp}")
        return
    message = MessageSchema(
        recipients=[to_email],
        subject="Your xspend login code",
        template_body={"otp": otp},
        subtype=MessageType.html,
    )
    await _fm.send_message(message, template_name="login_otp.html")


def reset_password_link(token: str, user_id: int) -> str:
    return f"{APP_BASE_URL.rstrip('/')}/reset-password?token={token}&eid={encode_id(user_id)}"


async def send_password_reset_email(to_email: str, token: str, user_id: int) -> None:
    link = reset_password_link(token, user_id)
    if _fm is None:
        print(f"[email] SMTP not configured — password reset link for {to_email}: {link}")
        return
    message = MessageSchema(
        recipients=[to_email],
        subject="Reset your xspend password",
        template_body={"link": link},
        subtype=MessageType.html,
    )
    await _fm.send_message(message, template_name="reset_password.html")
