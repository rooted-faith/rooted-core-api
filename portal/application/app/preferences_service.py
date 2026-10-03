"""Read and update synced End-user Preferences."""

from uuid import UUID

from portal.application.app.commands import UpdatePreferencesCommand
from portal.application.app.results import PreferencesResult
from portal.domain.app.entities import UserPreferences
from portal.domain.app.ports import EndUserRepositoryPort, PreferencesRepositoryPort
from portal.domain.bible.ports import BibleRepositoryPort
from portal.exceptions.responses import BadRequestException, NotFoundException, UnauthorizedException
from portal.libs.tracing.distributed_trace import distributed_trace


class PreferencesService:
    """Serve Preferences without interpreting them as calendar behavior."""

    def __init__(self, end_user_repository: EndUserRepositoryPort, preferences_repository: PreferencesRepositoryPort, bible_repository: BibleRepositoryPort):
        self._end_user_repository = end_user_repository
        self._preferences_repository = preferences_repository
        self._bible_repository = bible_repository

    async def _get_end_user_preferences(self, auth_user_id: UUID) -> UserPreferences:
        end_user = await self._end_user_repository.get_by_auth_user_id(auth_user_id)
        if end_user is None:
            raise UnauthorizedException(detail="This credential has no End user")
        preferences = await self._preferences_repository.get_by_user_id(end_user.id)
        if preferences is None:
            raise NotFoundException(detail="Preferences not found")
        return preferences

    @distributed_trace()
    async def get_preferences(self, *, auth_user_id: UUID) -> PreferencesResult:
        preferences = await self._get_end_user_preferences(auth_user_id)
        return PreferencesResult.model_validate(preferences, from_attributes=True)

    @distributed_trace()
    async def update_preferences(self, *, auth_user_id: UUID, command: UpdatePreferencesCommand) -> PreferencesResult:
        preferences = await self._get_end_user_preferences(auth_user_id)
        values = command.model_dump(exclude_unset=True)
        bible_version = values.get("bible_version")
        if bible_version is not None and not await self._bible_repository.youversion_bible_id_is_active(str(bible_version)):
            raise BadRequestException(detail="Bible version is not an active licensed version")
        updated = await self._preferences_repository.update_preferences(preferences.user_id, values)
        if updated is None:
            raise NotFoundException(detail="Preferences not found")
        return PreferencesResult.model_validate(updated, from_attributes=True)
