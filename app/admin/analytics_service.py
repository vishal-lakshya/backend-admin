from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.models import AdminSubject, AdminTestSeries, UserSubscription
from app.admin.schemas import (
    AnalyticsDeviceBreakdownOut,
    AnalyticsFunnelStepOut,
    AnalyticsGrowthPointOut,
    AnalyticsHeatmapCellOut,
    AnalyticsOverviewOut,
    AnalyticsStateOut,
    AnalyticsStatOut,
    AnalyticsSubjectAttemptOut,
)
from app.user.models import User, UserPracticeAttempt, UserQuestionBookmark, UserRefreshToken, UserTestAttempt
from app.user.security import now_utc


def _device_type(user_agent: str | None) -> str:
    value = str(user_agent or '').lower()
    if not value:
        return 'Unknown'
    if 'ipad' in value or 'tablet' in value:
        return 'Tablet'
    if 'android' in value or 'iphone' in value or 'mobile' in value:
        return 'Mobile'
    if 'macintosh' in value or 'windows' in value or 'linux' in value or 'x11' in value:
        return 'Desktop'
    return 'Other'


def _hour_label(hour: int) -> str:
    base = hour % 24
    suffix = 'AM' if base < 12 else 'PM'
    display = base % 12 or 12
    return f'{display}:00 {suffix}'


def _date_key(value: datetime) -> str:
    return value.strftime('%Y-%m-%d')


def _within_range(value: datetime, start: datetime) -> bool:
    return value >= start


def analytics_overview(db: Session, *, range_days: int) -> AnalyticsOverviewOut:
    now = now_utc()
    range_start = now - timedelta(days=range_days - 1)
    day_start = datetime(now.year, now.month, now.day)
    users = db.execute(select(User)).scalars().all()
    attempts = db.execute(select(UserPracticeAttempt)).scalars().all()
    test_attempts = db.execute(select(UserTestAttempt)).scalars().all()
    bookmarks = db.execute(select(UserQuestionBookmark)).scalars().all()
    refresh_tokens = db.execute(select(UserRefreshToken)).scalars().all()
    subjects = {row.id: row.name for row in db.execute(select(AdminSubject)).scalars().all()}
    tests = {row.id: row for row in db.execute(select(AdminTestSeries)).scalars().all()}
    subscriptions = db.execute(select(UserSubscription)).scalars().all()
    online_user_ids = {
        row.user_id for row in refresh_tokens
        if row.revoked_at is None and row.expires_at >= now and row.created_at >= now - timedelta(hours=2)
    }

    daily_active_ids = set()
    for row in attempts:
        if row.attempted_at >= day_start:
            daily_active_ids.add(row.user_id)
    for row in bookmarks:
        if row.created_at >= day_start:
            daily_active_ids.add(row.user_id)
    for row in test_attempts:
        if row.created_at >= day_start:
            daily_active_ids.add(row.user_id)
    for row in refresh_tokens:
        if row.created_at >= day_start:
            daily_active_ids.add(row.user_id)

    session_lengths: list[float] = []
    for row in refresh_tokens:
        if row.created_at < range_start:
            continue
        end_at = row.revoked_at or min(row.expires_at, now)
        minutes = max((end_at - row.created_at).total_seconds() / 60, 0)
        session_lengths.append(min(minutes, 180))
    avg_session_length = round(sum(session_lengths) / len(session_lengths), 1) if session_lengths else 0.0

    cohort_start = now - timedelta(days=60)
    cohort_end = now - timedelta(days=30)
    retained_candidates = [user for user in users if cohort_start <= user.created_at < cohort_end]
    retained_ids: set[int] = set()
    for row in attempts:
        if row.user_id and row.attempted_at >= now - timedelta(days=30):
            retained_ids.add(row.user_id)
    for row in test_attempts:
        if row.user_id and row.created_at >= now - timedelta(days=30):
            retained_ids.add(row.user_id)
    for row in bookmarks:
        if row.user_id and row.created_at >= now - timedelta(days=30):
            retained_ids.add(row.user_id)
    for row in refresh_tokens:
        if row.user_id and row.created_at >= now - timedelta(days=30):
            retained_ids.add(row.user_id)
    retained_count = sum(1 for user in retained_candidates if user.id in retained_ids)
    retention_pct = round((retained_count / len(retained_candidates)) * 100, 1) if retained_candidates else 0.0

    growth_signup_counter: Counter[str] = Counter()
    growth_active_counter: defaultdict[str, set[int]] = defaultdict(set)
    cursor = datetime(range_start.year, range_start.month, range_start.day)
    while cursor <= now:
        growth_signup_counter.setdefault(_date_key(cursor), 0)
        cursor += timedelta(days=1)

    for user in users:
        if _within_range(user.created_at, range_start):
            growth_signup_counter[_date_key(user.created_at)] += 1
    for row in attempts:
        if _within_range(row.attempted_at, range_start):
            growth_active_counter[_date_key(row.attempted_at)].add(row.user_id)
    for row in test_attempts:
        if _within_range(row.created_at, range_start):
            growth_active_counter[_date_key(row.created_at)].add(row.user_id)
    for row in bookmarks:
        if _within_range(row.created_at, range_start):
            growth_active_counter[_date_key(row.created_at)].add(row.user_id)
    for row in refresh_tokens:
        if _within_range(row.created_at, range_start):
            growth_active_counter[_date_key(row.created_at)].add(row.user_id)

    user_growth: list[AnalyticsGrowthPointOut] = []
    cursor = datetime(range_start.year, range_start.month, range_start.day)
    while cursor <= now:
        key = _date_key(cursor)
        user_growth.append(
            AnalyticsGrowthPointOut(
                label=cursor.strftime('%d %b'),
                signups=int(growth_signup_counter.get(key, 0)),
                active_users=len(growth_active_counter.get(key, set())),
            )
        )
        cursor += timedelta(days=1)

    total_users = len(users)
    email_verified = sum(1 for user in users if user.is_email_verified)
    phone_verified = sum(1 for user in users if user.is_phone_verified)
    attempted_user_ids = {row.user_id for row in attempts}
    attempted_user_ids.update(row.user_id for row in test_attempts)
    active_subscription_user_ids = {
        row.user_id
        for row in subscriptions
        if row.status in {'active', 'trialing'} and (row.ends_at is None or row.ends_at >= now)
    }
    conversion_funnel = [
        AnalyticsFunnelStepOut(label='Accounts Created', count=total_users, percentage=100.0 if total_users else 0.0),
        AnalyticsFunnelStepOut(label='Email Verified', count=email_verified, percentage=round((email_verified / total_users) * 100, 1) if total_users else 0.0),
        AnalyticsFunnelStepOut(label='Phone Verified', count=phone_verified, percentage=round((phone_verified / total_users) * 100, 1) if total_users else 0.0),
        AnalyticsFunnelStepOut(label='Attempted Practice', count=len(attempted_user_ids), percentage=round((len(attempted_user_ids) / total_users) * 100, 1) if total_users else 0.0),
        AnalyticsFunnelStepOut(label='Subscribed', count=len(active_subscription_user_ids), percentage=round((len(active_subscription_user_ids) / total_users) * 100, 1) if total_users else 0.0),
    ]

    subject_counter: Counter[int] = Counter()
    for row in attempts:
        if _within_range(row.attempted_at, range_start):
            subject_counter[row.subject_id] += 1
    for row in test_attempts:
        if not _within_range(row.created_at, range_start):
            continue
        test = tests.get(row.test_id)
        subject_id = test.subject_id if test else None
        if subject_id:
            subject_counter[subject_id] += 1
    top_subjects = [
        AnalyticsSubjectAttemptOut(
            subject_name=subjects.get(subject_id, f'Subject {subject_id}'),
            attempts=count,
        )
        for subject_id, count in subject_counter.most_common(8)
    ]

    device_counter: Counter[str] = Counter()
    for row in refresh_tokens:
        if _within_range(row.created_at, range_start):
            device_counter[_device_type(row.user_agent)] += 1
    total_devices = sum(device_counter.values())
    device_breakdown = [
        AnalyticsDeviceBreakdownOut(
            device_type=device_type,
            count=count,
            percentage=round((count / total_devices) * 100, 1) if total_devices else 0.0,
        )
        for device_type, count in device_counter.most_common()
    ]

    hour_counter: Counter[int] = Counter()
    for row in attempts:
        if _within_range(row.attempted_at, range_start):
            hour_counter[row.attempted_at.hour] += 1
    for row in test_attempts:
        if _within_range(row.created_at, range_start):
            hour_counter[row.created_at.hour] += 1
    for row in refresh_tokens:
        if _within_range(row.created_at, range_start):
            hour_counter[row.created_at.hour] += 1
    for row in bookmarks:
        if _within_range(row.created_at, range_start):
            hour_counter[row.created_at.hour] += 1
    top_hour, top_hour_count = hour_counter.most_common(1)[0] if hour_counter else (0, 0)

    state_counter: Counter[str] = Counter()
    for user in users:
        if user.state:
            state_counter[user.state.strip()] += 1
    top_states = [
        AnalyticsStateOut(state_name=state_name, users=count)
        for state_name, count in state_counter.most_common(8)
    ]

    heatmap_counter: Counter[str] = Counter()
    heatmap_start = day_start - timedelta(days=104)
    for row in attempts:
        if row.attempted_at >= heatmap_start:
            heatmap_counter[_date_key(row.attempted_at)] += 1
    for row in test_attempts:
        if row.created_at >= heatmap_start:
            heatmap_counter[_date_key(row.created_at)] += 1
    for row in bookmarks:
        if row.created_at >= heatmap_start:
            heatmap_counter[_date_key(row.created_at)] += 1
    for row in refresh_tokens:
        if row.created_at >= heatmap_start:
            heatmap_counter[_date_key(row.created_at)] += 1
    max_heat = max(heatmap_counter.values(), default=0)
    heatmap: list[AnalyticsHeatmapCellOut] = []
    cursor = heatmap_start
    while cursor <= day_start:
        key = _date_key(cursor)
        count = int(heatmap_counter.get(key, 0))
        if max_heat <= 0:
            intensity = 0
        else:
            intensity = min(4, int((count / max_heat) * 4 + 0.9999))
        heatmap.append(AnalyticsHeatmapCellOut(date=key, count=count, intensity=intensity))
        cursor += timedelta(days=1)

    avg_session_meta = 'Based on active refresh sessions'
    retention_meta = 'Users created 30-60 days ago who returned in last 30 days'

    return AnalyticsOverviewOut(
        generated_at=now,
        range_days=range_days,
        online_right_now=AnalyticsStatOut(value=len(online_user_ids), label='Online Right Now', change_text='Active refresh sessions'),
        daily_active_users=AnalyticsStatOut(value=len(daily_active_ids), label='Daily Active (DAU)', change_text='Attempts, bookmarks, and logins today'),
        avg_session_length_minutes=AnalyticsStatOut(value=avg_session_length, label='Avg Session Length', change_text=avg_session_meta),
        retention_30d=AnalyticsStatOut(value=retention_pct, label='30-day Retention', change_text=retention_meta),
        user_growth=user_growth,
        conversion_funnel=conversion_funnel,
        top_subjects_attempted=top_subjects,
        device_breakdown=device_breakdown,
        most_active_time_label=_hour_label(top_hour),
        most_active_time_meta=f'{top_hour_count} tracked actions in peak hour',
        top_states=top_states,
        activity_heatmap=heatmap,
    )


def export_analytics_csv(db: Session, *, range_days: int) -> bytes:
    overview = analytics_overview(db, range_days=range_days)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['metric', 'value', 'meta'])
    writer.writerow(['online_right_now', overview.online_right_now.value, overview.online_right_now.change_text])
    writer.writerow(['daily_active_users', overview.daily_active_users.value, overview.daily_active_users.change_text])
    writer.writerow(['avg_session_length_minutes', overview.avg_session_length_minutes.value, overview.avg_session_length_minutes.change_text])
    writer.writerow(['retention_30d', overview.retention_30d.value, overview.retention_30d.change_text])
    writer.writerow([])
    writer.writerow(['growth_label', 'signups', 'active_users'])
    for row in overview.user_growth:
        writer.writerow([row.label, row.signups, row.active_users])
    writer.writerow([])
    writer.writerow(['funnel_label', 'count', 'percentage'])
    for row in overview.conversion_funnel:
        writer.writerow([row.label, row.count, row.percentage])
    writer.writerow([])
    writer.writerow(['subject_name', 'attempts'])
    for row in overview.top_subjects_attempted:
        writer.writerow([row.subject_name, row.attempts])
    writer.writerow([])
    writer.writerow(['device_type', 'count', 'percentage'])
    for row in overview.device_breakdown:
        writer.writerow([row.device_type, row.count, row.percentage])
    writer.writerow([])
    writer.writerow(['state_name', 'users'])
    for row in overview.top_states:
        writer.writerow([row.state_name, row.users])
    return buffer.getvalue().encode('utf-8')
