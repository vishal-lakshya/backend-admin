from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.admin.analytics_service import analytics_overview, export_analytics_csv
from app.admin.database import get_db
from app.admin.dependencies import get_current_admin_user
from app.admin.models import AdminUser
from app.admin.schemas import AnalyticsOverviewOut


router = APIRouter(prefix='/analytics', tags=['Admin Analytics'])


@router.get('/overview', response_model=AnalyticsOverviewOut)
def get_analytics_overview(
    range_days: int = Query(default=30, ge=7, le=365),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> AnalyticsOverviewOut:
    return analytics_overview(db, range_days=range_days)


@router.get('/export')
def get_analytics_export(
    range_days: int = Query(default=30, ge=7, le=365),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> Response:
    content = export_analytics_csv(db, range_days=range_days)
    return Response(
        content=content,
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename=admin-analytics-{range_days}d.csv'},
    )
