from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.models import PaymentTransaction, SubscriptionPlan, UserSubscription
from app.admin.schemas import (
    PaymentAnalyticsOut,
    PaymentDashboardOut,
    PaymentPlanBreakdownOut,
    PaymentTransactionListOut,
    PaymentTransactionOut,
    SubscriptionPlanListOut,
    SubscriptionPlanOut,
)
from app.user.models import User
from app.user.security import now_utc


def _serialize_plan(plan: SubscriptionPlan) -> SubscriptionPlanOut:
    return SubscriptionPlanOut(
        id=plan.id,
        name=plan.name,
        code=plan.code,
        monthly_price=plan.monthly_price,
        annual_price=plan.annual_price,
        annual_monthly_price=plan.annual_monthly_price,
        description=plan.description,
        is_active=plan.is_active,
        sort_order=plan.sort_order,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


def list_public_plans(db: Session) -> SubscriptionPlanListOut:
    rows = db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.is_active.is_(True)).order_by(SubscriptionPlan.sort_order.asc(), SubscriptionPlan.id.asc())
    ).scalars().all()
    return SubscriptionPlanListOut(items=[_serialize_plan(row) for row in rows])


def payment_dashboard(db: Session, *, skip: int = 0, limit: int = 50) -> PaymentDashboardOut:
    users = db.execute(select(User)).scalars().all()
    plans = db.execute(select(SubscriptionPlan)).scalars().all()
    subscriptions = db.execute(select(UserSubscription).order_by(UserSubscription.created_at.desc())).scalars().all()
    transactions = db.execute(select(PaymentTransaction).order_by(PaymentTransaction.created_at.desc(), PaymentTransaction.id.desc())).scalars().all()

    user_map = {user.id: user for user in users}
    plan_map = {plan.id: plan for plan in plans}
    now = now_utc()
    today_start = datetime(now.year, now.month, now.day)
    month_start = datetime(now.year, now.month, 1)
    six_months_ago = datetime(now.year, now.month, 1) - timedelta(days=150)

    active_subscriptions = [
        row for row in subscriptions
        if row.status in {'active', 'trialing'}
        and (row.ends_at is None or row.ends_at >= now)
    ]
    subscribed_users = len({row.user_id for row in active_subscriptions})

    monthly_revenue = 0.0
    plan_counts: dict[str, dict] = defaultdict(lambda: {'name': '-', 'users': 0, 'monthly_revenue': 0.0})
    for row in active_subscriptions:
        plan = plan_map.get(row.plan_id)
        if not plan:
            continue
        monthly_value = plan.monthly_price if row.billing_cycle == 'monthly' else (plan.annual_monthly_price or (plan.annual_price / 12 if plan.annual_price else 0.0))
        monthly_revenue += monthly_value
        bucket = plan_counts[plan.code]
        bucket['name'] = plan.name
        bucket['users'] += 1
        bucket['monthly_revenue'] += monthly_value

    transactions_today = sum(1 for row in transactions if row.created_at >= today_start)
    successful_transactions = [row for row in transactions if row.status == 'success']
    success_rate = round((len(successful_transactions) / len(transactions)) * 100, 2) if transactions else 0.0
    disputed_payments = sum(1 for row in transactions if row.status == 'disputed')
    refunds_this_month = sum(1 for row in transactions if row.status == 'refunded' and row.created_at >= month_start)
    avg_revenue = round((monthly_revenue / subscribed_users), 2) if subscribed_users else 0.0

    month_buckets: dict[str, float] = defaultdict(float)
    for row in transactions:
        if row.status != 'success' or row.created_at < six_months_ago:
            continue
        key = row.created_at.strftime('%b')
        month_buckets[key] += row.amount
    ordered_months = []
    cursor = datetime(now.year, now.month, 1)
    for _ in range(6):
        ordered_months.append(cursor.strftime('%b'))
        cursor = (cursor.replace(day=1) - timedelta(days=1)).replace(day=1)
    ordered_months.reverse()

    tx_items = [
        PaymentTransactionOut(
            id=row.id,
            user_id=row.user_id,
            user_name=(' '.join(part for part in [user_map[row.user_id].first_name, user_map[row.user_id].last_name] if part).strip() or user_map[row.user_id].username) if row.user_id in user_map else 'Guest',
            user_email=user_map[row.user_id].email if row.user_id in user_map else '-',
            transaction_type=row.transaction_type,
            plan_code=row.plan_code,
            amount=row.amount,
            currency=row.currency,
            method=row.method,
            gateway=row.gateway,
            status=row.status,
            created_at=row.created_at,
        )
        for row in transactions[skip: skip + limit]
    ]

    return PaymentDashboardOut(
        analytics=PaymentAnalyticsOut(
            total_users=len(users),
            subscribed_users=subscribed_users,
            monthly_recurring_revenue=round(monthly_revenue, 2),
            annual_run_rate=round(monthly_revenue * 12, 2),
            average_revenue_per_subscribed_user=avg_revenue,
            transactions_today=transactions_today,
            success_rate=success_rate,
            disputed_payments=disputed_payments,
            refunds_this_month=refunds_this_month,
        ),
        plan_breakdown=[
            PaymentPlanBreakdownOut(
                plan_code=code,
                plan_name=data['name'],
                users=data['users'],
                monthly_revenue=round(data['monthly_revenue'], 2),
            )
            for code, data in sorted(plan_counts.items(), key=lambda item: item[1]['monthly_revenue'], reverse=True)
        ],
        monthly_revenue=[{'month': month, 'amount': round(month_buckets.get(month, 0.0), 2)} for month in ordered_months],
        transactions=PaymentTransactionListOut(items=tx_items, total=len(transactions), skip=skip, limit=limit),
    )
