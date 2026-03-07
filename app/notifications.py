from __future__ import annotations

import smtplib
from email.message import EmailMessage

try:
    import emails
except ModuleNotFoundError:
    emails = None
try:
    from twilio.base.exceptions import TwilioRestException
    from twilio.rest import Client
except ModuleNotFoundError:
    TwilioRestException = Exception
    Client = None

from app.admin.config import settings


def _smtp_configured() -> bool:
    return all(
        [
            settings.SMTP_HOST,
            settings.SMTP_USERNAME,
            settings.SMTP_PASSWORD,
            settings.MAIL_FROM,
        ]
    )


def _twilio_configured() -> bool:
    return all(
        [
            settings.TWILIO_ACCOUNT_SID,
            settings.TWILIO_AUTH_TOKEN,
        ]
    ) and bool(settings.TWILIO_FROM_NUMBER or settings.TWILIO_MESSAGING_SERVICE_SID) and Client is not None


def _normalize_phone_number(phone: str) -> str:
    raw = ''.join(ch for ch in str(phone or '').strip() if ch.isdigit() or ch == '+')
    if not raw:
        raise RuntimeError('Phone number is empty')
    if raw.startswith('+'):
        digits = '+' + ''.join(ch for ch in raw if ch.isdigit())
        if len(digits) < 8:
            raise RuntimeError(f'Phone number is not valid E.164: {phone}')
        return digits

    digits_only = ''.join(ch for ch in raw if ch.isdigit())
    if len(digits_only) == 10:
        country = settings.DEFAULT_PHONE_COUNTRY_CODE.strip() or '+91'
        country_digits = '+' + ''.join(ch for ch in country if ch.isdigit())
        return f'{country_digits}{digits_only}'
    if len(digits_only) >= 11:
        return f'+{digits_only}'
    raise RuntimeError(f'Phone number is not valid E.164: {phone}')


def _build_email_message(*, subject: str, html: str):
    if emails is not None:
        return emails.Message(
            subject=subject,
            html=html,
            mail_from=(settings.MAIL_FROM_NAME, settings.MAIL_FROM or 'no-reply@example.com'),
        )

    message = EmailMessage()
    sender = settings.MAIL_FROM or 'no-reply@example.com'
    if settings.MAIL_FROM_NAME:
        message['From'] = f'{settings.MAIL_FROM_NAME} <{sender}>'
    else:
        message['From'] = sender
    message['Subject'] = subject
    message.set_content('HTML email')
    message.add_alternative(html, subtype='html')
    return message


def send_email_message(*, to_email: str, subject: str, html: str) -> None:
    if not _smtp_configured():
        if settings.APP_ENV == 'production':
            raise RuntimeError('SMTP is not configured')
        print(f'[DEV EMAIL] to={to_email} subject={subject}')
        return

    message = _build_email_message(subject=subject, html=html)
    if emails is not None:
        response = message.send(
            to=to_email,
            smtp={
                'host': settings.SMTP_HOST,
                'port': settings.SMTP_PORT,
                'user': settings.SMTP_USERNAME,
                'password': settings.SMTP_PASSWORD,
                'tls': settings.SMTP_USE_TLS,
            },
        )
        if response.status_code not in {250}:
            raise RuntimeError(f'Email send failed with status {response.status_code}')
        return

    message['To'] = to_email
    smtp_cls = smtplib.SMTP_SSL if not settings.SMTP_USE_TLS else smtplib.SMTP
    with smtp_cls(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as smtp:
        if settings.SMTP_USE_TLS:
            smtp.starttls()
        smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        smtp.send_message(message)


def send_signup_email_otp(*, email: str, otp: str, audience: str) -> None:
    subject = f'{audience} email verification code'
    html = (
        f'<h2>{audience} verification</h2>'
        f'<p>Your verification code is <strong>{otp}</strong>.</p>'
        f'<p>This code expires in {settings.SIGNUP_OTP_EXPIRE_MINUTES} minutes.</p>'
    )
    send_email_message(to_email=email, subject=subject, html=html)


def send_password_reset_email(*, email: str, reset_link: str, audience: str) -> None:
    subject = f'{audience} password reset'
    html = (
        f'<h2>{audience} password reset</h2>'
        f'<p>Use the link below to reset your password.</p>'
        f'<p><a href="{reset_link}">{reset_link}</a></p>'
        f'<p>This link expires in {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes.</p>'
    )
    send_email_message(to_email=email, subject=subject, html=html)


def send_phone_otp(*, phone: str, otp: str, audience: str) -> None:
    message = f'{audience} verification code: {otp}. Valid for {settings.SIGNUP_OTP_EXPIRE_MINUTES} minutes.'
    if not _twilio_configured():
        if settings.APP_ENV == 'production':
            raise RuntimeError('Twilio is not configured')
        print(f'[DEV SMS] phone={phone} message={message}')
        return

    account_sid = settings.TWILIO_ACCOUNT_SID or ''
    auth_token = settings.TWILIO_AUTH_TOKEN or ''
    to_number = _normalize_phone_number(phone)
    client = Client(account_sid, auth_token)
    payload = {
        'body': message,
        'to': to_number,
    }
    if settings.TWILIO_MESSAGING_SERVICE_SID:
        payload['messaging_service_sid'] = settings.TWILIO_MESSAGING_SERVICE_SID
    else:
        payload['from_'] = _normalize_phone_number(settings.TWILIO_FROM_NUMBER or '')
    try:
        client.messages.create(**payload)
    except TwilioRestException as exc:
        if settings.APP_ENV != 'production':
            print(f'[DEV SMS FALLBACK] phone={to_number} message={message} twilio_error={exc.msg}')
            return
        raise RuntimeError(f'Twilio SMS send failed: {exc.msg}') from exc
