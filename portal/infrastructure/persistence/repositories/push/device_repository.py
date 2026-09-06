"""
Device repository — SQLAlchemy-backed upsert by device_key.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

import sqlalchemy as sa

from portal.domain.push.entities import Device
from portal.libs.database import Session
from portal.models.push import PushDevice


class DeviceRepository:
    """Implements DeviceRepositoryPort via structural typing."""

    _DEVICE_COLUMNS = (
        PushDevice.id,
        PushDevice.device_key,
        PushDevice.token,
        PushDevice.platform,
        PushDevice.end_user_id,
        PushDevice.is_active,
        PushDevice.last_used_at,
        PushDevice.app_version,
    )

    def __init__(self, session: Session):
        self._session = session

    async def upsert_device(
        self, *, device_key: str, token: str, platform: str, app_version: Optional[str], end_user_id: Optional[UUID], last_used_at: datetime
    ) -> Device:
        await (
            self._session.insert(PushDevice)
            .values(
                id=uuid4(), device_key=device_key, token=token, platform=platform, app_version=app_version, end_user_id=end_user_id, last_used_at=last_used_at
            )
            .on_conflict_do_update(
                index_elements=["device_key"],
                set_=dict(token=token, platform=platform, app_version=app_version, end_user_id=end_user_id, last_used_at=last_used_at),
            )
            .execute()
        )
        return await self._session.select(*self._DEVICE_COLUMNS).where(PushDevice.device_key == device_key).fetchrow(as_model=Device)

    async def list_active_devices(self, end_user_id: UUID) -> list[Device]:
        return await (
            self._session.select(*self._DEVICE_COLUMNS)
            .where(sa.and_(PushDevice.end_user_id == end_user_id, PushDevice.is_active.is_(True)))
            .fetch(as_model=Device)
        )

    async def deactivate_devices(self, device_ids: list[UUID]) -> None:
        if not device_ids:
            return
        await self._session.update(PushDevice).values(is_active=False).where(PushDevice.id.in_(device_ids)).execute()
