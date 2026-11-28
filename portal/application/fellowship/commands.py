"""Fellowship application commands."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CreateFellowshipCommand(BaseModel):
    """Create a Fellowship; Covenant must be accepted explicitly by the client."""

    name: str = Field(..., min_length=1, max_length=100)
    discoverability: str = Field(default="private")
    covenant_accepted: bool = Field(...)


class AcceptCovenantCommand(BaseModel):
    """Explicit Covenant acceptance for an existing membership."""

    fellowship_id: UUID


class SetPrimaryFellowshipCommand(BaseModel):
    """Set the account-synced Primary Fellowship preference."""

    fellowship_id: Optional[UUID] = None


class AdmitMemberCommand(BaseModel):
    """Admit an End user into a Fellowship subject to capacity."""

    fellowship_id: UUID
    user_id: UUID
    role: str = "member"
    covenant_accepted: bool = False
