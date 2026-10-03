"""
Application-service seam: End user provisioning (stub ports).

Covers app signup (credential + End user + Preferences) and admin-only
credential path that skips app.user.
"""

from datetime import time
from typing import Optional
from uuid import UUID, uuid4

import pytest

from portal.application.app.commands import ProvisionIdentityCommand
from portal.application.app.end_user_provisioning_service import EndUserProvisioningService
from portal.domain.app.entities import EndUser, UserPreferences
from portal.exceptions.responses import ApiBaseException


class StubPasswordProvider:
    def validate_password(self, password: str) -> bool:
        return len(password) >= 8

    def hash_password(self, password: str) -> str:
        return f"hashed:{password}"


class StubUserRepository:
    def __init__(self):
        self.created: list[dict] = []

    async def create_credential(
        self, *, auth_user_id: UUID, email: str, password_hash: Optional[str], is_admin: bool, is_superuser: bool = False, verified: bool = False
    ) -> UUID:
        self.created.append(
            {
                "auth_user_id": auth_user_id,
                "email": email,
                "password_hash": password_hash,
                "is_admin": is_admin,
                "is_superuser": is_superuser,
                "verified": verified,
            }
        )
        return auth_user_id


class StubEndUserRepository:
    def __init__(self):
        self.created: list[EndUser] = []

    async def create_end_user(self, *, end_user_id: UUID, auth_user_id: UUID) -> EndUser:
        end_user = EndUser(id=end_user_id, auth_user_id=auth_user_id)
        self.created.append(end_user)
        return end_user


class StubPreferencesRepository:
    def __init__(self):
        self.created: list[UserPreferences] = []

    async def create_preferences(self, preferences: UserPreferences) -> UserPreferences:
        self.created.append(preferences)
        return preferences


class StubBibleRepository:
    def __init__(self, active_youversion_bible_ids: set[str] | None = None):
        self.active_youversion_bible_ids = active_youversion_bible_ids or {"113", "1392", "36"}

    async def youversion_bible_id_is_active(self, youversion_bible_id: str) -> bool:
        return youversion_bible_id in self.active_youversion_bible_ids


def _build_service(
    user_repo: StubUserRepository | None = None,
    end_user_repo: StubEndUserRepository | None = None,
    prefs_repo: StubPreferencesRepository | None = None,
    bible_repo: StubBibleRepository | None = None,
) -> tuple[EndUserProvisioningService, StubUserRepository, StubEndUserRepository, StubPreferencesRepository]:
    user_repo = user_repo or StubUserRepository()
    end_user_repo = end_user_repo or StubEndUserRepository()
    prefs_repo = prefs_repo or StubPreferencesRepository()
    bible_repo = bible_repo or StubBibleRepository()
    service = EndUserProvisioningService(
        user_repository=user_repo,
        end_user_repository=end_user_repo,
        preferences_repository=prefs_repo,
        bible_repository=bible_repo,
        password_provider=StubPasswordProvider(),
    )
    return service, user_repo, end_user_repo, prefs_repo


@pytest.mark.asyncio
async def test_register_end_user_creates_credential_end_user_and_preferences():
    service, user_repo, end_user_repo, prefs_repo = _build_service()
    command = ProvisionIdentityCommand(
        email="member@example.com",
        password="Secure1!",
        display_name="林安",
        theme="system",
        font_scale="M",
        locale_code="zh-TW",
        stage="growing",
        reminder_time=time(7, 30),
        reminder_enabled=True,
        create_end_user=True,
    )

    result = await service.provision(command)

    assert len(user_repo.created) == 1
    assert user_repo.created[0]["email"] == "member@example.com"
    assert user_repo.created[0]["password_hash"] == "hashed:Secure1!"
    assert user_repo.created[0]["is_admin"] is False
    assert user_repo.created[0]["verified"] is True
    assert result.auth_user_id == user_repo.created[0]["auth_user_id"]

    assert len(end_user_repo.created) == 1
    assert end_user_repo.created[0].auth_user_id == result.auth_user_id
    assert end_user_repo.created[0].id == result.end_user_id
    assert result.end_user_id != result.auth_user_id

    assert len(prefs_repo.created) == 1
    prefs = prefs_repo.created[0]
    assert prefs.user_id == result.end_user_id
    assert prefs.display_name == "林安"
    assert not hasattr(prefs, "locale")  # language is per-device, never an account Preference (ADR 0009)
    assert prefs.theme == "system"
    assert prefs.font_scale == "M"
    assert prefs.bible_version == "1392"
    assert prefs.stage == "growing"
    assert prefs.reminder_time == time(7, 30)
    assert prefs.reminder_enabled is True


@pytest.mark.asyncio
async def test_admin_only_provision_skips_end_user_and_preferences():
    service, user_repo, end_user_repo, prefs_repo = _build_service()
    command = ProvisionIdentityCommand(email="admin@example.com", password="Secure1!", create_end_user=False, is_admin=True)

    result = await service.provision(command)

    assert len(user_repo.created) == 1
    assert user_repo.created[0]["is_admin"] is True
    assert user_repo.created[0]["verified"] is False
    assert result.auth_user_id == user_repo.created[0]["auth_user_id"]
    assert result.end_user_id is None
    assert end_user_repo.created == []
    assert prefs_repo.created == []


@pytest.mark.asyncio
async def test_dual_capacity_creates_end_user_with_admin_credential():
    service, user_repo, end_user_repo, prefs_repo = _build_service()
    command = ProvisionIdentityCommand(email="both@example.com", password="Secure1!", display_name="Dual", create_end_user=True, is_admin=True)

    result = await service.provision(command)

    assert user_repo.created[0]["is_admin"] is True
    assert result.end_user_id is not None
    assert result.end_user_id != result.auth_user_id
    assert len(end_user_repo.created) == 1
    assert len(prefs_repo.created) == 1


@pytest.mark.asyncio
async def test_passwordless_provision_creates_credential_without_password_hash():
    service, user_repo, end_user_repo, prefs_repo = _build_service()
    command = ProvisionIdentityCommand(email="member@example.com", password=None, create_end_user=True)

    result = await service.provision(command)

    assert user_repo.created[0]["password_hash"] is None
    assert user_repo.created[0]["verified"] is True
    assert result.end_user_id is not None
    assert prefs_repo.created[0].display_name == "member"
    assert prefs_repo.created[0].bible_version == "113"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("locale_code", "expected_bible_version"),
    [("en-US", "113"), ("zh-Hant", "1392"), ("zh-HK", "1392"), ("zh-Hans-CN", "36"), ("zh-CN", "36"), ("ja-JP", "113"), (None, "113")],
)
async def test_provision_selects_an_active_bible_version_from_the_request_locale(locale_code: str | None, expected_bible_version: str):
    service, _, _, preferences_repository = _build_service()

    await service.provision(ProvisionIdentityCommand(email="member@example.com", password=None, locale_code=locale_code))

    assert preferences_repository.created[0].bible_version == expected_bible_version


@pytest.mark.asyncio
async def test_provision_fails_before_writing_when_the_locale_default_is_not_active():
    user_repository = StubUserRepository()
    end_user_repository = StubEndUserRepository()
    preferences_repository = StubPreferencesRepository()
    service, _, _, _ = _build_service(
        user_repo=user_repository,
        end_user_repo=end_user_repository,
        prefs_repo=preferences_repository,
        bible_repo=StubBibleRepository(active_youversion_bible_ids={"113", "36"}),
    )

    with pytest.raises(ApiBaseException) as exc_info:
        await service.provision(ProvisionIdentityCommand(email="member@example.com", password=None, locale_code="zh-TW"))

    assert exc_info.value.status_code == 503
    assert user_repository.created == []
    assert end_user_repository.created == []
    assert preferences_repository.created == []
