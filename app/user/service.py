import secrets
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.admin.config import settings
from app.admin.platform_settings_service import get_or_create_platform_settings, next_lock_expiry
from app.notifications import send_password_reset_email, send_phone_otp, send_signup_email_otp
from app.user.models import User, UserPasswordResetToken, UserRefreshToken, UserVerificationCode
from app.user.schemas import ProfileUpdateRequest, TokenResponse, UserOut
from app.user.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    now_utc,
    token_hash,
    verify_password,
)


def _normalize_login(login: str) -> str:
    return login.strip()


def _generate_otp(length: int = 6) -> str:
    return ''.join(secrets.choice('0123456789') for _ in range(length))


def _is_target_verified(db: Session, target: str, channel: str, purpose: str = 'signup') -> bool:
    stmt = (
        select(UserVerificationCode)
        .where(
            UserVerificationCode.target == target,
            UserVerificationCode.channel == channel,
            UserVerificationCode.purpose == purpose,
            UserVerificationCode.consumed_at.is_not(None),
        )
        .order_by(UserVerificationCode.created_at.desc())
    )
    return db.execute(stmt).scalars().first() is not None


def _issue_tokens(
    db: Session,
    user: User,
    *,
    session_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> TokenResponse:
    sid = session_id or uuid4().hex
    platform_settings = get_or_create_platform_settings(db)
    timeout_minutes = max(5, int(platform_settings.user_session_timeout_minutes))
    access_token, access_exp = create_access_token(user.id, user.token_version, sid, expires_minutes=timeout_minutes)
    refresh_token, jti, refresh_exp = create_refresh_token(user.id, user.token_version, sid, expires_minutes=timeout_minutes)

    db.add(
        UserRefreshToken(
            user_id=user.id,
            jti=jti,
            token_hash=token_hash(refresh_token),
            session_id=sid,
            expires_at=refresh_exp,
            created_by_ip=ip_address,
            user_agent=user_agent,
        )
    )
    db.commit()
    db.refresh(user)

    now = now_utc()
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=max(1, int((access_exp - now).total_seconds())),
        refresh_expires_in=max(1, int((refresh_exp - now).total_seconds())),
        user=UserOut.model_validate(user),
    )


def send_signup_otp(db: Session, *, target: str, channel: str) -> None:
    if channel == 'email':
        exists_stmt = select(User.id).where(User.email == target)
    else:
        exists_stmt = select(User.id).where(User.phone == target)
    if db.execute(exists_stmt).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f'{channel.title()} already registered')

    now = now_utc()
    otp = _generate_otp(6)

    cleanup_stmt = select(UserVerificationCode).where(
        UserVerificationCode.target == target,
        UserVerificationCode.channel == channel,
        UserVerificationCode.purpose == 'signup',
        UserVerificationCode.consumed_at.is_(None),
    )
    for item in db.execute(cleanup_stmt).scalars().all():
        db.delete(item)

    db.add(
        UserVerificationCode(
            target=target,
            channel=channel,
            purpose='signup',
            code_hash=token_hash(otp),
            expires_at=now + timedelta(minutes=settings.SIGNUP_OTP_EXPIRE_MINUTES),
        )
    )
    db.commit()

    if channel == 'email':
        send_signup_email_otp(email=target, otp=otp, audience='User')
    else:
        send_phone_otp(phone=target, otp=otp, audience='User')

    if settings.APP_ENV != 'production':
        print(f'[DEV USER OTP] channel={channel} target={target} otp={otp}')


def verify_signup_otp(db: Session, *, target: str, channel: str, code: str) -> None:
    now = now_utc()
    stmt = (
        select(UserVerificationCode)
        .where(
            UserVerificationCode.target == target,
            UserVerificationCode.channel == channel,
            UserVerificationCode.purpose == 'signup',
            UserVerificationCode.consumed_at.is_(None),
        )
        .order_by(UserVerificationCode.created_at.desc())
    )
    record = db.execute(stmt).scalars().first()
    if not record:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='OTP not found')
    if record.expires_at < now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='OTP expired')
    if record.code_hash != token_hash(code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid OTP')

    record.consumed_at = now
    db.commit()


def register_user(
    db: Session,
    *,
    username: str,
    first_name: str | None,
    last_name: str | None,
    email: str,
    phone: str | None,
    password: str,
) -> User:
    duplicate_conditions = [User.username == username, User.email == email]
    if phone:
        duplicate_conditions.append(User.phone == phone)
    duplicate_stmt = select(User).where(or_(*duplicate_conditions))
    if db.execute(duplicate_stmt).scalars().first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='User already exists')

    if not _is_target_verified(db, email, 'email'):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Email OTP not verified')
    if phone and not _is_target_verified(db, phone, 'phone'):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Phone OTP not verified')

    user = User(
        username=username,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        hashed_password=hash_password(password),
        is_email_verified=True,
        is_phone_verified=bool(phone),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login_user(
    db: Session,
    *,
    login: str,
    password: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> TokenResponse:
    normalized = _normalize_login(login)
    stmt = select(User).where(
        or_(
            User.username == normalized.lower(),
            User.email == normalized.lower(),
            User.phone == normalized,
        )
    )
    user = db.execute(stmt).scalars().first()
    platform_settings = get_or_create_platform_settings(db)
    now = now_utc()

    if user and user.locked_until and user.locked_until > now:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f'Account locked until {user.locked_until.isoformat()}',
        )
    if user and user.locked_until and user.locked_until <= now:
        user.locked_until = None
        user.failed_login_attempts = 0
        db.commit()
        db.refresh(user)

    if not user or not verify_password(password, user.hashed_password):
        if user:
            user.failed_login_attempts = int(user.failed_login_attempts or 0) + 1
            user.last_failed_login_at = now
            if platform_settings.lock_account_on_repeated_failures and user.failed_login_attempts >= int(platform_settings.max_login_attempts):
                user.locked_until = next_lock_expiry(now, platform_settings.timezone)
                user.token_version += 1
                for active_token in db.execute(
                    select(UserRefreshToken).where(UserRefreshToken.user_id == user.id, UserRefreshToken.revoked_at.is_(None))
                ).scalars().all():
                    active_token.revoked_at = now
                user.failed_login_attempts = 0
                db.commit()
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail=f'Account locked until {user.locked_until.isoformat()}',
                )
            db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid credentials')
    if user.is_blocked or not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Account is not allowed')

    if user.failed_login_attempts or user.locked_until:
        user.failed_login_attempts = 0
        user.locked_until = None
        db.commit()
        db.refresh(user)

    return _issue_tokens(db, user, ip_address=ip_address, user_agent=user_agent)


def refresh_user_token(
    db: Session,
    *,
    refresh_token: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> TokenResponse:
    try:
        payload = decode_token(refresh_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    if payload.get('type') != 'refresh':
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token type')

    user_id = payload.get('sub')
    jti = payload.get('jti')
    sid = payload.get('sid')
    token_version = int(payload.get('tv', -1))
    if not user_id or not jti or not sid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token payload')

    now = now_utc()
    token_row_stmt = select(UserRefreshToken).where(
        UserRefreshToken.jti == jti,
        UserRefreshToken.user_id == int(user_id),
        UserRefreshToken.token_hash == token_hash(refresh_token),
    )
    token_row = db.execute(token_row_stmt).scalars().first()
    if not token_row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Refresh token not found')
    if token_row.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Refresh token revoked')
    if token_row.expires_at < now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Refresh token expired')

    user = db.get(User, int(user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='User not found')
    if user.locked_until and user.locked_until > now:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=f'Account locked until {user.locked_until.isoformat()}')
    if token_version != user.token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Token no longer valid')
    if user.is_blocked or not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Account is not allowed')

    token_row.revoked_at = now
    db.flush()

    return _issue_tokens(
        db,
        user,
        session_id=sid,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def forgot_password(db: Session, *, email: str) -> None:
    stmt = select(User).where(User.email == email)
    user = db.execute(stmt).scalars().first()
    if not user:
        return

    token = secrets.token_urlsafe(48)
    now = now_utc()
    db.add(
        UserPasswordResetToken(
            user_id=user.id,
            token_hash=token_hash(token),
            expires_at=now + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
        )
    )
    db.commit()

    reset_link = f"{settings.FRONTEND_BASE_URL}/frontend/auth/reset-password.html?token={token}"
    send_password_reset_email(email=email, reset_link=reset_link, audience='User')

    if settings.APP_ENV != 'production':
        print(f'[DEV USER RESET LINK] email={email} url={reset_link}')


def reset_password(db: Session, *, token: str, new_password: str) -> None:
    now = now_utc()
    stmt = select(UserPasswordResetToken).where(
        UserPasswordResetToken.token_hash == token_hash(token),
        UserPasswordResetToken.used_at.is_(None),
    )
    reset_row = db.execute(stmt).scalars().first()
    if not reset_row:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid reset token')
    if reset_row.expires_at < now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Reset token expired')

    user = db.get(User, reset_row.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid reset token')

    user.hashed_password = hash_password(new_password)
    user.token_version += 1
    reset_row.used_at = now

    active_tokens_stmt = select(UserRefreshToken).where(
        UserRefreshToken.user_id == user.id,
        UserRefreshToken.revoked_at.is_(None),
    )
    for active_token in db.execute(active_tokens_stmt).scalars().all():
        active_token.revoked_at = now

    db.commit()


def logout_user(db: Session, *, refresh_token: str) -> None:
    try:
        payload = decode_token(refresh_token)
    except ValueError:
        return

    jti = payload.get('jti')
    user_id = payload.get('sub')
    if not jti or not user_id:
        return

    stmt = select(UserRefreshToken).where(
        UserRefreshToken.jti == jti,
        UserRefreshToken.user_id == int(user_id),
        UserRefreshToken.token_hash == token_hash(refresh_token),
        UserRefreshToken.revoked_at.is_(None),
    )
    row = db.execute(stmt).scalars().first()
    if row:
        row.revoked_at = now_utc()
        db.commit()


def logout_user_all_devices(db: Session, *, user: User) -> None:
    now = now_utc()
    user.token_version += 1
    active_tokens_stmt = select(UserRefreshToken).where(
        UserRefreshToken.user_id == user.id,
        UserRefreshToken.revoked_at.is_(None),
    )
    for active_token in db.execute(active_tokens_stmt).scalars().all():
        active_token.revoked_at = now
    db.commit()


def get_my_profile(user: User) -> UserOut:
    return UserOut.model_validate(user)


def update_my_profile(db: Session, *, user: User, payload: ProfileUpdateRequest) -> UserOut:
    if payload.username and payload.username != user.username:
        duplicate = db.execute(select(User).where(User.username == payload.username, User.id != user.id)).scalars().first()
        if duplicate:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Username already taken')
        user.username = payload.username

    if payload.phone != user.phone:
        if payload.phone:
            duplicate = db.execute(select(User).where(User.phone == payload.phone, User.id != user.id)).scalars().first()
            if duplicate:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Phone already taken')
        user.phone = payload.phone

    user.first_name = payload.first_name
    user.last_name = payload.last_name
    user.state = payload.state
    user.target_exam_year = payload.target_exam_year

    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


def change_my_password(db: Session, *, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Current password is incorrect')

    user.hashed_password = hash_password(new_password)
    user.token_version += 1
    now = now_utc()
    active_tokens_stmt = select(UserRefreshToken).where(
        UserRefreshToken.user_id == user.id,
        UserRefreshToken.revoked_at.is_(None),
    )
    for active_token in db.execute(active_tokens_stmt).scalars().all():
        active_token.revoked_at = now

    db.commit()
