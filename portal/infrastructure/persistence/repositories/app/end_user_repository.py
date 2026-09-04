"""
Repositories for End user provisioning under the app schema.
"""

from typing import Optional
from uuid import UUID

from portal.domain.app.entities import EndUser, UserPreferences
from portal.libs.database import Session
from portal.models.app import AppUser, AppUserPreferences


class EndUserRepository:
    """Insert and load app.user End user rows."""

    def __init__(self, session: Session):
        self._session = session

    async def create_end_user(self, *, end_user_id: UUID, auth_user_id: UUID) -> EndUser:
        await self._session.insert(AppUser).values(id=end_user_id, auth_user_id=auth_user_id).execute()
        return EndUser(id=end_user_id, auth_user_id=auth_user_id)

    async def get_by_auth_user_id(self, auth_user_id: UUID) -> Optional[EndUser]:
        return await (
            self._session.select(AppUser.id, AppUser.auth_user_id)
            .where(AppUser.auth_user_id == auth_user_id)
            .where(AppUser.is_deleted == False)
            .fetchrow(as_model=EndUser)
        )


class PreferencesRepository:
    """Insert and load app.user_preferences rows."""

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

    async def get_by_user_id(self, user_id: UUID) -> Optional[UserPreferences]:
        return await (
            self._session.select(
                AppUserPreferences.id,
                AppUserPreferences.user_id,
                AppUserPreferences.display_name,
                AppUserPreferences.locale,
                AppUserPreferences.theme,
                AppUserPreferences.font_scale,
                AppUserPreferences.bible_version,
                AppUserPreferences.stage,
                AppUserPreferences.reminder_time,
                AppUserPreferences.reminder_enabled,
            )
            .where(AppUserPreferences.user_id == user_id)
            .fetchrow(as_model=UserPreferences)
        )
