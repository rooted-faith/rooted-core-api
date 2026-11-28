"""Create, read, and prefer Fellowships for authenticated End users."""

from datetime import UTC, datetime
from typing import Callable, Optional
from uuid import UUID, uuid4

from portal.application.fellowship.commands import AcceptCovenantCommand, AdmitMemberCommand, CreateFellowshipCommand, SetPrimaryFellowshipCommand
from portal.application.fellowship.results import FellowshipListResult, FellowshipResult
from portal.domain.app.ports import EndUserRepositoryPort
from portal.domain.fellowship.constants import DEFAULT_FELLOWSHIP_MAX_ACTIVE_MEMBERS, FellowshipDiscoverability, FellowshipErrorCode, FellowshipRole
from portal.domain.fellowship.ports import FellowshipCapacitySettingsPort, FellowshipRepositoryPort, PrimaryFellowshipStorePort
from portal.exceptions.responses import BadRequestException, ConflictErrorException, ForbiddenException, NotFoundException, UnauthorizedException
from portal.libs.tracing.distributed_trace import distributed_trace


class FellowshipService:
    """Fellowship create/read/Primary preference and capacity-gated admission."""

    def __init__(
        self,
        end_user_repository: EndUserRepositoryPort,
        fellowship_repository: FellowshipRepositoryPort,
        capacity_settings: FellowshipCapacitySettingsPort,
        primary_fellowship_store: PrimaryFellowshipStorePort,
        clock: Optional[Callable[[], datetime]] = None,
    ):
        self._end_user_repository = end_user_repository
        self._fellowship_repository = fellowship_repository
        self._capacity_settings = capacity_settings
        self._primary_fellowship_store = primary_fellowship_store
        self._clock = clock or (lambda: datetime.now(UTC))

    async def _require_end_user(self, auth_user_id: UUID):
        end_user = await self._end_user_repository.get_by_auth_user_id(auth_user_id)
        if end_user is None:
            raise UnauthorizedException(detail="This credential has no End user")
        return end_user

    @staticmethod
    def _parse_discoverability(value: str) -> FellowshipDiscoverability:
        try:
            return FellowshipDiscoverability(value)
        except ValueError as exc:
            raise BadRequestException(detail="discoverability must be public or private", error_code=FellowshipErrorCode.INVALID_DISCOVERABILITY.value) from exc

    def _to_result(
        self,
        *,
        fellowship_id: UUID,
        name: str,
        discoverability: FellowshipDiscoverability,
        role: FellowshipRole,
        covenant_accepted_at: Optional[datetime],
        primary_fellowship_id: Optional[UUID],
    ) -> FellowshipResult:
        return FellowshipResult(
            id=fellowship_id,
            name=name,
            discoverability=discoverability,
            role=role,
            covenant_accepted_at=covenant_accepted_at,
            is_primary=primary_fellowship_id is not None and fellowship_id == primary_fellowship_id,
        )

    @distributed_trace()
    async def create_fellowship(self, *, auth_user_id: UUID, command: CreateFellowshipCommand) -> FellowshipResult:
        end_user = await self._require_end_user(auth_user_id)
        if command.covenant_accepted is not True:
            raise BadRequestException(
                detail="Creating a Fellowship requires explicit Covenant acceptance", error_code=FellowshipErrorCode.COVENANT_REQUIRED.value
            )
        discoverability = self._parse_discoverability(command.discoverability)
        fellowship_id = uuid4()
        membership_id = uuid4()
        accepted_at = self._clock()
        await self._fellowship_repository.insert_fellowship({"id": fellowship_id, "name": command.name.strip(), "discoverability": discoverability.value})
        await self._fellowship_repository.insert_membership(
            {
                "id": membership_id,
                "fellowship_id": fellowship_id,
                "user_id": end_user.id,
                "role": FellowshipRole.OWNER.value,
                "covenant_accepted_at": accepted_at,
            }
        )
        primary_id = await self._primary_fellowship_store.get_primary_fellowship_id(end_user.id)
        return self._to_result(
            fellowship_id=fellowship_id,
            name=command.name.strip(),
            discoverability=discoverability,
            role=FellowshipRole.OWNER,
            covenant_accepted_at=accepted_at,
            primary_fellowship_id=primary_id,
        )

    @distributed_trace()
    async def list_fellowships(self, *, auth_user_id: UUID) -> FellowshipListResult:
        end_user = await self._require_end_user(auth_user_id)
        primary_id = await self._primary_fellowship_store.get_primary_fellowship_id(end_user.id)
        rows = await self._fellowship_repository.list_for_user(end_user.id)
        items = [
            self._to_result(
                fellowship_id=row.fellowship_id,
                name=row.name,
                discoverability=row.discoverability,
                role=row.role,
                covenant_accepted_at=row.covenant_accepted_at,
                primary_fellowship_id=primary_id,
            )
            for row in rows
        ]
        return FellowshipListResult(items=items, primary_fellowship_id=primary_id)

    @distributed_trace()
    async def get_fellowship(self, *, auth_user_id: UUID, fellowship_id: UUID) -> FellowshipResult:
        end_user = await self._require_end_user(auth_user_id)
        membership = await self._fellowship_repository.get_membership(fellowship_id=fellowship_id, user_id=end_user.id)
        fellowship = await self._fellowship_repository.get_by_id(fellowship_id)
        if membership is None or fellowship is None:
            raise ForbiddenException(detail="Fellowship is not accessible", error_code=FellowshipErrorCode.NOT_MEMBER.value)
        primary_id = await self._primary_fellowship_store.get_primary_fellowship_id(end_user.id)
        return self._to_result(
            fellowship_id=fellowship.id,
            name=fellowship.name,
            discoverability=fellowship.discoverability,
            role=membership.role,
            covenant_accepted_at=membership.covenant_accepted_at,
            primary_fellowship_id=primary_id,
        )

    @distributed_trace()
    async def accept_covenant(self, *, auth_user_id: UUID, command: AcceptCovenantCommand) -> FellowshipResult:
        end_user = await self._require_end_user(auth_user_id)
        membership = await self._fellowship_repository.accept_covenant(fellowship_id=command.fellowship_id, user_id=end_user.id, accepted_at=self._clock())
        if membership is None:
            raise ForbiddenException(detail="Fellowship is not accessible", error_code=FellowshipErrorCode.NOT_MEMBER.value)
        return await self.get_fellowship(auth_user_id=auth_user_id, fellowship_id=command.fellowship_id)

    @distributed_trace()
    async def set_primary_fellowship(self, *, auth_user_id: UUID, command: SetPrimaryFellowshipCommand) -> FellowshipListResult:
        end_user = await self._require_end_user(auth_user_id)
        if command.fellowship_id is not None:
            membership = await self._fellowship_repository.get_membership(fellowship_id=command.fellowship_id, user_id=end_user.id)
            if membership is None:
                raise ForbiddenException(detail="Primary Fellowship requires an accessible membership", error_code=FellowshipErrorCode.NOT_MEMBER.value)
        await self._primary_fellowship_store.set_primary_fellowship_id(end_user.id, command.fellowship_id)
        return await self.list_fellowships(auth_user_id=auth_user_id)

    @distributed_trace()
    async def admit_member(self, *, command: AdmitMemberCommand) -> FellowshipResult:
        """Admit a member with atomic capacity enforcement (used by invitation flows)."""
        fellowship = await self._fellowship_repository.get_by_id(command.fellowship_id)
        if fellowship is None:
            raise NotFoundException(detail="Fellowship not found", error_code=FellowshipErrorCode.NOT_FOUND.value)
        existing = await self._fellowship_repository.get_membership(fellowship_id=command.fellowship_id, user_id=command.user_id)
        if existing is not None:
            raise ConflictErrorException(detail="Already a member of this Fellowship", error_code=FellowshipErrorCode.ALREADY_MEMBER.value)
        try:
            role = FellowshipRole(command.role)
        except ValueError as exc:
            raise BadRequestException(detail="Invalid Fellowship role") from exc
        if role == FellowshipRole.OWNER:
            raise BadRequestException(detail="Admission cannot create a second Owner")
        max_members = await self._capacity_settings.get_max_active_members()
        if max_members <= 0:
            max_members = DEFAULT_FELLOWSHIP_MAX_ACTIVE_MEMBERS
        covenant_accepted_at = self._clock() if command.covenant_accepted else None
        admitted = await self._fellowship_repository.admit_member_atomically(
            fellowship_id=command.fellowship_id,
            user_id=command.user_id,
            role=role.value,
            max_active_members=max_members,
            covenant_accepted_at=covenant_accepted_at,
            membership_id=uuid4(),
        )
        if not admitted:
            raise ConflictErrorException(detail="Fellowship is at capacity", error_code=FellowshipErrorCode.FULL.value)
        membership = await self._fellowship_repository.get_membership(fellowship_id=command.fellowship_id, user_id=command.user_id)
        assert membership is not None
        return self._to_result(
            fellowship_id=fellowship.id,
            name=fellowship.name,
            discoverability=fellowship.discoverability,
            role=membership.role,
            covenant_accepted_at=membership.covenant_accepted_at,
            primary_fellowship_id=None,
        )
