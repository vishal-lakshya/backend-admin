from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class MessageOut(BaseModel):
    message: str


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    email: EmailStr
    phone: str | None = Field(default=None, min_length=8, max_length=20)
    password: str = Field(min_length=8, max_length=128)

    @field_validator('username')
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator('phone')
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return ''.join(ch for ch in value if ch.isdigit() or ch == '+')


class LoginRequest(BaseModel):
    login: str = Field(min_length=3, max_length=255)  # username/email/phone
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
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr
    phone: str | None
    bio: str | None = None
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
    username: str | None = Field(default=None, min_length=3, max_length=80)
    first_name: str | None = Field(default=None, max_length=80)
    last_name: str | None = Field(default=None, max_length=80)
    phone: str | None = Field(default=None, min_length=8, max_length=20)
    bio: str | None = Field(default=None, max_length=2000)

    @field_validator('username')
    @classmethod
    def normalize_profile_username(cls, value: str | None) -> str | None:
        return value.strip().lower() if value is not None else value

    @field_validator('first_name', 'last_name', 'bio')
    @classmethod
    def normalize_profile_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = value.strip()
        return clean or None

    @field_validator('phone')
    @classmethod
    def normalize_profile_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = ''.join(ch for ch in value if ch.isdigit() or ch == '+')
        return clean or None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class AdminSessionOut(BaseModel):
    id: int
    session_id: str
    user_agent: str | None
    created_by_ip: str | None
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None


class AdminSessionListOut(BaseModel):
    items: list[AdminSessionOut]


class ExamCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    code: str = Field(min_length=2, max_length=40)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool = True
    subject_codes: list[str] = Field(default_factory=list)

    @field_validator('name')
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator('code')
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator('subject_codes')
    @classmethod
    def normalize_subject_codes(cls, value: list[str]) -> list[str]:
        clean: list[str] = []
        for item in value:
            norm = str(item).strip().upper()
            if norm and norm not in clean:
                clean.append(norm)
        return clean


class ExamUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    code: str | None = Field(default=None, min_length=2, max_length=40)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None
    subject_codes: list[str] | None = None

    @field_validator('name')
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value

    @field_validator('code')
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else value

    @field_validator('subject_codes')
    @classmethod
    def normalize_subject_codes(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        clean: list[str] = []
        for item in value:
            norm = str(item).strip().upper()
            if norm and norm not in clean:
                clean.append(norm)
        return clean


class ExamOut(BaseModel):
    id: int
    name: str
    code: str
    description: str | None
    is_active: bool
    subject_codes: list[str]
    created_by_admin_id: int | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExamListOut(BaseModel):
    items: list[ExamOut]
    total: int
    skip: int
    limit: int


class ExamAnalyticsOut(BaseModel):
    total_exams: int
    active_exams: int
    recent_added: int
    mapped_subjects: int


class SubjectCreateRequest(BaseModel):
    exam_id: int
    name: str = Field(min_length=2, max_length=150)
    code: str = Field(min_length=2, max_length=40)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool = True

    @field_validator('name')
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator('code')
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class SubjectUpdateRequest(BaseModel):
    exam_id: int | None = None
    name: str | None = Field(default=None, min_length=2, max_length=150)
    code: str | None = Field(default=None, min_length=2, max_length=40)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None
    mapped_questions: int | None = Field(default=None, ge=0)

    @field_validator('name')
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value

    @field_validator('code')
    @classmethod
    def normalize_code(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else value


class SubjectOut(BaseModel):
    id: int
    exam_id: int
    exam_name: str
    name: str
    code: str
    description: str | None
    is_active: bool
    mapped_questions: int
    created_by_admin_id: int | None
    created_at: datetime
    updated_at: datetime


class SubjectListOut(BaseModel):
    items: list[SubjectOut]
    total: int
    skip: int
    limit: int


class SubjectAnalyticsOut(BaseModel):
    total_subjects: int
    active_subjects: int
    updated_this_month: int
    mapped_questions: int


class QuestionOptionIn(BaseModel):
    model_config = ConfigDict(extra='forbid')

    key: str = Field(min_length=1, max_length=2)
    text: str = Field(min_length=1, max_length=1000)

    @field_validator('key')
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator('text')
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()


class QuestionCreateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    exam_id: int
    subject_id: int
    topic: str | None = Field(default=None, max_length=200)
    question_text: str = Field(min_length=5, max_length=5000)
    options: list[QuestionOptionIn] = Field(min_length=2, max_length=8)
    correct_option: str = Field(min_length=1, max_length=2)
    explanation: str = Field(min_length=2, max_length=5000)
    difficulty: str = Field(default='medium')
    status: str = Field(default='published')
    pyq_year: int | None = Field(default=None, ge=1900, le=2100)
    tags: list[str] = Field(default_factory=list)
    accuracy_pct: float = Field(default=0.0, ge=0.0, le=100.0)

    @field_validator('question_text', 'explanation')
    @classmethod
    def normalize_long_text(cls, value: str) -> str:
        return value.strip()

    @field_validator('topic')
    @classmethod
    def normalize_topic(cls, value: str | None) -> str | None:
        return value.strip() if value else None

    @field_validator('difficulty')
    @classmethod
    def normalize_difficulty(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed = {'easy', 'medium', 'hard'}
        return normalized if normalized in allowed else 'medium'

    @field_validator('status')
    @classmethod
    def normalize_status(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed = {'published', 'draft', 'under_review', 'flagged'}
        return normalized if normalized in allowed else 'draft'

    @field_validator('correct_option')
    @classmethod
    def normalize_correct_option(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator('tags')
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        clean: list[str] = []
        for tag in value:
            normalized = str(tag).strip()
            if normalized and normalized not in clean:
                clean.append(normalized)
        return clean


class QuestionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    exam_id: int | None = None
    subject_id: int | None = None
    topic: str | None = Field(default=None, max_length=200)
    question_text: str | None = Field(default=None, min_length=5, max_length=5000)
    options: list[QuestionOptionIn] | None = Field(default=None, min_length=2, max_length=8)
    correct_option: str | None = Field(default=None, min_length=1, max_length=2)
    explanation: str | None = Field(default=None, min_length=2, max_length=5000)
    difficulty: str | None = None
    status: str | None = None
    pyq_year: int | None = Field(default=None, ge=1900, le=2100)
    tags: list[str] | None = None
    accuracy_pct: float | None = Field(default=None, ge=0.0, le=100.0)


class QuestionOut(BaseModel):
    id: str
    exam_id: int
    exam_name: str
    subject_id: int
    subject_name: str
    topic: str | None
    question_text: str
    options: list[QuestionOptionIn]
    correct_option: str
    explanation: str
    difficulty: str
    status: str
    pyq_year: int | None
    tags: list[str]
    accuracy_pct: float
    created_at: datetime
    updated_at: datetime


class QuestionListOut(BaseModel):
    items: list[QuestionOut]
    total: int
    skip: int
    limit: int


class QuestionAnalyticsOut(BaseModel):
    total_questions: int
    published: int
    under_review: int
    avg_accuracy: float


class QuestionSubjectAnalyticsRow(BaseModel):
    subject_id: int
    subject_name: str
    total: int
    published: int
    draft: int
    flagged: int
    avg_difficulty: str


class QuestionSubjectAnalyticsOut(BaseModel):
    items: list[QuestionSubjectAnalyticsRow]


class QuestionBootstrapOut(BaseModel):
    exams: list[ExamOut]
    subjects: list[SubjectOut]
    pyq_years: list[int]


class QuestionBulkUploadOut(BaseModel):
    uploaded: int
    storage_key: str


class TestQuestionUploadIn(BaseModel):
    model_config = ConfigDict(extra='forbid')

    topic: str | None = Field(default=None, max_length=200)
    question_text: str = Field(min_length=5, max_length=5000)
    options: list[QuestionOptionIn] = Field(min_length=2, max_length=8)
    correct_option: str = Field(min_length=1, max_length=2)
    explanation: str = Field(min_length=2, max_length=5000)
    difficulty: str = Field(default='medium')
    tags: list[str] = Field(default_factory=list)

    @field_validator('topic')
    @classmethod
    def normalize_test_topic(cls, value: str | None) -> str | None:
        return value.strip() if value else None

    @field_validator('question_text', 'explanation')
    @classmethod
    def normalize_test_text(cls, value: str) -> str:
        return value.strip()

    @field_validator('difficulty')
    @classmethod
    def normalize_test_difficulty(cls, value: str) -> str:
        normalized = value.strip().lower()
        return normalized if normalized in {'easy', 'medium', 'hard'} else 'medium'

    @field_validator('correct_option')
    @classmethod
    def normalize_test_correct_option(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator('tags')
    @classmethod
    def normalize_test_tags(cls, value: list[str]) -> list[str]:
        clean: list[str] = []
        for tag in value:
            normalized = str(tag).strip()
            if normalized and normalized not in clean:
                clean.append(normalized)
        return clean


class TestSeriesOut(BaseModel):
    id: int
    name: str
    test_type: str
    subject_id: int | None
    subject_name: str
    question_count: int
    duration_minutes: int
    scheduled_at: datetime | None
    access_level: str
    positive_marks: float
    negative_marks: float
    status: str
    effective_status: str
    question_file_key: str
    created_by_admin_id: int | None
    created_at: datetime
    updated_at: datetime


class TestSeriesListOut(BaseModel):
    items: list[TestSeriesOut]
    total: int
    skip: int
    limit: int


class TestSeriesAnalyticsOut(BaseModel):
    live_now: int
    scheduled: int
    attempts_today: int
    avg_completion: float


class TestSeriesBootstrapOut(BaseModel):
    subjects: list[SubjectOut]
    test_types: list[str]
    access_levels: list[str]


class TestSeriesCreateOut(BaseModel):
    test: TestSeriesOut
    uploaded_questions: int


class TestSeriesMoveRequest(BaseModel):
    target_status: str = Field(min_length=4, max_length=20)
    scheduled_at: datetime | None = None


class PyqQuestionOut(BaseModel):
    id: int
    topic: str | None
    question_text: str
    options: list[QuestionOptionIn]
    correct_option: str
    explanation: str
    difficulty: str


class PyqPaperOut(BaseModel):
    id: int
    exam_id: int
    exam_name: str
    title: str
    year: int
    paper_type: str
    paper_set: str | None
    status: str
    paper_file_name: str | None
    paper_file_key: str | None
    questions_file_key: str | None
    has_paper_file: bool
    has_questions_file: bool
    question_count: int
    created_at: datetime
    updated_at: datetime


class PyqPaperDetailOut(BaseModel):
    paper: PyqPaperOut
    questions: list[PyqQuestionOut]


class PyqPaperListOut(BaseModel):
    items: list[PyqPaperOut]
    total: int
    skip: int
    limit: int


class PyqBootstrapOut(BaseModel):
    exams: list[ExamOut]
    years: list[int]
    paper_types: list[str]
    paper_sets: list[str]


class PyqAnalyticsOut(BaseModel):
    total_papers: int
    total_questions: int
    latest_year: int | None


class PyqCreateOut(BaseModel):
    paper: PyqPaperOut


class PyqUpdateOut(BaseModel):
    paper: PyqPaperOut


class PyqAssetDownloadOut(BaseModel):
    url: str
    asset: str


class DownloadUrlOut(BaseModel):
    url: str


class AdminManagedUserOut(BaseModel):
    id: int
    username: str
    first_name: str | None
    last_name: str | None
    full_name: str
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
    last_active_at: datetime | None
    practice_attempt_count: int
    bookmark_count: int
    accuracy: float


class AdminManagedUserListOut(BaseModel):
    items: list[AdminManagedUserOut]
    total: int
    skip: int
    limit: int


class AdminManagedUserAnalyticsOut(BaseModel):
    total_users: int
    active_last_30_days: int
    new_today: int
    blocked_users: int


class AdminManagedUserAttemptOut(BaseModel):
    question_id: str
    exam_id: int | None
    exam_name: str
    subject_id: int | None
    subject_name: str
    question_text: str
    selected_option: str
    correct_option: str
    is_correct: bool
    attempted_at: datetime


class AdminManagedUserBookmarkOut(BaseModel):
    question_id: str
    exam_id: int | None
    exam_name: str
    subject_id: int | None
    subject_name: str
    question_text: str
    created_at: datetime


class AdminManagedUserPerformanceOut(BaseModel):
    total_attempts: int
    correct_attempts: int
    accuracy: float
    unique_questions_attempted: int
    bookmarks: int
    tests_attempted: int
    last_active_at: datetime | None


class AdminManagedUserDetailOut(BaseModel):
    user: AdminManagedUserOut
    performance: AdminManagedUserPerformanceOut
    attempts: list[AdminManagedUserAttemptOut]
    bookmarks: list[AdminManagedUserBookmarkOut]
    tests: list[dict]


class AdminManagedUserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    first_name: str | None = Field(default=None, max_length=80)
    last_name: str | None = Field(default=None, max_length=80)
    email: EmailStr
    phone: str | None = Field(default=None, min_length=8, max_length=20)
    password: str = Field(min_length=8, max_length=128)
    state: str | None = Field(default=None, max_length=80)
    target_exam_year: int | None = Field(default=None, ge=2024, le=2100)
    is_active: bool = True
    is_blocked: bool = False
    is_email_verified: bool = True
    is_phone_verified: bool = False

    @field_validator('username')
    @classmethod
    def normalize_admin_managed_username(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator('first_name', 'last_name', 'state')
    @classmethod
    def normalize_admin_managed_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = value.strip()
        return clean or None

    @field_validator('phone')
    @classmethod
    def normalize_admin_managed_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = ''.join(ch for ch in value if ch.isdigit() or ch == '+')
        return clean or None


class AdminManagedUserUpdateRequest(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=80)
    first_name: str | None = Field(default=None, max_length=80)
    last_name: str | None = Field(default=None, max_length=80)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=8, max_length=20)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    state: str | None = Field(default=None, max_length=80)
    target_exam_year: int | None = Field(default=None, ge=2024, le=2100)
    is_active: bool | None = None
    is_blocked: bool | None = None
    is_email_verified: bool | None = None
    is_phone_verified: bool | None = None

    @field_validator('username')
    @classmethod
    def normalize_admin_managed_optional_username(cls, value: str | None) -> str | None:
        return value.strip().lower() if value is not None else value

    @field_validator('first_name', 'last_name', 'state')
    @classmethod
    def normalize_admin_managed_update_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = value.strip()
        return clean or None

    @field_validator('phone')
    @classmethod
    def normalize_admin_managed_update_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = ''.join(ch for ch in value if ch.isdigit() or ch == '+')
        return clean or None


class SubscriptionPlanOut(BaseModel):
    id: int
    name: str
    code: str
    monthly_price: float
    annual_price: float
    annual_monthly_price: float | None
    description: str | None
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


class SubscriptionPlanListOut(BaseModel):
    items: list[SubscriptionPlanOut]


class PaymentAnalyticsOut(BaseModel):
    total_users: int
    subscribed_users: int
    monthly_recurring_revenue: float
    annual_run_rate: float
    average_revenue_per_subscribed_user: float
    transactions_today: int
    success_rate: float
    disputed_payments: int
    refunds_this_month: int


class PaymentPlanBreakdownOut(BaseModel):
    plan_code: str
    plan_name: str
    users: int
    monthly_revenue: float


class PaymentTransactionOut(BaseModel):
    id: int
    user_id: int | None
    user_name: str
    user_email: str
    transaction_type: str
    plan_code: str | None
    amount: float
    currency: str
    method: str | None
    gateway: str | None
    status: str
    created_at: datetime


class PaymentTransactionListOut(BaseModel):
    items: list[PaymentTransactionOut]
    total: int
    skip: int
    limit: int


class PaymentDashboardOut(BaseModel):
    analytics: PaymentAnalyticsOut
    plan_breakdown: list[PaymentPlanBreakdownOut]
    monthly_revenue: list[dict]
    transactions: PaymentTransactionListOut


class PlatformSettingOut(BaseModel):
    platform_name: str
    default_exam_id: int | None
    timezone: str
    user_session_timeout_minutes: int
    max_login_attempts: int
    require_admin_2fa: bool
    allow_concurrent_admin_sessions: bool
    payment_failure_alerts: bool
    suspicious_login_alerts: bool
    daily_summary_mail: bool
    allowed_admin_ips: str | None
    audit_log_retention_days: int
    lock_account_on_repeated_failures: bool
    updated_at: datetime | None = None


class PlatformSettingUpdateRequest(BaseModel):
    platform_name: str = Field(min_length=2, max_length=120)
    default_exam_id: int | None = None
    timezone: str = Field(min_length=3, max_length=64)
    user_session_timeout_minutes: int = Field(ge=5, le=10080)
    max_login_attempts: int = Field(ge=1, le=20)
    require_admin_2fa: bool
    allow_concurrent_admin_sessions: bool
    payment_failure_alerts: bool
    suspicious_login_alerts: bool
    daily_summary_mail: bool
    allowed_admin_ips: str | None = Field(default=None, max_length=5000)
    audit_log_retention_days: int = Field(ge=1, le=3650)
    lock_account_on_repeated_failures: bool

    @field_validator('platform_name', 'timezone', 'allowed_admin_ips')
    @classmethod
    def normalize_platform_setting_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        clean = value.strip()
        return clean or None


class PlatformSettingBootstrapOut(BaseModel):
    settings: PlatformSettingOut
    exams: list[ExamOut]


class DashboardStatOut(BaseModel):
    value: float | int
    label: str
    change_text: str


class DashboardBarPointOut(BaseModel):
    label: str
    value: int


class DashboardActivityOut(BaseModel):
    tone: str
    text: str
    timestamp: datetime


class DashboardSubjectBreakdownOut(BaseModel):
    subject_name: str
    question_count: int


class DashboardSubscriptionSplitOut(BaseModel):
    total_users: int
    free_users: int
    pro_users: int
    elite_users: int
    monthly_recurring_revenue: float


class DashboardRecentUserOut(BaseModel):
    id: int
    full_name: str
    email: str
    plan: str
    tests_taken: int
    accuracy: float
    joined_at: datetime
    status: str


class DashboardOverviewOut(BaseModel):
    generated_at: datetime
    total_active_users: DashboardStatOut
    revenue_this_month: DashboardStatOut
    tests_attempted_today: DashboardStatOut
    total_questions: DashboardStatOut
    test_attempts_last_14_days: list[DashboardBarPointOut]
    recent_activity: list[DashboardActivityOut]
    subject_breakdown: list[DashboardSubjectBreakdownOut]
    subscription_split: DashboardSubscriptionSplitOut
    recent_users: list[DashboardRecentUserOut]


class AnalyticsStatOut(BaseModel):
    value: float | int
    label: str
    change_text: str


class AnalyticsGrowthPointOut(BaseModel):
    label: str
    signups: int
    active_users: int


class AnalyticsFunnelStepOut(BaseModel):
    label: str
    count: int
    percentage: float


class AnalyticsSubjectAttemptOut(BaseModel):
    subject_name: str
    attempts: int


class AnalyticsDeviceBreakdownOut(BaseModel):
    device_type: str
    count: int
    percentage: float


class AnalyticsStateOut(BaseModel):
    state_name: str
    users: int


class AnalyticsHeatmapCellOut(BaseModel):
    date: str
    count: int
    intensity: int


class AnalyticsOverviewOut(BaseModel):
    generated_at: datetime
    range_days: int
    online_right_now: AnalyticsStatOut
    daily_active_users: AnalyticsStatOut
    avg_session_length_minutes: AnalyticsStatOut
    retention_30d: AnalyticsStatOut
    user_growth: list[AnalyticsGrowthPointOut]
    conversion_funnel: list[AnalyticsFunnelStepOut]
    top_subjects_attempted: list[AnalyticsSubjectAttemptOut]
    device_breakdown: list[AnalyticsDeviceBreakdownOut]
    most_active_time_label: str
    most_active_time_meta: str
    top_states: list[AnalyticsStateOut]
    activity_heatmap: list[AnalyticsHeatmapCellOut]
