"""Single source of truth for every environment variable the app reads —
database, JWT, SMTP, CORS, and the AI chat provider. Reads `.env` directly
(independent of whether something else already called `load_dotenv()`), so
import order doesn't matter. Everywhere else should do
`from app.core.config import settings` instead of calling os.getenv directly.
"""
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: Optional[str] = None
    ENVIRONMENT: str = "development"

    JWT_SECRET_KEY: Optional[str] = None
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    ANTHROPIC_API_KEY: Optional[str] = None
    XSPEND_CHAT_MODEL: str = "claude-3-5-sonnet-20241022"
    XSPEND_CHAT_PROMPT_LIMIT: int = 10

    FRONTEND_ORIGINS: str = ""
    APP_BASE_URL: Optional[str] = None

    EMAIL_VERIFICATION_EXPIRE_HOURS: int = 24
    PASSWORD_RESET_EXPIRE_MINUTES: int = 60
    OTP_EXPIRE_MINUTES: int = 2
    MAX_OTP_ATTEMPTS: int = 5
    OTP_LOCKOUT_MINUTES: int = 10

    # Left as raw strings (not int/bool) so a test blanking them to "" via
    # os.environ never hits a type-coercion error — cast where actually used.
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[str] = None
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: Optional[str] = None
    SMTP_FROM_NAME: str = "xspend"
    SMTP_STARTTLS: str = "true"
    SMTP_SSL: str = "false"

    @property
    def database_url(self) -> str:
        if not self.DATABASE_URL:
            raise RuntimeError(
                "DATABASE_URL is not set. Set it explicitly before running anything, e.g. "
                'DATABASE_URL="sqlite:///./financeai.db" for local dev.'
            )
        return self.DATABASE_URL

    @property
    def jwt_secret_key(self) -> str:
        """In production this MUST be set — fail loud so we never silently
        fall back to a public default. Local dev keeps a fallback."""
        if self.JWT_SECRET_KEY:
            return self.JWT_SECRET_KEY
        if self.ENVIRONMENT.lower() == "production":
            raise RuntimeError("JWT_SECRET_KEY must be set in production")
        return "financeai-dev-only-secret-change-me"

    @property
    def frontend_origins_list(self) -> List[str]:
        return [o.strip() for o in self.FRONTEND_ORIGINS.split(",") if o.strip()]

    @property
    def smtp_configured(self) -> bool:
        return bool(self.SMTP_HOST and self.SMTP_PORT and self.SMTP_USERNAME
                    and self.SMTP_PASSWORD and self.SMTP_FROM)


settings = Settings()
