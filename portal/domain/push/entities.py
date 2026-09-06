"""
Push domain read models: Device, Notification, NotificationDelivery
(CONTEXT.md "Push notifications").
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from portal.domain.common.mixins import UUIDBaseModel
from portal.domain.push.constants import DeliveryStatus, PushSendStatus


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


class Notification(UUIDBaseModel):
    """A single push-worthy event addressed to one End user."""

    end_user_id: UUID = Field(..., description="FK to app.user.id (End user) this Notification is addressed to")
    category: str = Field(..., description="Free-form notification category")
    title: str = Field(..., description="Notification title")
    body: str = Field(..., description="Notification body")
    data: Optional[dict] = Field(default=None, description="Optional structured payload")
    created_at: datetime = Field(...)


class NotificationDelivery(UUIDBaseModel):
    """One attempt to deliver a Notification to one specific Device."""

    notification_id: UUID = Field(..., description="FK to push.notification.id")
    device_id: UUID = Field(..., description="FK to push.device.id")
    status: DeliveryStatus = Field(...)
    error: Optional[str] = Field(default=None, description="Failure detail, if any")
    delivered_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(...)


class NotificationDeliveryDraft(BaseModel):
    """A NotificationDelivery row to be persisted, before an id is assigned."""

    notification_id: UUID
    device_id: UUID
    status: DeliveryStatus
    error: Optional[str] = None
    delivered_at: Optional[datetime] = None


class PushSendResult(BaseModel):
    """One token's outcome from a PushGatewayPort.send_multicast call."""

    token: str
    status: PushSendStatus
    error: Optional[str] = None
