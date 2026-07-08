import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import col, func, select

from app import crud
from app.api.deps import CurrentUser, SessionDep, get_current_active_superuser
from app.api.routes.auth import clear_auth_cookies, set_auth_cookies
from app.core.config import settings
from app.core.exceptions import AppError, ExternalServiceError
from app.core.security import get_password_hash, verify_password
from app.models.user import (
    LlmProvider,
    Message,
    Token,
    UpdatePassword,
    User,
    UserCreate,
    UserPublic,
    UserRegister,
    UserSettings,
    UsersPublic,
    UserUpdate,
    UserUpdateMe,
)
from app.schemas.error import ErrorCode, StandardErrorResponse
from app.schemas.settings import OllamaModelOption, UserAISettingsResponse, UserAISettingsUpdate
from app.schemas.verification import (
    EmailChangeRequest,
    ResendVerificationRequest,
    ResendVerificationResponse,
    VerificationChallenge,
    VerifyEmailRequest,
)
from app.services import auth_service
from app.services.email_service import EmailDeliveryError, send_verification_email
from app.services.email_verification_service import (
    InvalidVerificationCodeError,
    VerificationCodeExpiredError,
    VerificationRateLimitError,
    issue_verification_code,
    mask_email,
    verify_email_code,
)

router = APIRouter(prefix="/users", tags=["users"])
logger = logging.getLogger(__name__)


@router.get(
    path="/",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=UsersPublic,
    responses={
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        403: {
            "model": StandardErrorResponse,
            "description": "Admin privileges required",
        },
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def read_users(session: SessionDep, skip: int = 0, limit: int = 100) -> Any:
    """
    Retrieve Users
    """
    count_statement = select(func.count()).select_from(User)
    count = session.exec(count_statement).one()

    statement = select(User).order_by(col(User.created_at).desc()).offset(skip).limit(limit)
    users = session.exec(statement).all()

    return UsersPublic(
        data=[UserPublic.model_validate(user) for user in users],
        count=count,
    )


@router.post(
    path="/",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=UserPublic,
    responses={
        400: {
            "model": StandardErrorResponse,
            "description": "User with this email already exists",
        },
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        403: {
            "model": StandardErrorResponse,
            "description": "Admin privileges required",
        },
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def create_user(*, session: SessionDep, user_in: UserCreate) -> Any:
    """
    Create new user
    """
    user = crud.get_user_by_email(session=session, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system.",
        )

    user = crud.create_user(session=session, user_create=user_in)

    return user


@router.patch(
    path="/me",
    response_model=UserPublic,
    responses={
        400: {"model": StandardErrorResponse, "description": "Validation error"},
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        409: {"model": StandardErrorResponse, "description": "Email already in use"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def update_user_me(*, session: SessionDep, user_in: UserUpdateMe, current_user: CurrentUser) -> Any:
    """
    Update own user
    """
    if user_in.email is not None and user_in.email != current_user.email:
        raise AppError(
            message="Use the email change endpoint to verify a new email address.",
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    user_data = user_in.model_dump(exclude_unset=True)
    current_user.sqlmodel_update(user_data)
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return current_user


@router.patch(
    path="/me/password",
    response_model=Message,
    responses={
        400: {
            "model": StandardErrorResponse,
            "description": "Invalid current password",
        },
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def update_password_me(
    *, session: SessionDep, body: UpdatePassword, current_user: CurrentUser
) -> Any:
    """
    Update current user password
    """
    verified, _ = verify_password(body.current_password, current_user.hashed_password)
    if not verified:
        raise HTTPException(status_code=400, detail="Incorrect Password")
    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=400,
            detail="New password cannot be same as old password",
        )
    hashed_password = get_password_hash(body.new_password)
    current_user.hashed_password = hashed_password
    session.add(current_user)
    session.commit()
    return Message(message="Password updated successfully")


@router.get(
    path="/me",
    response_model=UserPublic,
    responses={
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def read_user_me(current_user: CurrentUser) -> Any:
    """
    Get current user.
    """
    return current_user


def _model_base(name: str) -> str:
    return name.split(":", maxsplit=1)[0].strip().casefold()


def _parse_chat_models(payload: dict[str, Any], embedding_model: str) -> list[OllamaModelOption]:
    embedding_base = _model_base(embedding_model)
    models: list[OllamaModelOption] = []
    for item in payload.get("models", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name or _model_base(name) == embedding_base:
            continue
        models.append(
            OllamaModelOption(
                name=name,
                size=int(item.get("size") or 0),
                modified_at=item.get("modified_at"),
            )
        )
    return sorted(models, key=lambda model: model.name.casefold())


async def _fetch_chat_models(
    embedding_model: str,
) -> tuple[bool, list[OllamaModelOption]]:
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            response = await client.get(f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags")
            response.raise_for_status()
            return True, _parse_chat_models(response.json(), embedding_model)
    except (httpx.HTTPError, ValueError, TypeError):
        return False, []


def _resolve_user_ai_settings(session: SessionDep, user_id: int) -> UserSettings:
    preferences = session.get(UserSettings, user_id)
    if preferences is not None:
        return preferences
    return UserSettings(user_id=user_id)


def _current_user_id(current_user: User) -> int:
    if current_user.id is None:
        raise HTTPException(status_code=401, detail="Invalid authenticated user")
    return current_user.id


@router.get(
    path="/me/ai-settings",
    response_model=UserAISettingsResponse,
    responses={401: {"model": StandardErrorResponse, "description": "Authentication required"}},
)
async def read_user_ai_settings(
    session: SessionDep, current_user: CurrentUser
) -> UserAISettingsResponse:
    preferences = _resolve_user_ai_settings(session, _current_user_id(current_user))
    ollama_available, models = await _fetch_chat_models(preferences.embedding_model)
    return UserAISettingsResponse(
        llm_model=preferences.llm_model,
        embedding_model=preferences.embedding_model,
        ollama_available=ollama_available,
        available_models=models,
    )


@router.patch(
    path="/me/ai-settings",
    response_model=UserAISettingsResponse,
    responses={
        400: {"model": StandardErrorResponse, "description": "Model is not installed"},
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        503: {"model": StandardErrorResponse, "description": "Ollama unavailable"},
    },
)
async def update_user_ai_settings(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    body: UserAISettingsUpdate,
) -> UserAISettingsResponse:
    preferences = _resolve_user_ai_settings(session, _current_user_id(current_user))
    ollama_available, models = await _fetch_chat_models(preferences.embedding_model)
    installed_names = {model.name for model in models}
    if not ollama_available:
        raise HTTPException(status_code=503, detail="Ollama is unavailable")
    if body.llm_model not in installed_names:
        raise HTTPException(status_code=400, detail="Selected model is not installed")

    preferences.llm_provider = LlmProvider.ollama
    preferences.llm_model = body.llm_model
    session.add(preferences)
    session.commit()
    session.refresh(preferences)

    return UserAISettingsResponse(
        llm_model=preferences.llm_model,
        embedding_model=preferences.embedding_model,
        ollama_available=True,
        available_models=models,
    )


@router.delete(
    path="/me",
    response_model=Message,
    responses={
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        403: {
            "model": StandardErrorResponse,
            "description": "Superuser cannot delete self",
        },
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def delete_user_me(session: SessionDep, current_user: CurrentUser) -> Any:
    """
    Delete the current user
    """
    if current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Superuser is not allowed to delete themself",
        )
    session.delete(current_user)
    session.commit()
    return Message(message="User Deleted Successfully")


@router.post(
    path="/signup",
    response_model=VerificationChallenge,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {
            "model": StandardErrorResponse,
            "description": "User with this email already exists",
        },
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def register_user(session: SessionDep, user_in: UserRegister) -> VerificationChallenge:
    """
    Register a new user
    """
    user = crud.get_user_by_email(session=session, email=user_in.email)
    if user:
        raise AppError(
            message="The user with this email already exists",
            error_code=ErrorCode.CONFLICT,
            status_code=status.HTTP_409_CONFLICT,
        )
    user_create = UserCreate.model_validate(user_in)
    user = crud.create_user(
        session=session,
        user_create=user_create,
        is_verified=False,
    )
    issued = issue_verification_code(session=session, user=user)
    try:
        send_verification_email(
            recipient=user.email,
            code=issued.code,
            recipient_name=user.full_name,
        )
    except EmailDeliveryError as exc:
        raise ExternalServiceError(
            "Your account was created, but the verification email could not be sent. "
            "Please retry from the verification page."
        ) from exc
    return VerificationChallenge(
        masked_email=mask_email(user.email),
        expires_at=issued.expires_at,
        resend_available_at=issued.resend_available_at,
    )


@router.post(path="/verify-email", response_model=Token)
def verify_email(
    response: Response,
    session: SessionDep,
    body: VerifyEmailRequest,
) -> Token:
    user = crud.get_user_by_email(session=session, email=str(body.email))
    if user is None or user.is_verified:
        raise AppError(
            message="Invalid or expired verification code.",
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        verify_email_code(session=session, user=user, code=body.code)
    except VerificationCodeExpiredError as exc:
        raise AppError(
            message="Verification code has expired.",
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=status.HTTP_410_GONE,
        ) from exc
    except InvalidVerificationCodeError as exc:
        raise AppError(
            message="Invalid or expired verification code.",
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    token_pair = auth_service.create_token_pair(session=session, user=user)
    set_auth_cookies(response, token_pair.access_token, token_pair.refresh_token)
    return Token(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        token_type=token_pair.token_type,
    )


@router.post(
    path="/resend-verification",
    response_model=ResendVerificationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def resend_verification(
    session: SessionDep,
    body: ResendVerificationRequest,
) -> ResendVerificationResponse:
    user = crud.get_user_by_email(session=session, email=str(body.email))
    if user is None or user.is_verified:
        return ResendVerificationResponse()
    try:
        issued = issue_verification_code(session=session, user=user)
        send_verification_email(
            recipient=user.email,
            code=issued.code,
            recipient_name=user.full_name,
        )
    except VerificationRateLimitError:
        pass
    except EmailDeliveryError:
        logger.warning("Verification email delivery failed for user %s", user.id)
    return ResendVerificationResponse()


@router.post(
    path="/me/email-change",
    response_model=VerificationChallenge,
    status_code=status.HTTP_202_ACCEPTED,
)
def change_email(
    response: Response,
    session: SessionDep,
    current_user: CurrentUser,
    body: EmailChangeRequest,
) -> VerificationChallenge:
    password_valid, _ = verify_password(body.password, current_user.hashed_password)
    if not password_valid:
        raise AppError(
            message="Current password is incorrect.",
            error_code=ErrorCode.AUTHENTICATION_ERROR,
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    new_email = str(body.new_email)
    existing = crud.get_user_by_email(session=session, email=new_email)
    if existing is not None and existing.id != current_user.id:
        raise AppError(
            message="An account already uses this email address.",
            error_code=ErrorCode.CONFLICT,
            status_code=status.HTTP_409_CONFLICT,
        )

    current_user.email = new_email
    current_user.is_verified = False
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    if current_user.id is None:
        raise AppError(message="Invalid authenticated user")
    auth_service.revoke_all_user_tokens(session=session, user_id=current_user.id)
    issued = issue_verification_code(session=session, user=current_user)
    try:
        send_verification_email(
            recipient=current_user.email,
            code=issued.code,
            recipient_name=current_user.full_name,
        )
    except EmailDeliveryError as exc:
        raise ExternalServiceError("Verification email could not be delivered.") from exc
    clear_auth_cookies(response)
    return VerificationChallenge(
        masked_email=mask_email(current_user.email),
        expires_at=issued.expires_at,
        resend_available_at=issued.resend_available_at,
    )


@router.get(
    path="/{user_id}",
    response_model=UserPublic,
    responses={
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        403: {"model": StandardErrorResponse, "description": "Insufficient privileges"},
        404: {"model": StandardErrorResponse, "description": "User not found"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def read_user_by_id(user_id: int, session: SessionDep, current_user: CurrentUser) -> Any:
    """
    Get a specific user by id
    """
    user = session.get(User, user_id)
    if user == current_user:
        return user
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="The user doesn't have enough priviledges",
        )
    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )
    return user


@router.patch(
    path="/{user_id}",
    dependencies=[Depends(get_current_active_superuser)],
    response_model=UserPublic,
    responses={
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        403: {
            "model": StandardErrorResponse,
            "description": "Admin privileges required",
        },
        404: {"model": StandardErrorResponse, "description": "User not found"},
        409: {"model": StandardErrorResponse, "description": "Email already in use"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def update_user(*, session: SessionDep, user_id: int, user_in: UserUpdate) -> Any:
    """
    Update a user.
    """
    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(
            status_code=404,
            detail="The user with this id does not exist",
        )
    if user_in.email:
        existing_user = crud.get_user_by_email(session=session, email=user_in.email)
        if existing_user and existing_user.id != user_id:
            raise HTTPException(status_code=409, detail="User with this email already exists")

    db_user = crud.update_user(session=session, db_user=db_user, user_in=user_in)
    return db_user


@router.delete(
    path="/{user_id}",
    dependencies=[Depends(get_current_active_superuser)],
    responses={
        401: {"model": StandardErrorResponse, "description": "Authentication required"},
        403: {
            "model": StandardErrorResponse,
            "description": "Admin privileges or cannot delete self",
        },
        404: {"model": StandardErrorResponse, "description": "User not found"},
        500: {"model": StandardErrorResponse, "description": "Internal server error"},
    },
)
def delete_user(session: SessionDep, current_user: CurrentUser, user_id: int) -> Message:
    """
    Delete a user.
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user == current_user:
        raise HTTPException(
            status_code=403, detail="Super users are not allowed to delete themselves"
        )
    # Cascade delete handles related records (documents, notes, etc.)
    session.delete(user)
    session.commit()
    return Message(message="User deleted successfully")
