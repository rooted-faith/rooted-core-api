"""Persist Primary Fellowship preference on End-user Preferences."""

from typing import Optional
from uuid import UUID

from portal.domain.app.ports import PreferencesRepositoryPort


class PrimaryFellowshipStore:
    """Account-synced Primary Fellowship preference via app.user_preferences."""

    def __init__(self, preferences_repository: PreferencesRepositoryPort):
        self._preferences_repository = preferences_repository

    async def get_primary_fellowship_id(self, user_id: UUID) -> Optional[UUID]:
        preferences = await self._preferences_repository.get_by_user_id(user_id)
        if preferences is None:
            return None
        return preferences.primary_fellowship_id

    async def set_primary_fellowship_id(self, user_id: UUID, fellowship_id: Optional[UUID]) -> None:
        await self._preferences_repository.update_preferences(user_id, {"primary_fellowship_id": fellowship_id})
