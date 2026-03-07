from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class MessageOut(BaseModel):
    message: str


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, min_length=1, max_length=80)
    email: EmailStr
    phone: str | None = Field(default=None, min_length=8, max_length=20)
    password: str = Field(min_length=8, max_length=128)

    @field_validator('username')
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator('first_name', 'last_name')
    @classmethod
    def normalize_optional_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value

    @field_validator('phone')
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return ''.join(ch for ch in value if ch.isdigit() or ch == '+')


class LoginRequest(BaseModel):
    login: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20)


class OtpSendEmailRequest(BaseModel):
    email: EmailStr


class OtpVerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=8)


class OtpSendPhoneRequest(BaseModel):
    phone: str = Field(min_length=8, max_length=20)

    @field_validator('phone')
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        return ''.join(ch for ch in value if ch.isdigit() or ch == '+')


class OtpVerifyPhoneRequest(BaseModel):
    phone: str = Field(min_length=8, max_length=20)
    code: str = Field(min_length=4, max_length=8)

    @field_validator('phone')
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        return ''.join(ch for ch in value if ch.isdigit() or ch == '+')


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=20)
    new_password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    id: int
    username: str
    first_name: str | None
    last_name: str | None
    email: EmailStr
    phone: str | None
    state: str | None
    target_exam_year: int | None
    is_active: bool
    is_blocked: bool
    is_email_verified: bool
    is_phone_verified: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = 'bearer'
    expires_in: int
    refresh_expires_in: int
    user: UserOut


class ProfileUpdateRequest(BaseModel):
    first_name: str | None = Field(default=None, max_length=80)
    last_name: str | None = Field(default=None, max_length=80)
    username: str | None = Field(default=None, min_length=3, max_length=80)
    phone: str | None = Field(default=None, min_length=8, max_length=20)
    state: str | None = Field(default=None, max_length=80)
    target_exam_year: int | None = Field(default=None, ge=2024, le=2100)

    @field_validator('first_name', 'last_name', 'state')
    @classmethod
    def normalize_optional_fields(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = value.strip()
        return clean or None

    @field_validator('username')
    @classmethod
    def normalize_optional_username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().lower()

    @field_validator('phone')
    @classmethod
    def normalize_optional_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = ''.join(ch for ch in value if ch.isdigit() or ch == '+')
        return clean or None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
