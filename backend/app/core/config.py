"""Single source of truth for every environment variable the app reads —
database, JWT, SMTP, CORS, rate limiting, and the AI chat provider. Reads
`.env` directly (independent of whether something else already called
`load_dotenv()`), so import order doesn't matter. Everywhere else should do
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

    CORS_ORIGINS: str = ""
    ALLOWED_HOSTS: str = ""
    APP_BASE_URL: Optional[str] = None

    EMAIL_VERIFICATION_EXPIRE_HOURS: int = 24
    PASSWORD_RESET_EXPIRE_MINUTES: int = 60
    OTP_EXPIRE_MINUTES: int = 2
    MAX_OTP_ATTEMPTS: int = 5
    OTP_LOCKOUT_MINUTES: int = 10

    # Rate limiting (slowapi/limits, keyed by client IP). Disabled entirely in
    # tests — see tests/conftest.py — so rapid repeated calls in the test
    # suite never trip these. RATE_LIMIT_DEFAULT applies to every route that
    # doesn't set its own explicit @limiter.limit(...); the auth-specific
    # ones below override it on the endpoints most worth protecting.
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT: str = "100/minute"
    RATE_LIMIT_SIGNUP: str = "5/minute"
    RATE_LIMIT_LOGIN: str = "10/minute"
    RATE_LIMIT_OTP_VERIFY: str = "10/minute"
    RATE_LIMIT_SENSITIVE: str = "5/minute"  # forgot-password, resend-*

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
        """The dev fallback is an allow-list on ENVIRONMENT=="development",
        not a block-list on =="production" — anything unset, mistyped, or
        unrecognized (e.g. "prod", "staging") fails loud instead of quietly
        signing tokens with a secret that's public in this repo."""
        if self.JWT_SECRET_KEY:
            return self.JWT_SECRET_KEY
        if self.ENVIRONMENT.lower() == "development":
            return "financeai-dev-only-secret-change-me"
        raise RuntimeError(
            f'JWT_SECRET_KEY must be set when ENVIRONMENT="{self.ENVIRONMENT}" '
            '(the dev fallback only applies when ENVIRONMENT="development")'
        )

    @property
    def allowed_origins(self) -> List[str]:
        """Fails loud on a wildcard rather than silently allow-listing every
        origin — the app doesn't use cookies (see setup_cors: allow_credentials
        is off), so a wildcard isn't the classic credentials+"*" CORS hole
        today, but it defeats the point of having an allow-list at all, and
        would become a real hole the moment anyone re-enables credentials
        without remembering this. An empty/unset value is fine — that just
        means no cross-origin browser requests are allowed, the safe default."""
        origins = [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]
        if "*" in origins:
            raise RuntimeError(
                'CORS_ORIGINS must not contain "*" — list explicit origins instead, '
                "e.g. https://app.example.com. A wildcard defeats the allow-list."
            )
        return origins

    @property
    def allowed_hosts(self) -> List[str]:
        """Starlette's TrustedHostMiddleware equivalent of Django's
        ALLOWED_HOSTS — validates the incoming `Host` header, not the
        `Origin` header (that's allowed_origins/CORS_ORIGINS above; a different
        concern). Required in production, same fail-loud rule as
        jwt_secret_key. Left unset in dev just means the middleware is
        skipped entirely (see setup_trusted_hosts) — there's no real domain
        to check the Host header against locally, so there's nothing a
        wildcard-style fallback would actually protect."""
        hosts = [h.strip() for h in self.ALLOWED_HOSTS.split(",") if h.strip()]
        if not hosts and self.ENVIRONMENT.lower() == "production":
            raise RuntimeError(
                "ALLOWED_HOSTS must be set in production, e.g. ALLOWED_HOSTS=api.yourapp.com"
            )
        return hosts

    @property
    def smtp_configured(self) -> bool:
        return bool(self.SMTP_HOST and self.SMTP_PORT and self.SMTP_USERNAME
                    and self.SMTP_PASSWORD and self.SMTP_FROM)


settings = Settings()
