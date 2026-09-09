from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from portal.application.devotion.commands import (
    CreateDevotionCommand,
    DailyLessonScheduleQuery,
    DevotionPagesQuery,
    ScheduleDailyLessonCommand,
    UpdateDevotionCommand,
    UpsertDevotionTranslationCommand,
    UpsertLessonNoteCommand,
)
from portal.application.devotion.results import (
    DailyLessonScheduleRangeResult,
    DailyLessonScheduleResult,
    DevotionDetailResult,
    DevotionPageResult,
    DevotionTranslationResult,
    EncounterResult,
    RhythmResult,
)
from portal.domain.app.ports import EndUserRepositoryPort
from portal.domain.devotion.constants import DevotionErrorCode, DevotionStatus
from portal.domain.devotion.entities import AnonymousDailyLesson, DailyLesson, Devotion, EncounterStreak, LessonNote
from portal.domain.devotion.ports import DevotionRepositoryPort
from portal.exceptions.responses import BadRequestException, ConflictErrorException, NotFoundException, UnauthorizedException
from portal.libs.tracing.distributed_trace import distributed_trace


class DevotionService:
    def __init__(
        self,
        devotion_repository: DevotionRepositoryPort,
        end_user_repository: EndUserRepositoryPort | None,
        now_provider: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self._repository = devotion_repository
        self._end_user_repository = end_user_repository
        self._now_provider = now_provider

    @distributed_trace()
    async def get_daily_lesson(
        self, lesson_date: date, locale_id: UUID | None, locale_code: str | None, include_authored_sections: bool, auth_user_id: UUID | None = None
    ) -> AnonymousDailyLesson | DailyLesson:
        lesson = await self._repository.fetch_daily_lesson(lesson_date, locale_id, locale_code, include_authored_sections)
        if lesson is not None:
            if isinstance(lesson, DailyLesson) and auth_user_id is not None:
                end_user_id = await self._get_end_user_id(auth_user_id)
                note = await self._repository.get_lesson_note(end_user_id, lesson_date)
                return lesson.model_copy(update={"note": note})
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

    @staticmethod
    def _to_daily_lesson_schedule_result(lesson_date: date, devotion_id: UUID | None) -> DailyLessonScheduleResult:
        return DailyLessonScheduleResult(date=lesson_date, devotion_id=devotion_id)

    def _raise_if_past_daily_lesson_schedule_date(self, lesson_date: date) -> None:
        if lesson_date < self._now_provider().date():
            raise ConflictErrorException(
                detail="Daily lesson schedules for past dates cannot be changed",
                error_code=DevotionErrorCode.DAILY_LESSON_DATE_IN_PAST,
                context={"date": str(lesson_date)},
            )

    async def _get_ready_devotion_or_raise(self, devotion_id: UUID) -> Devotion:
        devotion = await self._get_devotion_or_raise(devotion_id)
        if devotion.status != DevotionStatus.READY:
            raise ConflictErrorException(
                detail="Only a ready Devotion can be scheduled", error_code=DevotionErrorCode.DEVOTION_NOT_READY, context={"devotion_id": str(devotion_id)}
            )
        return devotion

    @distributed_trace()
    async def schedule_daily_lesson(self, lesson_date: date, command: ScheduleDailyLessonCommand) -> DailyLessonScheduleResult:
        self._raise_if_past_daily_lesson_schedule_date(lesson_date)
        devotion_id = command.devotion_id
        await self._get_ready_devotion_or_raise(devotion_id)
        if not await self._repository.insert_daily_lesson_schedule(lesson_date, devotion_id):
            raise ConflictErrorException(
                detail="A Daily lesson is already scheduled for this date",
                error_code=DevotionErrorCode.DAILY_LESSON_DATE_ALREADY_SCHEDULED,
                context={"date": str(lesson_date)},
            )
        return self._to_daily_lesson_schedule_result(lesson_date, devotion_id)

    @distributed_trace()
    async def reschedule_daily_lesson(self, lesson_date: date, command: ScheduleDailyLessonCommand) -> DailyLessonScheduleResult:
        self._raise_if_past_daily_lesson_schedule_date(lesson_date)
        devotion_id = command.devotion_id
        await self._get_ready_devotion_or_raise(devotion_id)
        if await self._repository.update_daily_lesson_schedule(lesson_date, devotion_id) < 1:
            raise NotFoundException(
                detail="Daily lesson schedule not found", error_code=DevotionErrorCode.DAILY_LESSON_SCHEDULE_NOT_FOUND, context={"date": str(lesson_date)}
            )
        return self._to_daily_lesson_schedule_result(lesson_date, devotion_id)

    @distributed_trace()
    async def unschedule_daily_lesson(self, lesson_date: date) -> None:
        self._raise_if_past_daily_lesson_schedule_date(lesson_date)
        if await self._repository.delete_daily_lesson_schedule(lesson_date) < 1:
            raise NotFoundException(
                detail="Daily lesson schedule not found", error_code=DevotionErrorCode.DAILY_LESSON_SCHEDULE_NOT_FOUND, context={"date": str(lesson_date)}
            )

    @distributed_trace()
    async def get_daily_lesson_schedule(self, query: DailyLessonScheduleQuery) -> DailyLessonScheduleRangeResult:
        from_date = query.from_date
        to_date = query.to_date
        if from_date > to_date:
            raise BadRequestException(
                detail="The schedule range start must not be after its end", error_code=DevotionErrorCode.INVALID_DAILY_LESSON_SCHEDULE_RANGE
            )
        schedules = await self._repository.list_daily_lesson_schedules(from_date, to_date)
        devotion_ids_by_date = {schedule.date: schedule.devotion_id for schedule in schedules}
        items = []
        scheduled_through = None
        has_gap = False
        lesson_date = from_date
        while lesson_date <= to_date:
            devotion_id = devotion_ids_by_date.get(lesson_date)
            items.append(self._to_daily_lesson_schedule_result(lesson_date, devotion_id))
            if devotion_id is None:
                has_gap = True
            elif not has_gap:
                scheduled_through = lesson_date
            lesson_date += timedelta(days=1)
        return DailyLessonScheduleRangeResult(items=items, scheduled_through=scheduled_through)

    async def _get_end_user_id(self, auth_user_id: UUID) -> UUID:
        if self._end_user_repository is None:
            raise UnauthorizedException(detail="This service is not configured for End users")
        end_user = await self._end_user_repository.get_by_auth_user_id(auth_user_id)
        if end_user is None:
            raise UnauthorizedException(detail="This credential has no End user")
        return end_user.id

    @distributed_trace()
    async def upsert_lesson_note(self, *, auth_user_id: UUID, command: UpsertLessonNoteCommand, time_zone: str | None) -> LessonNote:
        current_local_date = self._current_local_date(time_zone)
        if command.date != current_local_date:
            raise BadRequestException(
                detail="Lesson note must be written for the caller's current local date", error_code=DevotionErrorCode.LESSON_NOTE_DATE_NOT_TODAY
            )
        note = LessonNote(date=command.date, body=command.body, reflects=command.reflects)
        await self._repository.upsert_lesson_note(await self._get_end_user_id(auth_user_id), note)
        return note

    def _current_local_date(self, time_zone: str | None) -> date:
        try:
            zone = ZoneInfo(time_zone) if time_zone else None
        except ZoneInfoNotFoundError:
            zone = None
        if zone is None:
            raise BadRequestException(detail="X-Timezone must be a valid IANA time zone", error_code=DevotionErrorCode.INVALID_TIME_ZONE)
        return self._now_provider().astimezone(zone).date()

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
