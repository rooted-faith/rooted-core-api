"""
Shared App build gate (ADR 0017, docs/api/app-support-policy.md).

Runs on the App API sub-application only, outside its CoreRequestMiddleware and AuthMiddleware,
so a rejected request opens no App API database session and never reaches auth or a feature route.
Admin routes, /healthz, and webhooks are separate mounts and never pass through it.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from portal.application.app_support.app_support_service import AppSupportService
from portal.exceptions.api_error_response import api_exception_response
from portal.exceptions.responses import ApiBaseException

APP_PLATFORM_HEADER = "X-App-Platform"
APP_BUILD_HEADER = "X-App-Build"

# Paths relative to the App API mount (/api).
APP_SUPPORT_POLICY_PATH = "/v1/app-support/policy"


class AppSupportGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if self._is_exempt(request):
            return await call_next(request)
        app_support_service: AppSupportService = request.app.container.app_support_service()
        try:
            await app_support_service.check_request(platform=request.headers.get(APP_PLATFORM_HEADER), build=request.headers.get(APP_BUILD_HEADER))
        except ApiBaseException as exc:
            return api_exception_response(request, exc)
        return await call_next(request)

    @staticmethod
    def _relative_path(request: Request) -> str:
        root_path = request.scope.get("root_path", "")
        path = request.url.path
        if root_path and path.startswith(root_path):
            path = path[len(root_path) :]
        return path.rstrip("/") or "/"

    def _is_exempt(self, request: Request) -> bool:
        app = request.app
        exempt = {APP_SUPPORT_POLICY_PATH, app.openapi_url, app.docs_url, app.redoc_url, app.swagger_ui_oauth2_redirect_url}
        return self._relative_path(request) in exempt
