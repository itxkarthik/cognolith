from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import settings


class EmailDeliveryError(RuntimeError):
    pass


def build_verification_email(
    *, recipient: str, code: str, recipient_name: str | None = None
) -> EmailMessage:
    greeting = f"Hello {recipient_name}," if recipient_name else "Hello,"
    sender_email = str(settings.EMAILS_FROM_EMAIL or "no-reply@localhost")
    sender_name = settings.EMAILS_FROM_NAME or settings.PROJECT_NAME
    message = EmailMessage()
    message["Subject"] = f"Verify your {settings.PROJECT_NAME} account"
    message["From"] = formataddr((sender_name, sender_email))
    message["To"] = recipient
    message.set_content(
        f"{greeting}\n\n"
        f"Your verification code is {code}.\n\n"
        "This code expires in 10 minutes. If you did not create this account, "
        "you can ignore this email.\n"
    )
    message.add_alternative(
        f"""
        <html>
          <body style="font-family:Arial,sans-serif;color:#171717;line-height:1.5">
            <p>{greeting}</p>
            <p>Use this code to verify your {settings.PROJECT_NAME} account:</p>
            <p style="font-size:28px;font-weight:700;letter-spacing:8px">{code}</p>
            <p>This code expires in 10 minutes.</p>
            <p>If you did not create this account, you can ignore this email.</p>
          </body>
        </html>
        """,
        subtype="html",
    )
    return message


def send_verification_email(
    *, recipient: str, code: str, recipient_name: str | None = None
) -> None:
    if not settings.SMTP_HOST or not settings.EMAILS_FROM_EMAIL:
        raise EmailDeliveryError("Email delivery is not configured")

    message = build_verification_email(
        recipient=recipient,
        code=code,
        recipient_name=recipient_name,
    )
    smtp_type = smtplib.SMTP_SSL if settings.SMTP_SSL else smtplib.SMTP
    try:
        with smtp_type(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
            if settings.SMTP_TLS and not settings.SMTP_SSL:
                smtp.starttls()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailDeliveryError("Verification email could not be delivered") from exc
