"""Read Fellowship capacity limits from system settings."""

from portal.domain.fellowship.constants import (
    DEFAULT_FELLOWSHIP_MAX_ACTIVE_MEMBERS,
    DEFAULT_FELLOWSHIP_MAX_GROUP_MEMBERS,
    FELLOWSHIP_MAX_ACTIVE_MEMBERS_KEY,
    FELLOWSHIP_MAX_GROUP_MEMBERS_KEY,
    FELLOWSHIP_SETTING_NAMESPACE,
)
from portal.domain.system.ports import SettingRepositoryPort


class FellowshipCapacitySettings:
    """System-setting backed Fellowship capacity."""

    def __init__(self, setting_repository: SettingRepositoryPort):
        self._setting_repository = setting_repository

    async def get_max_active_members(self) -> int:
        return await self._read_number(FELLOWSHIP_MAX_ACTIVE_MEMBERS_KEY, DEFAULT_FELLOWSHIP_MAX_ACTIVE_MEMBERS)

    async def get_max_group_members(self) -> int:
        return await self._read_number(FELLOWSHIP_MAX_GROUP_MEMBERS_KEY, DEFAULT_FELLOWSHIP_MAX_GROUP_MEMBERS)

    async def _read_number(self, setting_key: str, default: int) -> int:
        row = await self._setting_repository.get_by_namespace_key(FELLOWSHIP_SETTING_NAMESPACE, setting_key)
        if row is None or not row.is_active or row.is_deleted:
            return default
        value = row.value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return default
        return int(value)
