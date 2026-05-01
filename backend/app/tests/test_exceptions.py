"""
Unit tests for global exception handling and standardized error responses.
"""

import pytest
from app.core.exceptions import (
    AppError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    ErrorCode,
    ErrorDetail,
    ExternalServiceError,
    RateLimitedError,
    ResourceNotFoundError,
    StandardErrorResponse,
    ValidationError,
    global_exception_handler,
)
from fastapi.testclient import TestClient


class TestErrorCodes:
    """Test error code enumeration."""

    def test_validation_error_code(self):
        assert ErrorCode.VALIDATION_ERROR.value == "validation_error"

    def test_authentication_error_code(self):
        assert ErrorCode.AUTHENTICATION_ERROR.value == "authentication_error"

    def test_authorization_error_code(self):
        assert ErrorCode.AUTHORIZATION_ERROR.value == "authorization_error"

    def test_not_found_code(self):
        assert ErrorCode.NOT_FOUND.value == "not_found"

    def test_database_error_code(self):
        assert ErrorCode.DATABASE_ERROR.value == "database_error"

    def test_external_service_error_code(self):
        assert ErrorCode.EXTERNAL_SERVICE_ERROR.value == "external_service_error"


class TestAppError:
    """Test base AppError class."""

    def test_app_error_creation(self):
        exc = AppError(message="Test error", error_code=ErrorCode.UNKNOWN_ERROR, status_code=500)
        assert exc.message == "Test error"
        assert exc.error_code == ErrorCode.UNKNOWN_ERROR
        assert exc.status_code == 500

    def test_app_error_with_details(self):
        detail = ErrorDetail(code="test_code", message="Test detail", field="test_field")
        exc = AppError(
            message="Test error",
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=422,
            details=[detail],
        )
        assert len(exc.details) == 1
        assert exc.details[0].field == "test_field"


class TestValidationError:
    """Test ValidationError class."""

    def test_validation_exception_defaults(self):
        exc = ValidationError()
        assert exc.message == "Request validation failed"
        assert exc.error_code == ErrorCode.VALIDATION_ERROR
        assert exc.status_code == 422

    def test_validation_exception_custom_message(self):
        exc = ValidationError(message="Custom validation error")
        assert exc.message == "Custom validation error"

    def test_validation_exception_with_details(self):
        detail = ErrorDetail(
            code="email_invalid",
            message="Email format is invalid",
            field="email",
            value="not-an-email",
        )
        exc = ValidationError(message="Email validation failed", details=[detail])
        assert exc.details[0].field == "email"


class TestAuthenticationError:
    """Test AuthenticationError class."""

    def test_authentication_exception_defaults(self):
        exc = AuthenticationError()
        assert exc.message == "Authentication failed"
        assert exc.error_code == ErrorCode.AUTHENTICATION_ERROR
        assert exc.status_code == 401

    def test_authentication_exception_custom_message(self):
        exc = AuthenticationError("Invalid credentials")
        assert exc.message == "Invalid credentials"


class TestAuthorizationError:
    """Test AuthorizationError class."""

    def test_authorization_exception_defaults(self):
        exc = AuthorizationError()
        assert exc.message == "Insufficient permissions"
        assert exc.error_code == ErrorCode.AUTHORIZATION_ERROR
        assert exc.status_code == 403


class TestResourceNotFoundError:
    """Test ResourceNotFoundError class."""

    def test_not_found_exception_defaults(self):
        exc = ResourceNotFoundError()
        assert exc.message == "Resource not found"
        assert exc.error_code == ErrorCode.NOT_FOUND
        assert exc.status_code == 404

    def test_not_found_exception_custom_message(self):
        exc = ResourceNotFoundError("Document with ID 123 not found")
        assert exc.message == "Document with ID 123 not found"


class TestConflictError:
    """Test ConflictError class."""

    def test_conflict_exception_defaults(self):
        exc = ConflictError()
        assert exc.message == "Resource conflict"
        assert exc.error_code == ErrorCode.CONFLICT
        assert exc.status_code == 409


class TestRateLimitedError:
    """Test RateLimitedError class."""

    def test_rate_limited_exception_defaults(self):
        exc = RateLimitedError()
        assert exc.message == "Rate limit exceeded"
        assert exc.error_code == ErrorCode.RATE_LIMITED
        assert exc.status_code == 429


class TestExternalServiceError:
    """Test ExternalServiceError class."""

    def test_external_service_exception_defaults(self):
        exc = ExternalServiceError()
        assert exc.message == "External service error"
        assert exc.error_code == ErrorCode.EXTERNAL_SERVICE_ERROR
        assert exc.status_code == 503

    def test_external_service_exception_custom_message(self):
        exc = ExternalServiceError("LLM service unavailable")
        assert exc.message == "LLM service unavailable"


class TestStandardErrorResponse:
    """Test StandardErrorResponse schema."""

    def test_error_response_creation(self):
        response = StandardErrorResponse(
            status="error",
            error="validation_error",
            message="Invalid input",
            request_id="550e8400-e29b-41d4-a716-446655440000",
        )
        assert response.status == "error"
        assert response.error == "validation_error"
        assert response.message == "Invalid input"
        assert response.request_id == "550e8400-e29b-41d4-a716-446655440000"

    def test_error_response_with_details(self):
        detail = ErrorDetail(code="email_invalid", message="Email is required", field="email")
        response = StandardErrorResponse(
            status="error",
            error="validation_error",
            message="Validation failed",
            request_id="550e8400-e29b-41d4-a716-446655440000",
            details=[detail],
        )
        assert len(response.details) == 1
        assert response.details[0].field == "email"

    def test_error_response_json_serialization(self):
        response = StandardErrorResponse(
            status="error",
            error="not_found",
            message="Resource not found",
            request_id="550e8400-e29b-41d4-a716-446655440000",
        )
        json_data = response.model_dump(exclude_none=True)
        assert json_data["status"] == "error"
        assert json_data["error"] == "not_found"
        assert "details" not in json_data  # Should be excluded if None


class TestExceptionHandler:
    """Test global exception handler in FastAPI context."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app."""
        from app.core.middleware import RequestIDMiddleware
        from fastapi import FastAPI

        test_app = FastAPI()
        test_app.add_middleware(RequestIDMiddleware)
        test_app.add_exception_handler(Exception, global_exception_handler)

        @test_app.get("/validation-error")
        async def validation_error_endpoint():
            raise ValidationError(
                message="Invalid request",
                details=[
                    ErrorDetail(code="email_invalid", message="Email is invalid", field="email")
                ],
            )

        @test_app.get("/auth-error")
        async def auth_error_endpoint():
            raise AuthenticationError("Invalid token")

        @test_app.get("/not-found")
        async def not_found_endpoint():
            raise ResourceNotFoundError("User not found")

        @test_app.get("/generic-error")
        async def generic_error_endpoint():
            raise ValueError("Something went wrong")

        return test_app

    def test_validation_error_handling(self, app):
        client = TestClient(app)
        response = client.get("/validation-error")

        assert response.status_code == 422
        data = response.json()
        assert data["status"] == "error"
        assert data["error"] == "validation_error"
        assert data["message"] == "Invalid request"
        assert data["request_id"] is not None
        assert len(data["details"]) == 1
        assert data["details"][0]["field"] == "email"

    def test_auth_error_handling(self, app):
        client = TestClient(app)
        response = client.get("/auth-error")

        assert response.status_code == 401
        data = response.json()
        assert data["status"] == "error"
        assert data["error"] == "authentication_error"
        assert data["message"] == "Invalid token"

    def test_not_found_handling(self, app):
        client = TestClient(app)
        response = client.get("/not-found")

        assert response.status_code == 404
        data = response.json()
        assert data["status"] == "error"
        assert data["error"] == "not_found"
        assert data["message"] == "User not found"

    def test_generic_error_handling(self, app):
        client = TestClient(app)
        response = client.get("/generic-error")

        assert response.status_code == 500
        data = response.json()
        assert data["status"] == "error"
        assert data["error"] == "internal_server_error"
        assert "request_id" in data


class TestErrorDetailVariations:
    """Test ErrorDetail with various configurations."""

    def test_error_detail_minimal(self):
        detail = ErrorDetail(code="error_code", message="Error message")
        assert detail.field is None
        assert detail.value is None

    def test_error_detail_with_field(self):
        detail = ErrorDetail(code="validation_error", message="Field is required", field="username")
        assert detail.field == "username"

    def test_error_detail_with_all_fields(self):
        detail = ErrorDetail(code="type_error", message="Expected string", field="age", value=25)
        assert detail.code == "type_error"
        assert detail.field == "age"
        assert detail.value == 25
