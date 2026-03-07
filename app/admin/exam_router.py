from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.admin.database import get_db
from app.admin.dependencies import get_current_admin_user
from app.admin.exam_service import create_exam, delete_exam, exam_analytics, get_exam, list_exams, update_exam
from app.admin.models import AdminUser
from app.admin.schemas import (
    ExamAnalyticsOut,
    ExamCreateRequest,
    ExamListOut,
    ExamOut,
    ExamUpdateRequest,
    MessageOut,
)


router = APIRouter(prefix='/exams', tags=['Admin Exams'])


@router.get('/analytics/summary', response_model=ExamAnalyticsOut)
def get_exam_analytics(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> ExamAnalyticsOut:
    return exam_analytics(db)


@router.get('', response_model=ExamListOut)
def get_exams(
    search: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> ExamListOut:
    return list_exams(db, search=search, is_active=is_active, skip=skip, limit=limit)


@router.post('', response_model=ExamOut, status_code=status.HTTP_201_CREATED)
def add_exam(
    payload: ExamCreateRequest,
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_admin_user),
) -> ExamOut:
    return create_exam(db, payload, current_user)


@router.get('/{exam_id}', response_model=ExamOut)
def get_exam_by_id(
    exam_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> ExamOut:
    return get_exam(db, exam_id)


@router.put('/{exam_id}', response_model=ExamOut)
def edit_exam(
    exam_id: int,
    payload: ExamUpdateRequest,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> ExamOut:
    return update_exam(db, exam_id, payload)


@router.delete('/{exam_id}', response_model=MessageOut)
def remove_exam(
    exam_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> MessageOut:
    delete_exam(db, exam_id)
    return MessageOut(message='Exam deleted')
