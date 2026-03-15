from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.db_config import get_database_url

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    APP_ENV: str = 'development'
    DATABASE_URL: str = get_database_url()

    SECRET_KEY: str = 'change-this-secret-key'
    ALGORITHM: str = 'HS256'
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 15
    SIGNUP_OTP_EXPIRE_MINUTES: int = 5

    FRONTEND_BASE_URL: str = 'http://127.0.0.1:5500'
    CORS_ORIGINS: str = 'http://127.0.0.1:5500,http://localhost:5500'

    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_USE_TLS: bool = True
    MAIL_FROM: str | None = None
    MAIL_FROM_NAME: str = 'CivilEdge'

    TWILIO_ACCOUNT_SID: str | None = None
    TWILIO_AUTH_TOKEN: str | None = None
    TWILIO_FROM_NUMBER: str | None = None
    TWILIO_MESSAGING_SERVICE_SID: str | None = None
    DEFAULT_PHONE_COUNTRY_CODE: str = '+91'

    AWS_REGION: str = 'us-east-1'
    AWS_S3_BUCKET_QUESTIONS: str = 'vishal-lakshya'
    AWS_S3_QUESTIONS_OBJECT_KEY: str = 'manual-question/manual-question.ndjson.gz'
    AWS_S3_TESTS_PREFIX: str = 'tests/'
    AWS_S3_PYQ_PREFIX: str = 'pyq/'
    AWS_S3_ENDPOINT_URL: str | None = None

    @field_validator('APP_ENV')
    @classmethod
    def normalize_env(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator('ACCESS_TOKEN_EXPIRE_MINUTES')
    @classmethod
    def validate_access_ttl(cls, value: int) -> int:
        return max(120, int(value))

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.CORS_ORIGINS.split(',') if item.strip()]

    @property
    def cors_origin_regex(self) -> str | None:
        if self.APP_ENV == 'development':
            return r'^https?://(localhost|127\.0\.0\.1)(:\d+)?$'
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
