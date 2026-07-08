from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class VerificationChallenge(BaseModel):
    masked_email: str
    expires_at: datetime
    resend_available_at: datetime


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ResendVerificationResponse(BaseModel):
    message: str = "If the account is pending verification, a new code will be sent."
    retry_after_seconds: int = 60


class EmailChangeRequest(BaseModel):
    new_email: EmailStr
    password: str = Field(min_length=8, max_length=128)
