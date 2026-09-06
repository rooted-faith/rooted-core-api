"""
Application-service seam: Admin Google ID-token sign-in (ADR 0006, stub verifier + stub repos).

Happy path: a first success matching by verified email upserts a Google Identity
link on an already admin-eligible Auth credential and returns the same admin
login session shape as password login; a later success resolves by `sub` alone.
Every rejection path (inactive provider, missing Client ID allowlist, invalid
token, unverified email, non-admin-eligible credential) fails generically.
"""

from typing import Any, Optional
from uuid import UUID, uuid4

import pytest

from portal.application.auth.admin_google_auth_service import AdminGoogleAuthService
from portal.application.auth.commands import AdminGoogleLoginCommand
from portal.application.auth.login_service import LoginService
from portal.application.auth.results import LoginResult, UserSensitive
from portal.domain.auth.entities import GoogleIdentityClaims
from portal.exceptions.responses import UnauthorizedException

ALLOWED_CLIENT_IDS = ["web-client-id"]


class StubUserRepository:
    def __init__(self):
        self.by_email: dict[str, UserSensitive] = {}
        self.by_id: dict[UUID, UserSensitive] = {}
        self.identity_links: dict[tuple[str, str], UUID] = {}
        self.link_calls: list[dict[str, Any]] = []
        self.google_provider_active = True
        self.last_login_updates: list[UUID] = []

    def seed_admin(
        self, *, email: str, is_admin: bool = True, verified: bool = True, is_active: bool = True, password_hash: Optional[str] = "hashed:pw"
    ) -> UserSensitive:
        user = UserSensitive(
            id=uuid4(), email=email, password_hash=password_hash, verified=verified, is_active=is_active, is_admin=is_admin, first_name="Ada", last_name="Min"
        )
        self.by_email[email.strip().lower()] = user
        self.by_id[user.id] = user
        return user

    async def identity_provider_is_active(self, code: str) -> bool:
        assert code == "google"
        return self.google_provider_active

    async def get_user_id_by_identity_link(self, provider: str, provider_subject: str, provider_tenant: Optional[str] = None) -> Optional[UUID]:
        return self.identity_links.get((provider, provider_subject))

    async def upsert_identity_link(
        self, user_id: UUID, provider: str, provider_subject: str, *, provider_tenant: Optional[str] = None, additional_data: Optional[dict[str, Any]] = None
    ) -> None:
        self.link_calls.append({"user_id": user_id, "provider": provider, "provider_subject": provider_subject, "additional_data": additional_data})
        self.identity_links[(provider, provider_subject)] = user_id

    async def get_sensitive_by_email(self, email: str) -> Optional[UserSensitive]:
        return self.by_email.get(email.strip().lower())

    async def get_sensitive_by_id(self, user_id: UUID) -> Optional[UserSensitive]:
        return self.by_id.get(user_id)

    async def update_last_login_at(self, user_id: UUID, last_login_at) -> None:
        self.last_login_updates.append(user_id)


class StubGoogleIdTokenVerifier:
    def __init__(self):
        self.claims_by_token: dict[str, GoogleIdentityClaims] = {}

    def register(self, token: str, claims: GoogleIdentityClaims) -> None:
        self.claims_by_token[token] = claims

    async def verify(self, id_token: str, audiences: list[str]) -> Optional[GoogleIdentityClaims]:
        claims = self.claims_by_token.get(id_token)
        if not claims or claims.audience not in audiences:
            return None
        return claims


class StubJwtProvider:
    def create_access_token(self, *args, **kwargs) -> str:
        return "access-token"


class StubRefreshTokenProvider:
    async def issue(self, *, user_id: UUID, device_id: UUID, family_id: UUID) -> str:
        return "refresh-token"


class StubRoleService:
    async def init_user_roles_cache(self, user: UserSensitive, expire: int) -> list[str]:
        return ["admin"]


class StubPermissionService:
    async def init_user_permissions_cache(self, user: UserSensitive, expire: int) -> list[str]:
        return []


def _build_service(
    monkeypatch: pytest.MonkeyPatch, client_ids: list[str] = ALLOWED_CLIENT_IDS
) -> tuple[AdminGoogleAuthService, StubUserRepository, StubGoogleIdTokenVerifier]:
    from portal.config import settings

    monkeypatch.setattr(settings, "GOOGLE_ADMIN_CLIENT_IDS", ",".join(client_ids))

    user_repo = StubUserRepository()
    verifier = StubGoogleIdTokenVerifier()
    login_service = LoginService(
        user_repository=user_repo,
        jwt_provider=StubJwtProvider(),
        refresh_token_provider=StubRefreshTokenProvider(),
        password_provider=None,
        role_service=StubRoleService(),
        permission_service=StubPermissionService(),
    )
    service = AdminGoogleAuthService(user_repository=user_repo, google_id_token_verifier=verifier, login_service=login_service)
    return service, user_repo, verifier


@pytest.mark.asyncio
async def test_first_success_matches_verified_email_and_upserts_link(monkeypatch: pytest.MonkeyPatch):
    service, user_repo, verifier = _build_service(monkeypatch)
    admin = user_repo.seed_admin(email="admin@example.com")
    verifier.register("token-1", GoogleIdentityClaims(subject="google-sub-1", email="Admin@Example.com", email_verified=True, audience="web-client-id"))

    result = await service.login_with_google(AdminGoogleLoginCommand(id_token="token-1"))

    assert isinstance(result, LoginResult)
    assert result.admin.id == admin.id
    assert result.token.access_token == "access-token"
    assert result.token.refresh_token == "refresh-token"
    assert user_repo.link_calls == [
        {"user_id": admin.id, "provider": "google", "provider_subject": "google-sub-1", "additional_data": {"email": "Admin@Example.com"}}
    ]
    assert admin.password_hash == "hashed:pw"  # linking Google never clears password_hash


@pytest.mark.asyncio
async def test_later_success_resolves_by_subject_without_email_lookup(monkeypatch: pytest.MonkeyPatch):
    service, user_repo, verifier = _build_service(monkeypatch)
    admin = user_repo.seed_admin(email="admin@example.com")
    verifier.register("token-1", GoogleIdentityClaims(subject="google-sub-1", email="admin@example.com", email_verified=True, audience="web-client-id"))
    await service.login_with_google(AdminGoogleLoginCommand(id_token="token-1"))

    # Remove the email match path entirely — only the Identity link should resolve the user now.
    user_repo.by_email.clear()
    verifier.register("token-2", GoogleIdentityClaims(subject="google-sub-1", email="admin@example.com", email_verified=True, audience="web-client-id"))

    result = await service.login_with_google(AdminGoogleLoginCommand(id_token="token-2"))

    assert result.admin.id == admin.id
    assert len(user_repo.link_calls) == 1  # no re-upsert needed on subject-match path


@pytest.mark.asyncio
async def test_rejects_when_provider_inactive(monkeypatch: pytest.MonkeyPatch):
    service, user_repo, verifier = _build_service(monkeypatch)
    user_repo.seed_admin(email="admin@example.com")
    user_repo.google_provider_active = False
    verifier.register("token-1", GoogleIdentityClaims(subject="google-sub-1", email="admin@example.com", email_verified=True, audience="web-client-id"))

    with pytest.raises(UnauthorizedException):
        await service.login_with_google(AdminGoogleLoginCommand(id_token="token-1"))
    assert user_repo.link_calls == []


@pytest.mark.asyncio
async def test_rejects_when_client_id_allowlist_empty(monkeypatch: pytest.MonkeyPatch):
    service, user_repo, verifier = _build_service(monkeypatch, client_ids=[])
    user_repo.seed_admin(email="admin@example.com")
    verifier.register("token-1", GoogleIdentityClaims(subject="google-sub-1", email="admin@example.com", email_verified=True, audience="web-client-id"))

    with pytest.raises(UnauthorizedException):
        await service.login_with_google(AdminGoogleLoginCommand(id_token="token-1"))


@pytest.mark.asyncio
async def test_rejects_invalid_or_unverified_token(monkeypatch: pytest.MonkeyPatch):
    service, _user_repo, _verifier = _build_service(monkeypatch)

    with pytest.raises(UnauthorizedException):
        await service.login_with_google(AdminGoogleLoginCommand(id_token="not-a-registered-token"))


@pytest.mark.asyncio
async def test_rejects_wrong_audience(monkeypatch: pytest.MonkeyPatch):
    service, user_repo, verifier = _build_service(monkeypatch)
    user_repo.seed_admin(email="admin@example.com")
    verifier.register("token-1", GoogleIdentityClaims(subject="google-sub-1", email="admin@example.com", email_verified=True, audience="other-client-id"))

    with pytest.raises(UnauthorizedException):
        await service.login_with_google(AdminGoogleLoginCommand(id_token="token-1"))


@pytest.mark.asyncio
async def test_rejects_unverified_email(monkeypatch: pytest.MonkeyPatch):
    service, user_repo, verifier = _build_service(monkeypatch)
    user_repo.seed_admin(email="admin@example.com")
    verifier.register("token-1", GoogleIdentityClaims(subject="google-sub-1", email="admin@example.com", email_verified=False, audience="web-client-id"))

    with pytest.raises(UnauthorizedException):
        await service.login_with_google(AdminGoogleLoginCommand(id_token="token-1"))


@pytest.mark.asyncio
async def test_rejects_credential_not_found_without_enumeration(monkeypatch: pytest.MonkeyPatch):
    service, _user_repo, verifier = _build_service(monkeypatch)
    verifier.register("token-1", GoogleIdentityClaims(subject="google-sub-1", email="unknown@example.com", email_verified=True, audience="web-client-id"))

    with pytest.raises(UnauthorizedException):
        await service.login_with_google(AdminGoogleLoginCommand(id_token="token-1"))


@pytest.mark.asyncio
async def test_rejects_credential_not_admin_eligible_and_does_not_link(monkeypatch: pytest.MonkeyPatch):
    service, user_repo, verifier = _build_service(monkeypatch)
    user_repo.seed_admin(email="notadmin@example.com", is_admin=False)
    verifier.register("token-1", GoogleIdentityClaims(subject="google-sub-1", email="notadmin@example.com", email_verified=True, audience="web-client-id"))

    with pytest.raises(UnauthorizedException):
        await service.login_with_google(AdminGoogleLoginCommand(id_token="token-1"))
    assert user_repo.link_calls == []


@pytest.mark.asyncio
async def test_rejects_unverified_admin_credential_and_does_not_link(monkeypatch: pytest.MonkeyPatch):
    service, user_repo, verifier = _build_service(monkeypatch)
    user_repo.seed_admin(email="admin@example.com", verified=False)
    verifier.register("token-1", GoogleIdentityClaims(subject="google-sub-1", email="admin@example.com", email_verified=True, audience="web-client-id"))

    with pytest.raises(UnauthorizedException):
        await service.login_with_google(AdminGoogleLoginCommand(id_token="token-1"))
    assert user_repo.link_calls == []


@pytest.mark.asyncio
async def test_rejects_inactive_admin_credential_and_does_not_link(monkeypatch: pytest.MonkeyPatch):
    service, user_repo, verifier = _build_service(monkeypatch)
    user_repo.seed_admin(email="admin@example.com", is_active=False)
    verifier.register("token-1", GoogleIdentityClaims(subject="google-sub-1", email="admin@example.com", email_verified=True, audience="web-client-id"))

    with pytest.raises(UnauthorizedException):
        await service.login_with_google(AdminGoogleLoginCommand(id_token="token-1"))
    assert user_repo.link_calls == []


@pytest.mark.asyncio
async def test_rejects_linked_subject_whose_credential_is_no_longer_admin_eligible(monkeypatch: pytest.MonkeyPatch):
    """A pre-existing Google link must fail the same generic way as every other rejection once its
    credential is demoted/deactivated/unverified — not leak LoginService's distinct admin-portal message."""
    service, user_repo, verifier = _build_service(monkeypatch)
    admin = user_repo.seed_admin(email="admin@example.com")
    verifier.register("token-1", GoogleIdentityClaims(subject="google-sub-1", email="admin@example.com", email_verified=True, audience="web-client-id"))
    await service.login_with_google(AdminGoogleLoginCommand(id_token="token-1"))

    admin.is_admin = False  # demoted after the link was created

    with pytest.raises(UnauthorizedException) as exc_info:
        await service.login_with_google(AdminGoogleLoginCommand(id_token="token-1"))
    assert exc_info.value.detail == "Google sign-in failed"
