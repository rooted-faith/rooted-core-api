"""
Content admin API router aggregate.
"""

from portal.routers.auth_router import AuthRouter

from .bible import router as bible_router
from .daily_lesson_schedule import router as daily_lesson_schedule_router
from .devotion import router as devotion_router
from .file import router as file_router
from .legal_document import router as legal_document_router

router = AuthRouter(is_admin=True)
router.include_router(bible_router, prefix="/bible", tags=["Content Bible"])
router.include_router(devotion_router, prefix="/devotions", tags=["Content Devotion"])
router.include_router(daily_lesson_schedule_router, prefix="/daily-lesson-schedule", tags=["Content Daily Lesson Schedule"])
router.include_router(file_router, prefix="/file", tags=["Content File"])
router.include_router(legal_document_router, prefix="/legal-document", tags=["Content Legal Document"])
