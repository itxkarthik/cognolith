import logging

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

logger = logging.getLogger(__name__)


def get_storage_uri() -> str:
    """
    Return storage URI for rate limiting.

    Uses Redis in production (distributed across workers) or memory in local dev.

    Fallback Behavior:
    - If REDIS_URL is configured: Try to connect with 5s timeout
    - If Redis connection fails: Fall back to in-memory storage (single-worker only)
    - If no REDIS_URL: Use in-memory storage by default

    In-Memory Storage Limitations:
    - Only works with single worker process (gunicorn -w 1)
    - Rate limits not shared across workers
    - Recommended for development only
    """
    if settings.REDIS_URL:
        try:
            # Test Redis connection with timeout
            import redis

            redis_client = redis.from_url(
                settings.REDIS_URL,
                socket_connect_timeout=5,
                socket_keepalive=True,
                socket_keepalive_options={
                    1: 3,  # TCP_KEEPIDLE
                    2: 3,  # TCP_KEEPINTVL
                },
            )
            # Ping to verify connection
            redis_client.ping()
            logger.info("Redis connected successfully for rate limiting")
            return settings.REDIS_URL
        except Exception as e:
            logger.warning(
                f"Redis connection failed ({str(e)}), falling back to in-memory rate limiting. "
                f"This only works with a single worker process."
            )
            return "memory://"

    logger.debug("Using in-memory rate limiting (not suitable for multi-worker deployments)")
    return "memory://"


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_MAX_REQUESTS}/{settings.RATE_LIMIT_WINDOW}seconds"],
    storage_uri=get_storage_uri(),
)
