"""
Push application service.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from portal.application.push.results import DeviceResult
from portal.domain.push.ports import DeviceRepositoryPort
from portal.libs.tracing.distributed_trace import distributed_trace


class PushService:
    """Device registration & lifecycle use cases."""

    def __init__(self, device_repository: DeviceRepositoryPort):
        self._device_repository = device_repository

    @distributed_trace()
    async def register_device(self, *, device_key: str, token: str, platform: str, app_version: Optional[str], end_user_id: Optional[UUID]) -> DeviceResult:
        """
        Upsert by device_key: unconditionally overwrite token/platform/app_version/
        last_used_at, and set end_user_id to whatever this call resolved (the
        signed-in End user's id, or None if unauthenticated).
        """
        return await self._device_repository.upsert_device(
            device_key=device_key, token=token, platform=platform, app_version=app_version, end_user_id=end_user_id, last_used_at=datetime.now(timezone.utc)
        )
