from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.admin.models import AdminExam, AdminUser
from app.admin.schemas import ExamAnalyticsOut, ExamCreateRequest, ExamListOut, ExamOut, ExamUpdateRequest
from app.admin.security import now_utc


def _get_exam_or_404(db: Session, exam_id: int) -> AdminExam:
    exam = db.get(AdminExam, exam_id)
    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Exam not found')
    return exam


def create_exam(db: Session, payload: ExamCreateRequest, current_user: AdminUser) -> ExamOut:
    existing_stmt = select(AdminExam).where(
        or_(AdminExam.name == payload.name, AdminExam.code == payload.code)
    )
    if db.execute(existing_stmt).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Exam name or code already exists')

    exam = AdminExam(
        name=payload.name,
        code=payload.code,
        description=payload.description,
        is_active=payload.is_active,
        subject_codes=payload.subject_codes,
        created_by_admin_id=current_user.id,
    )
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return ExamOut.model_validate(exam)


def list_exams(
    db: Session,
    *,
    search: str | None,
    is_active: bool | None,
    skip: int,
    limit: int,
) -> ExamListOut:
    stmt = select(AdminExam)
    if search:
        pattern = f'%{search.strip()}%'
        stmt = stmt.where(or_(AdminExam.name.ilike(pattern), AdminExam.code.ilike(pattern)))
    if is_active is not None:
        stmt = stmt.where(AdminExam.is_active == is_active)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(AdminExam.created_at.desc()).offset(skip).limit(limit)).scalars().all()
    return ExamListOut(items=[ExamOut.model_validate(row) for row in rows], total=total, skip=skip, limit=limit)


def get_exam(db: Session, exam_id: int) -> ExamOut:
    exam = _get_exam_or_404(db, exam_id)
    return ExamOut.model_validate(exam)


def update_exam(db: Session, exam_id: int, payload: ExamUpdateRequest) -> ExamOut:
    exam = _get_exam_or_404(db, exam_id)
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return ExamOut.model_validate(exam)

    if 'name' in updates or 'code' in updates:
        name_value = updates.get('name', exam.name)
        code_value = updates.get('code', exam.code)
        duplicate_stmt = select(AdminExam).where(
            AdminExam.id != exam.id,
            or_(AdminExam.name == name_value, AdminExam.code == code_value),
        )
        if db.execute(duplicate_stmt).scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Exam name or code already exists')

    for key, value in updates.items():
        setattr(exam, key, value)

    db.commit()
    db.refresh(exam)
    return ExamOut.model_validate(exam)


def delete_exam(db: Session, exam_id: int) -> None:
    exam = _get_exam_or_404(db, exam_id)
    db.delete(exam)
    db.commit()


def exam_analytics(db: Session) -> ExamAnalyticsOut:
    total_exams = db.execute(select(func.count()).select_from(AdminExam)).scalar_one()
    active_exams = db.execute(
        select(func.count()).select_from(AdminExam).where(AdminExam.is_active.is_(True))
    ).scalar_one()
    recent_cutoff = now_utc() - timedelta(days=7)
    recent_added = db.execute(
        select(func.count()).select_from(AdminExam).where(AdminExam.created_at >= recent_cutoff)
    ).scalar_one()

    mapped = set()
    subject_rows = db.execute(select(AdminExam.subject_codes)).scalars().all()
    for item in subject_rows:
        if not item:
            continue
        for code in item:
            norm = str(code).strip().upper()
            if norm:
                mapped.add(norm)

    return ExamAnalyticsOut(
        total_exams=total_exams,
        active_exams=active_exams,
        recent_added=recent_added,
        mapped_subjects=len(mapped),
    )
