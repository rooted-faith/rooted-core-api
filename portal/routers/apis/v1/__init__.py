"""
v1 API router
"""

from fastapi import APIRouter

from .app_support import router as app_support_router
from .auth import router as auth_router
from .bible import router as bible_router
from .devotion import router as devotion_router
from .push import router as push_router
from .user import router as user_router

router = APIRouter()

router.include_router(app_support_router, prefix="/app-support", tags=["App support"])
router.include_router(auth_router, prefix="/auth", tags=["Auth"])
router.include_router(bible_router, prefix="/bible", tags=["Bible"])
router.include_router(devotion_router, prefix="/devotion", tags=["Devotion"])
router.include_router(push_router, prefix="/push", tags=["Push"])
router.include_router(user_router, prefix="/users", tags=["Users"])
