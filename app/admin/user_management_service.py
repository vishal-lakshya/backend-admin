import csv
import io
from datetime import datetime, timedelta

from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError
from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.admin.models import AdminExam, AdminSubject
from app.admin.question_storage import load_question_payload
from app.admin.schemas import (
    AdminManagedUserAnalyticsOut,
    AdminManagedUserAttemptOut,
    AdminManagedUserBookmarkOut,
    AdminManagedUserCreateRequest,
    AdminManagedUserDetailOut,
    AdminManagedUserListOut,
    AdminManagedUserOut,
    AdminManagedUserPerformanceOut,
    AdminManagedUserUpdateRequest,
)
from app.admin.user_models import User, UserPracticeAttempt, UserQuestionBookmark, UserRefreshToken
from app.admin.security import hash_password, now_utc


def _safe_question_payload(question_id: str) -> dict:
    try:
        return load_question_payload(question_id) or {}
    except (NoCredentialsError, PartialCredentialsError, ClientError):
        return {}


def _full_name(user: User) -> str:
    name = ' '.join(part for part in [user.first_name, user.last_name] if part)
    return name.strip() or user.username


def _last_active_at(
    user: User,
    *,
    attempts: list[UserPracticeAttempt],
    bookmarks: list[UserQuestionBookmark],
    refresh_tokens: list[UserRefreshToken],
) -> datetime | None:
    values = [user.updated_at, user.created_at]
    values.extend(item.attempted_at for item in attempts)
    values.extend(item.created_at for item in bookmarks)
    values.extend(item.created_at for item in refresh_tokens)
    return max((value for value in values if value), default=None)


def _performance_from_attempts(
    user: User,
    *,
    attempts: list[UserPracticeAttempt],
    bookmarks: list[UserQuestionBookmark],
    refresh_tokens: list[UserRefreshToken],
) -> AdminManagedUserPerformanceOut:
    total_attempts = len(attempts)
    correct_attempts = sum(1 for attempt in attempts if attempt.is_correct)
    accuracy = round((correct_attempts / total_attempts) * 100, 2) if total_attempts else 0.0
    unique_questions_attempted = len({attempt.question_id for attempt in attempts})
    return AdminManagedUserPerformanceOut(
        total_attempts=total_attempts,
        correct_attempts=correct_attempts,
        accuracy=accuracy,
        unique_questions_attempted=unique_questions_attempted,
        bookmarks=len(bookmarks),
        tests_attempted=0,
        last_active_at=_last_active_at(user, attempts=attempts, bookmarks=bookmarks, refresh_tokens=refresh_tokens),
    )


def _serialize_user_summary(
    user: User,
    *,
    attempts: list[UserPracticeAttempt],
    bookmarks: list[UserQuestionBookmark],
    refresh_tokens: list[UserRefreshToken],
) -> AdminManagedUserOut:
    perf = _performance_from_attempts(user, attempts=attempts, bookmarks=bookmarks, refresh_tokens=refresh_tokens)
    return AdminManagedUserOut(
        id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=_full_name(user),
        email=user.email,
        phone=user.phone,
        state=user.state,
        target_exam_year=user.target_exam_year,
        is_active=user.is_active,
        is_blocked=user.is_blocked,
        is_email_verified=user.is_email_verified,
        is_phone_verified=user.is_phone_verified,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_active_at=perf.last_active_at,
        practice_attempt_count=perf.total_attempts,
        bookmark_count=perf.bookmarks,
        accuracy=perf.accuracy,
    )


def _duplicate_user(db: Session, *, payload: AdminManagedUserCreateRequest, exclude_user_id: int | None = None) -> User | None:
    conditions = [User.username == payload.username, User.email == str(payload.email).lower()]
    if payload.phone:
        conditions.append(User.phone == payload.phone)
    stmt = select(User).where(or_(*conditions))
    rows = db.execute(stmt).scalars().all()
    for row in rows:
        if exclude_user_id is None or row.id != exclude_user_id:
            return row
    return None


def user_analytics(db: Session) -> AdminManagedUserAnalyticsOut:
    users = db.execute(select(User).order_by(User.created_at.desc())).scalars().all()
    now = now_utc()
    recent_cutoff = now - timedelta(days=30)
    today_start = datetime(now.year, now.month, now.day)

    active_last_30_days = 0
    new_today = 0
    blocked_users = 0
    refresh_rows = db.execute(select(UserRefreshToken)).scalars().all()
    refresh_map: dict[int, list[UserRefreshToken]] = {}
    for row in refresh_rows:
        refresh_map.setdefault(row.user_id, []).append(row)

    attempts = db.execute(select(UserPracticeAttempt)).scalars().all()
    attempt_map: dict[int, list[UserPracticeAttempt]] = {}
    for row in attempts:
        attempt_map.setdefault(row.user_id, []).append(row)

    bookmarks = db.execute(select(UserQuestionBookmark)).scalars().all()
    bookmark_map: dict[int, list[UserQuestionBookmark]] = {}
    for row in bookmarks:
        bookmark_map.setdefault(row.user_id, []).append(row)

    for user in users:
        if user.created_at >= today_start:
            new_today += 1
        if user.is_blocked:
            blocked_users += 1
        last_active = _last_active_at(
            user,
            attempts=attempt_map.get(user.id, []),
            bookmarks=bookmark_map.get(user.id, []),
            refresh_tokens=refresh_map.get(user.id, []),
        )
        if last_active and last_active >= recent_cutoff:
            active_last_30_days += 1

    return AdminManagedUserAnalyticsOut(
        total_users=len(users),
        active_last_30_days=active_last_30_days,
        new_today=new_today,
        blocked_users=blocked_users,
    )


def list_users(
    db: Session,
    *,
    search: str | None,
    status_filter: str | None,
    skip: int,
    limit: int,
) -> AdminManagedUserListOut:
    stmt = select(User)
    if search:
        pattern = f'%{search.strip()}%'
        stmt = stmt.where(
            or_(
                User.username.ilike(pattern),
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
                User.email.ilike(pattern),
                User.phone.ilike(pattern),
            )
        )
    rows = db.execute(stmt.order_by(User.created_at.desc(), User.id.desc())).scalars().all()

    attempts = db.execute(select(UserPracticeAttempt)).scalars().all()
    attempt_map: dict[int, list[UserPracticeAttempt]] = {}
    for row in attempts:
        attempt_map.setdefault(row.user_id, []).append(row)

    bookmarks = db.execute(select(UserQuestionBookmark)).scalars().all()
    bookmark_map: dict[int, list[UserQuestionBookmark]] = {}
    for row in bookmarks:
        bookmark_map.setdefault(row.user_id, []).append(row)

    refresh_rows = db.execute(select(UserRefreshToken)).scalars().all()
    refresh_map: dict[int, list[UserRefreshToken]] = {}
    for row in refresh_rows:
        refresh_map.setdefault(row.user_id, []).append(row)

    items: list[AdminManagedUserOut] = []
    for user in rows:
        summary = _serialize_user_summary(
            user,
            attempts=attempt_map.get(user.id, []),
            bookmarks=bookmark_map.get(user.id, []),
            refresh_tokens=refresh_map.get(user.id, []),
        )
        if status_filter == 'active' and (not summary.is_active or summary.is_blocked):
            continue
        if status_filter == 'blocked' and not summary.is_blocked:
            continue
        if status_filter == 'inactive' and summary.is_active:
            continue
        items.append(summary)

    total = len(items)
    return AdminManagedUserListOut(items=items[skip: skip + limit], total=total, skip=skip, limit=limit)


def create_user(db: Session, *, payload: AdminManagedUserCreateRequest) -> AdminManagedUserOut:
    duplicate = _duplicate_user(db, payload=payload)
    if duplicate:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='User already exists.')

    user = User(
        username=payload.username,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=str(payload.email).lower(),
        phone=payload.phone,
        state=payload.state,
        target_exam_year=payload.target_exam_year,
        hashed_password=hash_password(payload.password),
        is_active=payload.is_active,
        is_blocked=payload.is_blocked,
        is_email_verified=payload.is_email_verified,
        is_phone_verified=payload.is_phone_verified,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _serialize_user_summary(user, attempts=[], bookmarks=[], refresh_tokens=[])


def update_user(db: Session, *, user_id: int, payload: AdminManagedUserUpdateRequest) -> AdminManagedUserOut:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found.')

    candidate = AdminManagedUserCreateRequest(
        username=payload.username or user.username,
        first_name=payload.first_name if payload.first_name is not None else user.first_name,
        last_name=payload.last_name if payload.last_name is not None else user.last_name,
        email=payload.email or user.email,
        phone=payload.phone if payload.phone is not None else user.phone,
        password=payload.password or 'placeholder-password',
        state=payload.state if payload.state is not None else user.state,
        target_exam_year=payload.target_exam_year if payload.target_exam_year is not None else user.target_exam_year,
        is_active=payload.is_active if payload.is_active is not None else user.is_active,
        is_blocked=payload.is_blocked if payload.is_blocked is not None else user.is_blocked,
        is_email_verified=payload.is_email_verified if payload.is_email_verified is not None else user.is_email_verified,
        is_phone_verified=payload.is_phone_verified if payload.is_phone_verified is not None else user.is_phone_verified,
    )
    duplicate = _duplicate_user(db, payload=candidate, exclude_user_id=user.id)
    if duplicate:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Another user already uses this username, email, or phone.')

    if payload.username is not None:
        user.username = payload.username
    if payload.first_name is not None:
        user.first_name = payload.first_name
    if payload.last_name is not None:
        user.last_name = payload.last_name
    if payload.email is not None:
        user.email = str(payload.email).lower()
    if payload.phone is not None:
        user.phone = payload.phone
    if payload.state is not None:
        user.state = payload.state
    if payload.target_exam_year is not None:
        user.target_exam_year = payload.target_exam_year
    if payload.password:
        user.hashed_password = hash_password(payload.password)
        user.token_version += 1
        for token in db.execute(
            select(UserRefreshToken).where(UserRefreshToken.user_id == user.id, UserRefreshToken.revoked_at.is_(None))
        ).scalars().all():
            token.revoked_at = now_utc()
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.is_blocked is not None:
        user.is_blocked = payload.is_blocked
    if payload.is_email_verified is not None:
        user.is_email_verified = payload.is_email_verified
    if payload.is_phone_verified is not None:
        user.is_phone_verified = payload.is_phone_verified

    db.commit()
    db.refresh(user)
    attempts = db.execute(select(UserPracticeAttempt).where(UserPracticeAttempt.user_id == user.id)).scalars().all()
    bookmarks = db.execute(select(UserQuestionBookmark).where(UserQuestionBookmark.user_id == user.id)).scalars().all()
    refresh_tokens = db.execute(select(UserRefreshToken).where(UserRefreshToken.user_id == user.id)).scalars().all()
    return _serialize_user_summary(user, attempts=attempts, bookmarks=bookmarks, refresh_tokens=refresh_tokens)


def delete_user(db: Session, *, user_id: int) -> None:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found.')
    db.delete(user)
    db.commit()


def get_user_detail(db: Session, *, user_id: int) -> AdminManagedUserDetailOut:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found.')

    attempts = db.execute(
        select(UserPracticeAttempt)
        .where(UserPracticeAttempt.user_id == user.id)
        .order_by(UserPracticeAttempt.attempted_at.desc(), UserPracticeAttempt.id.desc())
    ).scalars().all()
    bookmarks = db.execute(
        select(UserQuestionBookmark)
        .where(UserQuestionBookmark.user_id == user.id)
        .order_by(UserQuestionBookmark.created_at.desc(), UserQuestionBookmark.id.desc())
    ).scalars().all()
    refresh_tokens = db.execute(select(UserRefreshToken).where(UserRefreshToken.user_id == user.id)).scalars().all()

    exam_map = {item.id: item for item in db.execute(select(AdminExam)).scalars().all()}
    subject_map = {item.id: item for item in db.execute(select(AdminSubject)).scalars().all()}

    attempt_items: list[AdminManagedUserAttemptOut] = []
    for item in attempts[:200]:
        question = _safe_question_payload(item.question_id)
        exam = exam_map.get(item.exam_id)
        subject = subject_map.get(item.subject_id)
        attempt_items.append(
            AdminManagedUserAttemptOut(
                question_id=item.question_id,
                exam_id=item.exam_id,
                exam_name=exam.name if exam else '-',
                subject_id=item.subject_id,
                subject_name=subject.name if subject else '-',
                question_text=str(question.get('question_text') or f'Question {item.question_id}'),
                selected_option=item.selected_option,
                correct_option=item.correct_option,
                is_correct=item.is_correct,
                attempted_at=item.attempted_at,
            )
        )

    bookmark_items: list[AdminManagedUserBookmarkOut] = []
    for item in bookmarks[:200]:
        question = _safe_question_payload(item.question_id)
        exam_id = question.get('exam_id')
        subject_id = question.get('subject_id')
        exam = exam_map.get(int(exam_id)) if exam_id else None
        subject = subject_map.get(int(subject_id)) if subject_id else None
        bookmark_items.append(
            AdminManagedUserBookmarkOut(
                question_id=item.question_id,
                exam_id=int(exam_id) if exam_id else None,
                exam_name=exam.name if exam else '-',
                subject_id=int(subject_id) if subject_id else None,
                subject_name=subject.name if subject else '-',
                question_text=str(question.get('question_text') or f'Question {item.question_id}'),
                created_at=item.created_at,
            )
        )

    perf = _performance_from_attempts(user, attempts=attempts, bookmarks=bookmarks, refresh_tokens=refresh_tokens)
    summary = _serialize_user_summary(user, attempts=attempts, bookmarks=bookmarks, refresh_tokens=refresh_tokens)
    return AdminManagedUserDetailOut(
        user=summary,
        performance=perf,
        attempts=attempt_items,
        bookmarks=bookmark_items,
        tests=[],
    )


def export_user_performance_csv(db: Session, *, user_id: int) -> tuple[str, str]:
    detail = get_user_detail(db, user_id=user_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['user_id', detail.user.id])
    writer.writerow(['username', detail.user.username])
    writer.writerow(['email', detail.user.email])
    writer.writerow([])
    writer.writerow(['total_attempts', detail.performance.total_attempts])
    writer.writerow(['correct_attempts', detail.performance.correct_attempts])
    writer.writerow(['accuracy', detail.performance.accuracy])
    writer.writerow(['bookmarks', detail.performance.bookmarks])
    writer.writerow([])
    writer.writerow(['question_id', 'exam', 'subject', 'selected_option', 'correct_option', 'is_correct', 'attempted_at', 'question_text'])
    for item in detail.attempts:
        writer.writerow([
            item.question_id,
            item.exam_name,
            item.subject_name,
            item.selected_option,
            item.correct_option,
            'yes' if item.is_correct else 'no',
            item.attempted_at.isoformat(),
            item.question_text,
        ])
    filename = f'user-{detail.user.id}-performance.csv'
    return filename, buffer.getvalue()
