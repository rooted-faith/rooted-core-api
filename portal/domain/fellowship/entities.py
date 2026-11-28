"""Fellowship domain entities."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from portal.domain.fellowship.constants import FellowshipDiscoverability, FellowshipRole


class Fellowship(BaseModel):
    """Invitation-based community that may contain Groups."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    discoverability: FellowshipDiscoverability
    is_deleted: bool = False


class FellowshipMembership(BaseModel):
    """An End user's participation in one Fellowship."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fellowship_id: UUID
    user_id: UUID
    role: FellowshipRole
    covenant_accepted_at: Optional[datetime] = None
    is_deleted: bool = False


class FellowshipMembershipSummary(BaseModel):
    """Membership plus Fellowship fields for list/detail reads."""

    model_config = ConfigDict(from_attributes=True)

    fellowship_id: UUID
    name: str
    discoverability: FellowshipDiscoverability
    role: FellowshipRole
    covenant_accepted_at: Optional[datetime] = None
    is_primary: bool = False
