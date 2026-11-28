"""Fellowship domain ports."""

from datetime import datetime
from typing import Optional, Protocol
from uuid import UUID

from portal.domain.fellowship.entities import Fellowship, FellowshipMembership, FellowshipMembershipSummary


class FellowshipRepositoryPort(Protocol):
    """Persistence for Fellowships and memberships."""

    async def insert_fellowship(self, payload: dict) -> None: ...

    async def get_by_id(self, fellowship_id: UUID) -> Optional[Fellowship]: ...

    async def insert_membership(self, payload: dict) -> None: ...

    async def get_membership(self, *, fellowship_id: UUID, user_id: UUID) -> Optional[FellowshipMembership]: ...

    async def list_for_user(self, user_id: UUID) -> list[FellowshipMembershipSummary]: ...

    async def count_active_members(self, fellowship_id: UUID) -> int: ...

    async def admit_member_atomically(
        self, *, fellowship_id: UUID, user_id: UUID, role: str, max_active_members: int, covenant_accepted_at: Optional[datetime], membership_id: UUID
    ) -> bool:
        """Insert membership when under capacity. Returns False when full."""
        ...

    async def accept_covenant(self, *, fellowship_id: UUID, user_id: UUID, accepted_at: datetime) -> Optional[FellowshipMembership]: ...


class FellowshipCapacitySettingsPort(Protocol):
    """Read Fellowship capacity from system settings."""

    async def get_max_active_members(self) -> int: ...

    async def get_max_group_members(self) -> int: ...


class PrimaryFellowshipStorePort(Protocol):
    """Account-synced Primary Fellowship preference."""

    async def get_primary_fellowship_id(self, user_id: UUID) -> Optional[UUID]: ...

    async def set_primary_fellowship_id(self, user_id: UUID, fellowship_id: Optional[UUID]) -> None: ...
