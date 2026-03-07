from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.admin.config import settings


pwd_context = CryptContext(schemes=['pbkdf2_sha256'], deprecated='auto')


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return pwd_context.verify(password, hashed_password)


def now_utc() -> datetime:
    return datetime.utcnow()


def _unix_utc(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


def token_hash(value: str) -> str:
    return sha256(value.encode('utf-8')).hexdigest()


def create_access_token(user_id: int, token_version: int, session_id: str) -> tuple[str, datetime]:
    expire_at = now_utc() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        'sub': str(user_id),
        'tv': int(token_version),
        'sid': session_id,
        'type': 'access',
        'exp': _unix_utc(expire_at),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM), expire_at


def create_refresh_token(user_id: int, token_version: int, session_id: str) -> tuple[str, str, datetime]:
    expire_at = now_utc() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    jti = uuid4().hex
    payload = {
        'sub': str(user_id),
        'tv': int(token_version),
        'sid': session_id,
        'jti': jti,
        'type': 'refresh',
        'exp': _unix_utc(expire_at),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM), jti, expire_at


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        raise ValueError('Invalid or expired token') from exc
