"""
Member push device serializers (camelCase JSON via serialization_alias).
"""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_serializer


class DeviceRegistrationRequest(BaseModel):
    """Register or refresh a push device's token/platform."""

    token: str = Field(..., description="Current push token (FCM/APNs-via-FCM)")
    platform: Literal["ios", "android"] = Field(..., description="Platform: ios|android")
    app_version: Optional[str] = Field(default=None, description="Client app version")


class DeviceRegistration(BaseModel):
    """Registered device state after upsert."""

    id: UUID = Field(...)
    device_key: str = Field(..., serialization_alias="deviceKey")
    platform: str = Field(...)
    end_user_id: Optional[UUID] = Field(default=None, serialization_alias="endUserId")
    is_active: bool = Field(..., serialization_alias="isActive")
    last_used_at: datetime = Field(..., serialization_alias="lastUsedAt")
    app_version: Optional[str] = Field(default=None, serialization_alias="appVersion")

    @field_serializer("id", "end_user_id")
    def serialize_uuid(self, value: Optional[UUID], _info) -> Optional[str]:
        return str(value) if value is not None else None
