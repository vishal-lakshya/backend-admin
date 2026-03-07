from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.admin.database import get_db
from app.admin.dependencies import get_current_admin_user
from app.admin.models import AdminUser
from app.admin.pyq_service import (
    create_pyq_paper,
    delete_pyq_paper,
    get_pyq_download_url,
    get_pyq_paper_detail,
    list_pyq_papers,
    pyq_analytics,
    pyq_bootstrap,
    update_pyq_paper,
)
from app.admin.schemas import MessageOut, PyqAnalyticsOut, PyqAssetDownloadOut, PyqBootstrapOut, PyqCreateOut, PyqPaperDetailOut, PyqPaperListOut, PyqUpdateOut


router = APIRouter(prefix='/pyq', tags=['Admin PYQ'])


@router.get('/bootstrap', response_model=PyqBootstrapOut)
def get_pyq_bootstrap(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> PyqBootstrapOut:
    return pyq_bootstrap(db)


@router.get('/analytics/summary', response_model=PyqAnalyticsOut)
def get_pyq_analytics(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> PyqAnalyticsOut:
    return pyq_analytics(db)


@router.get('', response_model=PyqPaperListOut)
def get_pyq_papers(
    search: str | None = Query(default=None),
    exam_id: int | None = Query(default=None),
    year: int | None = Query(default=None),
    paper_type: str | None = Query(default=None),
    paper_set: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> PyqPaperListOut:
    return list_pyq_papers(
        db,
        search=search,
        exam_id=exam_id,
        year=year,
        paper_type=paper_type,
        paper_set=paper_set,
        skip=skip,
        limit=limit,
    )


@router.post('', response_model=PyqCreateOut, status_code=status.HTTP_201_CREATED)
async def create_new_pyq(
    exam_id: int = Form(...),
    title: str = Form(...),
    year: int = Form(...),
    paper_type: str = Form(...),
    paper_set: str | None = Form(default=None),
    paper_file: UploadFile | None = File(default=None),
    questions_file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    current_user: AdminUser = Depends(get_current_admin_user),
) -> PyqCreateOut:
    return create_pyq_paper(
        db,
        current_user=current_user,
        exam_id=exam_id,
        title=title,
        year=year,
        paper_type=paper_type,
        paper_set=paper_set,
        paper_file_name=(paper_file.filename if paper_file else None) or None,
        paper_file_bytes=(await paper_file.read()) if paper_file else None,
        paper_content_type=paper_file.content_type if paper_file else None,
        questions_file_name=(questions_file.filename if questions_file else None) or None,
        questions_file_bytes=(await questions_file.read()) if questions_file else None,
    )


@router.get('/{pyq_id}', response_model=PyqPaperDetailOut)
def get_pyq_by_id(
    pyq_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> PyqPaperDetailOut:
    return get_pyq_paper_detail(db, pyq_id)


@router.put('/{pyq_id}', response_model=PyqUpdateOut)
async def update_pyq(
    pyq_id: int,
    exam_id: int = Form(...),
    title: str = Form(...),
    year: int = Form(...),
    paper_type: str = Form(...),
    paper_set: str | None = Form(default=None),
    paper_file: UploadFile | None = File(default=None),
    questions_file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> PyqUpdateOut:
    return update_pyq_paper(
        db,
        pyq_id=pyq_id,
        exam_id=exam_id,
        title=title,
        year=year,
        paper_type=paper_type,
        paper_set=paper_set,
        paper_file_name=(paper_file.filename if paper_file else None) or None,
        paper_file_bytes=(await paper_file.read()) if paper_file else None,
        paper_content_type=paper_file.content_type if paper_file else None,
        questions_file_name=(questions_file.filename if questions_file else None) or None,
        questions_file_bytes=(await questions_file.read()) if questions_file else None,
    )


@router.delete('/{pyq_id}', response_model=MessageOut)
def remove_pyq(
    pyq_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> MessageOut:
    delete_pyq_paper(db, pyq_id)
    return MessageOut(message='PYQ paper deleted.')


@router.get('/{pyq_id}/download', response_model=PyqAssetDownloadOut)
def download_pyq(
    pyq_id: int,
    asset: str = Query(default='paper'),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> PyqAssetDownloadOut:
    return get_pyq_download_url(db, pyq_id, asset)
