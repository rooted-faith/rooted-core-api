"""
App (End user) authentication HTTP routes.
"""

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, status

from portal.application.auth.app_auth_service import AppAuthService
from portal.application.auth.commands import AppLoginCommand, AppRegisterCommand, LogoutCommand, RefreshTokenCommand
from portal.application.auth.mappers import member_login_result_to_api, token_result_to_api
from portal.application.auth.refresh_token_service import RefreshTokenService
from portal.container import Container
from portal.routers.auth_router import AuthRouter
from portal.serializers.apis.v1.auth import MemberLoginRequest, MemberLoginResponse, MemberRegisterRequest
from portal.serializers.mixins import LogoutRequest, LogoutResponse, RefreshTokenRequest, TokenResponse

router: AuthRouter = AuthRouter()


@router.post("/register", response_model=MemberLoginResponse, response_model_by_alias=True, status_code=status.HTTP_200_OK, require_auth=False)
@inject
async def app_register(body: MemberRegisterRequest, app_auth_service: AppAuthService = Depends(Provide[Container.app_auth_service])):
    result = await app_auth_service.register(AppRegisterCommand(email=body.email, password=body.password, display_name=body.display_name))
    return member_login_result_to_api(result)


@router.post("/login", response_model=MemberLoginResponse, response_model_by_alias=True, status_code=status.HTTP_200_OK, require_auth=False)
@inject
async def app_login(body: MemberLoginRequest, app_auth_service: AppAuthService = Depends(Provide[Container.app_auth_service])):
    result = await app_auth_service.login(AppLoginCommand(email=body.email, password=body.password))
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
