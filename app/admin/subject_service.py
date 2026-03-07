from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.admin.models import AdminExam, AdminSubject, AdminUser
from app.admin.schemas import (
    SubjectAnalyticsOut,
    SubjectCreateRequest,
    SubjectListOut,
    SubjectOut,
    SubjectUpdateRequest,
)
from app.admin.security import now_utc


def _resolve_subject_out(db: Session, subject: AdminSubject) -> SubjectOut:
    exam_name = db.execute(select(AdminExam.name).where(AdminExam.id == subject.exam_id)).scalar_one_or_none() or '-'
    return SubjectOut(
        id=subject.id,
        exam_id=subject.exam_id,
        exam_name=exam_name,
        name=subject.name,
        code=subject.code,
        description=subject.description,
        is_active=subject.is_active,
        mapped_questions=subject.mapped_questions,
        created_by_admin_id=subject.created_by_admin_id,
        created_at=subject.created_at,
        updated_at=subject.updated_at,
    )


def _get_subject_or_404(db: Session, subject_id: int) -> AdminSubject:
    subject = db.get(AdminSubject, subject_id)
    if not subject:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subject not found')
    return subject


def _validate_exam_exists(db: Session, exam_id: int) -> None:
    if not db.get(AdminExam, exam_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid exam id')


def create_subject(db: Session, payload: SubjectCreateRequest, current_user: AdminUser) -> SubjectOut:
    _validate_exam_exists(db, payload.exam_id)
    duplicate_stmt = select(AdminSubject).where(AdminSubject.code == payload.code)
    if db.execute(duplicate_stmt).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Subject code already exists')

    subject = AdminSubject(
        exam_id=payload.exam_id,
        name=payload.name,
        code=payload.code,
        description=payload.description,
        is_active=payload.is_active,
        created_by_admin_id=current_user.id,
    )
    db.add(subject)
    db.commit()
    db.refresh(subject)
    return _resolve_subject_out(db, subject)


def list_subjects(
    db: Session,
    *,
    search: str | None,
    exam_id: int | None,
    is_active: bool | None,
    skip: int,
    limit: int,
) -> SubjectListOut:
    stmt = select(AdminSubject)
    if search:
        pattern = f'%{search.strip()}%'
        stmt = stmt.where(or_(AdminSubject.name.ilike(pattern), AdminSubject.code.ilike(pattern)))
    if exam_id is not None:
        stmt = stmt.where(AdminSubject.exam_id == exam_id)
    if is_active is not None:
        stmt = stmt.where(AdminSubject.is_active == is_active)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.execute(stmt.order_by(AdminSubject.created_at.desc()).offset(skip).limit(limit)).scalars().all()
    items = [_resolve_subject_out(db, row) for row in rows]
    return SubjectListOut(items=items, total=total, skip=skip, limit=limit)


def get_subject(db: Session, subject_id: int) -> SubjectOut:
    subject = _get_subject_or_404(db, subject_id)
    return _resolve_subject_out(db, subject)


def update_subject(db: Session, subject_id: int, payload: SubjectUpdateRequest) -> SubjectOut:
    subject = _get_subject_or_404(db, subject_id)
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return _resolve_subject_out(db, subject)

    if 'exam_id' in updates and updates['exam_id'] is not None:
        _validate_exam_exists(db, updates['exam_id'])

    if 'code' in updates and updates['code']:
        duplicate_stmt = select(AdminSubject).where(
            AdminSubject.id != subject.id,
            AdminSubject.code == updates['code'],
        )
        if db.execute(duplicate_stmt).scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Subject code already exists')

    for key, value in updates.items():
        setattr(subject, key, value)

    db.commit()
    db.refresh(subject)
    return _resolve_subject_out(db, subject)


def delete_subject(db: Session, subject_id: int) -> None:
    subject = _get_subject_or_404(db, subject_id)
    db.delete(subject)
    db.commit()


def subject_analytics(db: Session) -> SubjectAnalyticsOut:
    total_subjects = db.execute(select(func.count()).select_from(AdminSubject)).scalar_one()
    active_subjects = db.execute(
        select(func.count()).select_from(AdminSubject).where(AdminSubject.is_active.is_(True))
    ).scalar_one()
    month_cutoff = now_utc() - timedelta(days=30)
    updated_this_month = db.execute(
        select(func.count()).select_from(AdminSubject).where(AdminSubject.updated_at >= month_cutoff)
    ).scalar_one()
    mapped_questions = db.execute(select(func.coalesce(func.sum(AdminSubject.mapped_questions), 0))).scalar_one()

    return SubjectAnalyticsOut(
        total_subjects=total_subjects,
        active_subjects=active_subjects,
        updated_this_month=updated_this_month,
        mapped_questions=int(mapped_questions or 0),
    )
