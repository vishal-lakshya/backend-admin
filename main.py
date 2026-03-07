from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session
from sqlalchemy.engine import make_url

from app.admin.config import settings
from app.admin.analytics_router import router as admin_analytics_router
from app.admin.dashboard_router import router as admin_dashboard_router
from app.admin.database import Base, engine
from app.admin.exam_router import router as admin_exam_router
from app.admin.models import SubscriptionPlan
from app.admin.question_router import router as admin_question_router
from app.admin.pyq_router import router as admin_pyq_router
from app.admin.payment_router import admin_router as admin_payment_router
from app.admin.payment_router import router as subscription_router
from app.admin.platform_settings_router import router as admin_platform_settings_router
from app.admin.router import router as admin_auth_router
from app.admin.subject_router import router as admin_subject_router
from app.admin.test_router import router as admin_test_router
from app.admin.user_management_router import router as admin_user_management_router
from app.user import models as user_models  # noqa: F401
from app.user.practice_router import router as user_practice_router
from app.user.router import router as user_auth_router


app = FastAPI(title='UPSC Backend', version='1.0.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


def log_database_target() -> None:
    url = make_url(settings.DATABASE_URL)
    print(
        '[DB TARGET] '
        f'driver={url.drivername} '
        f'host={url.host} '
        f'port={url.port} '
        f'database={url.database} '
        f'query={dict(url.query)}'
    )


def ensure_user_profile_columns() -> None:
    inspector = inspect(engine)
    if 'users' not in inspector.get_table_names():
        return

    columns = {col['name'] for col in inspector.get_columns('users')}
    alter_statements: list[str] = []
    if 'first_name' not in columns:
        alter_statements.append('ALTER TABLE users ADD COLUMN first_name VARCHAR(80)')
    if 'last_name' not in columns:
        alter_statements.append('ALTER TABLE users ADD COLUMN last_name VARCHAR(80)')
    if 'state' not in columns:
        alter_statements.append('ALTER TABLE users ADD COLUMN state VARCHAR(80)')
    if 'target_exam_year' not in columns:
        alter_statements.append('ALTER TABLE users ADD COLUMN target_exam_year INTEGER')

    if not alter_statements:
        return

    with engine.begin() as conn:
        for stmt in alter_statements:
            conn.execute(text(stmt))


def ensure_user_auth_policy_columns() -> None:
    inspector = inspect(engine)
    if 'users' not in inspector.get_table_names():
        return

    columns = {col['name'] for col in inspector.get_columns('users')}
    alter_statements: list[str] = []
    if 'failed_login_attempts' not in columns:
        alter_statements.append('ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER DEFAULT 0')
    if 'locked_until' not in columns:
        alter_statements.append('ALTER TABLE users ADD COLUMN locked_until TIMESTAMP')
    if 'last_failed_login_at' not in columns:
        alter_statements.append('ALTER TABLE users ADD COLUMN last_failed_login_at TIMESTAMP')

    if not alter_statements:
        return

    with engine.begin() as conn:
        for stmt in alter_statements:
            conn.execute(text(stmt))


def ensure_admin_profile_columns() -> None:
    inspector = inspect(engine)
    if 'admin_users' not in inspector.get_table_names():
        return

    columns = {col['name'] for col in inspector.get_columns('admin_users')}
    alter_statements: list[str] = []
    if 'first_name' not in columns:
        alter_statements.append('ALTER TABLE admin_users ADD COLUMN first_name VARCHAR(80)')
    if 'last_name' not in columns:
        alter_statements.append('ALTER TABLE admin_users ADD COLUMN last_name VARCHAR(80)')
    if 'bio' not in columns:
        alter_statements.append('ALTER TABLE admin_users ADD COLUMN bio TEXT')

    if not alter_statements:
        return

    with engine.begin() as conn:
        for stmt in alter_statements:
            conn.execute(text(stmt))


def ensure_admin_pyq_columns() -> None:
    inspector = inspect(engine)
    if 'admin_pyq_papers' not in inspector.get_table_names():
        return

    column_meta = {col['name']: col for col in inspector.get_columns('admin_pyq_papers')}
    columns = set(column_meta)
    alter_statements: list[str] = []
    if 'paper_type' not in columns:
        alter_statements.append("ALTER TABLE admin_pyq_papers ADD COLUMN paper_type VARCHAR(120) DEFAULT 'General'")
    if 'paper_set' not in columns:
        alter_statements.append('ALTER TABLE admin_pyq_papers ADD COLUMN paper_set VARCHAR(80)')
    if 'subject_id' in column_meta and not column_meta['subject_id'].get('nullable', True):
        alter_statements.append('ALTER TABLE admin_pyq_papers ALTER COLUMN subject_id DROP NOT NULL')
    if 'paper_file_key' in column_meta and not column_meta['paper_file_key'].get('nullable', True):
        alter_statements.append('ALTER TABLE admin_pyq_papers ALTER COLUMN paper_file_key DROP NOT NULL')
    if 'paper_file_name' in column_meta and not column_meta['paper_file_name'].get('nullable', True):
        alter_statements.append('ALTER TABLE admin_pyq_papers ALTER COLUMN paper_file_name DROP NOT NULL')
    if 'questions_file_key' in column_meta and not column_meta['questions_file_key'].get('nullable', True):
        alter_statements.append('ALTER TABLE admin_pyq_papers ALTER COLUMN questions_file_key DROP NOT NULL')

    if not alter_statements:
        return

    with engine.begin() as conn:
        for stmt in alter_statements:
            conn.execute(text(stmt))


def seed_default_subscription_plans() -> None:
    from sqlalchemy.orm import Session

    with Session(engine) as db:
        exists = db.execute(select(SubscriptionPlan).limit(1)).scalars().first()
        if exists:
            return
        db.add_all([
            SubscriptionPlan(
                name='Free',
                code='free',
                monthly_price=0.0,
                annual_price=0.0,
                annual_monthly_price=0.0,
                description='Get started with UPSC prep at no cost',
                sort_order=1,
            ),
            SubscriptionPlan(
                name='Pro',
                code='pro',
                monthly_price=499.0,
                annual_price=3599.0,
                annual_monthly_price=299.92,
                description='Everything you need to crack Prelims',
                sort_order=2,
            ),
            SubscriptionPlan(
                name='Elite',
                code='elite',
                monthly_price=999.0,
                annual_price=7199.0,
                annual_monthly_price=599.92,
                description='Complete CSE preparation, Prelims + Mains',
                sort_order=3,
            ),
        ])
        db.commit()


@app.on_event('startup')
def on_startup() -> None:
    log_database_target()
    Base.metadata.create_all(bind=engine)
    ensure_user_profile_columns()
    ensure_user_auth_policy_columns()
    ensure_admin_profile_columns()
    ensure_admin_pyq_columns()
    seed_default_subscription_plans()


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


api_v1 = APIRouter(prefix='/api/v1')
api_v1.include_router(admin_auth_router, prefix='/admin')
api_v1.include_router(admin_analytics_router, prefix='/admin')
api_v1.include_router(admin_dashboard_router, prefix='/admin')
api_v1.include_router(admin_exam_router, prefix='/admin')
api_v1.include_router(admin_subject_router, prefix='/admin')
api_v1.include_router(admin_question_router, prefix='/admin')
api_v1.include_router(admin_pyq_router, prefix='/admin')
api_v1.include_router(admin_test_router, prefix='/admin')
api_v1.include_router(admin_user_management_router, prefix='/admin')
api_v1.include_router(admin_payment_router, prefix='/admin')
api_v1.include_router(admin_platform_settings_router, prefix='/admin')
api_v1.include_router(subscription_router)
api_v1.include_router(user_auth_router, prefix='/user')
api_v1.include_router(user_practice_router, prefix='/user')
api_v1.include_router(admin_auth_router)  # compatibility for current frontend auth pages
app.include_router(api_v1)
