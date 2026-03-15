from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.admin.models import (
    AdminBroadcastNotification,
    AdminExam,
    AdminSubject,
    AdminTestSeries,
    PaymentTransaction,
    SubscriptionPlan,
    UserNotificationRead,
    UserSubscription,
)
from app.admin.schemas import (
    AdminAlertItemOut,
    AdminNotificationBootstrapOut,
    AdminNotificationOverviewOut,
    BroadcastNotificationCreateRequest,
    BroadcastNotificationListOut,
    BroadcastNotificationOut,
    BroadcastNotificationUpdateRequest,
    NotificationPlanOptionOut,
    NotificationTargetOptionOut,
    UserNotificationListOut,
    UserNotificationOut,
)
from app.user.models import User, UserPracticeAttempt, UserTestAttempt
from app.user.security import now_utc


VALID_AUDIENCE_TYPES = {'all', 'email', 'phone', 'exam', 'subject', 'subscription'}
VALID_NOTIFICATION_STATUSES = {'active', 'draft', 'archived'}


@dataclass
class NotificationRecipientContext:
    exam_ids: set[int]
    subject_ids: set[int]
    plan_codes: set[str]


def _normalize_filters(payload: BroadcastNotificationCreateRequest | BroadcastNotificationUpdateRequest) -> dict:
    base = {
        'email_addresses': [str(item).lower() for item in (payload.email_addresses or [])],
        'phone_numbers': payload.phone_numbers or [],
        'exam_ids': payload.exam_ids or [],
        'subject_ids': payload.subject_ids or [],
        'subscription_plan_codes': payload.subscription_plan_codes or [],
    }
    incoming = getattr(payload, 'audience_filters', {}) or {}
    for key in ('email_addresses', 'phone_numbers', 'exam_ids', 'subject_ids', 'subscription_plan_codes'):
        if key in incoming and incoming[key] not in (None, []):
            base[key] = incoming[key]
    return base


def _validate_notification_payload(
    db: Session,
    *,
    audience_type: str,
    filters: dict,
    starts_at: datetime | None,
    expires_at: datetime | None,
    status_value: str,
) -> None:
    if audience_type not in VALID_AUDIENCE_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid audience type.')
    if status_value not in VALID_NOTIFICATION_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid notification status.')
    if starts_at and expires_at and expires_at <= starts_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Expiry must be after start time.')

    if audience_type == 'email' and not filters['email_addresses']:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='At least one email is required.')
    if audience_type == 'phone' and not filters['phone_numbers']:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='At least one phone number is required.')
    if audience_type == 'exam' and not filters['exam_ids']:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='At least one exam is required.')
    if audience_type == 'subject' and not filters['subject_ids']:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='At least one subject is required.')
    if audience_type == 'subscription' and not filters['subscription_plan_codes']:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='At least one subscription plan is required.')

    if filters['exam_ids']:
        valid_exam_ids = {row.id for row in db.execute(select(AdminExam.id)).all()}
        invalid = [item for item in filters['exam_ids'] if item not in valid_exam_ids]
        if invalid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'Invalid exam ids: {invalid}')
    if filters['subject_ids']:
        valid_subject_ids = {row.id for row in db.execute(select(AdminSubject.id)).all()}
        invalid = [item for item in filters['subject_ids'] if item not in valid_subject_ids]
        if invalid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'Invalid subject ids: {invalid}')
    if filters['subscription_plan_codes']:
        valid_plan_codes = {row.code for row in db.execute(select(SubscriptionPlan.code)).all()}
        invalid = [item for item in filters['subscription_plan_codes'] if item not in valid_plan_codes]
        if invalid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'Invalid subscription plan codes: {invalid}')


def _collect_recipient_context(db: Session) -> dict[int, NotificationRecipientContext]:
    attempts = db.execute(select(UserPracticeAttempt.user_id, UserPracticeAttempt.exam_id, UserPracticeAttempt.subject_id)).all()
    test_attempts = db.execute(select(UserTestAttempt.user_id, UserTestAttempt.test_id)).all()
    tests = {
        row.id: row
        for row in db.execute(select(AdminTestSeries)).scalars().all()
    }
    subjects = {
        row.id: row
        for row in db.execute(select(AdminSubject)).scalars().all()
    }
    subscriptions = db.execute(
        select(UserSubscription.user_id, SubscriptionPlan.code)
        .join(SubscriptionPlan, SubscriptionPlan.id == UserSubscription.plan_id)
        .where(UserSubscription.status.in_(['active', 'trialing']))
    ).all()

    context: dict[int, NotificationRecipientContext] = {}
    for user_id, exam_id, subject_id in attempts:
        bucket = context.setdefault(user_id, NotificationRecipientContext(set(), set(), set()))
        if exam_id:
            bucket.exam_ids.add(exam_id)
        if subject_id:
            bucket.subject_ids.add(subject_id)
    for user_id, test_id in test_attempts:
        bucket = context.setdefault(user_id, NotificationRecipientContext(set(), set(), set()))
        test = tests.get(test_id)
        if not test or not test.subject_id:
            continue
        bucket.subject_ids.add(test.subject_id)
        subject = subjects.get(test.subject_id)
        if subject and subject.exam_id:
            bucket.exam_ids.add(subject.exam_id)
    for user_id, plan_code in subscriptions:
        bucket = context.setdefault(user_id, NotificationRecipientContext(set(), set(), set()))
        if plan_code:
            bucket.plan_codes.add(plan_code)
    return context


def _user_matches_notification(user: User, notification: AdminBroadcastNotification, context: NotificationRecipientContext | None) -> bool:
    audience_type = notification.audience_type
    filters = notification.audience_filters or {}
    if audience_type == 'all':
        return True
    if audience_type == 'email':
        return str(user.email).lower() in {str(item).lower() for item in filters.get('email_addresses', [])}
    if audience_type == 'phone':
        return bool(user.phone) and user.phone in set(filters.get('phone_numbers', []))
    if audience_type == 'exam':
        return bool(context and context.exam_ids.intersection(set(filters.get('exam_ids', []))))
    if audience_type == 'subject':
        return bool(context and context.subject_ids.intersection(set(filters.get('subject_ids', []))))
    if audience_type == 'subscription':
        return bool(context and context.plan_codes.intersection(set(filters.get('subscription_plan_codes', []))))
    return False


def _notification_is_live(notification: AdminBroadcastNotification, *, at_time: datetime | None = None) -> bool:
    now = at_time or now_utc()
    if notification.status != 'active':
        return False
    if notification.starts_at and notification.starts_at > now:
        return False
    if notification.expires_at and notification.expires_at < now:
        return False
    return True


def _recipient_count(db: Session, notification: AdminBroadcastNotification) -> int:
    users = db.execute(select(User)).scalars().all()
    context_map = _collect_recipient_context(db)
    return sum(1 for user in users if _user_matches_notification(user, notification, context_map.get(user.id)))


def _serialize_broadcast(db: Session, notification: AdminBroadcastNotification) -> BroadcastNotificationOut:
    return BroadcastNotificationOut(
        id=notification.id,
        title=notification.title,
        message=notification.message,
        audience_type=notification.audience_type,
        audience_filters=notification.audience_filters or {},
        status=notification.status,
        recipient_count=_recipient_count(db, notification),
        starts_at=notification.starts_at,
        expires_at=notification.expires_at,
        created_by_admin_id=notification.created_by_admin_id,
        created_at=notification.created_at,
        updated_at=notification.updated_at,
    )


def notification_bootstrap(db: Session) -> AdminNotificationBootstrapOut:
    exams = db.execute(select(AdminExam).order_by(AdminExam.name.asc())).scalars().all()
    subjects = db.execute(select(AdminSubject).order_by(AdminSubject.name.asc())).scalars().all()
    plans = db.execute(select(SubscriptionPlan).where(SubscriptionPlan.is_active.is_(True)).order_by(SubscriptionPlan.sort_order.asc())).scalars().all()
    return AdminNotificationBootstrapOut(
        exams=[NotificationTargetOptionOut(id=row.id, label=row.name, code=row.code) for row in exams],
        subjects=[NotificationTargetOptionOut(id=row.id, label=row.name, code=row.code) for row in subjects],
        subscription_plans=[NotificationPlanOptionOut(id=row.id, code=row.code, label=row.name) for row in plans],
    )


def create_broadcast_notification(
    db: Session,
    *,
    payload: BroadcastNotificationCreateRequest,
    created_by_admin_id: int | None,
) -> BroadcastNotificationOut:
    filters = _normalize_filters(payload)
    _validate_notification_payload(
        db,
        audience_type=payload.audience_type,
        filters=filters,
        starts_at=payload.starts_at,
        expires_at=payload.expires_at,
        status_value=payload.status,
    )
    row = AdminBroadcastNotification(
        title=payload.title.strip(),
        message=payload.message.strip(),
        audience_type=payload.audience_type,
        audience_filters=filters,
        status=payload.status,
        created_by_admin_id=created_by_admin_id,
        starts_at=payload.starts_at,
        expires_at=payload.expires_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_broadcast(db, row)


def update_broadcast_notification(
    db: Session,
    *,
    notification_id: int,
    payload: BroadcastNotificationUpdateRequest,
) -> BroadcastNotificationOut:
    row = db.get(AdminBroadcastNotification, notification_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Notification not found.')

    audience_type = payload.audience_type or row.audience_type
    merged_filters = dict(row.audience_filters or {})
    explicit_field_map = {
        'email_addresses': payload.email_addresses,
        'phone_numbers': payload.phone_numbers,
        'exam_ids': payload.exam_ids,
        'subject_ids': payload.subject_ids,
        'subscription_plan_codes': payload.subscription_plan_codes,
    }
    updates = _normalize_filters(payload)
    for key, explicit_value in explicit_field_map.items():
        if explicit_value is not None:
            merged_filters[key] = updates[key]

    starts_at = payload.starts_at if payload.starts_at is not None else row.starts_at
    expires_at = payload.expires_at if payload.expires_at is not None else row.expires_at
    status_value = payload.status or row.status
    _validate_notification_payload(
        db,
        audience_type=audience_type,
        filters=merged_filters,
        starts_at=starts_at,
        expires_at=expires_at,
        status_value=status_value,
    )

    if payload.title is not None:
        row.title = payload.title.strip()
    if payload.message is not None:
        row.message = payload.message.strip()
    row.audience_type = audience_type
    row.audience_filters = merged_filters
    row.status = status_value
    row.starts_at = starts_at
    row.expires_at = expires_at
    db.commit()
    db.refresh(row)
    return _serialize_broadcast(db, row)


def delete_broadcast_notification(db: Session, *, notification_id: int) -> None:
    row = db.get(AdminBroadcastNotification, notification_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Notification not found.')
    db.delete(row)
    db.commit()


def list_broadcast_notifications(db: Session, *, skip: int, limit: int) -> BroadcastNotificationListOut:
    rows = db.execute(
        select(AdminBroadcastNotification)
        .order_by(desc(AdminBroadcastNotification.created_at), desc(AdminBroadcastNotification.id))
    ).scalars().all()
    items = [_serialize_broadcast(db, row) for row in rows]
    return BroadcastNotificationListOut(items=items[skip: skip + limit], total=len(items), skip=skip, limit=limit)


def _system_alerts(db: Session) -> tuple[list[AdminAlertItemOut], dict[str, int]]:
    now = now_utc()
    soon = now + timedelta(days=3)

    transactions = db.execute(select(PaymentTransaction).order_by(desc(PaymentTransaction.created_at))).scalars().all()
    subscriptions = db.execute(select(UserSubscription).order_by(desc(UserSubscription.created_at))).scalars().all()
    users = db.execute(select(User)).scalars().all()
    broadcasts = db.execute(select(AdminBroadcastNotification)).scalars().all()

    alerts: list[AdminAlertItemOut] = []

    refund_requests = [row for row in transactions if row.status in {'refund_requested', 'refunded'}]
    if refund_requests:
        latest = refund_requests[0]
        alerts.append(AdminAlertItemOut(
            id=f'refund-{latest.id}',
            category='refund',
            severity='high' if latest.status == 'refund_requested' else 'medium',
            title='Refund activity detected',
            message=f'{len(refund_requests)} refund-related transaction(s) need review.',
            href='admin-payments.html',
            created_at=latest.created_at,
        ))

    expiring_subscriptions = [
        row for row in subscriptions
        if row.status in {'active', 'trialing'}
        and ((row.renews_at and now <= row.renews_at <= soon) or (row.ends_at and now <= row.ends_at <= soon))
    ]
    if expiring_subscriptions:
        latest_expiry = max(
            (row.renews_at or row.ends_at or row.created_at) for row in expiring_subscriptions
        )
        alerts.append(AdminAlertItemOut(
            id='expiring-subscriptions',
            category='subscription',
            severity='medium',
            title='Subscriptions expiring soon',
            message=f'{len(expiring_subscriptions)} subscription(s) will expire or renew within 3 days.',
            href='admin-payments.html',
            created_at=latest_expiry,
        ))

    failed_payments = [row for row in transactions if row.status in {'failed', 'disputed'}]
    if failed_payments:
        latest_failed = failed_payments[0]
        alerts.append(AdminAlertItemOut(
            id=f'payment-{latest_failed.id}',
            category='payment',
            severity='high',
            title='Payment failures require attention',
            message=f'{len(failed_payments)} failed or disputed payment(s) found.',
            href='admin-payments.html',
            created_at=latest_failed.created_at,
        ))

    locked_users = [row for row in users if row.locked_until and row.locked_until > now]
    if locked_users:
        latest_lock = max((row.locked_until or row.updated_at) for row in locked_users)
        alerts.append(AdminAlertItemOut(
            id='locked-users',
            category='security',
            severity='medium',
            title='Users are currently locked out',
            message=f'{len(locked_users)} user account(s) are locked due to repeated failed login attempts.',
            href='admin-users.html',
            created_at=latest_lock,
        ))

    new_users_today = [row for row in users if row.created_at.date() == now.date()]
    if new_users_today:
        latest_user = max(row.created_at for row in new_users_today)
        alerts.append(AdminAlertItemOut(
            id='new-users-today',
            category='growth',
            severity='low',
            title='New user signups today',
            message=f'{len(new_users_today)} new user account(s) were created today.',
            href='admin-users.html',
            created_at=latest_user,
        ))

    active_broadcasts = sum(1 for row in broadcasts if _notification_is_live(row, at_time=now))
    alerts.sort(key=lambda item: item.created_at, reverse=True)
    return alerts, {
        'refund_requests': len(refund_requests),
        'expiring_subscriptions': len(expiring_subscriptions),
        'failed_payments': len(failed_payments),
        'locked_users': len(locked_users),
        'active_broadcasts': active_broadcasts,
    }


def admin_notification_overview(db: Session, *, limit: int = 8) -> AdminNotificationOverviewOut:
    alerts, counts = _system_alerts(db)
    return AdminNotificationOverviewOut(
        unread_count=min(len(alerts), limit),
        items=alerts[:limit],
        refund_requests=counts['refund_requests'],
        expiring_subscriptions=counts['expiring_subscriptions'],
        failed_payments=counts['failed_payments'],
        locked_users=counts['locked_users'],
        active_broadcasts=counts['active_broadcasts'],
    )


def list_user_notifications(db: Session, *, user: User, limit: int = 20) -> UserNotificationListOut:
    notifications = db.execute(
        select(AdminBroadcastNotification)
        .order_by(desc(AdminBroadcastNotification.created_at), desc(AdminBroadcastNotification.id))
    ).scalars().all()
    read_ids = {
        row.notification_id
        for row in db.execute(select(UserNotificationRead).where(UserNotificationRead.user_id == user.id)).scalars().all()
    }
    context_map = _collect_recipient_context(db)
    context = context_map.get(user.id)

    items: list[UserNotificationOut] = []
    for row in notifications:
        if not _notification_is_live(row):
            continue
        if not _user_matches_notification(user, row, context):
            continue
        items.append(UserNotificationOut(
            id=row.id,
            title=row.title,
            message=row.message,
            created_at=row.created_at,
            starts_at=row.starts_at,
            expires_at=row.expires_at,
            is_read=row.id in read_ids,
        ))
    unread_count = sum(1 for item in items if not item.is_read)
    return UserNotificationListOut(items=items[:limit], unread_count=unread_count)


def mark_user_notification_read(db: Session, *, user: User, notification_id: int) -> None:
    row = db.get(AdminBroadcastNotification, notification_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Notification not found.')
    existing = db.execute(
        select(UserNotificationRead).where(
            UserNotificationRead.user_id == user.id,
            UserNotificationRead.notification_id == notification_id,
        )
    ).scalars().first()
    if existing:
        return
    db.add(UserNotificationRead(user_id=user.id, notification_id=notification_id))
    db.commit()
