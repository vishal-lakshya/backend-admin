import json

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.admin.models import AdminExam, AdminPyqPaper, AdminUser
from app.admin.pyq_storage import (
    create_download_url,
    delete_object,
    load_pyq_questions,
    save_pyq_paper_file,
    save_pyq_questions,
)
from app.admin.schemas import (
    ExamOut,
    PyqAnalyticsOut,
    PyqAssetDownloadOut,
    PyqBootstrapOut,
    PyqCreateOut,
    PyqPaperDetailOut,
    PyqPaperListOut,
    PyqPaperOut,
    PyqQuestionOut,
    PyqUpdateOut,
    TestQuestionUploadIn,
)


def _serialize_paper(db: Session, paper: AdminPyqPaper) -> PyqPaperOut:
    exam = db.get(AdminExam, paper.exam_id)
    return PyqPaperOut(
        id=paper.id,
        exam_id=paper.exam_id,
        exam_name=exam.name if exam else '-',
        title=paper.title,
        year=paper.year,
        paper_type=paper.paper_type,
        paper_set=paper.paper_set,
        status=paper.status,
        paper_file_name=paper.paper_file_name,
        paper_file_key=paper.paper_file_key,
        questions_file_key=paper.questions_file_key,
        has_paper_file=bool(paper.paper_file_key),
        has_questions_file=bool(paper.questions_file_key),
        question_count=paper.question_count,
        created_at=paper.created_at,
        updated_at=paper.updated_at,
    )


def _parse_questions_upload(questions_file_name: str, questions_file_bytes: bytes) -> list[dict]:
    if not questions_file_name.lower().endswith('.json'):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Upload questions as a .json file.')
    try:
        payload = json.loads(questions_file_bytes.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Questions upload expects a UTF-8 JSON file.') from exc

    if isinstance(payload, dict) and isinstance(payload.get('questions'), list):
        items = payload['questions']
    elif isinstance(payload, list):
        items = payload
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Questions file must be an array or an object with a questions array.',
        )
    if not items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Questions file is empty.')

    questions: list[dict] = []
    for idx, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'Question row {idx} must be a JSON object.')
        try:
            question = TestQuestionUploadIn.model_validate(raw)
        except ValidationError as exc:
            detail = '; '.join(
                f'{".".join(str(part) for part in err.get("loc", []))}: {err.get("msg", "Invalid value")}'
                for err in exc.errors()
            )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'Question row {idx}: {detail}') from exc
        questions.append(
            {
                'id': idx,
                'topic': question.topic,
                'question_text': question.question_text,
                'options': [item.model_dump() for item in question.options],
                'correct_option': question.correct_option,
                'explanation': question.explanation,
                'difficulty': question.difficulty,
            }
        )
    return questions


def pyq_bootstrap(db: Session) -> PyqBootstrapOut:
    exams = db.execute(select(AdminExam).order_by(AdminExam.name.asc())).scalars().all()
    years = db.execute(select(AdminPyqPaper.year).distinct().order_by(AdminPyqPaper.year.desc())).scalars().all()
    paper_types = db.execute(select(AdminPyqPaper.paper_type).distinct().order_by(AdminPyqPaper.paper_type.asc())).scalars().all()
    paper_sets = db.execute(select(AdminPyqPaper.paper_set).distinct().order_by(AdminPyqPaper.paper_set.asc())).scalars().all()
    return PyqBootstrapOut(
        exams=[ExamOut.model_validate(exam) for exam in exams],
        years=sorted([int(year) for year in years if year], reverse=True),
        paper_types=[str(value) for value in paper_types if value],
        paper_sets=[str(value) for value in paper_sets if value],
    )


def pyq_analytics(db: Session) -> PyqAnalyticsOut:
    rows = db.execute(select(AdminPyqPaper)).scalars().all()
    years = [paper.year for paper in rows]
    return PyqAnalyticsOut(
        total_papers=len(rows),
        total_questions=sum(paper.question_count for paper in rows),
        latest_year=max(years) if years else None,
    )


def list_pyq_papers(
    db: Session,
    *,
    search: str | None,
    exam_id: int | None,
    year: int | None,
    paper_type: str | None,
    paper_set: str | None,
    skip: int,
    limit: int,
) -> PyqPaperListOut:
    stmt = select(AdminPyqPaper)
    if search:
        pattern = f'%{search.strip()}%'
        stmt = stmt.where(AdminPyqPaper.title.ilike(pattern))
    if exam_id is not None:
        stmt = stmt.where(AdminPyqPaper.exam_id == exam_id)
    if year is not None:
        stmt = stmt.where(AdminPyqPaper.year == year)
    if paper_type:
        stmt = stmt.where(AdminPyqPaper.paper_type.ilike(paper_type.strip()))
    if paper_set:
        stmt = stmt.where(AdminPyqPaper.paper_set.ilike(f'%{paper_set.strip()}%'))
    rows = db.execute(stmt.order_by(AdminPyqPaper.year.desc(), AdminPyqPaper.created_at.desc())).scalars().all()
    total = len(rows)
    window = rows[skip: skip + limit]
    return PyqPaperListOut(
        items=[_serialize_paper(db, row) for row in window],
        total=total,
        skip=skip,
        limit=limit,
    )


def create_pyq_paper(
    db: Session,
    *,
    current_user: AdminUser,
    exam_id: int,
    title: str,
    year: int,
    paper_type: str,
    paper_set: str | None,
    paper_file_name: str | None,
    paper_file_bytes: bytes | None,
    paper_content_type: str | None,
    questions_file_name: str | None,
    questions_file_bytes: bytes | None,
) -> PyqCreateOut:
    exam = db.get(AdminExam, exam_id)
    if not exam:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid exam id.')
    if not title.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Paper title is required.')
    if not paper_type.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Paper type is required.')
    if not paper_file_bytes and not questions_file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Upload either the paper file or questions JSON.')

    questions: list[dict] = []
    if questions_file_bytes:
        questions = _parse_questions_upload(questions_file_name or 'questions.json', questions_file_bytes)

    paper = AdminPyqPaper(
        exam_id=exam_id,
        title=title.strip(),
        year=year,
        paper_type=paper_type.strip(),
        paper_set=paper_set.strip() if paper_set and paper_set.strip() else None,
        status='published',
        paper_file_key=None,
        paper_file_name=paper_file_name if paper_file_bytes else None,
        questions_file_key=None,
        question_count=len(questions),
        created_by_admin_id=current_user.id,
    )
    db.add(paper)
    db.commit()
    db.refresh(paper)

    if paper_file_bytes:
        paper.paper_file_key = save_pyq_paper_file(
            paper.id,
            paper_file_name or 'paper.pdf',
            paper_file_bytes,
            paper_content_type,
        )
        paper.paper_file_name = paper_file_name or 'paper.pdf'
    if questions:
        paper.questions_file_key = save_pyq_questions(paper.id, questions)
        paper.question_count = len(questions)

    db.commit()
    db.refresh(paper)
    return PyqCreateOut(paper=_serialize_paper(db, paper))


def update_pyq_paper(
    db: Session,
    *,
    pyq_id: int,
    exam_id: int,
    title: str,
    year: int,
    paper_type: str,
    paper_set: str | None,
    paper_file_name: str | None,
    paper_file_bytes: bytes | None,
    paper_content_type: str | None,
    questions_file_name: str | None,
    questions_file_bytes: bytes | None,
) -> PyqUpdateOut:
    paper = db.get(AdminPyqPaper, pyq_id)
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='PYQ paper not found.')
    exam = db.get(AdminExam, exam_id)
    if not exam:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid exam id.')
    if not title.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Paper title is required.')
    if not paper_type.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Paper type is required.')

    paper.exam_id = exam_id
    paper.title = title.strip()
    paper.year = year
    paper.paper_type = paper_type.strip()
    paper.paper_set = paper_set.strip() if paper_set and paper_set.strip() else None

    if paper_file_bytes:
        delete_object(paper.paper_file_key)
        paper.paper_file_key = save_pyq_paper_file(
            paper.id,
            paper_file_name or paper.paper_file_name or 'paper.pdf',
            paper_file_bytes,
            paper_content_type,
        )
        paper.paper_file_name = paper_file_name or paper.paper_file_name or 'paper.pdf'

    if questions_file_bytes:
        questions = _parse_questions_upload(questions_file_name or 'questions.json', questions_file_bytes)
        delete_object(paper.questions_file_key)
        paper.questions_file_key = save_pyq_questions(paper.id, questions)
        paper.question_count = len(questions)

    db.commit()
    db.refresh(paper)
    return PyqUpdateOut(paper=_serialize_paper(db, paper))


def delete_pyq_paper(db: Session, pyq_id: int) -> None:
    paper = db.get(AdminPyqPaper, pyq_id)
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='PYQ paper not found.')
    delete_object(paper.paper_file_key)
    delete_object(paper.questions_file_key)
    db.delete(paper)
    db.commit()


def get_pyq_paper_detail(db: Session, pyq_id: int) -> PyqPaperDetailOut:
    paper = db.get(AdminPyqPaper, pyq_id)
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='PYQ paper not found.')
    questions = []
    if paper.questions_file_key:
        questions = [
            PyqQuestionOut(
                id=int(item.get('id') or idx + 1),
                topic=item.get('topic'),
                question_text=item.get('question_text', ''),
                options=item.get('options', []),
                correct_option=item.get('correct_option', ''),
                explanation=item.get('explanation', ''),
                difficulty=item.get('difficulty', 'medium'),
            )
            for idx, item in enumerate(load_pyq_questions(paper.questions_file_key))
        ]
    return PyqPaperDetailOut(paper=_serialize_paper(db, paper), questions=questions)


def get_pyq_download_url(db: Session, pyq_id: int, asset: str) -> PyqAssetDownloadOut:
    paper = db.get(AdminPyqPaper, pyq_id)
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='PYQ paper not found.')

    normalized = asset.strip().lower()
    if normalized == 'paper':
        if not paper.paper_file_key:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='This PYQ does not have a paper file.')
        return PyqAssetDownloadOut(
            url=create_download_url(paper.paper_file_key, file_name=paper.paper_file_name or 'paper'),
            asset='paper',
        )
    if normalized == 'questions':
        if not paper.questions_file_key:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='This PYQ does not have questions JSON.')
        return PyqAssetDownloadOut(
            url=create_download_url(paper.questions_file_key, file_name=f'pyq-{paper.id}-questions.ndjson.gz'),
            asset='questions',
        )
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid asset type. Use paper or questions.')
