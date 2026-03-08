from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from app.core import security
from app.core.config import settings
from app import crud
from app.api.deps import CurrentUser, SessionDep, get_current_active_superuser
from app.models.user import Message, Token, UserPublic
from app.core.rate_limit import limiter

router = APIRouter(tags=["login"])

@router.post(path="/login/access-token")
@limiter.limit("5/minute")
def login_access_token(
        request: Request,
        session: SessionDep, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
    ) -> Token:
    """
        OAuth2 token login, get an access token for future requests.
        Rate limited to 5 attempts per minute per IP.
    """
    user = crud.authenticate(
        session=session, email=form_data.username, password=form_data.password
    )
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect Email or Password")
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    access_token_expires: timedelta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return Token(
        access_token=security.create_access_token(
            subject=user.id, expires_delta=access_token_expires
        )
    )

@router.post(path="/login/test-token", response_model=UserPublic)
def test_token(current_user: CurrentUser) -> Any:
    return current_user
