"""
Root router
"""

from portal.routers.auth_router import AuthRouter

from .v1 import router as api_v1_router

router: AuthRouter = AuthRouter(require_auth=False)
router.include_router(api_v1_router, prefix="/v1")
