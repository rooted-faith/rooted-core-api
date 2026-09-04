"""
Repositories for End user provisioning under the app schema.
"""

from uuid import UUID

from portal.domain.app.entities import EndUser, UserPreferences
from portal.libs.database import Session
from portal.models.app import AppUser, AppUserPreferences


class EndUserRepository:
    """Insert app.user End user rows."""

    def __init__(self, session: Session):
        self._session = session

    async def create_end_user(self, *, end_user_id: UUID, auth_user_id: UUID) -> EndUser:
        await self._session.insert(AppUser).values(id=end_user_id, auth_user_id=auth_user_id).execute()
        return EndUser(id=end_user_id, auth_user_id=auth_user_id)


class PreferencesRepository:
    """Insert app.user_preferences rows."""

    def __init__(self, session: Session):
        self._session = session

    async def create_preferences(self, preferences: UserPreferences) -> UserPreferences:
        await (
            self._session.insert(AppUserPreferences)
            .values(
                id=preferences.id,
                user_id=preferences.user_id,
                display_name=preferences.display_name,
                locale=preferences.locale,
                theme=preferences.theme,
                font_scale=preferences.font_scale,
                bible_version=preferences.bible_version,
                stage=preferences.stage,
                reminder_time=preferences.reminder_time,
                reminder_enabled=preferences.reminder_enabled,
            )
            .execute()
        )
        return preferences
