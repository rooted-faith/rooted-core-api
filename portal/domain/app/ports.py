"""
Ports for End user identity and Preferences persistence.
"""

from typing import Protocol
from uuid import UUID

from portal.domain.app.entities import EndUser, UserPreferences


class EndUserRepositoryPort(Protocol):
    """Persist End user rows keyed by app.user.id."""

    async def create_end_user(self, *, end_user_id: UUID, auth_user_id: UUID) -> EndUser: ...


class PreferencesRepositoryPort(Protocol):
    """Persist 1:1 Preferences for an End user."""

    async def create_preferences(self, preferences: UserPreferences) -> UserPreferences: ...
