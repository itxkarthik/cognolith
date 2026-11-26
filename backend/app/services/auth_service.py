import logging
from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple

from sqlmodel import Session, col, update

from app import crud  # type: ignore[attr-defined]
from app.core import security
from app.core.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)

# A rotated token presented again within this window is a concurrent refresh, not theft.
REFRESH_REUSE_GRACE_SECONDS = 30


class TokenPair(NamedTuple):
    """Response model for token creation - contains both JWT and refresh token."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


def create_token_pair(session: Session, user: User, family_id: str | None = None) -> TokenPair:
    """
    Create a new access token + refresh token pair for a user.

    This is called during login and refresh operations.

    Args:
        session: Database session
        user: User model instance
        family_id: Refresh-token family to continue (rotation); a new family when None

    Returns:
        TokenPair with access_token (JWT) and refresh_token (opaque)

    Token Details:
    - Access Token: HS256 JWT, expires in 30 minutes, includes JTI for revocation
    - Refresh Token: Random 64-byte urlsafe token, expires in 7 days, single-use
    """
    # Create access token with JWT exp + jti claims
    if user.id is None:
        raise ValueError("User must be persisted before tokens can be created")
    user_id = user.id
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        subject=user_id, expires_delta=access_token_expires, token_version=user.token_version
    )

    # Create refresh token (long-lived, single-use)
    raw_refresh_token = security.generate_refresh_token()
    crud.create_refresh_token(
        session=session,
        user_id=user_id,
        raw_token=raw_refresh_token,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        family_id=family_id,
    )

    return TokenPair(
        access_token=access_token, refresh_token=raw_refresh_token, token_type="bearer"
    )


def refresh_access_token_from_refresh(
    session: Session,
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
    The user is always the refresh token's owner; no other credential is consulted.

    Presenting an already-rotated token is treated as theft and the whole token
    family is revoked. A token rotated moments ago is exempt, so two tabs
    refreshing at the same time don't log each other out.

    Args:
        session: Database session
        refresh_token: Raw refresh token from request

    Returns:
        New TokenPair with fresh access and refresh tokens

    Raises:
        ValueError: If token is invalid, revoked, or expired
    """
    hashed = security.hash_refresh_token(refresh_token)
    owner_id = crud.get_refresh_token_owner_id(session=session, hashed_token=hashed)
    # Lock the owner first, as end_all_sessions does: a refresh and a sign-out-everywhere
    # then run one after the other, so the sign-out can't miss the replacement token
    user = None if owner_id is None else crud.lock_user(session=session, user_id=owner_id)
    db_token = crud.lock_refresh_token_by_hash(session=session, hashed_token=hashed)

    if not db_token or not user:
        session.rollback()
        raise ValueError("Invalid or expired refresh token")

    now = datetime.now(UTC)
    if db_token.revoked:
        # Reuse only signals theft while a newer token in the family is still live.
        # A family revoked as a whole (logout, password change) is just a stale session.
        if _within_reuse_grace(db_token.revoked_at, now) or not crud.family_has_active_token(
            session=session, family_id=db_token.family_id
        ):
            session.rollback()
        else:
            logger.warning(
                "Refresh token reuse detected; revoking token family",
                extra={
                    "event": "refresh_token_reuse",
                    "user_id": db_token.user_id,
                    "family_id": db_token.family_id,
                },
            )
            crud.revoke_refresh_token_family(session=session, family_id=db_token.family_id)
        raise ValueError("Invalid or expired refresh token")

    if _as_utc(db_token.expires_at) <= now or not user.is_active:
        session.rollback()
        raise ValueError("Invalid or expired refresh token")

    # Single use: the old token's revocation commits together with its replacement,
    # and that commit releases the locks
    crud.revoke_refresh_token(session=session, db_token=db_token)

    return create_token_pair(session=session, user=user, family_id=db_token.family_id)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _within_reuse_grace(revoked_at: datetime | None, now: datetime) -> bool:
    if revoked_at is None:
        return False
    return now - _as_utc(revoked_at) < timedelta(seconds=REFRESH_REUSE_GRACE_SECONDS)


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


def end_all_sessions(session: Session, user: User) -> None:
    """
    Sign the user out everywhere: revoke every refresh token and bump the token
    version, so other devices lose access immediately rather than when their
    30-minute access token expires. Tokens issued afterwards carry the new version.
    """
    if user.id is None:
        raise ValueError("User must be persisted before sessions can be ended")
    # The user-row update below takes the lock token rotation also takes first,
    # so an in-flight refresh either finishes before this or sees its token revoked.
    # Write the caller's pending changes (new password or email) first: the refresh
    # below reloads the row and would otherwise discard them
    session.add(user)
    session.flush()
    # Atomic in SQL: two concurrent calls must both move the version forward
    session.exec(
        update(User)
        .where(col(User.id) == user.id)
        .values(token_version=User.token_version + 1)
    )
    crud.revoke_all_user_refresh_tokens(session=session, user_id=user.id)
    # Pick up the incremented version (and drop any stale in-memory value)
    session.refresh(user)


def revoke_refresh_token_family(session: Session, refresh_token: str, user_id: int) -> None:
    """Revoke the session a raw refresh token belongs to, if it is this user's."""
    hashed = security.hash_refresh_token(refresh_token)
    if crud.get_refresh_token_owner_id(session=session, hashed_token=hashed) != user_id:
        session.rollback()
        return
    # Same lock order as rotation, so a concurrent refresh can't slip a token past us
    crud.lock_user(session=session, user_id=user_id)
    db_token = crud.lock_refresh_token_by_hash(session=session, hashed_token=hashed)
    if db_token is None:
        session.rollback()
        return
    crud.revoke_refresh_token_family(session=session, family_id=db_token.family_id)


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
