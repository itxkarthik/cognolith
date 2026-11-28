import logging

from limits import parse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_storage_uri() -> str:
    """
    Where the rate limiter keeps its counters.

    Redis when REDIS_URL is set, so every process counts against the same limits.
    Without it the counters are in this process's memory, which only limits anything
    when there is one process: with several, each would allow the full limit. So
    several workers without a reachable Redis refuse to start.
    """
    shared = settings.BACKEND_WORKERS > 1
    if not settings.REDIS_URL:
        if shared:
            raise RuntimeError(
                "BACKEND_WORKERS > 1 needs REDIS_URL: in-memory rate limits are per process"
            )
        logger.debug("Using in-memory rate limiting (one process)")
        return "memory://"
    try:
        import redis

        redis.from_url(settings.REDIS_URL, socket_connect_timeout=5).ping()
    except Exception as exc:
        if shared:
            raise RuntimeError(f"Redis for rate limiting is unreachable: {exc}") from exc
        logger.warning(
            "Redis connection failed (%s); falling back to in-memory rate limiting, "
            "which is only correct with one process",
            exc,
        )
        return "memory://"
    logger.info("Redis connected for rate limiting")
    return settings.REDIS_URL


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_MAX_REQUESTS}/{settings.RATE_LIMIT_WINDOW}seconds"],
    storage_uri=get_storage_uri(),
)


_login_email_limit = parse(settings.LOGIN_EMAIL_RATE_LIMIT)


def hit_login_email_limit(email: str) -> bool:
    """
    Count a login attempt against the account being targeted.

    The per-IP decorator stops a single client from brute-forcing; this stops a
    distributed attempt on one account. Returns False once the limit is exceeded.
    """
    if not limiter.enabled:
        return True
    return limiter.limiter.hit(_login_email_limit, "login-email", email.strip().lower())
