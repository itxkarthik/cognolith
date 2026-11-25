from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import settings


class EmailDeliveryError(RuntimeError):
    pass


def _new_message(*, recipient: str, subject: str) -> EmailMessage:
    sender_email = str(settings.EMAILS_FROM_EMAIL or "no-reply@localhost")
    sender_name = settings.EMAILS_FROM_NAME or settings.PROJECT_NAME
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((sender_name, sender_email))
    message["To"] = recipient
    return message


def build_verification_email(
    *, recipient: str, code: str, recipient_name: str | None = None
) -> EmailMessage:
    greeting = f"Hello {recipient_name}," if recipient_name else "Hello,"
    message = _new_message(
        recipient=recipient, subject=f"Verify your {settings.PROJECT_NAME} account"
    )
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


def build_email_change_code_email(
    *, recipient: str, code: str, recipient_name: str | None = None
) -> EmailMessage:
    greeting = f"Hello {recipient_name}," if recipient_name else "Hello,"
    message = _new_message(
        recipient=recipient, subject=f"Confirm your new {settings.PROJECT_NAME} email address"
    )
    message.set_content(
        f"{greeting}\n\n"
        f"Enter this code in {settings.PROJECT_NAME} to confirm this email address: {code}\n\n"
        "This code expires in 10 minutes. If you did not ask to change your email, "
        "you can ignore this message; your account is unchanged.\n"
    )
    return message


def build_security_notice_email(
    *, recipient: str, subject: str, body: str, recipient_name: str | None = None
) -> EmailMessage:
    greeting = f"Hello {recipient_name}," if recipient_name else "Hello,"
    message = _new_message(recipient=recipient, subject=subject)
    message.set_content(
        f"{greeting}\n\n{body}\n\n"
        "If this wasn't you, reset your password and sign out of all sessions.\n"
    )
    return message


def send_verification_email(
    *, recipient: str, code: str, recipient_name: str | None = None
) -> None:
    _deliver(build_verification_email(recipient=recipient, code=code, recipient_name=recipient_name))


def send_email_change_code(
    *, recipient: str, code: str, recipient_name: str | None = None
) -> None:
    _deliver(
        build_email_change_code_email(recipient=recipient, code=code, recipient_name=recipient_name)
    )


def send_security_notice(
    *, recipient: str, subject: str, body: str, recipient_name: str | None = None
) -> None:
    _deliver(
        build_security_notice_email(
            recipient=recipient, subject=subject, body=body, recipient_name=recipient_name
        )
    )


def _deliver(message: EmailMessage) -> None:
    if not settings.SMTP_HOST or not settings.EMAILS_FROM_EMAIL:
        raise EmailDeliveryError("Email delivery is not configured")

    smtp_type = smtplib.SMTP_SSL if settings.SMTP_SSL else smtplib.SMTP
    try:
        with smtp_type(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as smtp:
            if settings.SMTP_TLS and not settings.SMTP_SSL:
                smtp.starttls()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailDeliveryError("Email could not be delivered") from exc
