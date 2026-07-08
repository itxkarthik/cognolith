from app.services.email_service import build_verification_email


def test_verification_email_contains_code_and_expiry() -> None:
    message = build_verification_email(
        recipient="person@example.com",
        code="482913",
        recipient_name="Karthik",
    )

    assert message["To"] == "person@example.com"
    assert message["Subject"] == "Verify your Cognolith account"
    plain_part = message.get_body(preferencelist=("plain",))
    assert plain_part is not None
    body = plain_part.get_content()
    assert "482913" in body
    assert "10 minutes" in body
