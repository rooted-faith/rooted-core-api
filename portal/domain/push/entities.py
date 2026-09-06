"""
Push domain read model: Device (CONTEXT.md "Push notifications").
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from portal.domain.common.mixins import UUIDBaseModel


class Device(UUIDBaseModel):
    """
    An app install identified by a client-generated device_key.

    Holds at most one push token/platform, and is optionally linked to the
    End user currently signed in on it (nullable — overwritten on sign-in,
    cleared on sign-out).
    """

    device_key: str = Field(..., description="Client-generated device install key")
    token: str = Field(..., description="Current push token (FCM/APNs-via-FCM)")
    platform: str = Field(..., description="Platform: ios|android")
    end_user_id: Optional[UUID] = Field(default=None, description="FK to app.user.id (End user); None when unauthenticated")
    is_active: bool = Field(default=True, description="Whether this device should receive pushes")
    last_used_at: datetime = Field(..., description="Last time this device registered/refreshed")
    app_version: Optional[str] = Field(default=None, description="Client app version at last registration")
