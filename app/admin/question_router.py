from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.admin.database import get_db
from app.admin.dependencies import get_current_admin_user
from app.admin.models import AdminUser
from app.admin.question_service import (
    add_question,
    bulk_upload_questions,
    delete_question as delete_question_service,
    get_question,
    list_questions,
    question_bootstrap,
    question_analytics,
    question_analytics_by_subject,
    update_question,
)
from app.admin.schemas import (
    MessageOut,
    QuestionAnalyticsOut,
    QuestionBootstrapOut,
    QuestionBulkUploadOut,
    QuestionCreateRequest,
    QuestionListOut,
    QuestionOut,
    QuestionSubjectAnalyticsOut,
    QuestionUpdateRequest,
)


router = APIRouter(prefix='/questions', tags=['Admin Questions'])


@router.get('/bootstrap', response_model=QuestionBootstrapOut)
def get_question_bootstrap(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> QuestionBootstrapOut:
    return question_bootstrap(db)


@router.get('/analytics/summary', response_model=QuestionAnalyticsOut)
def get_question_analytics(
    search: str | None = Query(default=None),
    exam_id: int | None = Query(default=None),
    subject_id: int | None = Query(default=None),
    difficulty: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias='status'),
    pyq_year: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> QuestionAnalyticsOut:
    return question_analytics(
        db,
        search=search,
        exam_id=exam_id,
        subject_id=subject_id,
        difficulty=difficulty,
        status_value=status_value,
        pyq_year=pyq_year,
    )


@router.get('/analytics/by-subject', response_model=QuestionSubjectAnalyticsOut)
def get_question_analytics_by_subject(
    search: str | None = Query(default=None),
    exam_id: int | None = Query(default=None),
    subject_id: int | None = Query(default=None),
    difficulty: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias='status'),
    pyq_year: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> QuestionSubjectAnalyticsOut:
    return question_analytics_by_subject(
        db,
        search=search,
        exam_id=exam_id,
        subject_id=subject_id,
        difficulty=difficulty,
        status_value=status_value,
        pyq_year=pyq_year,
    )


@router.get('', response_model=QuestionListOut)
def get_questions(
    search: str | None = Query(default=None),
    exam_id: int | None = Query(default=None),
    subject_id: int | None = Query(default=None),
    difficulty: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias='status'),
    pyq_year: int | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> QuestionListOut:
    return list_questions(
        db,
        search=search,
        exam_id=exam_id,
        subject_id=subject_id,
        difficulty=difficulty,
        status_value=status_value,
        pyq_year=pyq_year,
        skip=skip,
        limit=limit,
    )


@router.post('', response_model=QuestionOut, status_code=status.HTTP_201_CREATED)
def create_question(
    payload: QuestionCreateRequest,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> QuestionOut:
    return add_question(db, payload)


@router.get('/{question_id}', response_model=QuestionOut)
def get_question_by_id(
    question_id: str,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> QuestionOut:
    return get_question(db, question_id)


@router.put('/{question_id}', response_model=QuestionOut)
def edit_question(
    question_id: str,
    payload: QuestionUpdateRequest,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> QuestionOut:
    return update_question(db, question_id, payload)


@router.delete('/{question_id}', response_model=MessageOut)
def delete_question_by_id(
    question_id: str,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> MessageOut:
    delete_question_service(db, question_id)
    return MessageOut(message='Question deleted')


@router.post('/bulk-upload', response_model=QuestionBulkUploadOut, status_code=status.HTTP_201_CREATED)
async def upload_questions(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> QuestionBulkUploadOut:
    file_bytes = await file.read()
    return bulk_upload_questions(db, file_name=file.filename or 'questions.json', file_bytes=file_bytes)
