"""
App (End user) authentication HTTP routes.
"""

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, status

from portal.application.auth.app_apple_auth_service import AppAppleAuthService
from portal.application.auth.app_auth_service import AppAuthService
from portal.application.auth.app_google_auth_service import AppGoogleAuthService
from portal.application.auth.commands import (
    AppAppleLoginCommand,
    AppGoogleLoginCommand,
    AppOtpRequestCommand,
    AppOtpVerifyCommand,
    LogoutCommand,
    RefreshTokenCommand,
)
from portal.application.auth.mappers import member_login_result_to_api, otp_request_result_to_api, token_result_to_api
from portal.application.auth.refresh_token_service import RefreshTokenService
from portal.container import Container
from portal.libs.depends.rate_limiters import WRITE_RATE_LIMITERS
from portal.route_classes.auth_route import UnloggedBodyAuthRoute
from portal.routers.auth_router import AuthRouter
from portal.serializers.apis.v1.auth import (
    MemberAppleLoginRequest,
    MemberGoogleLoginRequest,
    MemberLoginResponse,
    MemberOtpRequest,
    MemberOtpRequestResponse,
    MemberOtpVerifyRequest,
)
from portal.serializers.mixins import LogoutRequest, LogoutResponse, RefreshTokenRequest, TokenResponse

router: AuthRouter = AuthRouter()


@router.post(
    "/otp",
    response_model=MemberOtpRequestResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    require_auth=False,
    dependencies=[*WRITE_RATE_LIMITERS],
    operation_id="request_member_otp",
    summary="Request an email one-time passcode",
    description=(
        "Email a six-digit passcode to the address, or expect the shared test passcode for an eligible test "
        "identity in a non-production environment; `deliveryMode` reports which. The acknowledgement never "
        "depends on whether the email has an account, and repeated requests for the same email are throttled (429)."
    ),
)
@inject
async def app_request_otp(body: MemberOtpRequest, app_auth_service: AppAuthService = Depends(Provide[Container.app_auth_service])):
    result = await app_auth_service.request_otp(AppOtpRequestCommand(email=body.email))
    return otp_request_result_to_api(result)


@router.post(
    "/otp/verify",
    response_model=MemberLoginResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    require_auth=False,
    dependencies=[*WRITE_RATE_LIMITERS],
    route_class_override=UnloggedBodyAuthRoute,
    operation_id="verify_member_otp",
    summary="Verify an email one-time passcode",
    description="Redeem a live passcode to sign in, provisioning the End user on first use. Every rejection returns the same generic 401.",
)
@inject
async def app_verify_otp(body: MemberOtpVerifyRequest, app_auth_service: AppAuthService = Depends(Provide[Container.app_auth_service])):
    result = await app_auth_service.verify_otp(AppOtpVerifyCommand(email=body.email, code=body.code))
    return member_login_result_to_api(result)


@router.post(
    "/google",
    response_model=MemberLoginResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    require_auth=False,
    dependencies=[*WRITE_RATE_LIMITERS],
    operation_id="member_google_login",
    summary="Sign in with Google",
    description="Resolve a verified Google ID token to an End user, provisioning the account on first success. Every rejection returns the same generic 401.",
)
@inject
async def app_google_login(body: MemberGoogleLoginRequest, app_google_auth_service: AppGoogleAuthService = Depends(Provide[Container.app_google_auth_service])):
    result = await app_google_auth_service.login_with_google(AppGoogleLoginCommand(id_token=body.id_token))
    return member_login_result_to_api(result)


@router.post(
    "/apple",
    response_model=MemberLoginResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    require_auth=False,
    dependencies=[*WRITE_RATE_LIMITERS],
    operation_id="member_apple_login",
    summary="Sign in with Apple",
    description="Resolve a verified Apple identity token to an End user, provisioning the account on first success. Every rejection returns the same generic 401.",
)
@inject
async def app_apple_login(body: MemberAppleLoginRequest, app_apple_auth_service: AppAppleAuthService = Depends(Provide[Container.app_apple_auth_service])):
    result = await app_apple_auth_service.login_with_apple(AppAppleLoginCommand(id_token=body.id_token))
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
