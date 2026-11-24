"""HTTP route contract for End-user and Admin authentication."""

import contextlib

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from portal.application.auth.commands import AppOtpRequestCommand, AppOtpVerifyCommand
from portal.application.auth.results import OtpRequestResult
from portal.container import Container
from portal.domain.auth.constants import OtpDeliveryMode
from portal.exceptions.responses import UnauthorizedException
from portal.libs.depends.rate_limiters import WRITE_RATE_LIMITERS
from portal.routers.admin.v1.auth import router as admin_auth_router
from portal.routers.apis.v1.auth import router as app_auth_router


def _post_paths(router) -> set[str]:
    return {route.path for route in router.routes if isinstance(route, APIRoute) and "POST" in route.methods}


def test_end_user_password_register_and_login_routes_are_unreachable() -> None:
    post_paths = _post_paths(app_auth_router)

    assert "/register" not in post_paths
    assert "/login" not in post_paths


def test_admin_password_login_route_remains_available() -> None:
    assert "/login" in _post_paths(admin_auth_router)


def test_end_user_apple_login_route_is_available_without_an_admin_equivalent() -> None:
    assert "/apple" in _post_paths(app_auth_router)
    assert "/apple" not in _post_paths(admin_auth_router)


class StubAppAuthService:
    def __init__(self, delivery_mode: OtpDeliveryMode = OtpDeliveryMode.EMAIL):
        self._delivery_mode = delivery_mode
        self.requested: list[AppOtpRequestCommand] = []

    async def request_otp(self, command: AppOtpRequestCommand) -> OtpRequestResult:
        self.requested.append(command)
        return OtpRequestResult(message="acknowledged", delivery_mode=self._delivery_mode)

    async def verify_otp(self, command: AppOtpVerifyCommand):
        raise UnauthorizedException(detail="Invalid or expired passcode")


@pytest.fixture
def otp_client():
    container = Container()
    container.wire(modules=["portal.routers.apis.v1.auth"])
    app = FastAPI()
    app.include_router(app_auth_router, prefix="/auth")
    app.dependency_overrides.update({dependency.dependency: lambda: None for dependency in WRITE_RATE_LIMITERS})

    def build(service: StubAppAuthService) -> TestClient:
        container.app_auth_service.override(service)
        return TestClient(app)

    yield build
    container.unwire()


@pytest.mark.parametrize("delivery_mode", ["email", "fixed"])
def test_otp_request_reports_the_selected_mode_in_camel_case_without_a_wrapper(otp_client, delivery_mode: str) -> None:
    response = otp_client(StubAppAuthService(OtpDeliveryMode(delivery_mode))).post("/auth/otp", json={"email": "alice@test.example.com"})

    assert response.status_code == 200
    assert response.json() == {"message": "acknowledged", "deliveryMode": delivery_mode}


def test_otp_request_ignores_client_attempts_to_select_the_mode(otp_client) -> None:
    service = StubAppAuthService()

    response = otp_client(service).post(
        "/auth/otp", json={"email": "jay@example.com", "deliveryMode": "fixed", "delivery_mode": "fixed"}, headers={"X-Delivery-Mode": "fixed"}
    )

    assert response.json()["deliveryMode"] == "email"
    assert service.requested == [AppOtpRequestCommand(email="jay@example.com")]


@pytest.mark.parametrize("body", ['{"email": "jay@example.com", "code": "482913"}', '{"email": "jay@example.com", "code": "482913"'], ids=["json", "malformed"])
def test_otp_verification_never_logs_the_submitted_code(otp_client, caplog: pytest.LogCaptureFixture, body: str) -> None:
    caplog.set_level("DEBUG")

    with contextlib.suppress(UnauthorizedException):
        otp_client(StubAppAuthService()).post("/auth/otp/verify", content=body, headers={"Content-Type": "application/json"})

    assert "/auth/otp/verify" in caplog.text
    assert "482913" not in caplog.text
