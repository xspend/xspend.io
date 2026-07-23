"""Rate limiting via slowapi (built on the `limits` library), keyed by
client IP. `limiter.limit(...)` decorates specific routes with a tighter
threshold than the default; everything else falls back to
settings.RATE_LIMIT_DEFAULT via the middleware in main.py.

Disabled outright in tests (RATE_LIMIT_ENABLED=false, set in
tests/conftest.py before anything imports the app) — otherwise the test
suite's rapid repeated calls to /auth/login etc. would trip these limits,
since the in-memory counter is a process-wide singleton that persists across
test functions, not reset per-test.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.RATE_LIMIT_DEFAULT],
    enabled=settings.RATE_LIMIT_ENABLED,
)
