from datetime import date, timedelta
from uuid import UUID, uuid4

from portal.application.devotion.commands import CreateDevotionCommand, DevotionPagesQuery, UpdateDevotionCommand, UpsertDevotionTranslationCommand
from portal.application.devotion.results import DevotionDetailResult, DevotionPageResult, DevotionTranslationResult, EncounterResult, RhythmResult
from portal.domain.app.ports import EndUserRepositoryPort
from portal.domain.devotion.constants import DevotionErrorCode, DevotionStatus
from portal.domain.devotion.entities import AnonymousDailyLesson, DailyLesson, Devotion, EncounterStreak
from portal.domain.devotion.ports import DevotionRepositoryPort
from portal.exceptions.responses import ConflictErrorException, NotFoundException, UnauthorizedException
from portal.libs.tracing.distributed_trace import distributed_trace


class DevotionService:
    def __init__(self, devotion_repository: DevotionRepositoryPort, end_user_repository: EndUserRepositoryPort | None):
        self._repository = devotion_repository
        self._end_user_repository = end_user_repository

    @distributed_trace()
    async def get_daily_lesson(
        self, lesson_date: date, locale_id: UUID | None, locale_code: str | None, include_authored_sections: bool
    ) -> AnonymousDailyLesson | DailyLesson:
        lesson = await self._repository.fetch_daily_lesson(lesson_date, locale_id, locale_code, include_authored_sections)
        if lesson is not None:
            return lesson
        if not await self._repository.daily_lesson_exists(lesson_date):
            raise NotFoundException(detail=f"No Daily lesson scheduled for {lesson_date}", error_code=DevotionErrorCode.DATE_NOT_SCHEDULED)
        raise NotFoundException(detail="Devotion translation not found for the requested locale", error_code=DevotionErrorCode.TRANSLATION_NOT_FOUND)

    @staticmethod
    def _to_detail_result(devotion: Devotion) -> DevotionDetailResult:
        return DevotionDetailResult.model_validate(devotion)

    async def _get_devotion_or_raise(self, devotion_id: UUID) -> Devotion:
        devotion = await self._repository.get_devotion(devotion_id)
        if devotion is None:
            raise NotFoundException(detail="Devotion not found", error_code=DevotionErrorCode.DEVOTION_NOT_FOUND, context={"devotion_id": str(devotion_id)})
        return devotion

    @distributed_trace()
    async def create_devotion(self, command: CreateDevotionCommand) -> DevotionDetailResult:
        devotion_id = uuid4()
        await self._repository.insert_devotion(devotion_id, command.passage_start.strip(), command.passage_end.strip())
        return self._to_detail_result(await self._get_devotion_or_raise(devotion_id))

    @distributed_trace()
    async def get_devotion(self, devotion_id: UUID) -> DevotionDetailResult:
        return self._to_detail_result(await self._get_devotion_or_raise(devotion_id))

    @distributed_trace()
    async def update_devotion(self, devotion_id: UUID, command: UpdateDevotionCommand) -> DevotionDetailResult:
        await self._get_devotion_or_raise(devotion_id)
        await self._repository.update_devotion(devotion_id, command.passage_start.strip(), command.passage_end.strip())
        return self._to_detail_result(await self._get_devotion_or_raise(devotion_id))

    @distributed_trace()
    async def delete_devotion(self, devotion_id: UUID) -> None:
        await self._get_devotion_or_raise(devotion_id)
        if await self._repository.is_devotion_scheduled(devotion_id):
            raise ConflictErrorException(
                detail="A scheduled Devotion cannot be deleted", error_code=DevotionErrorCode.DEVOTION_SCHEDULED, context={"devotion_id": str(devotion_id)}
            )
        if await self._repository.delete_devotion(devotion_id) < 1:
            raise NotFoundException(detail="Devotion not found", error_code=DevotionErrorCode.DEVOTION_NOT_FOUND, context={"devotion_id": str(devotion_id)})

    @distributed_trace()
    async def upsert_devotion_translation(self, devotion_id: UUID, locale_code: str, command: UpsertDevotionTranslationCommand) -> DevotionTranslationResult:
        await self._get_devotion_or_raise(devotion_id)
        locale = await self._repository.resolve_locale(locale_code)
        if locale is None:
            raise NotFoundException(detail="System locale not found", error_code=DevotionErrorCode.LOCALE_NOT_FOUND, context={"locale_code": locale_code})
        await self._repository.upsert_translation(devotion_id, locale.id, command.reflect, command.apply, command.pray)
        devotion = await self._get_devotion_or_raise(devotion_id)
        for translation in devotion.translations:
            if translation.locale_id == locale.id:
                return DevotionTranslationResult.model_validate(translation)
        raise NotFoundException(detail="Devotion translation not found", error_code=DevotionErrorCode.TRANSLATION_NOT_FOUND)

    @distributed_trace()
    async def publish_devotion(self, devotion_id: UUID) -> DevotionDetailResult:
        await self._get_devotion_or_raise(devotion_id)
        active_locales = await self._repository.list_active_locales()
        translation_locale_ids = await self._repository.list_translation_locale_ids(devotion_id)
        missing_locales = [locale.code for locale in active_locales if locale.id not in translation_locale_ids]
        if missing_locales:
            raise ConflictErrorException(
                detail={
                    "message": "Devotion cannot be marked ready until every active locale has a translation",
                    "errorCode": DevotionErrorCode.TRANSLATIONS_INCOMPLETE,
                    "missingLocales": missing_locales,
                },
                error_code=DevotionErrorCode.TRANSLATIONS_INCOMPLETE,
            )
        await self._repository.update_devotion_status(devotion_id, DevotionStatus.READY)
        return self._to_detail_result(await self._get_devotion_or_raise(devotion_id))

    @distributed_trace()
    async def get_devotion_pages(self, query: DevotionPagesQuery) -> DevotionPageResult:
        missing_locale_id = None
        if query.missing_locale is not None:
            locale = await self._repository.resolve_locale(query.missing_locale)
            if locale is None:
                raise NotFoundException(
                    detail="System locale not found", error_code=DevotionErrorCode.LOCALE_NOT_FOUND, context={"locale_code": query.missing_locale}
                )
            missing_locale_id = locale.id
        items, total = await self._repository.fetch_devotion_pages(
            page=query.page, page_size=query.page_size, status=query.status, missing_locale_id=missing_locale_id
        )
        return DevotionPageResult(
            page=query.page,
            page_size=query.page_size,
            total=total,
            total_pages=(total + query.page_size - 1) // query.page_size,
            items=[DevotionDetailResult.model_validate(item) for item in items],
        )

    async def _get_end_user_id(self, auth_user_id: UUID) -> UUID:
        if self._end_user_repository is None:
            raise UnauthorizedException(detail="This service is not configured for End users")
        end_user = await self._end_user_repository.get_by_auth_user_id(auth_user_id)
        if end_user is None:
            raise UnauthorizedException(detail="This credential has no End user")
        return end_user.id

    @distributed_trace()
    async def record_encounter(self, *, auth_user_id: UUID, encounter_date: date) -> EncounterResult:
        end_user_id = await self._get_end_user_id(auth_user_id)
        inserted = await self._repository.insert_encounter_day(end_user_id, encounter_date)
        streak = await self._repository.get_encounter_streak(end_user_id)
        welcome_back = bool(streak and streak.last_encounter_date and streak.last_encounter_date < encounter_date - timedelta(days=1))

        if inserted:
            previous_length = streak.current_streak_length if streak and streak.last_encounter_date == encounter_date - timedelta(days=1) else 0
            current_streak = previous_length + 1
            longest_streak = max(streak.longest_streak if streak else 0, current_streak)
            streak = EncounterStreak(
                user_id=end_user_id, longest_streak=longest_streak, current_streak_length=current_streak, last_encounter_date=encounter_date
            )
            await self._repository.save_encounter_streak(streak)

        if streak is None:
            streak = EncounterStreak(user_id=end_user_id, longest_streak=0, current_streak_length=0, last_encounter_date=None)
        current_streak = self._validated_current_streak(streak, encounter_date)
        return EncounterResult(date=encounter_date, current_streak=current_streak, longest_streak=streak.longest_streak, welcome_back=welcome_back)

    @distributed_trace()
    async def get_rhythm(self, *, auth_user_id: UUID, reader_date: date) -> RhythmResult:
        end_user_id = await self._get_end_user_id(auth_user_id)
        streak = await self._repository.get_encounter_streak(end_user_id)
        completed_dates = await self._repository.list_recent_encounter_dates(end_user_id, reader_date)
        if streak is None:
            return RhythmResult(current_streak=0, longest_streak=0, completed_dates=completed_dates)
        return RhythmResult(
            current_streak=self._validated_current_streak(streak, reader_date), longest_streak=streak.longest_streak, completed_dates=completed_dates
        )

    @staticmethod
    def _validated_current_streak(streak: EncounterStreak, reader_date: date) -> int:
        if streak.last_encounter_date in {reader_date, reader_date - timedelta(days=1)}:
            return streak.current_streak_length
        return 0
