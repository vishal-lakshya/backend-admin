from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.admin.database import get_db
from app.admin.dependencies import get_current_admin_user
from app.admin.models import AdminUser
from app.admin.payment_service import (
    create_subscription_plan,
    delete_subscription_plan,
    list_admin_plans,
    list_public_plans,
    payment_dashboard,
    subscription_plan_bootstrap,
    update_subscription_plan,
)
from app.admin.schemas import PaymentDashboardOut, SubscriptionPlanBootstrapOut, SubscriptionPlanListOut, SubscriptionPlanOut, SubscriptionPlanUpdateRequest


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


@admin_router.get('/plans', response_model=SubscriptionPlanListOut)
def get_admin_plans(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> SubscriptionPlanListOut:
    return list_admin_plans(db)


@admin_router.get('/plans/bootstrap', response_model=SubscriptionPlanBootstrapOut)
def get_plan_bootstrap(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> SubscriptionPlanBootstrapOut:
    return subscription_plan_bootstrap(db)


@admin_router.post('/plans', response_model=SubscriptionPlanOut, status_code=201)
def create_admin_plan(
    payload: SubscriptionPlanUpdateRequest,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> SubscriptionPlanOut:
    return create_subscription_plan(db, payload=payload)


@admin_router.put('/plans/{plan_id}', response_model=SubscriptionPlanOut)
def update_admin_plan(
    payload: SubscriptionPlanUpdateRequest,
    plan_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> SubscriptionPlanOut:
    return update_subscription_plan(db, plan_id=plan_id, payload=payload)


@admin_router.delete('/plans/{plan_id}', status_code=204)
def delete_admin_plan(
    plan_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> Response:
    delete_subscription_plan(db, plan_id=plan_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
