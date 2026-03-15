from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.admin.database import get_db
from app.admin.dependencies import get_current_admin_user
from app.admin.models import AdminUser
from app.admin.schemas import MessageOut, TestSeriesAnalyticsOut, TestSeriesBootstrapOut, TestSeriesCreateOut, TestSeriesListOut, TestSeriesMoveRequest, TestSeriesOut
from app.admin.test_service import archive_test, create_test, delete_test, get_test, list_tests, move_test, test_analytics, test_bootstrap


router = APIRouter(prefix='/tests', tags=['Admin Tests'])


@router.get('/bootstrap', response_model=TestSeriesBootstrapOut)
def get_tests_bootstrap(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> TestSeriesBootstrapOut:
    return test_bootstrap(db)


@router.get('/analytics/summary', response_model=TestSeriesAnalyticsOut)
def get_tests_analytics(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> TestSeriesAnalyticsOut:
    return test_analytics(db)


@router.get('', response_model=TestSeriesListOut)
def get_tests(
    search: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias='status'),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> TestSeriesListOut:
    return list_tests(db, search=search, status_value=status_value, skip=skip, limit=limit)


@router.post('', response_model=TestSeriesCreateOut, status_code=status.HTTP_201_CREATED)
async def create_new_test(
    name: str = Form(...),
    test_type: str = Form(...),
    display_mode: str = Form(...),
    subject_id: int | None = Form(default=None),
    question_count: int | None = Form(default=None),
    duration_minutes: int = Form(...),
    scheduled_at: str | None = Form(default=None),
    access_level: str = Form(...),
    positive_marks: float = Form(...),
    negative_marks: float = Form(...),
    save_as_draft: bool = Form(default=False),
    questions_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_admin_user),
) -> TestSeriesCreateOut:
    scheduled_dt = datetime.fromisoformat(scheduled_at) if scheduled_at else None
    file_bytes = await questions_file.read()
    return create_test(
        db,
        current_user=current_user,
        name=name,
        test_type=test_type,
        display_mode=display_mode,
        subject_id=subject_id,
        question_count=question_count,
        duration_minutes=duration_minutes,
        scheduled_at=scheduled_dt,
        access_level=access_level,
        positive_marks=positive_marks,
        negative_marks=negative_marks,
        file_name=questions_file.filename or 'test-questions.json',
        file_bytes=file_bytes,
        save_as_draft=save_as_draft,
    )


@router.get('/{test_id}', response_model=TestSeriesOut)
def get_test_by_id(
    test_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> TestSeriesOut:
    return get_test(db, test_id)


@router.post('/{test_id}/archive', response_model=TestSeriesOut)
def archive_test_by_id(
    test_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> TestSeriesOut:
    return archive_test(db, test_id)


@router.post('/{test_id}/move', response_model=TestSeriesOut)
def move_test_by_id(
    test_id: int,
    payload: TestSeriesMoveRequest,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> TestSeriesOut:
    return move_test(db, test_id, target_status=payload.target_status, scheduled_at=payload.scheduled_at)


@router.delete('/{test_id}', response_model=MessageOut)
def delete_test_by_id(
    test_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> MessageOut:
    delete_test(db, test_id)
    return MessageOut(message='Test deleted')
