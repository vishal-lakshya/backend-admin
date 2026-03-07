from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.admin.database import get_db
from app.admin.dependencies import get_current_admin_user
from app.admin.models import AdminUser
from app.admin.schemas import (
    AdminSessionListOut,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MessageOut,
    OtpSendEmailRequest,
    OtpSendPhoneRequest,
    OtpVerifyEmailRequest,
    OtpVerifyPhoneRequest,
    ProfileUpdateRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
)
from app.admin.service import (
    forgot_password,
    change_my_password,
    get_my_profile,
    login_admin,
    list_my_sessions,
    logout_admin,
    logout_admin_all_devices,
    refresh_admin_token,
    register_admin,
    reset_password,
    send_signup_otp,
    update_my_profile,
    verify_signup_otp,
)


router = APIRouter(prefix='/auth', tags=['Admin Auth'])


@router.post('/signup/email-otp/send', response_model=MessageOut)
def signup_send_email_otp(payload: OtpSendEmailRequest, db: Session = Depends(get_db)) -> MessageOut:
    send_signup_otp(db, target=payload.email.lower(), channel='email')
    return MessageOut(message='Email OTP sent')


@router.post('/signup/email-otp/verify', response_model=MessageOut)
def signup_verify_email_otp(payload: OtpVerifyEmailRequest, db: Session = Depends(get_db)) -> MessageOut:
    verify_signup_otp(db, target=payload.email.lower(), channel='email', code=payload.code)
    return MessageOut(message='Email verified')


@router.post('/signup/phone-otp/send', response_model=MessageOut)
def signup_send_phone_otp(payload: OtpSendPhoneRequest, db: Session = Depends(get_db)) -> MessageOut:
    send_signup_otp(db, target=payload.phone, channel='phone')
    return MessageOut(message='Phone OTP sent')


@router.post('/signup/phone-otp/verify', response_model=MessageOut)
def signup_verify_phone_otp(payload: OtpVerifyPhoneRequest, db: Session = Depends(get_db)) -> MessageOut:
    verify_signup_otp(db, target=payload.phone, channel='phone', code=payload.code)
    return MessageOut(message='Phone verified')


@router.post('/register', response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> MessageOut:
    register_admin(
        db,
        username=payload.username,
        email=str(payload.email).lower(),
        phone=payload.phone,
        password=payload.password,
    )
    return MessageOut(message='Admin registered successfully')


@router.post('/login', response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    return login_admin(
        db,
        login=payload.login,
        password=payload.password,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get('user-agent'),
    )


@router.post('/refresh', response_model=TokenResponse)
def refresh(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    return refresh_admin_token(
        db,
        refresh_token=payload.refresh_token,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get('user-agent'),
    )


@router.post('/logout', response_model=MessageOut)
def logout(payload: RefreshRequest, db: Session = Depends(get_db)) -> MessageOut:
    logout_admin(db, refresh_token=payload.refresh_token)
    return MessageOut(message='Logged out')


@router.post('/logout-all-devices', response_model=MessageOut)
def logout_all_devices(
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_admin_user),
) -> MessageOut:
    logout_admin_all_devices(db, user=current_user)
    return MessageOut(message='Logged out from all devices')


@router.post('/forgot-password', response_model=MessageOut)
def forgot_password_handler(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> MessageOut:
    forgot_password(db, email=str(payload.email).lower())
    return MessageOut(message='If the account exists, reset instructions have been sent')


@router.post('/reset-password', response_model=MessageOut)
def reset_password_handler(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> MessageOut:
    reset_password(db, token=payload.token, new_password=payload.new_password)
    return MessageOut(message='Password reset successful')


@router.get('/me', response_model=UserOut)
def me(current_user: AdminUser = Depends(get_current_admin_user)) -> UserOut:
    return get_my_profile(current_user)


@router.put('/me', response_model=UserOut)
def update_me(
    payload: ProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_admin_user),
) -> UserOut:
    return update_my_profile(db, user=current_user, payload=payload)


@router.post('/change-password', response_model=MessageOut)
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_admin_user),
) -> MessageOut:
    change_my_password(db, user=current_user, current_password=payload.current_password, new_password=payload.new_password)
    return MessageOut(message='Password updated successfully')


@router.get('/sessions', response_model=AdminSessionListOut)
def sessions(
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_admin_user),
) -> AdminSessionListOut:
    return list_my_sessions(db, user=current_user)
