"""HTTP seam for Fellowship create/read/list/Primary preference routes."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute

from portal.application.fellowship.results import FellowshipListResult, FellowshipResult
from portal.domain.fellowship.constants import FellowshipDiscoverability, FellowshipRole
from portal.libs.contexts.user_context import UserContext
from portal.routers.apis.v1 import fellowship as fellowship_router_module
from portal.routers.apis.v1.fellowship import accept_fellowship_covenant, create_fellowship, get_fellowship, list_fellowships, router, set_primary_fellowship
from portal.serializers.apis.v1.fellowship import CreateFellowshipRequest, SetPrimaryFellowshipRequest

FIXED_NOW = datetime(2026, 11, 28, 12, 0, tzinfo=UTC)
FELLOWSHIP_ID = uuid4()


class StubFellowshipService:
    def __init__(self):
        self.created_command = None
        self.primary_command = None

    async def create_fellowship(self, *, auth_user_id, command):
        self.created_command = command
        return FellowshipResult(
            id=FELLOWSHIP_ID,
            name=command.name,
            discoverability=FellowshipDiscoverability(command.discoverability),
            role=FellowshipRole.OWNER,
            covenant_accepted_at=FIXED_NOW,
            is_primary=True,
        )

    async def list_fellowships(self, *, auth_user_id):
        return FellowshipListResult(
            items=[
                FellowshipResult(
                    id=FELLOWSHIP_ID,
                    name="Northside",
                    discoverability=FellowshipDiscoverability.PRIVATE,
                    role=FellowshipRole.OWNER,
                    covenant_accepted_at=FIXED_NOW,
                    is_primary=True,
                )
            ],
            primary_fellowship_id=FELLOWSHIP_ID,
        )

    async def get_fellowship(self, *, auth_user_id, fellowship_id):
        return FellowshipResult(
            id=fellowship_id,
            name="Northside",
            discoverability=FellowshipDiscoverability.PRIVATE,
            role=FellowshipRole.OWNER,
            covenant_accepted_at=FIXED_NOW,
            is_primary=True,
        )

    async def set_primary_fellowship(self, *, auth_user_id, command):
        self.primary_command = command
        return await self.list_fellowships(auth_user_id=auth_user_id)

    async def accept_covenant(self, *, auth_user_id, command):
        return await self.get_fellowship(auth_user_id=auth_user_id, fellowship_id=command.fellowship_id)


def stub_auth(monkeypatch, user_id=None):
    monkeypatch.setattr(fellowship_router_module, "get_user_context", lambda: UserContext(user_id=user_id or uuid4()))


def test_fellowship_routes_require_authentication():
    routes = [route for route in router.routes if isinstance(route, APIRoute)]
    paths = {route.path: route for route in routes}
    assert "" in paths or "/" in {route.path for route in routes} or any(route.path == "" for route in routes)
    for route in routes:
        assert route.endpoint.__auth_config__.require_auth is True


@pytest.mark.asyncio
async def test_create_fellowship_response_is_camel_case_without_data_wrapper(monkeypatch):
    stub_auth(monkeypatch)
    service = StubFellowshipService()

    response = await create_fellowship(
        request=CreateFellowshipRequest(name="Northside", discoverability="private", covenant_accepted=True), fellowship_service=service
    )
    payload = response.model_dump(mode="json", by_alias=True)

    assert "data" not in payload
    assert payload["covenantAcceptedAt"] == FIXED_NOW.isoformat().replace("+00:00", "Z") or payload["covenantAcceptedAt"].startswith("2026-11-28T12:00:00")
    assert payload["isPrimary"] is True
    assert payload["role"] == "owner"
    assert service.created_command.covenant_accepted is True


@pytest.mark.asyncio
async def test_list_and_primary_responses_include_primary_fellowship_id(monkeypatch):
    stub_auth(monkeypatch)
    service = StubFellowshipService()

    listed = await list_fellowships(fellowship_service=service)
    primary = await set_primary_fellowship(request=SetPrimaryFellowshipRequest(fellowship_id=FELLOWSHIP_ID), fellowship_service=service)

    listed_payload = listed.model_dump(mode="json", by_alias=True)
    primary_payload = primary.model_dump(mode="json", by_alias=True)

    assert listed_payload["primaryFellowshipId"] == str(FELLOWSHIP_ID)
    assert primary_payload["items"][0]["isPrimary"] is True
    assert service.primary_command.fellowship_id == FELLOWSHIP_ID


@pytest.mark.asyncio
async def test_get_and_covenant_routes_return_fellowship(monkeypatch):
    stub_auth(monkeypatch)
    service = StubFellowshipService()

    detail = await get_fellowship(fellowship_id=FELLOWSHIP_ID, fellowship_service=service)
    accepted = await accept_fellowship_covenant(fellowship_id=FELLOWSHIP_ID, fellowship_service=service)

    assert detail.id == FELLOWSHIP_ID
    assert accepted.id == FELLOWSHIP_ID
