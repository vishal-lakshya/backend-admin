from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from botocore.exceptions import ClientError, NoCredentialsError, PartialCredentialsError
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.models import AdminExam, AdminSubject
from app.admin.question_storage import list_question_payloads, load_question_payload
from app.user.models import User, UserPracticeAttempt, UserQuestionBookmark
from app.user.practice_schemas import (
    PracticeAttemptOut,
    PracticeBootstrapOut,
    PracticeExamOption,
    PracticeFilterOption,
    PracticeQuestionListOut,
    PracticeQuestionOptionOut,
    PracticeQuestionOut,
    PracticeSessionStatsOut,
    PracticeSubjectOption,
)


def _load_question_rows() -> list[dict]:
    try:
        return list_question_payloads()
    except (NoCredentialsError, PartialCredentialsError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Question storage is not configured. Add AWS credentials to load practice data.',
        ) from exc
    except ClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail='Question storage request failed. Check S3 bucket access and configuration.',
        ) from exc


def _load_question_row(question_id: str) -> dict:
    try:
        payload = load_question_payload(question_id)
    except (NoCredentialsError, PartialCredentialsError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Question storage is not configured. Add AWS credentials to load practice data.',
        ) from exc
    except ClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail='Question storage request failed. Check S3 bucket access and configuration.',
        ) from exc
    if not payload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Question not found')
    return payload


def _utc_today_start() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day)


def _active_exams(db: Session) -> list[AdminExam]:
    return db.execute(select(AdminExam).where(AdminExam.is_active.is_(True)).order_by(AdminExam.name.asc())).scalars().all()


def _active_subjects(db: Session, *, exam_id: int | None = None) -> list[AdminSubject]:
    stmt = select(AdminSubject).where(AdminSubject.is_active.is_(True))
    if exam_id is not None:
        stmt = stmt.where(AdminSubject.exam_id == exam_id)
    stmt = stmt.order_by(AdminSubject.name.asc())
    return db.execute(stmt).scalars().all()


def _session_stats(db: Session, *, user_id: int) -> PracticeSessionStatsOut:
    today_start = _utc_today_start()
    attempts = db.execute(
        select(UserPracticeAttempt).where(
            UserPracticeAttempt.user_id == user_id,
            UserPracticeAttempt.attempted_at >= today_start,
        )
    ).scalars().all()
    attempted = len(attempts)
    correct = sum(1 for item in attempts if item.is_correct)
    accuracy = round((correct / attempted) * 100, 2) if attempted else 0.0
    return PracticeSessionStatsOut(attempted=attempted, correct=correct, accuracy=accuracy)


def _latest_attempt_map(db: Session, *, user_id: int) -> dict[str, UserPracticeAttempt]:
    attempts = db.execute(
        select(UserPracticeAttempt)
        .where(UserPracticeAttempt.user_id == user_id)
        .order_by(UserPracticeAttempt.attempted_at.desc(), UserPracticeAttempt.id.desc())
    ).scalars().all()
    latest: dict[str, UserPracticeAttempt] = {}
    for attempt in attempts:
        if attempt.question_id not in latest:
            latest[attempt.question_id] = attempt
    return latest


def _bookmark_set(db: Session, *, user_id: int) -> set[str]:
    rows = db.execute(select(UserQuestionBookmark.question_id).where(UserQuestionBookmark.user_id == user_id)).all()
    return {row[0] for row in rows}


def _question_matches(
    payload: dict,
    *,
    exam_id: int | None,
    subject_ids: set[int] | None,
    difficulties: set[str] | None,
    question_types: set[str] | None,
    pyq_year: int | None,
    bookmarked_only: bool,
    bookmarks: set[str],
) -> bool:
    if str(payload.get('status', '')).lower() != 'published':
        return False
    if exam_id is not None and int(payload.get('exam_id', 0)) != exam_id:
        return False
    if subject_ids and int(payload.get('subject_id', 0)) not in subject_ids:
        return False
    if difficulties and str(payload.get('difficulty', '')).lower() not in difficulties:
        return False
    current_type = 'mcq'
    if question_types and current_type not in question_types:
        return False
    if pyq_year is not None and int(payload.get('pyq_year') or 0) != pyq_year:
        return False
    if bookmarked_only and str(payload.get('id')) not in bookmarks:
        return False
    return True


def _enrich_question(
    payload: dict,
    *,
    exam_map: dict[int, AdminExam],
    subject_map: dict[int, AdminSubject],
    bookmarks: set[str],
    attempts: dict[str, UserPracticeAttempt],
) -> PracticeQuestionOut:
    qid = str(payload['id'])
    attempt = attempts.get(qid)
    exam = exam_map.get(int(payload['exam_id']))
    subject = subject_map.get(int(payload['subject_id']))
    return PracticeQuestionOut(
        id=qid,
        exam_id=int(payload['exam_id']),
        exam_name=exam.name if exam else '-',
        subject_id=int(payload['subject_id']),
        subject_name=subject.name if subject else '-',
        topic=payload.get('topic'),
        question_text=payload['question_text'],
        options=[PracticeQuestionOptionOut(**item) for item in payload.get('options', [])],
        correct_option=str(payload.get('correct_option', '')).upper(),
        explanation=payload.get('explanation', ''),
        difficulty=str(payload.get('difficulty', 'medium')).title(),
        question_type='MCQ',
        pyq_year=payload.get('pyq_year'),
        tags=payload.get('tags', []),
        is_bookmarked=qid in bookmarks,
        selected_option=attempt.selected_option if attempt else None,
        is_attempted=attempt is not None,
        is_correct=attempt.is_correct if attempt else None,
    )


def practice_bootstrap(db: Session, *, user: User, exam_id: int | None = None) -> PracticeBootstrapOut:
    exams = _active_exams(db)
    subjects = _active_subjects(db, exam_id=exam_id)
    payloads = _load_question_rows()
    active_exam_ids = {exam.id for exam in exams}
    active_subject_ids = {subject.id for subject in subjects}

    subject_counter: Counter[int] = Counter()
    difficulty_counter: Counter[str] = Counter()
    pyq_years: set[int] = set()
    for payload in payloads:
        if str(payload.get('status', '')).lower() != 'published':
            continue
        payload_exam_id = int(payload.get('exam_id', 0))
        payload_subject_id = int(payload.get('subject_id', 0))
        if payload_exam_id not in active_exam_ids:
            continue
        if exam_id is not None and payload_exam_id != exam_id:
            continue
        if payload_subject_id in active_subject_ids:
            subject_counter[payload_subject_id] += 1
        difficulty_counter[str(payload.get('difficulty', 'medium')).lower()] += 1
        if payload.get('pyq_year'):
            pyq_years.add(int(payload['pyq_year']))

    return PracticeBootstrapOut(
        exams=[PracticeExamOption(id=exam.id, name=exam.name, code=exam.code) for exam in exams],
        subjects=[
            PracticeSubjectOption(id=subject.id, exam_id=subject.exam_id, name=subject.name, code=subject.code)
            for subject in subjects
            if subject_counter.get(subject.id, 0) > 0
        ],
        difficulty_options=[
            PracticeFilterOption(value=name, label=name.title(), count=difficulty_counter.get(name, 0))
            for name in ['easy', 'medium', 'hard']
            if difficulty_counter.get(name, 0) > 0
        ],
        question_type_options=[PracticeFilterOption(value='mcq', label='MCQ', count=sum(difficulty_counter.values()))],
        pyq_years=sorted(pyq_years, reverse=True),
        stats=_session_stats(db, user_id=user.id),
    )


def list_practice_questions(
    db: Session,
    *,
    user: User,
    exam_id: int | None,
    subject_ids: list[int] | None,
    difficulties: list[str] | None,
    question_types: list[str] | None,
    pyq_year: int | None,
    skip: int,
    limit: int,
    bookmarked_only: bool = False,
    shuffle: bool = False,
) -> PracticeQuestionListOut:
    bookmarks = _bookmark_set(db, user_id=user.id)
    attempts = _latest_attempt_map(db, user_id=user.id)
    exams = _active_exams(db)
    subjects = _active_subjects(db, exam_id=exam_id)
    exam_map = {exam.id: exam for exam in exams}
    subject_map = {subject.id: subject for subject in subjects}

    normalized_difficulties = {value.strip().lower() for value in (difficulties or []) if value.strip()}
    normalized_types = {value.strip().lower() for value in (question_types or []) if value.strip()}
    subject_id_set = set(subject_ids or [])

    rows = [
        payload for payload in _load_question_rows()
        if _question_matches(
            payload,
            exam_id=exam_id,
            subject_ids=subject_id_set or None,
            difficulties=normalized_difficulties or None,
            question_types=normalized_types or None,
            pyq_year=pyq_year,
            bookmarked_only=bookmarked_only,
            bookmarks=bookmarks,
        )
    ]
    rows.sort(key=lambda item: str(item.get('created_at', '')), reverse=not shuffle)
    if shuffle:
        rows.sort(key=lambda item: str(item.get('id', '')))

    total = len(rows)
    window = rows[skip: skip + limit]
    items = [
        _enrich_question(
            payload,
            exam_map=exam_map,
            subject_map=subject_map,
            bookmarks=bookmarks,
            attempts=attempts,
        )
        for payload in window
    ]
    return PracticeQuestionListOut(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
        stats=_session_stats(db, user_id=user.id),
    )


def submit_practice_attempt(db: Session, *, user: User, question_id: str, selected_option: str) -> PracticeAttemptOut:
    payload = _load_question_row(question_id)
    if str(payload.get('status', '')).lower() != 'published':
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Question not found')

    correct_option = str(payload.get('correct_option', '')).upper()
    attempt = UserPracticeAttempt(
        user_id=user.id,
        question_id=question_id,
        exam_id=int(payload.get('exam_id', 0)),
        subject_id=int(payload.get('subject_id', 0)),
        selected_option=selected_option,
        correct_option=correct_option,
        is_correct=selected_option == correct_option,
    )
    db.add(attempt)
    db.commit()
    return PracticeAttemptOut(
        question_id=question_id,
        selected_option=selected_option,
        correct_option=correct_option,
        is_correct=selected_option == correct_option,
        explanation=payload.get('explanation', ''),
        stats=_session_stats(db, user_id=user.id),
    )


def toggle_question_bookmark(db: Session, *, user: User, question_id: str) -> bool:
    payload = _load_question_row(question_id)

    row = db.execute(
        select(UserQuestionBookmark).where(
            UserQuestionBookmark.user_id == user.id,
            UserQuestionBookmark.question_id == question_id,
        )
    ).scalars().first()
    if row:
        db.delete(row)
        db.commit()
        return False

    db.add(UserQuestionBookmark(user_id=user.id, question_id=question_id))
    db.commit()
    return True
