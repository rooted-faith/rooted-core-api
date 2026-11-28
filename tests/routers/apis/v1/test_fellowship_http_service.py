"""HTTP handlers with the real FellowshipService (stubbed ports only)."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from portal.application.fellowship.fellowship_service import FellowshipService
from portal.domain.app.entities import EndUser
from portal.domain.fellowship.constants import FellowshipErrorCode
from portal.exceptions.responses import BadRequestException, ForbiddenException
from portal.libs.contexts.user_context import UserContext
from portal.routers.apis.v1 import fellowship as fellowship_router_module
from portal.routers.apis.v1.fellowship import create_fellowship, get_fellowship, set_primary_fellowship
from portal.serializers.apis.v1.fellowship import CreateFellowshipRequest, SetPrimaryFellowshipRequest
from tests.application.fellowship.test_fellowship_service import StubCapacitySettings, StubEndUserRepository, StubFellowshipRepository, StubPrimaryStore

FIXED_NOW = datetime(2026, 11, 28, 12, 0, tzinfo=UTC)


def build_real_service() -> tuple[FellowshipService, EndUser, StubFellowshipRepository, StubPrimaryStore]:
    end_user = EndUser(id=uuid4(), auth_user_id=uuid4())
    repository = StubFellowshipRepository()
    primary_store = StubPrimaryStore()
    service = FellowshipService(
        end_user_repository=StubEndUserRepository(end_user),
        fellowship_repository=repository,
        capacity_settings=StubCapacitySettings(),
        primary_fellowship_store=primary_store,
        clock=lambda: FIXED_NOW,
    )
    return service, end_user, repository, primary_store


@pytest.mark.asyncio
async def test_create_handler_uses_real_service_and_rejects_silent_covenant(monkeypatch) -> None:
    service, end_user, repository, _ = build_real_service()
    monkeypatch.setattr(fellowship_router_module, "get_user_context", lambda: UserContext(user_id=end_user.auth_user_id))

    with pytest.raises(BadRequestException) as raised:
        await create_fellowship(request=CreateFellowshipRequest(name="Northside", covenant_accepted=False), fellowship_service=service)
    assert raised.value.error_code == FellowshipErrorCode.COVENANT_REQUIRED.value
    assert repository.fellowships == {}

    response = await create_fellowship(
        request=CreateFellowshipRequest(name="Northside", discoverability="private", covenant_accepted=True), fellowship_service=service
    )
    payload = response.model_dump(mode="json", by_alias=True)

    assert payload["role"] == "owner"
    assert payload["isPrimary"] is False
    assert "data" not in payload
    assert payload["covenantAcceptedAt"].startswith("2026-11-28T12:00:00")


@pytest.mark.asyncio
async def test_get_and_primary_handlers_deny_inaccessible_fellowship(monkeypatch) -> None:
    service, end_user, _, _ = build_real_service()
    monkeypatch.setattr(fellowship_router_module, "get_user_context", lambda: UserContext(user_id=end_user.auth_user_id))
    created = await create_fellowship(request=CreateFellowshipRequest(name="Mine", covenant_accepted=True), fellowship_service=service)
    other_id = uuid4()

    with pytest.raises(ForbiddenException):
        await get_fellowship(fellowship_id=other_id, fellowship_service=service)

    with pytest.raises(ForbiddenException):
        await set_primary_fellowship(request=SetPrimaryFellowshipRequest(fellowship_id=other_id), fellowship_service=service)

    primary = await set_primary_fellowship(request=SetPrimaryFellowshipRequest(fellowship_id=UUID(str(created.id))), fellowship_service=service)
    assert primary.primary_fellowship_id == created.id
