from collections import Counter, defaultdict
from datetime import datetime, timedelta

from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.models import AdminSubject, AdminTestSeries, PaymentTransaction, SubscriptionPlan, UserSubscription
from app.admin.question_storage import list_question_payloads
from app.admin.schemas import (
    DashboardActivityOut,
    DashboardBarPointOut,
    DashboardOverviewOut,
    DashboardRecentUserOut,
    DashboardStatOut,
    DashboardSubjectBreakdownOut,
    DashboardSubscriptionSplitOut,
)
from app.user.models import User, UserPracticeAttempt
from app.user.security import now_utc


def _safe_question_rows() -> list[dict]:
    try:
        return list_question_payloads()
    except (NoCredentialsError, PartialCredentialsError, ClientError):
        return []


def dashboard_overview(db: Session) -> DashboardOverviewOut:
    now = now_utc()
    today_start = datetime(now.year, now.month, now.day)
    month_start = datetime(now.year, now.month, 1)
    fourteen_days_ago = today_start - timedelta(days=13)
    thirty_days_ago = now - timedelta(days=30)

    users = db.execute(select(User).order_by(User.created_at.desc())).scalars().all()
    attempts = db.execute(select(UserPracticeAttempt).order_by(UserPracticeAttempt.attempted_at.desc())).scalars().all()
    subscriptions = db.execute(select(UserSubscription).order_by(UserSubscription.created_at.desc())).scalars().all()
    plans = db.execute(select(SubscriptionPlan)).scalars().all()
    transactions = db.execute(select(PaymentTransaction).order_by(PaymentTransaction.created_at.desc())).scalars().all()
    tests = db.execute(select(AdminTestSeries).order_by(AdminTestSeries.created_at.desc())).scalars().all()
    subjects = {subject.id: subject for subject in db.execute(select(AdminSubject)).scalars().all()}
    question_rows = _safe_question_rows()

    user_attempt_map: dict[int, list[UserPracticeAttempt]] = defaultdict(list)
    for item in attempts:
        user_attempt_map[item.user_id].append(item)

    active_user_ids = set()
    for user in users:
        if user.created_at >= thirty_days_ago or user.updated_at >= thirty_days_ago:
            active_user_ids.add(user.id)
    for item in attempts:
        if item.attempted_at >= thirty_days_ago:
            active_user_ids.add(item.user_id)

    monthly_revenue = sum(row.amount for row in transactions if row.status == 'success' and row.created_at >= month_start)
    total_questions = sum(1 for row in question_rows if str(row.get('status', '')).lower() == 'published')

    attempt_day_counter: Counter[str] = Counter()
    for item in attempts:
        if item.attempted_at >= fourteen_days_ago:
            attempt_day_counter[item.attempted_at.strftime('%d %b')] += 1
    bar_points: list[DashboardBarPointOut] = []
    cursor = fourteen_days_ago
    for _ in range(14):
        label = cursor.strftime('%d %b')
        bar_points.append(DashboardBarPointOut(label=label, value=int(attempt_day_counter.get(label, 0))))
        cursor += timedelta(days=1)

    subject_counter: Counter[int] = Counter()
    for row in question_rows:
        if str(row.get('status', '')).lower() != 'published':
            continue
        subject_id = int(row.get('subject_id') or 0)
        if subject_id:
            subject_counter[subject_id] += 1
    subject_breakdown = [
        DashboardSubjectBreakdownOut(
            subject_name=subjects[subject_id].name if subject_id in subjects else f'Subject {subject_id}',
            question_count=count,
        )
        for subject_id, count in subject_counter.most_common(8)
    ]

    plan_map = {plan.id: plan for plan in plans}
    active_subscriptions = [
        row for row in subscriptions
        if row.status in {'active', 'trialing'} and (row.ends_at is None or row.ends_at >= now)
    ]
    latest_subscription_by_user: dict[int, UserSubscription] = {}
    for row in active_subscriptions:
        if row.user_id not in latest_subscription_by_user:
            latest_subscription_by_user[row.user_id] = row

    free_users = 0
    pro_users = 0
    elite_users = 0
    for user in users:
        sub = latest_subscription_by_user.get(user.id)
        if not sub:
            free_users += 1
            continue
        plan = plan_map.get(sub.plan_id)
        code = (plan.code if plan else '').lower()
        if code == 'elite':
            elite_users += 1
        elif code == 'pro':
            pro_users += 1
        else:
            free_users += 1

    recent_activity: list[DashboardActivityOut] = []
    for user in users[:4]:
        recent_activity.append(DashboardActivityOut(tone='green', text=f'New user signup: {user.email}', timestamp=user.created_at))
    for tx in transactions[:3]:
        recent_activity.append(DashboardActivityOut(tone='gold', text=f'Payment {tx.status}: {tx.plan_code or "plan"} {tx.amount:.2f} {tx.currency}', timestamp=tx.created_at))
    for test in tests[:3]:
        recent_activity.append(DashboardActivityOut(tone='amber', text=f'Test created: {test.name}', timestamp=test.created_at))
    recent_activity.sort(key=lambda item: item.timestamp, reverse=True)
    recent_activity = recent_activity[:8]

    recent_users: list[DashboardRecentUserOut] = []
    for user in users[:8]:
        user_attempts = user_attempt_map.get(user.id, [])
        correct = sum(1 for item in user_attempts if item.is_correct)
        accuracy = round((correct / len(user_attempts)) * 100, 2) if user_attempts else 0.0
        sub = latest_subscription_by_user.get(user.id)
        plan_name = 'Free'
        if sub and sub.plan_id in plan_map:
            plan_name = plan_map[sub.plan_id].name
        status = 'Blocked' if user.is_blocked else ('Active' if user.is_active else 'Inactive')
        full_name = ' '.join(part for part in [user.first_name, user.last_name] if part).strip() or user.username
        recent_users.append(
            DashboardRecentUserOut(
                id=user.id,
                full_name=full_name,
                email=user.email,
                plan=plan_name,
                tests_taken=0,
                accuracy=accuracy,
                joined_at=user.created_at,
                status=status,
            )
        )

    return DashboardOverviewOut(
        generated_at=now,
        total_active_users=DashboardStatOut(value=len(active_user_ids), label='Total Active Users', change_text='Last 30 days'),
        revenue_this_month=DashboardStatOut(value=round(monthly_revenue, 2), label='Revenue This Month', change_text='Successful transactions'),
        tests_attempted_today=DashboardStatOut(value=0, label='Tests Attempted Today', change_text='Test attempt tracking pending'),
        total_questions=DashboardStatOut(value=total_questions, label='Total Questions', change_text='Published question bank'),
        test_attempts_last_14_days=bar_points,
        recent_activity=recent_activity,
        subject_breakdown=subject_breakdown,
        subscription_split=DashboardSubscriptionSplitOut(
            total_users=len(users),
            free_users=free_users,
            pro_users=pro_users,
            elite_users=elite_users,
            monthly_recurring_revenue=round(
                sum(
                    (
                        plan_map[row.plan_id].monthly_price if row.billing_cycle == 'monthly'
                        else (plan_map[row.plan_id].annual_monthly_price or (plan_map[row.plan_id].annual_price / 12 if plan_map[row.plan_id].annual_price else 0))
                    )
                    for row in active_subscriptions if row.plan_id in plan_map
                ),
                2,
            ),
        ),
        recent_users=recent_users,
    )
