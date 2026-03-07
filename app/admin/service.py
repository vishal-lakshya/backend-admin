import secrets
from datetime import timedelta
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.admin.config import settings
from app.admin.models import AdminUser, PasswordResetToken, RefreshToken, VerificationCode
from app.admin.schemas import AdminSessionListOut, AdminSessionOut, ProfileUpdateRequest, TokenResponse, UserOut
from app.notifications import send_password_reset_email, send_phone_otp, send_signup_email_otp
from app.admin.security import (
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
        select(VerificationCode)
        .where(
            VerificationCode.target == target,
            VerificationCode.channel == channel,
            VerificationCode.purpose == purpose,
            VerificationCode.consumed_at.is_not(None),
        )
        .order_by(VerificationCode.created_at.desc())
    )
    return db.execute(stmt).scalars().first() is not None


def _issue_tokens(
    db: Session,
    user: AdminUser,
    *,
    session_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> TokenResponse:
    sid = session_id or uuid4().hex
    access_token, access_exp = create_access_token(user.id, user.token_version, sid)
    refresh_token, jti, refresh_exp = create_refresh_token(user.id, user.token_version, sid)

    db.add(
        RefreshToken(
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
        exists_stmt = select(AdminUser.id).where(AdminUser.email == target)
    else:
        exists_stmt = select(AdminUser.id).where(AdminUser.phone == target)
    if db.execute(exists_stmt).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f'{channel.title()} already registered')

    now = now_utc()
    otp = _generate_otp(6)

    cleanup_stmt = select(VerificationCode).where(
        VerificationCode.target == target,
        VerificationCode.channel == channel,
        VerificationCode.purpose == 'signup',
        VerificationCode.consumed_at.is_(None),
    )
    for item in db.execute(cleanup_stmt).scalars().all():
        db.delete(item)

    db.add(
        VerificationCode(
            target=target,
            channel=channel,
            purpose='signup',
            code_hash=token_hash(otp),
            expires_at=now + timedelta(minutes=settings.SIGNUP_OTP_EXPIRE_MINUTES),
        )
    )
    db.commit()

    if channel == 'email':
        send_signup_email_otp(email=target, otp=otp, audience='Admin')
    else:
        send_phone_otp(phone=target, otp=otp, audience='Admin')

    if settings.APP_ENV != 'production':
        print(f'[DEV OTP] channel={channel} target={target} otp={otp}')


def verify_signup_otp(db: Session, *, target: str, channel: str, code: str) -> None:
    now = now_utc()
    stmt = (
        select(VerificationCode)
        .where(
            VerificationCode.target == target,
            VerificationCode.channel == channel,
            VerificationCode.purpose == 'signup',
            VerificationCode.consumed_at.is_(None),
        )
        .order_by(VerificationCode.created_at.desc())
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


def register_admin(
    db: Session,
    *,
    username: str,
    email: str,
    phone: str | None,
    password: str,
) -> AdminUser:
    duplicate_conditions = [AdminUser.username == username, AdminUser.email == email]
    if phone:
        duplicate_conditions.append(AdminUser.phone == phone)
    duplicate_stmt = select(AdminUser).where(or_(*duplicate_conditions))
    if db.execute(duplicate_stmt).scalars().first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Admin already exists')

    if not _is_target_verified(db, email, 'email'):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Email OTP not verified')
    if phone and not _is_target_verified(db, phone, 'phone'):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Phone OTP not verified')

    user = AdminUser(
        username=username,
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


def login_admin(
    db: Session,
    *,
    login: str,
    password: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> TokenResponse:
    normalized = _normalize_login(login)
    stmt = select(AdminUser).where(
        or_(
            AdminUser.username == normalized.lower(),
            AdminUser.email == normalized.lower(),
            AdminUser.phone == normalized,
        )
    )
    user = db.execute(stmt).scalars().first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid credentials')
    if user.is_blocked or not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Account is not allowed')

    return _issue_tokens(db, user, ip_address=ip_address, user_agent=user_agent)


def refresh_admin_token(
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
    token_row_stmt = select(RefreshToken).where(
        RefreshToken.jti == jti,
        RefreshToken.user_id == int(user_id),
        RefreshToken.token_hash == token_hash(refresh_token),
    )
    token_row = db.execute(token_row_stmt).scalars().first()
    if not token_row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Refresh token not found')
    if token_row.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Refresh token revoked')
    if token_row.expires_at < now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Refresh token expired')

    user = db.get(AdminUser, int(user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='User not found')
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
    stmt = select(AdminUser).where(AdminUser.email == email)
    user = db.execute(stmt).scalars().first()
    if not user:
        return

    token = secrets.token_urlsafe(48)
    now = now_utc()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash(token),
            expires_at=now + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
        )
    )
    db.commit()

    reset_link = f"{settings.FRONTEND_BASE_URL}/frontend/auth/reset-password.html?token={token}"
    send_password_reset_email(email=email, reset_link=reset_link, audience='Admin')

    if settings.APP_ENV != 'production':
        print(f'[DEV RESET LINK] email={email} url={reset_link}')


def reset_password(db: Session, *, token: str, new_password: str) -> None:
    now = now_utc()
    stmt = select(PasswordResetToken).where(
        PasswordResetToken.token_hash == token_hash(token),
        PasswordResetToken.used_at.is_(None),
    )
    reset_row = db.execute(stmt).scalars().first()
    if not reset_row:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid reset token')
    if reset_row.expires_at < now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Reset token expired')

    user = db.get(AdminUser, reset_row.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid reset token')

    user.hashed_password = hash_password(new_password)
    user.token_version += 1
    reset_row.used_at = now

    active_tokens_stmt = select(RefreshToken).where(
        RefreshToken.user_id == user.id,
        RefreshToken.revoked_at.is_(None),
    )
    for active_token in db.execute(active_tokens_stmt).scalars().all():
        active_token.revoked_at = now

    db.commit()


def logout_admin(db: Session, *, refresh_token: str) -> None:
    try:
        payload = decode_token(refresh_token)
    except ValueError:
        return

    jti = payload.get('jti')
    user_id = payload.get('sub')
    if not jti or not user_id:
        return

    stmt = select(RefreshToken).where(
        RefreshToken.jti == jti,
        RefreshToken.user_id == int(user_id),
        RefreshToken.token_hash == token_hash(refresh_token),
        RefreshToken.revoked_at.is_(None),
    )
    row = db.execute(stmt).scalars().first()
    if row:
        row.revoked_at = now_utc()
        db.commit()


def logout_admin_all_devices(db: Session, *, user: AdminUser) -> None:
    now = now_utc()
    user.token_version += 1
    active_tokens_stmt = select(RefreshToken).where(
        RefreshToken.user_id == user.id,
        RefreshToken.revoked_at.is_(None),
    )
    for active_token in db.execute(active_tokens_stmt).scalars().all():
        active_token.revoked_at = now
    db.commit()


def get_my_profile(user: AdminUser) -> UserOut:
    return UserOut.model_validate(user)


def update_my_profile(db: Session, *, user: AdminUser, payload: ProfileUpdateRequest) -> UserOut:
    if payload.username and payload.username != user.username:
        duplicate = db.execute(select(AdminUser).where(AdminUser.username == payload.username, AdminUser.id != user.id)).scalars().first()
        if duplicate:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Username already in use')
        user.username = payload.username
    if payload.phone != user.phone:
        if payload.phone:
            duplicate = db.execute(select(AdminUser).where(AdminUser.phone == payload.phone, AdminUser.id != user.id)).scalars().first()
            if duplicate:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Phone already in use')
        user.phone = payload.phone
    if payload.first_name is not None:
        user.first_name = payload.first_name
    if payload.last_name is not None:
        user.last_name = payload.last_name
    if payload.bio is not None:
        user.bio = payload.bio
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


def change_my_password(db: Session, *, user: AdminUser, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Current password is incorrect')
    user.hashed_password = hash_password(new_password)
    user.token_version += 1
    now = now_utc()
    for active_token in db.execute(
        select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
    ).scalars().all():
        active_token.revoked_at = now
    db.commit()


def list_my_sessions(db: Session, *, user: AdminUser) -> AdminSessionListOut:
    rows = db.execute(
        select(RefreshToken).where(RefreshToken.user_id == user.id).order_by(RefreshToken.created_at.desc(), RefreshToken.id.desc())
    ).scalars().all()
    return AdminSessionListOut(
        items=[
            AdminSessionOut(
                id=row.id,
                session_id=row.session_id,
                user_agent=row.user_agent,
                created_by_ip=row.created_by_ip,
                created_at=row.created_at,
                expires_at=row.expires_at,
                revoked_at=row.revoked_at,
            )
            for row in rows
        ]
    )
