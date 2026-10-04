"""
Public provider webhook routers (no member or admin auth; each verifies its own signature).
"""

from fastapi import APIRouter

from .resend import router as resend_email_events_router

router = APIRouter(prefix="/webhooks")
router.include_router(resend_email_events_router, prefix="/resend")

__all__ = ["router"]
