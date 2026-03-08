from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_MAX_REQUESTS}/{settings.RATE_LIMIT_WINDOW}seconds"],
    storage_uri="memory://",  # Use Redis URI in production for multi-worker setups
)
