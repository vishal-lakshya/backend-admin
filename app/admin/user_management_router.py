from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.admin.database import get_db
from app.admin.dependencies import get_current_admin_user
from app.admin.models import AdminUser
from app.admin.schemas import (
    AdminManagedUserAnalyticsOut,
    AdminManagedUserCreateRequest,
    AdminManagedUserDetailOut,
    AdminManagedUserListOut,
    AdminManagedUserOut,
    AdminManagedUserUpdateRequest,
    MessageOut,
)
from app.admin.user_management_service import (
    create_user,
    delete_user,
    export_user_performance_csv,
    get_user_detail,
    list_users,
    update_user,
    user_analytics,
)


router = APIRouter(prefix='/users', tags=['Admin Users'])


@router.get('/analytics/summary', response_model=AdminManagedUserAnalyticsOut)
def get_user_analytics(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> AdminManagedUserAnalyticsOut:
    return user_analytics(db)


@router.get('', response_model=AdminManagedUserListOut)
def get_users(
    search: str | None = Query(default=None),
    status_filter: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> AdminManagedUserListOut:
    return list_users(db, search=search, status_filter=status_filter, skip=skip, limit=limit)


@router.post('', response_model=AdminManagedUserOut)
def create_managed_user(
    payload: AdminManagedUserCreateRequest,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> AdminManagedUserOut:
    return create_user(db, payload=payload)


@router.get('/{user_id}', response_model=AdminManagedUserDetailOut)
def get_managed_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> AdminManagedUserDetailOut:
    return get_user_detail(db, user_id=user_id)


@router.put('/{user_id}', response_model=AdminManagedUserOut)
def update_managed_user(
    user_id: int,
    payload: AdminManagedUserUpdateRequest,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> AdminManagedUserOut:
    return update_user(db, user_id=user_id, payload=payload)


@router.delete('/{user_id}', response_model=MessageOut)
def delete_managed_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> MessageOut:
    delete_user(db, user_id=user_id)
    return MessageOut(message='User deleted.')


@router.get('/{user_id}/export')
def export_managed_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> Response:
    filename, payload = export_user_performance_csv(db, user_id=user_id)
    return Response(
        content=payload,
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )
