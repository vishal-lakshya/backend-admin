import json
from datetime import datetime

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.admin.models import AdminExam, AdminSubject, AdminTestSeries, AdminUser
from app.admin.schemas import SubjectOut, TestQuestionUploadIn, TestSeriesAnalyticsOut, TestSeriesBootstrapOut, TestSeriesCreateOut, TestSeriesListOut, TestSeriesOut
from app.admin.test_storage import save_test_question_payloads
from app.admin.user_models import UserTestAttempt


TEST_TYPE_OPTIONS = ['Full Length Mock', 'Topic Test', 'CSAT', 'Mains GS']
ACCESS_LEVEL_OPTIONS = ['all_users', 'pro_elite', 'elite_only']
DISPLAY_MODE_OPTIONS = ['live', 'scheduled', 'exam_based', 'subject_based']

def _reconcile_test_statuses(db: Session) -> None:
    return None


def _effective_status(test: AdminTestSeries) -> str:
    if test.status == 'archived':
        return 'archived'
    if test.status == 'draft':
        return 'draft'
    if test.scheduled_at and test.scheduled_at <= datetime.utcnow():
        return 'live'
    return 'scheduled'


def _serialize_test(db: Session, test: AdminTestSeries) -> TestSeriesOut:
    subject = db.get(AdminSubject, test.subject_id) if test.subject_id else None
    return TestSeriesOut(
        id=test.id,
        name=test.name,
        test_type=test.test_type,
        display_mode=(test.display_mode or 'live'),
        subject_id=test.subject_id,
        subject_name=subject.name if subject else 'Mixed',
        question_count=test.question_count,
        duration_minutes=test.duration_minutes,
        scheduled_at=test.scheduled_at,
        access_level=test.access_level,
        positive_marks=float(test.positive_marks),
        negative_marks=float(test.negative_marks),
        status=test.status,
        effective_status=_effective_status(test),
        question_file_key=test.question_file_key,
        created_by_admin_id=test.created_by_admin_id,
        created_at=test.created_at,
        updated_at=test.updated_at,
    )


def test_bootstrap(db: Session) -> TestSeriesBootstrapOut:
    _reconcile_test_statuses(db)
    exams = db.execute(select(AdminExam.id, AdminExam.name)).all()
    exam_name_map = {row[0]: row[1] for row in exams}
    subjects = db.execute(
        select(AdminSubject).where(AdminSubject.is_active.is_(True)).order_by(AdminSubject.name.asc())
    ).scalars().all()
    subject_rows = [
        SubjectOut(
            id=subject.id,
            exam_id=subject.exam_id,
            exam_name=exam_name_map.get(subject.exam_id, '-'),
            name=subject.name,
            code=subject.code,
            description=subject.description,
            is_active=subject.is_active,
            mapped_questions=subject.mapped_questions,
            created_by_admin_id=subject.created_by_admin_id,
            created_at=subject.created_at,
            updated_at=subject.updated_at,
        )
        for subject in subjects
    ]
    return TestSeriesBootstrapOut(
        subjects=subject_rows,
        test_types=TEST_TYPE_OPTIONS,
        access_levels=ACCESS_LEVEL_OPTIONS,
        display_modes=DISPLAY_MODE_OPTIONS,
    )


def list_tests(
    db: Session,
    *,
    search: str | None,
    status_value: str | None,
    skip: int,
    limit: int,
) -> TestSeriesListOut:
    _reconcile_test_statuses(db)
    stmt = select(AdminTestSeries)
    if search:
        pattern = f'%{search.strip()}%'
        stmt = stmt.where(AdminTestSeries.name.ilike(pattern))
    rows = db.execute(stmt.order_by(AdminTestSeries.created_at.desc())).scalars().all()
    if status_value:
        rows = [item for item in rows if _effective_status(item) == status_value]
    total = len(rows)
    window = rows[skip: skip + limit]
    return TestSeriesListOut(
        items=[_serialize_test(db, row) for row in window],
        total=total,
        skip=skip,
        limit=limit,
    )


def test_analytics(db: Session) -> TestSeriesAnalyticsOut:
    _reconcile_test_statuses(db)
    rows = db.execute(select(AdminTestSeries)).scalars().all()
    live_now = sum(1 for item in rows if _effective_status(item) == 'live')
    scheduled = sum(1 for item in rows if _effective_status(item) == 'scheduled')
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    attempts = db.execute(select(UserTestAttempt)).scalars().all()
    attempts_today = sum(1 for item in attempts if item.created_at and item.created_at >= today_start)
    completion_values = [
        (float(item.answered_count or 0) / float(item.total_questions)) * 100.0
        for item in attempts
        if int(item.total_questions or 0) > 0
    ]
    avg_completion = round(sum(completion_values) / len(completion_values), 1) if completion_values else 0.0
    return TestSeriesAnalyticsOut(
        live_now=live_now,
        scheduled=scheduled,
        attempts_today=attempts_today,
        avg_completion=avg_completion,
    )


def create_test(
    db: Session,
    *,
    current_user: AdminUser,
    name: str,
    test_type: str,
    display_mode: str,
    subject_id: int | None,
    question_count: int | None,
    duration_minutes: int,
    scheduled_at: datetime | None,
    access_level: str,
    positive_marks: float,
    negative_marks: float,
    file_name: str,
    file_bytes: bytes,
    save_as_draft: bool,
) -> TestSeriesCreateOut:
    if not name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Test name is required.')
    if test_type not in TEST_TYPE_OPTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid test type.')
    if display_mode not in DISPLAY_MODE_OPTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid display mode.')
    if access_level not in ACCESS_LEVEL_OPTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid access level.')
    if subject_id is not None and not db.get(AdminSubject, subject_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid subject id.')
    if display_mode in {'exam_based', 'subject_based'} and subject_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Subject is required for exam-based and subject-based test series.')
    if display_mode == 'scheduled' and not save_as_draft and scheduled_at is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Schedule date and time are required for scheduled test series.')

    normalized_schedule = scheduled_at.replace(microsecond=0) if scheduled_at else None
    if not save_as_draft and display_mode != 'scheduled' and normalized_schedule is None:
        normalized_schedule = datetime.utcnow().replace(microsecond=0)
    if not file_name.lower().endswith('.json'):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Upload a .json question file.')

    try:
        payload = json.loads(file_bytes.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Question upload expects a UTF-8 JSON file.') from exc

    if isinstance(payload, dict) and isinstance(payload.get('questions'), list):
        items = payload['questions']
    elif isinstance(payload, list):
        items = payload
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Question upload JSON must be an array of questions or an object with a questions array.',
        )
    if not items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Question upload JSON is empty.')

    question_rows: list[dict] = []
    for idx, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'Question row {idx} must be a JSON object.')
        try:
            question = TestQuestionUploadIn.model_validate(raw)
        except ValidationError as exc:
            errors = '; '.join(
                f'{".".join(str(part) for part in err.get("loc", []))}: {err.get("msg", "Invalid value")}'
                for err in exc.errors()
            )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'Question row {idx}: {errors}') from exc

        question_rows.append(
            {
                'id': idx,
                'topic': question.topic,
                'question_text': question.question_text,
                'options': [item.model_dump() for item in question.options],
                'correct_option': question.correct_option,
                'explanation': question.explanation,
                'difficulty': question.difficulty,
                'tags': question.tags,
            }
        )

    uploaded_question_count = len(question_rows)
    if question_count is not None and question_count != uploaded_question_count:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Uploaded question count ({uploaded_question_count}) does not match requested count ({question_count}).',
        )

    test = AdminTestSeries(
        name=name.strip(),
        test_type=test_type,
        display_mode=display_mode,
        subject_id=subject_id,
        question_count=uploaded_question_count,
        duration_minutes=duration_minutes,
        scheduled_at=normalized_schedule,
        access_level=access_level,
        positive_marks=positive_marks,
        negative_marks=negative_marks,
        status='draft' if save_as_draft else 'scheduled',
        question_file_key='',
        created_by_admin_id=current_user.id,
    )
    db.add(test)
    db.commit()
    db.refresh(test)

    storage_key = save_test_question_payloads(test.id, question_rows)
    test.question_file_key = storage_key
    db.commit()
    db.refresh(test)

    return TestSeriesCreateOut(test=_serialize_test(db, test), uploaded_questions=uploaded_question_count)


def get_test(db: Session, test_id: int) -> TestSeriesOut:
    _reconcile_test_statuses(db)
    test = db.get(AdminTestSeries, test_id)
    if not test:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Test not found.')
    return _serialize_test(db, test)


def archive_test(db: Session, test_id: int) -> TestSeriesOut:
    _reconcile_test_statuses(db)
    test = db.get(AdminTestSeries, test_id)
    if not test:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Test not found.')
    test.status = 'archived'
    db.commit()
    db.refresh(test)
    return _serialize_test(db, test)


def move_test(db: Session, test_id: int, *, target_status: str, scheduled_at: datetime | None = None) -> TestSeriesOut:
    _reconcile_test_statuses(db)
    test = db.get(AdminTestSeries, test_id)
    if not test:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Test not found.')

    normalized = target_status.strip().lower()
    allowed = {'live', 'scheduled', 'draft', 'archived'}
    if normalized not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid target status.')

    now = datetime.utcnow().replace(microsecond=0)
    if normalized == 'draft':
        test.status = 'draft'
    elif normalized == 'archived':
        test.status = 'archived'
    elif normalized == 'live':
        test.status = 'scheduled'
        test.scheduled_at = now
    elif normalized == 'scheduled':
        test.status = 'scheduled'
        if scheduled_at is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='scheduled_at is required when moving a test to scheduled.',
            )
        test.scheduled_at = scheduled_at.replace(microsecond=0)

    db.commit()
    db.refresh(test)
    return _serialize_test(db, test)


def delete_test(db: Session, test_id: int) -> None:
    test = db.get(AdminTestSeries, test_id)
    if not test:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Test not found.')
    db.delete(test)
    db.commit()
