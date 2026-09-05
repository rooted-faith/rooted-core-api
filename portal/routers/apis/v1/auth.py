"""
App (End user) authentication HTTP routes.
"""

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, status

from portal.application.auth.app_auth_service import AppAuthService
from portal.application.auth.commands import AppMagicLinkRequestCommand, AppMagicLinkVerifyCommand, LogoutCommand, RefreshTokenCommand
from portal.application.auth.mappers import magic_link_request_result_to_api, member_login_result_to_api, token_result_to_api
from portal.application.auth.refresh_token_service import RefreshTokenService
from portal.container import Container
from portal.libs.depends.rate_limiters import WRITE_RATE_LIMITERS
from portal.routers.auth_router import AuthRouter
from portal.serializers.apis.v1.auth import MemberLoginResponse, MemberMagicLinkRequest, MemberMagicLinkRequestResponse, MemberMagicLinkVerifyRequest
from portal.serializers.mixins import LogoutRequest, LogoutResponse, RefreshTokenRequest, TokenResponse

router: AuthRouter = AuthRouter()


@router.post(
    "/magic-link",
    response_model=MemberMagicLinkRequestResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    require_auth=False,
    dependencies=[*WRITE_RATE_LIMITERS],
)
@inject
async def app_request_magic_link(body: MemberMagicLinkRequest, app_auth_service: AppAuthService = Depends(Provide[Container.app_auth_service])):
    result = await app_auth_service.request_magic_link(AppMagicLinkRequestCommand(email=body.email))
    return magic_link_request_result_to_api(result)


@router.post(
    "/verify",
    response_model=MemberLoginResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    require_auth=False,
    dependencies=[*WRITE_RATE_LIMITERS],
)
@inject
async def app_verify_magic_link(body: MemberMagicLinkVerifyRequest, app_auth_service: AppAuthService = Depends(Provide[Container.app_auth_service])):
    result = await app_auth_service.verify_magic_link(AppMagicLinkVerifyCommand(email=body.email, token=body.token))
    return member_login_result_to_api(result)


@router.post("/refresh", response_model=TokenResponse, response_model_by_alias=True, require_auth=False)
@inject
async def app_refresh_token(body: RefreshTokenRequest, refresh_token_service: RefreshTokenService = Depends(Provide[Container.refresh_token_service])):
    result = await refresh_token_service.refresh_member_token(RefreshTokenCommand(refresh_token=body.refresh_token))
    return token_result_to_api(result)


@router.post("/logout", response_model=LogoutResponse, response_model_by_alias=True, require_auth=False)
@inject
async def app_logout(body: LogoutRequest, refresh_token_service: RefreshTokenService = Depends(Provide[Container.refresh_token_service])):
    await refresh_token_service.logout_member(LogoutCommand(access_token=body.access_token, refresh_token=body.refresh_token))
    return LogoutResponse(message="Logged out")
