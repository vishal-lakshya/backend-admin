from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.admin.dashboard_service import dashboard_overview
from app.admin.database import get_db
from app.admin.dependencies import get_current_admin_user
from app.admin.models import AdminUser
from app.admin.schemas import DashboardOverviewOut


router = APIRouter(prefix='/dashboard', tags=['Admin Dashboard'])


@router.get('/overview', response_model=DashboardOverviewOut)
def get_dashboard_overview(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> DashboardOverviewOut:
    return dashboard_overview(db)
