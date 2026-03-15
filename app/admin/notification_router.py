from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.admin.database import get_db
from app.admin.dependencies import get_current_admin_user
from app.admin.models import AdminUser
from app.admin.notification_service import (
    admin_notification_overview,
    create_broadcast_notification,
    delete_broadcast_notification,
    list_broadcast_notifications,
    notification_bootstrap,
    update_broadcast_notification,
)
from app.admin.schemas import (
    AdminNotificationBootstrapOut,
    AdminNotificationOverviewOut,
    BroadcastNotificationCreateRequest,
    BroadcastNotificationListOut,
    BroadcastNotificationOut,
    BroadcastNotificationUpdateRequest,
    MessageOut,
)


router = APIRouter(prefix='/notifications', tags=['Admin Notifications'])


@router.get('/bootstrap', response_model=AdminNotificationBootstrapOut)
def get_notification_bootstrap(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> AdminNotificationBootstrapOut:
    return notification_bootstrap(db)


@router.get('/overview', response_model=AdminNotificationOverviewOut)
def get_notification_overview(
    limit: int = Query(default=8, ge=1, le=50),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> AdminNotificationOverviewOut:
    return admin_notification_overview(db, limit=limit)


@router.get('', response_model=BroadcastNotificationListOut)
def get_notifications(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> BroadcastNotificationListOut:
    return list_broadcast_notifications(db, skip=skip, limit=limit)


@router.post('', response_model=BroadcastNotificationOut)
def create_notification(
    payload: BroadcastNotificationCreateRequest,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin_user),
) -> BroadcastNotificationOut:
    return create_broadcast_notification(db, payload=payload, created_by_admin_id=current_admin.id)


@router.put('/{notification_id}', response_model=BroadcastNotificationOut)
def update_notification(
    notification_id: int,
    payload: BroadcastNotificationUpdateRequest,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> BroadcastNotificationOut:
    return update_broadcast_notification(db, notification_id=notification_id, payload=payload)


@router.delete('/{notification_id}', response_model=MessageOut)
def remove_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> MessageOut:
    delete_broadcast_notification(db, notification_id=notification_id)
    return MessageOut(message='Notification deleted')
