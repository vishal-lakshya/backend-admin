from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.admin.database import get_db
from app.admin.dependencies import get_current_admin_user
from app.admin.models import AdminUser
from app.admin.payment_service import list_public_plans, payment_dashboard
from app.admin.schemas import PaymentDashboardOut, SubscriptionPlanListOut


router = APIRouter(tags=['Payments'])
admin_router = APIRouter(prefix='/payments', tags=['Admin Payments'])


@router.get('/subscriptions/public/plans', response_model=SubscriptionPlanListOut)
@router.get('/subscriptions/plans', response_model=SubscriptionPlanListOut)
def get_public_plans(db: Session = Depends(get_db)) -> SubscriptionPlanListOut:
    return list_public_plans(db)


@admin_router.get('/dashboard', response_model=PaymentDashboardOut)
def get_payment_dashboard(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> PaymentDashboardOut:
    return payment_dashboard(db, skip=skip, limit=limit)
