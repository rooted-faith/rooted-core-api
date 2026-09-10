"""Application-service seam for End-user Apple identity-token sign-in."""

from typing import Optional

import pytest

from portal.application.app.end_user_provisioning_service import EndUserProvisioningService
from portal.application.auth.app_apple_auth_service import GENERIC_FAILURE_DETAIL, AppAppleAuthService
from portal.application.auth.commands import AppAppleLoginCommand
from portal.application.auth.member_login_service import MemberLoginService
from portal.application.auth.results import MemberLoginResult
from portal.domain.auth.entities import AppleIdentityClaims
from portal.exceptions.responses import UnauthorizedException
from tests.application.auth.test_app_google_auth_service import (
    StubEndUserRepository,
    StubJwtProvider,
    StubMemberRefreshAppBindingProvider,
    StubMemberWebAppRegistry,
    StubPasswordProvider,
    StubPreferencesRepository,
    StubRefreshTokenProvider,
    StubUserRepository,
)

ALLOWED_CLIENT_IDS = ["com.rooted.app"]


class StubAppleIdTokenVerifier:
    def __init__(self):
        self.claims_by_token: dict[str, AppleIdentityClaims] = {}

    def register(self, token: str, claims: AppleIdentityClaims) -> None:
        self.claims_by_token[token] = claims

    async def verify(self, id_token: str, audiences: list[str]) -> Optional[AppleIdentityClaims]:
        claims = self.claims_by_token.get(id_token)
        if not claims or claims.audience not in audiences:
            return None
        return claims


def _build_service(monkeypatch: pytest.MonkeyPatch, client_ids: list[str] = ALLOWED_CLIENT_IDS):
    from portal.config import settings

    monkeypatch.setattr(settings, "APPLE_APP_CLIENT_IDS", ",".join(client_ids))
    user_repo = StubUserRepository()
    user_repo.apple_provider_active = True
    original_provider_check = user_repo.identity_provider_is_active

    async def provider_is_active(code: str) -> bool:
        if code == "apple":
            return user_repo.apple_provider_active
        return await original_provider_check(code)

    user_repo.identity_provider_is_active = provider_is_active
    end_user_repo = StubEndUserRepository()
    prefs_repo = StubPreferencesRepository()
    verifier = StubAppleIdTokenVerifier()
    provisioning = EndUserProvisioningService(user_repo, end_user_repo, prefs_repo, StubPasswordProvider())
    login = MemberLoginService(
        user_repo, prefs_repo, StubJwtProvider(), StubRefreshTokenProvider(), StubMemberRefreshAppBindingProvider(), StubMemberWebAppRegistry()
    )
    service = AppAppleAuthService(provisioning, user_repo, end_user_repo, verifier, login)
    return service, user_repo, end_user_repo, prefs_repo, verifier


def _claims(subject="apple-sub-1", email="jay@example.com", email_verified=True, audience="com.rooted.app"):
    return AppleIdentityClaims(subject=subject, email=email, email_verified=email_verified, audience=audience)


@pytest.mark.asyncio
async def test_first_success_provisions_a_brand_new_account_and_links_it(monkeypatch: pytest.MonkeyPatch):
    service, user_repo, end_user_repo, prefs_repo, verifier = _build_service(monkeypatch)
    verifier.register("token-1", _claims(email="Jay@Example.com"))

    result = await service.login_with_apple(AppAppleLoginCommand(id_token="token-1"))

    assert isinstance(result, MemberLoginResult)
    credential = user_repo.by_email["jay@example.com"]
    end_user = end_user_repo.by_auth_user_id[credential.id]
    assert result.member.id == end_user.id
    assert prefs_repo.by_user_id[end_user.id].display_name == "jay"
    assert user_repo.link_calls == [
        {"user_id": credential.id, "provider": "apple", "provider_subject": "apple-sub-1", "additional_data": {"email": "Jay@Example.com"}}
    ]


@pytest.mark.asyncio
async def test_existing_identity_link_resolves_before_email_match(monkeypatch: pytest.MonkeyPatch):
    service, user_repo, end_user_repo, _prefs, verifier = _build_service(monkeypatch)
    verifier.register("token-1", _claims())
    first = await service.login_with_apple(AppAppleLoginCommand(id_token="token-1"))
    user_repo.by_email.clear()

    verifier.register("token-2", _claims(email=None, email_verified=False))
    second = await service.login_with_apple(AppAppleLoginCommand(id_token="token-2"))

    assert second.member.id == first.member.id
    assert len(end_user_repo.by_auth_user_id) == 1
    assert len(user_repo.link_calls) == 1


@pytest.mark.asyncio
async def test_verified_email_matches_existing_end_user_and_upserts_link(monkeypatch: pytest.MonkeyPatch):
    service, user_repo, end_user_repo, _prefs, verifier = _build_service(monkeypatch)
    credential = user_repo.seed_credential(email="jay@example.com")
    end_user = end_user_repo.seed(credential.id)
    verifier.register("token-1", _claims(email="JAY@example.com"))

    result = await service.login_with_apple(AppAppleLoginCommand(id_token="token-1"))

    assert result.member.id == end_user.id
    assert user_repo.link_calls[0]["provider"] == "apple"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["inactive_provider", "no_audience", "invalid_token", "unverified_email", "inactive_user", "admin_only"])
async def test_every_rejection_uses_the_same_generic_failure(monkeypatch: pytest.MonkeyPatch, failure: str):
    client_ids = [] if failure == "no_audience" else ALLOWED_CLIENT_IDS
    service, user_repo, end_user_repo, _prefs, verifier = _build_service(monkeypatch, client_ids)
    claims = _claims(email_verified=failure != "unverified_email")
    if failure != "invalid_token":
        verifier.register("token-1", claims)
    if failure == "inactive_provider":
        user_repo.apple_provider_active = False
    if failure == "inactive_user":
        credential = user_repo.seed_credential(email=claims.email, is_active=False)
        end_user_repo.seed(credential.id)
    if failure == "admin_only":
        user_repo.seed_credential(email=claims.email, is_admin=True, has_admin_profile=True)

    with pytest.raises(UnauthorizedException) as exc_info:
        await service.login_with_apple(AppAppleLoginCommand(id_token="token-1"))

    assert exc_info.value.detail == GENERIC_FAILURE_DETAIL
