import logging
import traceback
from typing import Any, Optional
from enum import Enum

from fastapi import Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class ErrorCode(str, Enum):
    """Standardized error codes for API responses."""
    
    # Client errors (4xx)
    VALIDATION_ERROR = "validation_error"
    AUTHENTICATION_ERROR = "authentication_error"
    AUTHORIZATION_ERROR = "authorization_error"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"
    REQUEST_TIMEOUT = "request_timeout"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    
    # Server errors (5xx)
    INTERNAL_SERVER_ERROR = "internal_server_error"
    SERVICE_UNAVAILABLE = "service_unavailable"
    DATABASE_ERROR = "database_error"
    EXTERNAL_SERVICE_ERROR = "external_service_error"
    
    # Generic
    UNKNOWN_ERROR = "unknown_error"


class ErrorDetail(BaseModel):
    """Detailed error information."""
    
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    field: Optional[str] = Field(None, description="Field name if validation error")
    value: Optional[Any] = Field(None, description="Invalid value that caused error")


class StandardErrorResponse(BaseModel):
    """Standardized error response schema."""
    
    status: str = Field("error", description="Response status")
    error: str = Field(..., description="Error code")
    message: str = Field(..., description="User-friendly error message")
    request_id: Optional[str] = Field(None, description="Unique request ID for tracking")
    details: Optional[list[ErrorDetail]] = Field(
        None, 
        description="Detailed error information (e.g., validation errors)"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "error",
                "error": "validation_error",
                "message": "Request validation failed",
                "request_id": "550e8400-e29b-41d4-a716-446655440000",
                "details": [
                    {
                        "code": "value_error",
                        "message": "Field required",
                        "field": "title",
                        "value": None
                    }
                ]
            }
        }


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
