"""
Push application service.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from portal.application.push.results import DeviceResult
from portal.domain.app.ports import EndUserRepositoryPort
from portal.domain.push.ports import DeviceRepositoryPort
from portal.libs.tracing.distributed_trace import distributed_trace


class PushService:
    """Device registration & lifecycle use cases."""

    def __init__(self, device_repository: DeviceRepositoryPort, end_user_repository: EndUserRepositoryPort):
        self._device_repository = device_repository
        self._end_user_repository = end_user_repository

    @distributed_trace()
    async def resolve_end_user_id(self, auth_user_id: Optional[UUID]) -> Optional[UUID]:
        """Map an authenticated auth.user.id to its app.user.id (End user), or None when unauthenticated."""
        if auth_user_id is None:
            return None
        end_user = await self._end_user_repository.get_by_auth_user_id(auth_user_id)
        return end_user.id if end_user else None

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
