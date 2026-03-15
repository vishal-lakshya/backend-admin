from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.admin.database import Base


class AdminUser(Base):
    __tablename__ = 'admin_users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    first_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_phone_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    refresh_tokens: Mapped[list['RefreshToken']] = relationship(
        back_populates='user',
        cascade='all, delete-orphan',
    )
    password_reset_tokens: Mapped[list['PasswordResetToken']] = relationship(
        back_populates='user',
        cascade='all, delete-orphan',
    )


class RefreshToken(Base):
    __tablename__ = 'admin_refresh_tokens'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('admin_users.id', ondelete='CASCADE'), index=True)

    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    created_by_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    user: Mapped['AdminUser'] = relationship(back_populates='refresh_tokens')


class PasswordResetToken(Base):
    __tablename__ = 'admin_password_reset_tokens'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('admin_users.id', ondelete='CASCADE'), index=True)

    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped['AdminUser'] = relationship(back_populates='password_reset_tokens')


class VerificationCode(Base):
    __tablename__ = 'admin_verification_codes'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    target: Mapped[str] = mapped_column(String(255), index=True)
    channel: Mapped[str] = mapped_column(String(20), index=True)  # email|phone
    purpose: Mapped[str] = mapped_column(String(30), index=True)  # signup

    code_hash: Mapped[str] = mapped_column(String(128), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AdminExam(Base):
    __tablename__ = 'admin_exams'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    subject_codes: Mapped[list[str]] = mapped_column(JSON, default=list)

    created_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey('admin_users.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AdminSubject(Base):
    __tablename__ = 'admin_subjects'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey('admin_exams.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(150), index=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    mapped_questions: Mapped[int] = mapped_column(Integer, default=0)

    created_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey('admin_users.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AdminTestSeries(Base):
    __tablename__ = 'admin_test_series'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    test_type: Mapped[str] = mapped_column(String(60), index=True)
    display_mode: Mapped[str] = mapped_column(String(40), default='live', index=True)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey('admin_subjects.id', ondelete='SET NULL'), nullable=True, index=True)
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    access_level: Mapped[str] = mapped_column(String(60), default='all_users')
    positive_marks: Mapped[float] = mapped_column(default=2.0)
    negative_marks: Mapped[float] = mapped_column(default=0.66)
    status: Mapped[str] = mapped_column(String(30), default='draft', index=True)
    question_file_key: Mapped[str] = mapped_column(String(255))

    created_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey('admin_users.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AdminPyqPaper(Base):
    __tablename__ = 'admin_pyq_papers'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey('admin_exams.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    paper_type: Mapped[str] = mapped_column(String(120), index=True)
    paper_set: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default='published', index=True)
    paper_file_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    paper_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    questions_file_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    question_count: Mapped[int] = mapped_column(Integer, default=0)

    created_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey('admin_users.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SubscriptionPlan(Base):
    __tablename__ = 'subscription_plans'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    section: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    duration_value: Mapped[int] = mapped_column(Integer, default=1)
    duration_unit: Mapped[str] = mapped_column(String(20), default='month')
    price_type: Mapped[str] = mapped_column(String(20), default='permanent', index=True)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    discount_percent: Mapped[float] = mapped_column(Float, default=0.0)
    what_is_covered: Mapped[str | None] = mapped_column(Text, nullable=True)
    what_is_not_covered: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_scope: Mapped[str] = mapped_column(String(30), default='full', index=True)
    access_exam_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    access_subject_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    access_items: Mapped[list[str]] = mapped_column(JSON, default=list)
    monthly_price: Mapped[float] = mapped_column(Float, default=0.0)
    annual_price: Mapped[float] = mapped_column(Float, default=0.0)
    annual_monthly_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserSubscription(Base):
    __tablename__ = 'user_subscriptions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey('subscription_plans.id', ondelete='CASCADE'), index=True)
    billing_cycle: Mapped[str] = mapped_column(String(20), default='monthly', index=True)
    status: Mapped[str] = mapped_column(String(30), default='active', index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    renews_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    amount_paid: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PaymentTransaction(Base):
    __tablename__ = 'payment_transactions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    subscription_id: Mapped[int | None] = mapped_column(ForeignKey('user_subscriptions.id', ondelete='SET NULL'), nullable=True, index=True)
    transaction_type: Mapped[str] = mapped_column(String(30), default='subscription', index=True)
    plan_code: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), default='INR')
    method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    gateway: Mapped[str | None] = mapped_column(String(40), nullable=True)
    gateway_transaction_id: Mapped[str | None] = mapped_column(String(120), nullable=True, unique=True)
    status: Mapped[str] = mapped_column(String(30), default='success', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class PlatformSetting(Base):
    __tablename__ = 'platform_settings'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    platform_name: Mapped[str] = mapped_column(String(120), default='CivilEdge')
    default_exam_id: Mapped[int | None] = mapped_column(ForeignKey('admin_exams.id', ondelete='SET NULL'), nullable=True, index=True)
    timezone: Mapped[str] = mapped_column(String(64), default='Asia/Kolkata')
    user_session_timeout_minutes: Mapped[int] = mapped_column(Integer, default=120)
    max_login_attempts: Mapped[int] = mapped_column(Integer, default=5)
    require_admin_2fa: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_concurrent_admin_sessions: Mapped[bool] = mapped_column(Boolean, default=True)
    payment_failure_alerts: Mapped[bool] = mapped_column(Boolean, default=True)
    suspicious_login_alerts: Mapped[bool] = mapped_column(Boolean, default=True)
    daily_summary_mail: Mapped[bool] = mapped_column(Boolean, default=False)
    allowed_admin_ips: Mapped[str | None] = mapped_column(Text, nullable=True)
    audit_log_retention_days: Mapped[int] = mapped_column(Integer, default=90)
    lock_account_on_repeated_failures: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AdminBroadcastNotification(Base):
    __tablename__ = 'admin_broadcast_notifications'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(180), index=True)
    message: Mapped[str] = mapped_column(Text)
    audience_type: Mapped[str] = mapped_column(String(30), default='all', index=True)
    audience_filters: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default='active', index=True)
    created_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey('admin_users.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserNotificationRead(Base):
    __tablename__ = 'user_notification_reads'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    notification_id: Mapped[int] = mapped_column(ForeignKey('admin_broadcast_notifications.id', ondelete='CASCADE'), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    read_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
