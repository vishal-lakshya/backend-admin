from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.admin.database import get_db
from app.admin.dependencies import get_current_admin_user
from app.admin.models import AdminUser
from app.admin.platform_settings_service import get_platform_settings_bootstrap, update_platform_settings
from app.admin.schemas import PlatformSettingBootstrapOut, PlatformSettingOut, PlatformSettingUpdateRequest


router = APIRouter(prefix='/settings', tags=['Admin Settings'])


@router.get('/bootstrap', response_model=PlatformSettingBootstrapOut)
def settings_bootstrap(
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> PlatformSettingBootstrapOut:
    return get_platform_settings_bootstrap(db)


@router.put('', response_model=PlatformSettingOut)
def save_settings(
    payload: PlatformSettingUpdateRequest,
    db: Session = Depends(get_db),
    _: AdminUser = Depends(get_current_admin_user),
) -> PlatformSettingOut:
    return update_platform_settings(db, payload)
