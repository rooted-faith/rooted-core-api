"""SQLAlchemy-backed Fellowship repository."""

from datetime import datetime
from typing import Optional
from uuid import UUID

import sqlalchemy as sa

from portal.domain.fellowship.entities import Fellowship, FellowshipMembership, FellowshipMembershipSummary
from portal.libs.database import Session
from portal.models.fellowship import FellowshipFellowship
from portal.models.fellowship import FellowshipMembership as FellowshipMembershipModel


class FellowshipRepository:
    """Persist Fellowships and memberships."""

    def __init__(self, session: Session):
        self._session = session

    async def insert_fellowship(self, payload: dict) -> None:
        await self._session.insert(FellowshipFellowship).values(payload).execute()

    async def get_by_id(self, fellowship_id: UUID) -> Optional[Fellowship]:
        return await (
            self._session.select(FellowshipFellowship.id, FellowshipFellowship.name, FellowshipFellowship.discoverability, FellowshipFellowship.is_deleted)
            .where(FellowshipFellowship.id == fellowship_id)
            .where(FellowshipFellowship.is_deleted == False)
            .fetchrow(as_model=Fellowship)
        )

    async def insert_membership(self, payload: dict) -> None:
        await self._session.insert(FellowshipMembershipModel).values(payload).execute()

    async def get_membership(self, *, fellowship_id: UUID, user_id: UUID) -> Optional[FellowshipMembership]:
        return await (
            self._session.select(
                FellowshipMembershipModel.id,
                FellowshipMembershipModel.fellowship_id,
                FellowshipMembershipModel.user_id,
                FellowshipMembershipModel.role,
                FellowshipMembershipModel.covenant_accepted_at,
                FellowshipMembershipModel.is_deleted,
            )
            .where(FellowshipMembershipModel.fellowship_id == fellowship_id)
            .where(FellowshipMembershipModel.user_id == user_id)
            .where(FellowshipMembershipModel.is_deleted == False)
            .fetchrow(as_model=FellowshipMembership)
        )

    async def list_for_user(self, user_id: UUID) -> list[FellowshipMembershipSummary]:
        rows = await (
            self._session.select(
                FellowshipMembershipModel.fellowship_id,
                FellowshipFellowship.name,
                FellowshipFellowship.discoverability,
                FellowshipMembershipModel.role,
                FellowshipMembershipModel.covenant_accepted_at,
            )
            .select_from(FellowshipMembershipModel)
            .join(FellowshipFellowship, FellowshipFellowship.id == FellowshipMembershipModel.fellowship_id)
            .where(FellowshipMembershipModel.user_id == user_id)
            .where(FellowshipMembershipModel.is_deleted == False)
            .where(FellowshipFellowship.is_deleted == False)
            .order_by(FellowshipFellowship.name)
            .fetch(as_model=FellowshipMembershipSummary)
        )
        return rows or []

    async def count_active_members(self, fellowship_id: UUID) -> int:
        value = await (
            self._session.select(sa.func.count())
            .select_from(FellowshipMembershipModel)
            .where(FellowshipMembershipModel.fellowship_id == fellowship_id)
            .where(FellowshipMembershipModel.is_deleted == False)
            .fetchval()
        )
        return int(value or 0)

    async def admit_member_atomically(
        self, *, fellowship_id: UUID, user_id: UUID, role: str, max_active_members: int, covenant_accepted_at: Optional[datetime], membership_id: UUID
    ) -> bool:
        lock_stmt = (
            sa.select(FellowshipFellowship.id).where(FellowshipFellowship.id == fellowship_id).where(FellowshipFellowship.is_deleted == False).with_for_update()
        )
        locked_id = await self._session.fetchval(lock_stmt)
        if locked_id is None:
            return False
        active_count = await self.count_active_members(fellowship_id)
        if active_count >= max_active_members:
            return False
        await self.insert_membership(
            {"id": membership_id, "fellowship_id": fellowship_id, "user_id": user_id, "role": role, "covenant_accepted_at": covenant_accepted_at}
        )
        return True

    async def accept_covenant(self, *, fellowship_id: UUID, user_id: UUID, accepted_at: datetime) -> Optional[FellowshipMembership]:
        membership = await self.get_membership(fellowship_id=fellowship_id, user_id=user_id)
        if membership is None:
            return None
        if membership.covenant_accepted_at is None:
            await (
                self._session.update(FellowshipMembershipModel)
                .values(covenant_accepted_at=accepted_at)
                .where(FellowshipMembershipModel.id == membership.id)
                .where(FellowshipMembershipModel.is_deleted == False)
                .execute()
            )
            return await self.get_membership(fellowship_id=fellowship_id, user_id=user_id)
        return membership
