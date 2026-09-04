"""
Results for End user / identity provisioning.
"""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ProvisionIdentityResult(BaseModel):
    """Outcome of credential (+ optional End user) provisioning."""

    auth_user_id: UUID = Field(...)
    end_user_id: Optional[UUID] = Field(default=None, description="app.user.id when create_end_user was True; None for admin-only")
