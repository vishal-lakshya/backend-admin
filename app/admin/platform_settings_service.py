from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.models import AdminExam, PlatformSetting
from app.admin.schemas import ExamOut, PlatformSettingBootstrapOut, PlatformSettingOut, PlatformSettingUpdateRequest


def get_or_create_platform_settings(db: Session) -> PlatformSetting:
    row = db.execute(select(PlatformSetting).limit(1)).scalars().first()
    if row:
        return row
    row = PlatformSetting()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def serialize_platform_settings(row: PlatformSetting) -> PlatformSettingOut:
    return PlatformSettingOut(
        platform_name=row.platform_name,
        default_exam_id=row.default_exam_id,
        timezone=row.timezone,
        user_session_timeout_minutes=row.user_session_timeout_minutes,
        max_login_attempts=row.max_login_attempts,
        require_admin_2fa=row.require_admin_2fa,
        allow_concurrent_admin_sessions=row.allow_concurrent_admin_sessions,
        payment_failure_alerts=row.payment_failure_alerts,
        suspicious_login_alerts=row.suspicious_login_alerts,
        daily_summary_mail=row.daily_summary_mail,
        allowed_admin_ips=row.allowed_admin_ips,
        audit_log_retention_days=row.audit_log_retention_days,
        lock_account_on_repeated_failures=row.lock_account_on_repeated_failures,
        updated_at=row.updated_at,
    )


def get_platform_settings_bootstrap(db: Session) -> PlatformSettingBootstrapOut:
    row = get_or_create_platform_settings(db)
    exams = db.execute(select(AdminExam).order_by(AdminExam.name.asc())).scalars().all()
    return PlatformSettingBootstrapOut(
        settings=serialize_platform_settings(row),
        exams=[ExamOut.model_validate(item) for item in exams],
    )


def update_platform_settings(db: Session, payload: PlatformSettingUpdateRequest) -> PlatformSettingOut:
    row = get_or_create_platform_settings(db)
    row.platform_name = payload.platform_name
    row.default_exam_id = payload.default_exam_id
    row.timezone = payload.timezone
    row.user_session_timeout_minutes = payload.user_session_timeout_minutes
    row.max_login_attempts = payload.max_login_attempts
    row.require_admin_2fa = payload.require_admin_2fa
    row.allow_concurrent_admin_sessions = payload.allow_concurrent_admin_sessions
    row.payment_failure_alerts = payload.payment_failure_alerts
    row.suspicious_login_alerts = payload.suspicious_login_alerts
    row.daily_summary_mail = payload.daily_summary_mail
    row.allowed_admin_ips = payload.allowed_admin_ips
    row.audit_log_retention_days = payload.audit_log_retention_days
    row.lock_account_on_repeated_failures = payload.lock_account_on_repeated_failures
    db.commit()
    db.refresh(row)
    return serialize_platform_settings(row)


def next_lock_expiry(now: datetime, timezone_name: str) -> datetime:
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = ZoneInfo('Asia/Kolkata')
    local = now.replace(tzinfo=ZoneInfo('UTC')).astimezone(tz)
    tomorrow_local = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return tomorrow_local.astimezone(ZoneInfo('UTC')).replace(tzinfo=None)
