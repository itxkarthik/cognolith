from app.core.config import Settings


def test_mailpit_defaults_are_valid() -> None:
    configured = Settings(
        SECRET_KEY="test-secret",
        SMTP_HOST="mailpit",
        SMTP_PORT=1025,
        SMTP_TLS=False,
        EMAILS_FROM_EMAIL="no-reply@example.com",
    )

    assert configured.emails_enabled is True
