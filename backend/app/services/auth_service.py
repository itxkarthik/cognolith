from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple, cast

from sqlmodel import Session

from app import crud  # type: ignore[attr-defined]
from app.core import security
from app.core.config import settings
from app.models.user import RefreshToken, TokenBlacklist, User


class TokenPair(NamedTuple):
    """Response model for token creation - contains both JWT and refresh token."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


def create_token_pair(session: Session, user: User) -> TokenPair:
    """
    Create a new access token + refresh token pair for a user.

    This is called during login and refresh operations.

    Args:
        session: Database session
        user: User model instance

    Returns:
        TokenPair with access_token (JWT) and refresh_token (opaque)

    Token Details:
    - Access Token: HS256 JWT, expires in 30 minutes, includes JTI for revocation
    - Refresh Token: Random 64-byte urlsafe token, expires in 7 days, single-use
    """
    # Create access token with JWT exp + jti claims
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(subject=user.id, expires_delta=access_token_expires)

    # Create refresh token (long-lived, single-use)
    raw_refresh_token = security.generate_refresh_token()
    crud.create_refresh_token(
        session=session,
        user_id=user.id,
        raw_token=raw_refresh_token,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )

    return TokenPair(
        access_token=access_token, refresh_token=raw_refresh_token, token_type="bearer"
    )


def refresh_access_token_from_refresh(
    session: Session,
    user_id: int,
    refresh_token: str,
) -> TokenPair:
    """
    Exchange a valid refresh token for a new access + refresh token pair.

    Implements token rotation pattern:
    1. Validate refresh token exists, not revoked, not expired
    2. Revoke old refresh token (single-use enforcement)
    3. Issue new access + refresh token pair
    4. Return new tokens

    This prevents replay attacks by ensuring each refresh token can only be used once.

    Args:
        session: Database session
        user_id: User ID (validated externally)
        refresh_token: Raw refresh token from request

    Returns:
        New TokenPair with fresh access and refresh tokens

    Raises:
        ValueError: If token is invalid, revoked, or expired
    """
    # Hash and lookup the refresh token
    hashed = security.hash_refresh_token(refresh_token)
    db_token = crud.get_refresh_token_by_hash(session=session, hashed_token=hashed)

    if not db_token:
        raise ValueError("Invalid or expired refresh token")

    # Revoke the old token (single-use pattern)
    crud.revoke_refresh_token(session=session, db_token=db_token)

    # Issue new token pair
    user = session.get(User, user_id)
    if not user:
        raise ValueError("User not found")

    return create_token_pair(session=session, user=user)


def revoke_access_token(
    session: Session,
    jti: str,
    expires_at: datetime,
) -> None:
    """
    Explicitly revoke an access token by blacklisting its JTI.

    Used for:
    - Logout (revoke current session token)
    - Administrative revocation
    - Security incidents

    Args:
        session: Database session
        jti: JWT ID from token payload (unique identifier)
        expires_at: Token expiration timestamp (for cleanup scheduling)
    """
    crud.blacklist_token(session=session, jti=jti, expires_at=expires_at)


def revoke_all_user_tokens(session: Session, user_id: int) -> None:
    """
    Revoke ALL tokens for a user (logout everywhere).

    Revokes:
    - All valid refresh tokens (set revoked flag)
    - All active access tokens will be blacklisted at logout endpoint

    Used for:
    - Account security (password change)
    - Logout from all devices
    - Account deactivation

    Args:
        session: Database session
        user_id: User ID
    """
    crud.revoke_all_user_refresh_tokens(session=session, user_id=user_id)


def is_access_token_blacklisted(session: Session, jti: str) -> bool:
    """
    Check if an access token has been revoked (blacklisted).

    Called during token validation in get_current_user dependency.
    Fast lookup via JTI (no user ID needed).

    Args:
        session: Database session
        jti: JWT ID from token payload

    Returns:
        True if token is blacklisted (revoked), False otherwise
    """
    result = crud.is_token_blacklisted(session=session, jti=jti)
    return bool(result) if result is not None else False


def cleanup_expired_tokens(session: Session) -> int:
    """
    Remove expired tokens from database to keep storage clean.

    Deletes:
    - Expired refresh tokens (revoked or not)
    - Expired blacklisted access tokens

    Should be run periodically (e.g., daily via Celery job).

    Args:
        session: Database session

    Returns:
        Number of tokens deleted
    """
    from sqlmodel import delete

    now = datetime.now(UTC)

    # Delete expired refresh tokens
    refresh_stmt = delete(RefreshToken).where(RefreshToken.expires_at < now)
    refresh_result = session.execute(refresh_stmt)  # type: ignore
    refresh_deleted = (
        cast(int, refresh_result.rowcount) if hasattr(refresh_result, "rowcount") else 0
    )

    # Delete expired blacklisted tokens
    blacklist_stmt = delete(TokenBlacklist).where(TokenBlacklist.expires_at < now)
    blacklist_result = session.exec(blacklist_stmt)  # type: ignore
    blacklist_deleted = (
        cast(int, blacklist_result.rowcount) if hasattr(blacklist_result, "rowcount") else 0
    )

    session.commit()

    total_deleted = refresh_deleted + blacklist_deleted
    return total_deleted


def get_token_info(session: Session, token_payload: dict[str, Any]) -> dict[str, Any]:
    """
    Get information about a token for debugging/monitoring.

    Args:
        session: Database session
        token_payload: Decoded JWT payload

    Returns:
        Dict with token metadata (exp, jti, user_id, etc.)
    """
    jti = token_payload.get("jti")
    user_id = token_payload.get("sub")
    exp_timestamp = token_payload.get("exp")

    exp_datetime = datetime.fromtimestamp(exp_timestamp, tz=UTC) if exp_timestamp else None
    is_blacklisted = is_access_token_blacklisted(session, jti) if jti else None

    return {
        "user_id": user_id,
        "jti": jti,
        "expires_at": exp_datetime,
        "is_blacklisted": is_blacklisted,
        "is_expired": exp_datetime < datetime.now(UTC) if exp_datetime else None,
    }
