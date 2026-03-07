import json
from collections import defaultdict
from datetime import datetime
from uuid import uuid4

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.models import AdminExam, AdminSubject
from app.admin.question_storage import (
    add_manual_question_payload,
    delete_question_payload,
    list_question_payloads,
    load_question_payload,
    save_bulk_question_payloads,
    update_question_payload,
)
from app.admin.schemas import (
    ExamOut,
    QuestionBootstrapOut,
    QuestionAnalyticsOut,
    QuestionBulkUploadOut,
    QuestionCreateRequest,
    QuestionListOut,
    QuestionOut,
    QuestionSubjectAnalyticsOut,
    QuestionSubjectAnalyticsRow,
    QuestionUpdateRequest,
    SubjectOut,
)
from app.admin.security import now_utc


def _iso_now() -> str:
    return now_utc().replace(microsecond=0).isoformat()


def _difficulty_score(value: str) -> int:
    return {'easy': 1, 'medium': 2, 'hard': 3}.get(str(value).lower(), 2)


def _score_to_difficulty(score: float) -> str:
    if score < 1.67:
        return 'Easy'
    if score < 2.34:
        return 'Medium'
    return 'Hard'


def _to_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _ensure_exam_and_subject(db: Session, exam_id: int, subject_id: int) -> tuple[AdminExam, AdminSubject]:
    exam = db.get(AdminExam, exam_id)
    if not exam:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid exam id')

    subject = db.get(AdminSubject, subject_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid subject id')
    if subject.exam_id != exam_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Subject does not belong to selected exam',
        )
    return exam, subject


def _normalize_reference_id(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    return None


def _resolve_bulk_exam_and_subject(
    raw: dict,
    *,
    row_number: int,
    exams_by_id: dict[int, AdminExam],
    exams_by_code: dict[str, AdminExam],
    subjects_by_id: dict[int, AdminSubject],
    subjects_by_code: dict[str, AdminSubject],
) -> tuple[AdminExam, AdminSubject]:
    raw_exam_ref = raw.get('exam_id')
    raw_subject_ref = raw.get('subject_id')
    exam_id = _normalize_reference_id(raw_exam_ref)
    subject_id = _normalize_reference_id(raw_subject_ref)
    exam_code = str(raw.get('exam_code') or '').strip().upper()
    subject_code = str(raw.get('subject_code') or '').strip().upper()

    exam = exams_by_id.get(exam_id) if exam_id is not None else None
    if exam is None and raw_exam_ref is not None and not exam_code:
        exam_code = str(raw_exam_ref).strip().upper()
    if exam is None and exam_code:
        exam = exams_by_code.get(exam_code)

    subject = subjects_by_id.get(subject_id) if subject_id is not None else None
    if subject is None and raw_subject_ref is not None and not subject_code:
        subject_code = str(raw_subject_ref).strip().upper()
    if subject is None and subject_code:
        subject = subjects_by_code.get(subject_code)

    if not exam:
        valid_exam_ids = ', '.join(str(key) for key in sorted(exams_by_id)[:20]) or 'none'
        valid_exam_codes = ', '.join(sorted(exams_by_code)[:20]) or 'none'
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f'Row {row_number}: invalid exam reference. '
                f'Provided exam_id={raw.get("exam_id")!r}, exam_code={raw.get("exam_code")!r}. '
                f'Valid exam ids: {valid_exam_ids}. Valid exam codes: {valid_exam_codes}.'
            ),
        )

    if not subject:
        valid_subject_ids = ', '.join(str(key) for key in sorted(subjects_by_id)[:30]) or 'none'
        valid_subject_codes = ', '.join(sorted(subjects_by_code)[:30]) or 'none'
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f'Row {row_number}: invalid subject reference. '
                f'Provided subject_id={raw.get("subject_id")!r}, subject_code={raw.get("subject_code")!r}. '
                f'Valid subject ids: {valid_subject_ids}. Valid subject codes: {valid_subject_codes}.'
            ),
        )

    if subject.exam_id != exam.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f'Row {row_number}: subject {subject.id} ({subject.code}) does not belong to '
                f'exam {exam.id} ({exam.code}).'
            ),
        )

    return exam, subject


def _rebuild_subject_question_counts(db: Session) -> None:
    counts: defaultdict[int, int] = defaultdict(int)
    for row in list_question_payloads():
        subject_id = int(row.get('subject_id') or 0)
        if subject_id > 0:
            counts[subject_id] += 1

    subjects = db.execute(select(AdminSubject)).scalars().all()
    for subject in subjects:
        subject.mapped_questions = counts.get(subject.id, 0)
    db.commit()


def _enrich_payload(db: Session, payload: dict) -> QuestionOut:
    exam = db.get(AdminExam, int(payload['exam_id']))
    subject = db.get(AdminSubject, int(payload['subject_id']))
    exam_name = exam.name if exam else '-'
    subject_name = subject.name if subject else '-'
    return QuestionOut(
        id=str(payload['id']),
        exam_id=int(payload['exam_id']),
        exam_name=exam_name,
        subject_id=int(payload['subject_id']),
        subject_name=subject_name,
        topic=payload.get('topic'),
        question_text=payload['question_text'],
        options=payload['options'],
        correct_option=payload['correct_option'],
        explanation=payload['explanation'],
        difficulty=payload.get('difficulty', 'medium'),
        status=payload.get('status', 'draft'),
        pyq_year=payload.get('pyq_year'),
        tags=payload.get('tags', []),
        accuracy_pct=float(payload.get('accuracy_pct', 0.0)),
        created_at=_to_datetime(payload['created_at']),
        updated_at=_to_datetime(payload['updated_at']),
    )


def add_question(db: Session, payload: QuestionCreateRequest) -> QuestionOut:
    exam, subject = _ensure_exam_and_subject(db, payload.exam_id, payload.subject_id)
    question_id = uuid4().hex
    now_iso = _iso_now()
    row = {
        'id': question_id,
        'exam_id': exam.id,
        'subject_id': subject.id,
        'topic': payload.topic,
        'question_text': payload.question_text,
        'options': [item.model_dump() for item in payload.options],
        'correct_option': payload.correct_option,
        'explanation': payload.explanation,
        'difficulty': payload.difficulty,
        'status': payload.status,
        'pyq_year': payload.pyq_year,
        'tags': payload.tags,
        'accuracy_pct': float(payload.accuracy_pct),
        'created_at': now_iso,
        'updated_at': now_iso,
    }
    add_manual_question_payload(row)
    _rebuild_subject_question_counts(db)
    return _enrich_payload(db, row)


def get_question(db: Session, question_id: str) -> QuestionOut:
    row = load_question_payload(question_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Question not found')
    return _enrich_payload(db, row)


def update_question(db: Session, question_id: str, payload: QuestionUpdateRequest) -> QuestionOut:
    row = load_question_payload(question_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Question not found')

    updates = payload.model_dump(exclude_unset=True)
    next_exam = int(updates.get('exam_id', row['exam_id']))
    next_subject = int(updates.get('subject_id', row['subject_id']))
    _ensure_exam_and_subject(db, next_exam, next_subject)

    for key, value in updates.items():
        if key == 'options' and value is not None:
            row[key] = [item.model_dump() for item in value]
        elif value is not None:
            row[key] = value

    row['updated_at'] = _iso_now()
    update_question_payload(question_id, row)
    _rebuild_subject_question_counts(db)
    return _enrich_payload(db, row)


def remove_question(question_id: str) -> None:
    existing = load_question_payload(question_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Question not found')
    try:
        delete_question_payload(question_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Question not found') from exc


def delete_question(db: Session, question_id: str) -> None:
    remove_question(question_id)
    _rebuild_subject_question_counts(db)


def list_questions(
    db: Session,
    *,
    search: str | None,
    exam_id: int | None,
    subject_id: int | None,
    difficulty: str | None,
    status_value: str | None,
    pyq_year: int | None,
    skip: int,
    limit: int,
) -> QuestionListOut:
    filtered = _filter_question_rows(
        list_question_payloads(),
        search=search,
        exam_id=exam_id,
        subject_id=subject_id,
        difficulty=difficulty,
        status_value=status_value,
        pyq_year=pyq_year,
    )
    filtered.sort(key=lambda x: str(x.get('created_at', '')), reverse=True)
    total = len(filtered)
    window = filtered[skip: skip + limit]
    return QuestionListOut(
        items=[_enrich_payload(db, row) for row in window],
        total=total,
        skip=skip,
        limit=limit,
    )


def _filter_question_rows(
    items: list[dict],
    *,
    search: str | None,
    exam_id: int | None,
    subject_id: int | None,
    difficulty: str | None,
    status_value: str | None,
    pyq_year: int | None,
) -> list[dict]:
    def ok(row: dict) -> bool:
        if search:
            q = search.strip().lower()
            hay = ' '.join(
                [
                    str(row.get('question_text', '')),
                    str(row.get('topic', '')),
                    ' '.join(str(t) for t in row.get('tags', [])),
                ]
            ).lower()
            if q not in hay:
                return False
        if exam_id is not None and int(row.get('exam_id', 0)) != int(exam_id):
            return False
        if subject_id is not None and int(row.get('subject_id', 0)) != int(subject_id):
            return False
        if difficulty and str(row.get('difficulty', '')).lower() != difficulty.lower():
            return False
        if status_value and str(row.get('status', '')).lower() != status_value.lower():
            return False
        if pyq_year is not None and int(row.get('pyq_year') or 0) != int(pyq_year):
            return False
        return True

    return [row for row in items if ok(row)]


def question_analytics(
    _: Session,
    *,
    search: str | None = None,
    exam_id: int | None = None,
    subject_id: int | None = None,
    difficulty: str | None = None,
    status_value: str | None = None,
    pyq_year: int | None = None,
) -> QuestionAnalyticsOut:
    items = _filter_question_rows(
        list_question_payloads(),
        search=search,
        exam_id=exam_id,
        subject_id=subject_id,
        difficulty=difficulty,
        status_value=status_value,
        pyq_year=pyq_year,
    )
    total = len(items)
    published = sum(1 for x in items if str(x.get('status', '')).lower() == 'published')
    under_review = sum(1 for x in items if str(x.get('status', '')).lower() in {'under_review', 'flagged'})
    avg_accuracy = 0.0
    if total:
        avg_accuracy = sum(float(x.get('accuracy_pct', 0.0)) for x in items) / total

    return QuestionAnalyticsOut(
        total_questions=total,
        published=published,
        under_review=under_review,
        avg_accuracy=round(avg_accuracy, 2),
    )


def question_analytics_by_subject(
    db: Session,
    *,
    search: str | None = None,
    exam_id: int | None = None,
    subject_id: int | None = None,
    difficulty: str | None = None,
    status_value: str | None = None,
    pyq_year: int | None = None,
) -> QuestionSubjectAnalyticsOut:
    items = _filter_question_rows(
        list_question_payloads(),
        search=search,
        exam_id=exam_id,
        subject_id=subject_id,
        difficulty=difficulty,
        status_value=status_value,
        pyq_year=pyq_year,
    )
    grouped: dict[int, dict] = defaultdict(lambda: {
        'total': 0, 'published': 0, 'draft': 0, 'flagged': 0, 'difficulty_scores': []
    })

    for row in items:
        sid = int(row.get('subject_id', 0))
        if sid <= 0:
            continue
        group = grouped[sid]
        group['total'] += 1
        status_name = str(row.get('status', '')).lower()
        if status_name == 'published':
            group['published'] += 1
        elif status_name == 'draft':
            group['draft'] += 1
        elif status_name in {'flagged', 'under_review'}:
            group['flagged'] += 1
        group['difficulty_scores'].append(_difficulty_score(str(row.get('difficulty', 'medium'))))

    subject_names = {
        item.id: item.name for item in db.execute(select(AdminSubject)).scalars().all()
    }
    output: list[QuestionSubjectAnalyticsRow] = []
    for sid, val in grouped.items():
        avg = 2.0
        if val['difficulty_scores']:
            avg = sum(val['difficulty_scores']) / len(val['difficulty_scores'])
        output.append(
            QuestionSubjectAnalyticsRow(
                subject_id=sid,
                subject_name=subject_names.get(sid, f'Subject {sid}'),
                total=val['total'],
                published=val['published'],
                draft=val['draft'],
                flagged=val['flagged'],
                avg_difficulty=_score_to_difficulty(avg),
            )
        )

    output.sort(key=lambda x: x.total, reverse=True)
    return QuestionSubjectAnalyticsOut(items=output)


def question_bootstrap(db: Session) -> QuestionBootstrapOut:
    exams = db.execute(select(AdminExam).order_by(AdminExam.name.asc())).scalars().all()
    subjects = db.execute(select(AdminSubject).order_by(AdminSubject.name.asc())).scalars().all()
    exam_name_map = {exam.id: exam.name for exam in exams}
    years = {
        int(item['pyq_year'])
        for item in list_question_payloads()
        if item.get('pyq_year')
    }
    return QuestionBootstrapOut(
        exams=[ExamOut.model_validate(exam) for exam in exams],
        subjects=[
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
        ],
        pyq_years=sorted(years, reverse=True),
    )


def bulk_upload_questions(db: Session, *, file_name: str, file_bytes: bytes) -> QuestionBulkUploadOut:
    if not file_name.lower().endswith('.json'):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Only .json bulk uploads are supported.')
    try:
        payload = json.loads(file_bytes.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Bulk upload expects a UTF-8 JSON file.',
        ) from exc

    if isinstance(payload, dict) and isinstance(payload.get('questions'), list):
        items = payload['questions']
    elif isinstance(payload, list):
        items = payload
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Bulk upload JSON must be an array of questions or an object with a questions array.',
        )
    if not items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Bulk upload JSON is empty.')

    exams = db.execute(select(AdminExam)).scalars().all()
    subjects = db.execute(select(AdminSubject)).scalars().all()
    exams_by_id = {exam.id: exam for exam in exams}
    exams_by_code = {exam.code.upper(): exam for exam in exams}
    subjects_by_id = {subject.id: subject for subject in subjects}
    subjects_by_code = {subject.code.upper(): subject for subject in subjects}

    rows: list[dict] = []
    for idx, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f'Row {idx}: each uploaded question must be a JSON object.',
            )
        normalized_raw = dict(raw)
        normalized_raw.pop('exam_code', None)
        normalized_raw.pop('subject_code', None)
        try:
            question = QuestionCreateRequest.model_validate(normalized_raw)
        except ValidationError as exc:
            errors = []
            for item in exc.errors():
                loc = '.'.join(str(part) for part in item.get('loc', []))
                msg = item.get('msg', 'Invalid value')
                errors.append(f'{loc}: {msg}')
            detail = '; '.join(errors) if errors else 'Invalid question payload.'
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f'Row {idx}: {detail}',
            ) from exc

        exam, subject = _resolve_bulk_exam_and_subject(
            raw,
            row_number=idx,
            exams_by_id=exams_by_id,
            exams_by_code=exams_by_code,
            subjects_by_id=subjects_by_id,
            subjects_by_code=subjects_by_code,
        )
        now_iso = _iso_now()
        rows.append(
            {
                'id': uuid4().hex,
                'exam_id': exam.id,
                'subject_id': subject.id,
                'topic': question.topic,
                'question_text': question.question_text,
                'options': [item.model_dump() for item in question.options],
                'correct_option': question.correct_option,
                'explanation': question.explanation,
                'difficulty': question.difficulty,
                'status': question.status,
                'pyq_year': question.pyq_year,
                'tags': question.tags,
                'accuracy_pct': float(question.accuracy_pct),
                'created_at': now_iso,
                'updated_at': now_iso,
            }
        )

    upload_id = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
    storage_key = save_bulk_question_payloads(upload_id, rows)
    _rebuild_subject_question_counts(db)
    return QuestionBulkUploadOut(uploaded=len(rows), storage_key=storage_key)
