from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.core.security import get_password_hash, hash_refresh_token, verify_password
from app.models.user import (
    RefreshToken,
    TokenBlacklist,
    User,
    UserCreate,
    UserUpdate,
    normalize_email,
)


def create_user(*, session: Session, user_create: UserCreate, is_verified: bool = True) -> User:
    db_obj = User.model_validate(
        user_create,
        update={
            "hashed_password": get_password_hash(user_create.password),
            "is_verified": is_verified,
        },
    )
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def update_user(*, session: Session, db_user: User, user_in: UserUpdate) -> Any:
    user_data = user_in.model_dump(exclude_unset=True)
    extra_data = {}
    if "password" in user_data:
        password = user_data["password"]
        hashed_password = get_password_hash(password)
        extra_data["hashed_password"] = hashed_password
    db_user.sqlmodel_update(user_data, update=extra_data)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


def get_user_by_email(*, session: Session, email: str) -> User | None:
    # Case-insensitive, matching the unique index on lower(email)
    statement = select(User).where(func.lower(User.email) == normalize_email(email))
    session_user = session.exec(statement).first()
    return session_user


DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"


def authenticate(*, session: Session, email: str, password: str) -> User | None:
    db_user = get_user_by_email(session=session, email=email)
    if not db_user:
        # Prevent timing attack by running dummy hash when user doesn't exist
        verify_password(password, DUMMY_HASH)
        return None
    verified, updated_password_hash = verify_password(password, db_user.hashed_password)
    if not verified:
        return None
    if updated_password_hash:
        db_user.hashed_password = updated_password_hash
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
    return db_user


# Refresh Token CRUD
def create_refresh_token(
    *,
    session: Session,
    user_id: int,
    raw_token: str,
    expires_delta: timedelta,
    family_id: str | None = None,
) -> RefreshToken:
    db_token = RefreshToken(
        user_id=user_id,
        hashed_token=hash_refresh_token(raw_token),
        expires_at=datetime.now(UTC) + expires_delta,
    )
    if family_id is not None:
        db_token.family_id = family_id
    session.add(db_token)
    session.commit()
    session.refresh(db_token)
    return db_token


def get_refresh_token_by_hash(*, session: Session, hashed_token: str) -> RefreshToken | None:
    statement = select(RefreshToken).where(
        RefreshToken.hashed_token == hashed_token,
        col(RefreshToken.revoked).is_(False),
        RefreshToken.expires_at > datetime.now(UTC),
    )
    return session.exec(statement).first()


def get_refresh_token_owner_id(*, session: Session, hashed_token: str) -> int | None:
    statement = select(RefreshToken.user_id).where(RefreshToken.hashed_token == hashed_token)
    return session.exec(statement).first()


def lock_user(*, session: Session, user_id: int) -> User | None:
    """
    Row-lock a user (and reload it). Paths that issue or revoke a user's tokens take
    this lock before any token lock, so they serialize in one order and never deadlock.
    """
    statement = (
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return session.exec(statement).first()


def lock_refresh_token_by_hash(*, session: Session, hashed_token: str) -> RefreshToken | None:
    """Fetch a refresh token in any state, row-locked so concurrent refreshes serialize."""
    statement = (
        select(RefreshToken).where(RefreshToken.hashed_token == hashed_token).with_for_update()
    )
    return session.exec(statement).first()


def revoke_refresh_token(*, session: Session, db_token: RefreshToken) -> None:
    """Stage a token's revocation; the caller commits it with the rest of its change."""
    db_token.revoked = True
    db_token.revoked_at = datetime.now(UTC)
    session.add(db_token)


def _revoke_refresh_tokens(*, session: Session, tokens: Sequence[RefreshToken]) -> None:
    revoked_at = datetime.now(UTC)
    for token in tokens:
        token.revoked = True
        token.revoked_at = revoked_at
        session.add(token)
    session.commit()


def family_has_active_token(*, session: Session, family_id: str) -> bool:
    statement = select(RefreshToken.id).where(
        RefreshToken.family_id == family_id,
        col(RefreshToken.revoked).is_(False),
        RefreshToken.expires_at > datetime.now(UTC),
    )
    return session.exec(statement).first() is not None


def revoke_refresh_token_family(*, session: Session, family_id: str) -> None:
    statement = select(RefreshToken).where(
        RefreshToken.family_id == family_id, col(RefreshToken.revoked).is_(False)
    )
    _revoke_refresh_tokens(session=session, tokens=session.exec(statement).all())


def revoke_all_user_refresh_tokens(*, session: Session, user_id: int) -> None:
    statement = select(RefreshToken).where(
        RefreshToken.user_id == user_id, col(RefreshToken.revoked).is_(False)
    )
    _revoke_refresh_tokens(session=session, tokens=session.exec(statement).all())


# Token Blacklist CRUD for Access Token Revocation
def blacklist_token(*, session: Session, jti: str, expires_at: datetime) -> None:
    entry = TokenBlacklist(jti=jti, expires_at=expires_at)
    session.add(entry)
    session.commit()


def is_token_blacklisted(*, session: Session, jti: str) -> bool:
    statement = select(TokenBlacklist).where(TokenBlacklist.jti == jti)
    return session.exec(statement).first() is not None
