"""Fellowship application results."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from portal.domain.fellowship.constants import FellowshipDiscoverability, FellowshipRole


class FellowshipResult(BaseModel):
    """Single Fellowship with the caller's membership context."""

    id: UUID
    name: str
    discoverability: FellowshipDiscoverability
    role: FellowshipRole
    covenant_accepted_at: Optional[datetime] = None
    is_primary: bool = False


class FellowshipListResult(BaseModel):
    """Fellowships the End user belongs to, plus Primary preference."""

    items: list[FellowshipResult] = Field(default_factory=list)
    primary_fellowship_id: Optional[UUID] = None
