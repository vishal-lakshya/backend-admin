from sqlalchemy import inspect, select, text

from app.admin.database import Base, engine
from app.admin import models as admin_models  # noqa: F401
from app.user import models as user_models  # noqa: F401
from app.admin.models import SubscriptionPlan


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


def ensure_admin_test_columns() -> None:
    inspector = inspect(engine)
    if 'admin_test_series' not in inspector.get_table_names():
        return

    columns = {col['name'] for col in inspector.get_columns('admin_test_series')}
    alter_statements: list[str] = []
    if 'display_mode' not in columns:
        alter_statements.append("ALTER TABLE admin_test_series ADD COLUMN display_mode VARCHAR(40) DEFAULT 'live'")

    if not alter_statements:
        return

    with engine.begin() as conn:
        for stmt in alter_statements:
            conn.execute(text(stmt))


def ensure_subscription_plan_columns() -> None:
    inspector = inspect(engine)
    if 'subscription_plans' not in inspector.get_table_names():
        return

    columns = {col['name'] for col in inspector.get_columns('subscription_plans')}
    alter_statements: list[str] = []
    if 'section' not in columns:
        alter_statements.append("ALTER TABLE subscription_plans ADD COLUMN section VARCHAR(80)")
    if 'duration_value' not in columns:
        alter_statements.append('ALTER TABLE subscription_plans ADD COLUMN duration_value INTEGER DEFAULT 1')
    if 'duration_unit' not in columns:
        alter_statements.append("ALTER TABLE subscription_plans ADD COLUMN duration_unit VARCHAR(20) DEFAULT 'month'")
    if 'price_type' not in columns:
        alter_statements.append("ALTER TABLE subscription_plans ADD COLUMN price_type VARCHAR(20) DEFAULT 'permanent'")
    if 'price' not in columns:
        alter_statements.append('ALTER TABLE subscription_plans ADD COLUMN price DOUBLE PRECISION DEFAULT 0')
    if 'discount_percent' not in columns:
        alter_statements.append('ALTER TABLE subscription_plans ADD COLUMN discount_percent DOUBLE PRECISION DEFAULT 0')
    if 'what_is_covered' not in columns:
        alter_statements.append('ALTER TABLE subscription_plans ADD COLUMN what_is_covered TEXT')
    if 'what_is_not_covered' not in columns:
        alter_statements.append('ALTER TABLE subscription_plans ADD COLUMN what_is_not_covered TEXT')
    if 'access_scope' not in columns:
        alter_statements.append("ALTER TABLE subscription_plans ADD COLUMN access_scope VARCHAR(30) DEFAULT 'full'")
    if 'access_exam_ids' not in columns:
        alter_statements.append("ALTER TABLE subscription_plans ADD COLUMN access_exam_ids JSON DEFAULT '[]'")
    if 'access_subject_ids' not in columns:
        alter_statements.append("ALTER TABLE subscription_plans ADD COLUMN access_subject_ids JSON DEFAULT '[]'")
    if 'access_items' not in columns:
        alter_statements.append("ALTER TABLE subscription_plans ADD COLUMN access_items JSON DEFAULT '[]'")

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
                section='Starter',
                duration_value=1,
                duration_unit='month',
                price=0.0,
                discount_percent=0.0,
                what_is_covered='Basic access for getting started',
                access_scope='full',
                access_items=['50 practice questions per day', 'Basic analytics', 'Limited PYQ access'],
                monthly_price=0.0,
                annual_price=0.0,
                annual_monthly_price=0.0,
                description='Get started with UPSC prep at no cost',
                sort_order=1,
            ),
            SubscriptionPlan(
                name='Pro',
                code='pro',
                section='Prelims',
                duration_value=1,
                duration_unit='month',
                price=499.0,
                discount_percent=0.0,
                what_is_covered='Best for Prelims preparation with full question and mock access',
                access_scope='full',
                access_items=['Unlimited practice questions', 'Mock tests', 'All PYQ papers', 'Detailed explanations'],
                monthly_price=499.0,
                annual_price=3599.0,
                annual_monthly_price=299.92,
                description='Everything you need to crack Prelims',
                sort_order=2,
            ),
            SubscriptionPlan(
                name='Elite',
                code='elite',
                section='Prelims + Mains',
                duration_value=1,
                duration_unit='month',
                price=999.0,
                discount_percent=0.0,
                what_is_covered='Complete CSE preparation with advanced access',
                access_scope='full',
                access_items=['Everything in Pro', 'Mains test series', 'Essay practice', 'Priority support'],
                monthly_price=999.0,
                annual_price=7199.0,
                annual_monthly_price=599.92,
                description='Complete CSE preparation, Prelims + Mains',
                sort_order=3,
            ),
        ])
        db.commit()


def run_bootstrap() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_user_profile_columns()
    ensure_user_auth_policy_columns()
    ensure_admin_profile_columns()
    ensure_admin_pyq_columns()
    ensure_admin_test_columns()
    ensure_subscription_plan_columns()
    seed_default_subscription_plans()
