"""
Ports for Device persistence.
"""

from datetime import datetime
from typing import Optional, Protocol
from uuid import UUID

from portal.domain.push.entities import Device


class DeviceRepositoryPort(Protocol):
    """Persist push Device rows keyed by device_key."""

    async def upsert_device(
        self, *, device_key: str, token: str, platform: str, app_version: Optional[str], end_user_id: Optional[UUID], last_used_at: datetime
    ) -> Device:
        """
        Insert a Device on first registration, or overwrite token/platform/
        app_version/last_used_at/end_user_id on every subsequent call.
        """
