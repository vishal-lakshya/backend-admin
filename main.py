import asyncio
import logging

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.admin.config import settings
from app.admin.database import engine
from app.admin.payment_router import admin_router as admin_payment_router
from app.admin.payment_router import router as subscription_router
from app.admin.analytics_router import router as admin_analytics_router
from app.admin.dashboard_router import router as admin_dashboard_router
from app.admin.exam_router import router as admin_exam_router
from app.admin.notification_router import router as admin_notification_router
from app.admin.platform_settings_router import router as admin_platform_settings_router
from app.admin.pyq_router import router as admin_pyq_router
from app.admin.question_router import router as admin_question_router
from app.admin.router import router as admin_auth_router
from app.admin.subject_router import router as admin_subject_router
from app.admin.test_router import router as admin_test_router
from app.admin.user_management_router import router as admin_user_management_router
from app.bootstrap import run_bootstrap

app = FastAPI(title='UPSC Admin API', version='1.0.0')
logger = logging.getLogger('admin.healthcheck')

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


async def _check_health_once() -> None:
    def _db_ping() -> None:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))

    try:
        await asyncio.to_thread(_db_ping)
        logger.info('health_check_ok', extra={'interval_seconds': 30, 'database': 'reachable'})
    except Exception as exc:
        logger.exception('health_check_failed', extra={'interval_seconds': 30, 'error': str(exc)})


async def _health_check_loop() -> None:
    while True:
        await _check_health_once()
        await asyncio.sleep(30)


@app.on_event('startup')
async def on_startup() -> None:
    run_bootstrap()
    app.state.health_check_task = asyncio.create_task(_health_check_loop())


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


@app.on_event('shutdown')
async def on_shutdown() -> None:
    task = getattr(app.state, 'health_check_task', None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            logger.info('health_check_stopped')


api_v1 = APIRouter(prefix='/api/v1')
api_v1.include_router(admin_auth_router, prefix='/admin')
api_v1.include_router(admin_analytics_router, prefix='/admin')
api_v1.include_router(admin_dashboard_router, prefix='/admin')
api_v1.include_router(admin_exam_router, prefix='/admin')
api_v1.include_router(admin_subject_router, prefix='/admin')
api_v1.include_router(admin_question_router, prefix='/admin')
api_v1.include_router(admin_pyq_router, prefix='/admin')
api_v1.include_router(admin_test_router, prefix='/admin')
api_v1.include_router(admin_user_management_router, prefix='/admin')
api_v1.include_router(admin_payment_router, prefix='/admin')
api_v1.include_router(admin_platform_settings_router, prefix='/admin')
api_v1.include_router(admin_notification_router, prefix='/admin')
# Public plan listing for UI
api_v1.include_router(subscription_router)

app.include_router(api_v1)
