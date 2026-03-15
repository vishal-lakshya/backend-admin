from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.models import AdminExam, AdminSubject, PaymentTransaction, SubscriptionPlan, UserSubscription
from app.admin.schemas import (
    ExamOut,
    PaymentAnalyticsOut,
    PaymentDashboardOut,
    PaymentPlanBreakdownOut,
    PaymentTransactionListOut,
    PaymentTransactionOut,
    SubjectOut,
    SubscriptionPlanBootstrapOut,
    SubscriptionPlanListOut,
    SubscriptionPlanOut,
    SubscriptionPlanUpdateRequest,
)
from app.admin.user_models import User
from app.admin.security import now_utc


def _comma_items(value: str | None) -> list[str]:
    return [item.strip() for item in str(value or '').split(',') if item.strip()]


def _plan_final_price(plan: SubscriptionPlan) -> float:
    return max(0.0, round(float(plan.price or 0.0) * (1 - (float(plan.discount_percent or 0.0) / 100)), 2))


def _plan_monthly_value(plan: SubscriptionPlan, billing_cycle: str | None = None) -> float:
    if billing_cycle == 'monthly' and plan.monthly_price:
        return float(plan.monthly_price)
    if billing_cycle == 'annual':
        if plan.annual_monthly_price:
            return float(plan.annual_monthly_price)
        if plan.annual_price:
            return float(plan.annual_price) / 12

    unit = (plan.duration_unit or 'month').lower()
    value = max(1, int(plan.duration_value or 1))
    final_price = _plan_final_price(plan)
    if unit == 'day':
        return round(final_price * (30 / value), 2)
    if unit == 'year':
        return round(final_price / (value * 12), 2)
    return round(final_price / value, 2)


def _duration_label(plan: SubscriptionPlan) -> str:
    unit = (plan.duration_unit or 'month').lower()
    suffix = unit if int(plan.duration_value or 1) == 1 else f'{unit}s'
    return f'{int(plan.duration_value or 1)} {suffix}'


def _scope_label(plan: SubscriptionPlan) -> str:
    scope = (plan.access_scope or 'full').lower()
    return {'full': 'Full Access', 'exam': 'Exam Based', 'subject': 'Subject Based'}.get(scope, scope.title())


def _serialize_plan(db: Session, plan: SubscriptionPlan) -> SubscriptionPlanOut:
    exam_map = {row.id: row.name for row in db.execute(select(AdminExam.id, AdminExam.name)).all()}
    subject_map = {row.id: row.name for row in db.execute(select(AdminSubject.id, AdminSubject.name)).all()}
    return SubscriptionPlanOut(
        id=plan.id,
        name=plan.name,
        code=plan.code,
        section=plan.section,
        duration_value=plan.duration_value,
        duration_unit=plan.duration_unit,
        price_type=plan.price_type or 'permanent',
        price=plan.price,
        discount_percent=plan.discount_percent or 0.0,
        final_price=_plan_final_price(plan),
        duration_label=_duration_label(plan),
        section_label=(plan.section or 'General').strip() if plan.section else 'General',
        what_is_covered=plan.what_is_covered,
        what_is_not_covered=plan.what_is_not_covered,
        covered_items=_comma_items(plan.what_is_covered),
        not_covered_items=_comma_items(plan.what_is_not_covered),
        access_scope=plan.access_scope,
        access_scope_label=_scope_label(plan),
        access_exam_ids=[int(item) for item in (plan.access_exam_ids or [])],
        access_subject_ids=[int(item) for item in (plan.access_subject_ids or [])],
        access_exam_names=[exam_map[item] for item in (plan.access_exam_ids or []) if item in exam_map],
        access_subject_names=[subject_map[item] for item in (plan.access_subject_ids or []) if item in subject_map],
        access_items=[str(item) for item in (plan.access_items or []) if str(item).strip()],
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
    return SubscriptionPlanListOut(items=[_serialize_plan(db, row) for row in rows])


def list_admin_plans(db: Session) -> SubscriptionPlanListOut:
    rows = db.execute(select(SubscriptionPlan).order_by(SubscriptionPlan.sort_order.asc(), SubscriptionPlan.id.asc())).scalars().all()
    return SubscriptionPlanListOut(items=[_serialize_plan(db, row) for row in rows])


def subscription_plan_bootstrap(db: Session) -> SubscriptionPlanBootstrapOut:
    exams = db.execute(select(AdminExam).where(AdminExam.is_active.is_(True)).order_by(AdminExam.name.asc())).scalars().all()
    subjects = db.execute(select(AdminSubject).where(AdminSubject.is_active.is_(True)).order_by(AdminSubject.name.asc())).scalars().all()
    exam_names = {row.id: row.name for row in exams}
    return SubscriptionPlanBootstrapOut(
        exams=[ExamOut.model_validate(row) for row in exams],
        subjects=[
            SubjectOut(
                id=row.id,
                exam_id=row.exam_id,
                exam_name=exam_names.get(row.exam_id, '-'),
                name=row.name,
                code=row.code,
                description=row.description,
                is_active=row.is_active,
                mapped_questions=row.mapped_questions,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in subjects
        ],
    )


def _apply_plan_payload(db: Session, *, plan: SubscriptionPlan, payload: SubscriptionPlanUpdateRequest) -> None:
    valid_exam_ids = {row.id for row in db.execute(select(AdminExam.id)).all()}
    valid_subject_ids = {row.id for row in db.execute(select(AdminSubject.id)).all()}
    bad_exam_ids = [item for item in payload.access_exam_ids if item not in valid_exam_ids]
    bad_subject_ids = [item for item in payload.access_subject_ids if item not in valid_subject_ids]
    if bad_exam_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'Invalid exam ids: {bad_exam_ids}')
    if bad_subject_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'Invalid subject ids: {bad_subject_ids}')
    if payload.access_scope == 'exam' and not payload.access_exam_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Select at least one exam for exam-based access.')
    if payload.access_scope == 'subject' and not payload.access_subject_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Select at least one subject for subject-based access.')

    plan.name = payload.name
    plan.code = payload.code.lower()
    plan.section = payload.section
    plan.duration_value = int(payload.duration_value)
    plan.duration_unit = payload.duration_unit
    plan.price_type = payload.price_type
    plan.price = float(payload.price)
    plan.discount_percent = float(payload.discount_percent or 0.0)
    plan.what_is_covered = payload.what_is_covered
    plan.what_is_not_covered = payload.what_is_not_covered
    plan.access_scope = payload.access_scope
    plan.access_exam_ids = payload.access_exam_ids if payload.access_scope == 'exam' else []
    plan.access_subject_ids = payload.access_subject_ids if payload.access_scope == 'subject' else []
    plan.access_items = payload.access_items
    plan.monthly_price = float(payload.monthly_price)
    plan.annual_price = float(payload.annual_price)
    plan.annual_monthly_price = float(payload.annual_monthly_price) if payload.annual_monthly_price is not None else (
        round(plan.annual_price / 12, 2) if plan.annual_price else None
    )
    plan.description = payload.description
    plan.is_active = payload.is_active
    plan.sort_order = int(payload.sort_order)


def create_subscription_plan(db: Session, *, payload: SubscriptionPlanUpdateRequest) -> SubscriptionPlanOut:
    duplicate_name = db.execute(select(SubscriptionPlan).where(SubscriptionPlan.name == payload.name)).scalars().first()
    if duplicate_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Plan name already exists.')
    duplicate_code = db.execute(select(SubscriptionPlan).where(SubscriptionPlan.code == payload.code.lower())).scalars().first()
    if duplicate_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Plan code already exists.')

    plan = SubscriptionPlan()
    _apply_plan_payload(db, plan=plan, payload=payload)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return _serialize_plan(db, plan)


def update_subscription_plan(db: Session, *, plan_id: int, payload: SubscriptionPlanUpdateRequest) -> SubscriptionPlanOut:
    plan = db.get(SubscriptionPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subscription plan not found.')

    duplicate_name = db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.id != plan_id, SubscriptionPlan.name == payload.name)
    ).scalars().first()
    if duplicate_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Plan name already exists.')

    duplicate_code = db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.id != plan_id, SubscriptionPlan.code == payload.code.lower())
    ).scalars().first()
    if duplicate_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Plan code already exists.')

    _apply_plan_payload(db, plan=plan, payload=payload)
    db.commit()
    db.refresh(plan)
    return _serialize_plan(db, plan)


def delete_subscription_plan(db: Session, *, plan_id: int) -> None:
    plan = db.get(SubscriptionPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subscription plan not found.')

    linked_subscription = db.execute(
        select(UserSubscription.id).where(UserSubscription.plan_id == plan_id).limit(1)
    ).first()
    if linked_subscription:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='This plan is already linked to user subscriptions. Deactivate it instead of deleting.',
        )

    db.delete(plan)
    db.commit()


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
        monthly_value = _plan_monthly_value(plan, row.billing_cycle)
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
