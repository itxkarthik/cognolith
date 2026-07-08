from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorCode(StrEnum):
    """Standardized error codes for API responses."""

    # Client errors (4xx)
    VALIDATION_ERROR = "validation_error"
    AUTHENTICATION_ERROR = "authentication_error"
    EMAIL_NOT_VERIFIED = "email_not_verified"
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
    AI_SERVICE_UNAVAILABLE = "ai_service_unavailable"
    DATABASE_ERROR = "database_error"
    EXTERNAL_SERVICE_ERROR = "external_service_error"

    # Generic
    UNKNOWN_ERROR = "unknown_error"


class ErrorDetail(BaseModel):
    """Detailed error information."""

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    field: str | None = Field(default=None, description="Field name if validation error")
    value: Any | None = Field(default=None, description="Invalid value that caused error")


class StandardErrorResponse(BaseModel):
    """Standardized error response schema."""

    model_config = ConfigDict(
        json_schema_extra={
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
                        "value": None,
                    }
                ],
            }
        }
    )

    status: str = Field(default="error", description="Response status")
    error: str = Field(..., description="Error code")
    message: str = Field(..., description="User-friendly error message")
    request_id: str | None = Field(default=None, description="Unique request ID for tracking")
    details: list[ErrorDetail] | None = Field(
        default=None,
        description="Detailed error information (e.g., validation errors)",
    )
