from datetime import datetime, timedelta, timezone
from typing import Any
from sqlmodel import Session, select
from app.core.security import get_password_hash, verify_password, hash_refresh_token
from app.models.user import User, UserCreate, UserUpdate, RefreshToken, TokenBlacklist

def create_user(*, session: Session, user_create: UserCreate) -> User:
    db_obj = User.model_validate(
        user_create, update={"hashed_password": get_password_hash(user_create.password)}
    )
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj
    
def update_user(*, session: Session, db_user: User, user_in: UserUpdate) -> Any:
    user_data = user_in.model_dump(exclude_unset=True)
    extra_data= {}
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
    statement = select(User).where(User.email==email)
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
    *, session: Session, user_id: int, raw_token: str, expires_delta: timedelta
) -> RefreshToken:
    db_token = RefreshToken(
        user_id=user_id,
        hashed_token=hash_refresh_token(raw_token),
        expires_at=datetime.now(timezone.utc) + expires_delta,
    )
    session.add(db_token)
    session.commit()
    session.refresh(db_token)
    return db_token

def get_refresh_token_by_hash(*, session: Session, hashed_token: str) -> RefreshToken | None:
    statement = select(RefreshToken).where(
        RefreshToken.hashed_token == hashed_token,
        RefreshToken.revoked == False,
        RefreshToken.expires_at > datetime.now(timezone.utc),
    )
    return session.exec(statement).first()

def revoke_refresh_token(*, session: Session, db_token: RefreshToken) -> None:
    db_token.revoked = True
    session.add(db_token)
    session.commit()

def revoke_all_user_refresh_tokens(*, session: Session, user_id: int) -> None:
    statement = select(RefreshToken).where(
        RefreshToken.user_id == user_id, RefreshToken.revoked == False
    )
    tokens = session.exec(statement).all()
    for token in tokens:
        token.revoked = True
        session.add(token)
    session.commit()

# Token Blacklist CRUD for Access Token Revocation
def blacklist_token(*, session: Session, jti: str, expires_at: datetime) -> None:
    entry = TokenBlacklist(jti=jti, expires_at=expires_at)
    session.add(entry)
    session.commit()

def is_token_blacklisted(*, session: Session, jti: str) -> bool:
    statement = select(TokenBlacklist).where(TokenBlacklist.jti == jti)
    return session.exec(statement).first() is not None
    