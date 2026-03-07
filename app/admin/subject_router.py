from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.admin.database import get_db
from app.admin.dependencies import get_current_admin_user
from app.admin.models import AdminUser
from app.admin.schemas import (
    MessageOut,
    SubjectAnalyticsOut,
    SubjectCreateRequest,
    SubjectListOut,
    SubjectOut,
    SubjectUpdateRequest,
)
from app.admin.subject_service import (
    create_subject,
    delete_subject,
    get_subject,
    list_subjects,
    subject_analytics,
    update_subject,
)


router = APIRouter(prefix='/subjects', tags=['Admin Subjects'])


@router.get('/analytics/summary', response_model=SubjectAnalyticsOut)
def get_subject_analytics(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> SubjectAnalyticsOut:
    return subject_analytics(db)


@router.get('', response_model=SubjectListOut)
def get_subjects(
    search: str | None = Query(default=None),
    exam_id: int | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> SubjectListOut:
    return list_subjects(
        db,
        search=search,
        exam_id=exam_id,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )


@router.post('', response_model=SubjectOut, status_code=status.HTTP_201_CREATED)
def add_subject(
    payload: SubjectCreateRequest,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_admin_user),
) -> SubjectOut:
    return create_subject(db, payload, current_user)


@router.get('/{subject_id}', response_model=SubjectOut)
def get_subject_by_id(
    subject_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> SubjectOut:
    return get_subject(db, subject_id)


@router.put('/{subject_id}', response_model=SubjectOut)
def edit_subject(
    subject_id: int,
    payload: SubjectUpdateRequest,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> SubjectOut:
    return update_subject(db, subject_id, payload)


@router.delete('/{subject_id}', response_model=MessageOut)
def remove_subject(
    subject_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> MessageOut:
    delete_subject(db, subject_id)
    return MessageOut(message='Subject deleted')
