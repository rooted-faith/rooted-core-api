"""Member Fellowship API serializers (camelCase JSON via serialization_alias)."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CreateFellowshipRequest(BaseModel):
    """Create a Fellowship; Covenant acceptance must be explicit."""

    name: str = Field(..., min_length=1, max_length=100)
    discoverability: str = Field(default="private")
    covenant_accepted: bool = Field(...)


class SetPrimaryFellowshipRequest(BaseModel):
    """Set or clear the account-synced Primary Fellowship."""

    fellowship_id: Optional[UUID] = Field(default=None)


class FellowshipResponse(BaseModel):
    """Fellowship detail for a member."""

    id: UUID
    name: str
    discoverability: str
    role: str
    covenant_accepted_at: Optional[datetime] = Field(default=None, serialization_alias="covenantAcceptedAt")
    is_primary: bool = Field(..., serialization_alias="isPrimary")


class FellowshipListResponse(BaseModel):
    """Fellowships the caller belongs to."""

    items: list[FellowshipResponse]
    primary_fellowship_id: Optional[UUID] = Field(default=None, serialization_alias="primaryFellowshipId")
