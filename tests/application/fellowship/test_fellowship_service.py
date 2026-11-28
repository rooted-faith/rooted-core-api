"""Application seam for Fellowship create/read/Primary preference and capacity."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from portal.application.fellowship.commands import AdmitMemberCommand, CreateFellowshipCommand, SetPrimaryFellowshipCommand
from portal.application.fellowship.fellowship_service import FellowshipService
from portal.domain.app.entities import EndUser
from portal.domain.fellowship.constants import FellowshipDiscoverability, FellowshipErrorCode, FellowshipRole
from portal.domain.fellowship.entities import Fellowship, FellowshipMembership, FellowshipMembershipSummary
from portal.exceptions.responses import BadRequestException, ConflictErrorException, ForbiddenException, UnauthorizedException

FIXED_NOW = datetime(2026, 11, 28, 12, 0, tzinfo=UTC)


class StubEndUserRepository:
    def __init__(self, end_user: EndUser | None):
        self.end_user = end_user

    async def get_by_auth_user_id(self, auth_user_id: UUID):
        if self.end_user is not None and self.end_user.auth_user_id == auth_user_id:
            return self.end_user
        return None


class StubCapacitySettings:
    def __init__(self, max_active_members: int = 50, max_group_members: int = 15):
        self.max_active_members = max_active_members
        self.max_group_members = max_group_members

    async def get_max_active_members(self) -> int:
        return self.max_active_members

    async def get_max_group_members(self) -> int:
        return self.max_group_members


class StubPrimaryStore:
    def __init__(self):
        self.primary_by_user: dict[UUID, UUID | None] = {}

    async def get_primary_fellowship_id(self, user_id: UUID):
        return self.primary_by_user.get(user_id)

    async def set_primary_fellowship_id(self, user_id: UUID, fellowship_id: UUID | None) -> None:
        self.primary_by_user[user_id] = fellowship_id


class StubFellowshipRepository:
    def __init__(self):
        self.fellowships: dict[UUID, Fellowship] = {}
        self.memberships: dict[tuple[UUID, UUID], FellowshipMembership] = {}

    async def insert_fellowship(self, payload: dict) -> None:
        fellowship = Fellowship(id=payload["id"], name=payload["name"], discoverability=FellowshipDiscoverability(payload["discoverability"]))
        self.fellowships[fellowship.id] = fellowship

    async def get_by_id(self, fellowship_id: UUID):
        return self.fellowships.get(fellowship_id)

    async def insert_membership(self, payload: dict) -> None:
        membership = FellowshipMembership(
            id=payload["id"],
            fellowship_id=payload["fellowship_id"],
            user_id=payload["user_id"],
            role=FellowshipRole(payload["role"]),
            covenant_accepted_at=payload.get("covenant_accepted_at"),
        )
        self.memberships[(membership.fellowship_id, membership.user_id)] = membership

    async def get_membership(self, *, fellowship_id: UUID, user_id: UUID):
        return self.memberships.get((fellowship_id, user_id))

    async def list_for_user(self, user_id: UUID):
        items = []
        for membership in self.memberships.values():
            if membership.user_id != user_id:
                continue
            fellowship = self.fellowships[membership.fellowship_id]
            items.append(
                FellowshipMembershipSummary(
                    fellowship_id=fellowship.id,
                    name=fellowship.name,
                    discoverability=fellowship.discoverability,
                    role=membership.role,
                    covenant_accepted_at=membership.covenant_accepted_at,
                )
            )
        return items

    async def count_active_members(self, fellowship_id: UUID) -> int:
        return sum(1 for key in self.memberships if key[0] == fellowship_id)

    async def admit_member_atomically(
        self, *, fellowship_id: UUID, user_id: UUID, role: str, max_active_members: int, covenant_accepted_at, membership_id: UUID
    ) -> bool:
        if await self.count_active_members(fellowship_id) >= max_active_members:
            return False
        await self.insert_membership(
            {"id": membership_id, "fellowship_id": fellowship_id, "user_id": user_id, "role": role, "covenant_accepted_at": covenant_accepted_at}
        )
        return True

    async def accept_covenant(self, *, fellowship_id: UUID, user_id: UUID, accepted_at: datetime):
        membership = self.memberships.get((fellowship_id, user_id))
        if membership is None:
            return None
        if membership.covenant_accepted_at is None:
            membership = membership.model_copy(update={"covenant_accepted_at": accepted_at})
            self.memberships[(fellowship_id, user_id)] = membership
        return membership


def build_service(*, max_active_members: int = 50) -> tuple[FellowshipService, EndUser, StubFellowshipRepository, StubPrimaryStore]:
    end_user = EndUser(id=uuid4(), auth_user_id=uuid4())
    repository = StubFellowshipRepository()
    primary_store = StubPrimaryStore()
    service = FellowshipService(
        end_user_repository=StubEndUserRepository(end_user),
        fellowship_repository=repository,
        capacity_settings=StubCapacitySettings(max_active_members=max_active_members),
        primary_fellowship_store=primary_store,
        clock=lambda: FIXED_NOW,
    )
    return service, end_user, repository, primary_store


@pytest.mark.asyncio
async def test_create_fellowship_rejects_missing_explicit_covenant_acceptance() -> None:
    service, end_user, repository, _ = build_service()

    with pytest.raises(BadRequestException) as raised:
        await service.create_fellowship(auth_user_id=end_user.auth_user_id, command=CreateFellowshipCommand(name="Northside", covenant_accepted=False))

    assert raised.value.error_code == FellowshipErrorCode.COVENANT_REQUIRED.value
    assert repository.fellowships == {}


@pytest.mark.asyncio
async def test_create_fellowship_makes_creator_the_sole_owner_with_covenant() -> None:
    service, end_user, repository, primary_store = build_service()

    result = await service.create_fellowship(
        auth_user_id=end_user.auth_user_id, command=CreateFellowshipCommand(name="Northside", discoverability="private", covenant_accepted=True)
    )

    assert result.role == FellowshipRole.OWNER
    assert result.covenant_accepted_at == FIXED_NOW
    assert result.discoverability == FellowshipDiscoverability.PRIVATE
    assert result.is_primary is False
    assert primary_store.primary_by_user.get(end_user.id) is None
    membership = next(iter(repository.memberships.values()))
    assert membership.role == FellowshipRole.OWNER
    assert sum(1 for m in repository.memberships.values() if m.role == FellowshipRole.OWNER) == 1


@pytest.mark.asyncio
async def test_get_fellowship_denies_cross_fellowship_reads() -> None:
    service, end_user, repository, _ = build_service()
    created = await service.create_fellowship(auth_user_id=end_user.auth_user_id, command=CreateFellowshipCommand(name="Mine", covenant_accepted=True))
    other_id = uuid4()
    repository.fellowships[other_id] = Fellowship(id=other_id, name="Theirs", discoverability=FellowshipDiscoverability.PRIVATE)

    with pytest.raises(ForbiddenException) as raised:
        await service.get_fellowship(auth_user_id=end_user.auth_user_id, fellowship_id=other_id)

    assert raised.value.error_code == FellowshipErrorCode.NOT_MEMBER.value
    assert created.id != other_id


@pytest.mark.asyncio
async def test_set_primary_requires_accessible_membership_and_ignores_browsing() -> None:
    service, end_user, _, primary_store = build_service()
    first = await service.create_fellowship(auth_user_id=end_user.auth_user_id, command=CreateFellowshipCommand(name="First", covenant_accepted=True))
    second = await service.create_fellowship(auth_user_id=end_user.auth_user_id, command=CreateFellowshipCommand(name="Second", covenant_accepted=True))
    assert primary_store.primary_by_user.get(end_user.id) is None

    listed = await service.set_primary_fellowship(auth_user_id=end_user.auth_user_id, command=SetPrimaryFellowshipCommand(fellowship_id=second.id))

    assert listed.primary_fellowship_id == second.id
    assert {item.id: item.is_primary for item in listed.items}[second.id] is True
    assert {item.id: item.is_primary for item in listed.items}[first.id] is False

    with pytest.raises(ForbiddenException):
        await service.set_primary_fellowship(auth_user_id=end_user.auth_user_id, command=SetPrimaryFellowshipCommand(fellowship_id=uuid4()))


@pytest.mark.asyncio
async def test_admit_member_rejects_when_fellowship_is_at_capacity() -> None:
    service, end_user, repository, _ = build_service(max_active_members=1)
    created = await service.create_fellowship(auth_user_id=end_user.auth_user_id, command=CreateFellowshipCommand(name="Full", covenant_accepted=True))

    with pytest.raises(ConflictErrorException) as raised:
        await service.admit_member(command=AdmitMemberCommand(fellowship_id=created.id, user_id=uuid4(), role="member"))

    assert raised.value.error_code == FellowshipErrorCode.FULL.value
    assert await repository.count_active_members(created.id) == 1


@pytest.mark.asyncio
async def test_create_fellowship_rejects_credential_without_end_user() -> None:
    _, _, repository, primary_store = build_service()
    service = FellowshipService(
        end_user_repository=StubEndUserRepository(None),
        fellowship_repository=repository,
        capacity_settings=StubCapacitySettings(),
        primary_fellowship_store=primary_store,
        clock=lambda: FIXED_NOW,
    )

    with pytest.raises(UnauthorizedException):
        await service.create_fellowship(auth_user_id=uuid4(), command=CreateFellowshipCommand(name="X", covenant_accepted=True))
