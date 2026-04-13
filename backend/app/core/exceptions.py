import logging
from typing import Optional

from fastapi import Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from app.schemas.error import ErrorCode, ErrorDetail, StandardErrorResponse

logger = logging.getLogger(__name__)


class AppException(Exception):
    """Base exception for the application."""
    
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[list[ErrorDetail]] = None,
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or []
        super().__init__(message)


class ValidationException(AppException):
    """Raised when request validation fails."""
    
    def __init__(
        self, 
        message: str = "Request validation failed",
        details: Optional[list[ErrorDetail]] = None
    ):
        super().__init__(
            message=message,
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class AuthenticationException(AppException):
    """Raised when authentication fails."""
    
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            message=message,
            error_code=ErrorCode.AUTHENTICATION_ERROR,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class AuthorizationException(AppException):
    """Raised when user lacks required permissions."""
    
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(
            message=message,
            error_code=ErrorCode.AUTHORIZATION_ERROR,
            status_code=status.HTTP_403_FORBIDDEN,
        )


class ResourceNotFoundException(AppException):
    """Raised when requested resource is not found."""
    
    def __init__(self, message: str = "Resource not found"):
        super().__init__(
            message=message,
            error_code=ErrorCode.NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ConflictException(AppException):
    """Raised when request conflicts with existing data."""
    
    def __init__(self, message: str = "Resource conflict"):
        super().__init__(
            message=message,
            error_code=ErrorCode.CONFLICT,
            status_code=status.HTTP_409_CONFLICT,
        )


class RateLimitedException(AppException):
    """Raised when rate limit is exceeded."""
    
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(
            message=message,
            error_code=ErrorCode.RATE_LIMITED,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )


class ExternalServiceException(AppException):
    """Raised when external service (LLM, embeddings, etc.) fails."""
    
    def __init__(self, message: str = "External service error"):
        super().__init__(
            message=message,
            error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Global exception handler for FastAPI.
    Converts all exceptions into standardized error responses.
    
    Args:
        request: The FastAPI request
        exc: The exception that was raised
    
    Returns:
        JSONResponse with standardized error format
    """
    # Get request ID from request state (set by RequestIDMiddleware)
    request_id = getattr(request.state, "request_id", None)
    
    # Handle AppException
    if isinstance(exc, AppException):
        error_response = StandardErrorResponse(
            status="error",
            error=exc.error_code.value,
            message=exc.message,
            request_id=request_id,
            details=exc.details if exc.details else None,
        )
        
        logger.warning(
            f"App exception: {exc.error_code.value} - {exc.message}",
            extra={"request_id": request_id}
        )
        
        return JSONResponse(
            status_code=exc.status_code,
            content=error_response.model_dump(exclude_none=True),
        )
    
    # Handle SQLAlchemy errors
    if isinstance(exc, SQLAlchemyError):
        error_response = StandardErrorResponse(
            status="error",
            error=ErrorCode.DATABASE_ERROR.value,
            message="Database operation failed",
            request_id=request_id,
        )
        
        logger.error(
            f"Database error: {str(exc)}",
            extra={"request_id": request_id},
            exc_info=True,
        )
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response.model_dump(exclude_none=True),
        )
    
    # Handle all other exceptions as internal server errors
    error_response = StandardErrorResponse(
        status="error",
        error=ErrorCode.INTERNAL_SERVER_ERROR.value,
        message="An unexpected error occurred. Please try again later.",
        request_id=request_id,
    )
    
    logger.error(
        f"Unhandled exception: {type(exc).__name__} - {str(exc)}",
        extra={"request_id": request_id},
        exc_info=True,
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.model_dump(exclude_none=True),
    )
