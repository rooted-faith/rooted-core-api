"""
v1 API router
"""

from fastapi import APIRouter

from .auth import router as auth_router
from .bible import router as bible_router
from .push import router as push_router

router = APIRouter()

router.include_router(auth_router, prefix="/auth", tags=["Auth"])
router.include_router(bible_router, prefix="/bible", tags=["Bible"])
router.include_router(push_router, prefix="/push", tags=["Push"])
