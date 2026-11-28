"""
App support policy API router (ADR 0017, docs/api/app-support-policy.md)
"""

from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, Query, Response
from starlette import status

from portal.application.app_support.app_support_service import AppSupportService
from portal.application.app_support.mappers import app_support_policy_to_api
from portal.container import Container
from portal.routers.auth_router import AuthRouter
from portal.serializers.apis.v1.app_support import AppSupportPolicyResponse

router: AuthRouter = AuthRouter(require_auth=False)


@router.get(
    path="/policy",
    response_model=AppSupportPolicyResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    operation_id="get_app_support_policy",
    summary="Get the minimum supported App build",
    description=(
        "Unauthenticated and never subject to the App build gate. The backend environment is resolved by the server. "
        "400 APP_IDENTITY_INVALID for an unknown platform; 503 APP_SUPPORT_POLICY_UNAVAILABLE when no valid policy is configured."
    ),
)
@inject
async def get_app_support_policy(
    response: Response,
    platform: Annotated[str | None, Query(description="ios or android")] = None,
    app_support_service: AppSupportService = Depends(Provide[Container.app_support_service]),
) -> AppSupportPolicyResponse:
    response.headers["Cache-Control"] = "no-store"
    result = await app_support_service.get_policy(platform)
    return app_support_policy_to_api(result)
