from datetime import date, datetime, timezone
from uuid import UUID

import pytest

from portal.application.devotion.commands import UpsertLessonNoteCommand
from portal.application.devotion.devotion_service import DevotionService
from portal.domain.app.entities import EndUser
from portal.domain.devotion.constants import DevotionErrorCode
from portal.domain.devotion.entities import AnonymousDailyLesson, DailyLesson, EncounterStreak, LessonNote, Passage
from portal.exceptions.responses import BadRequestException, NotFoundException


class StubDevotionRepository:
    def __init__(self, lesson=None, scheduled=True, *, inserted=True, streak=None, recent_dates=None, notes=None):
        self.lesson = lesson
        self.scheduled = scheduled
        self.inserted = inserted
        self.streak = streak
        self.recent_dates = recent_dates or []
        self.saved_streak = None
        self.notes = notes or {}

    async def fetch_daily_lesson(self, lesson_date, locale_id, locale_code, include_authored_sections):
        return self.lesson

    async def daily_lesson_exists(self, lesson_date):
        return self.scheduled

    async def insert_encounter_day(self, user_id, encounter_date):
        return self.inserted

    async def get_encounter_streak(self, user_id):
        return self.streak

    async def save_encounter_streak(self, streak):
        self.saved_streak = streak
        self.streak = streak

    async def list_recent_encounter_dates(self, user_id, through_date):
        return self.recent_dates

    async def get_lesson_note(self, user_id, note_date):
        return self.notes.get((user_id, note_date))

    async def upsert_lesson_note(self, user_id, note):
        self.notes[(user_id, note.date)] = note


class StubEndUserRepository:
    def __init__(self, end_user):
        self.end_user = end_user

    async def get_by_auth_user_id(self, auth_user_id):
        return self.end_user


@pytest.mark.asyncio
async def test_get_daily_lesson_returns_verse_and_locked_sections_for_anonymous_end_user():
    lesson = AnonymousDailyLesson(
        date=date(2026, 9, 8), passage=Passage(start="JHN.3.16", end="JHN.3.16", ref="John 3:16", verses=["For God so loved the world"])
    )
    service = DevotionService(StubDevotionRepository(lesson=lesson), StubEndUserRepository(None))

    result = await service.get_daily_lesson(date(2026, 9, 8), locale_id=None, locale_code="en", include_authored_sections=False)

    assert result == lesson
    assert result.locked == ["reflect", "apply", "pray", "note"]


@pytest.mark.asyncio
async def test_get_daily_lesson_returns_all_authored_sections_for_signed_in_end_user():
    lesson = DailyLesson(
        date=date(2026, 9, 8),
        passage=Passage(start="JHN.3.16", end="JHN.3.16", ref="John 3:16", verses=["For God so loved the world"]),
        reflect=["Where do you see God's love today?", "Who can you love practically?"],
        apply="Encourage one person today.",
        pray="God, help me receive and share your love.",
    )
    service = DevotionService(StubDevotionRepository(lesson=lesson), StubEndUserRepository(None))

    result = await service.get_daily_lesson(date(2026, 9, 8), locale_id=None, locale_code="en", include_authored_sections=True)

    assert result == lesson
    assert result.locked == []
    assert result.reflect == ["Where do you see God's love today?", "Who can you love practically?"]
    assert result.apply == "Encourage one person today."
    assert result.pray == "God, help me receive and share your love."


@pytest.mark.asyncio
async def test_get_daily_lesson_anonymous_result_withholds_authored_sections():
    lesson = AnonymousDailyLesson(
        date=date(2026, 9, 7), passage=Passage(start="PSA.23.1", end="PSA.23.1", ref="Psalm 23:1", verses=["The Lord is my shepherd"])
    )
    service = DevotionService(StubDevotionRepository(lesson=lesson), StubEndUserRepository(None))

    result = await service.get_daily_lesson(date(2026, 9, 7), locale_id=None, locale_code="en", include_authored_sections=False)

    assert result == lesson
    assert result.locked == ["reflect", "apply", "pray", "note"]
    assert not hasattr(result, "reflect")
    assert not hasattr(result, "apply")
    assert not hasattr(result, "pray")


@pytest.mark.asyncio
async def test_get_daily_lesson_raises_when_date_is_not_scheduled():
    service = DevotionService(StubDevotionRepository(lesson=None, scheduled=False), StubEndUserRepository(None))

    with pytest.raises(NotFoundException) as error:
        await service.get_daily_lesson(date(2026, 9, 9), locale_id=None, locale_code="en", include_authored_sections=False)

    assert error.value.error_code == DevotionErrorCode.DATE_NOT_SCHEDULED


@pytest.mark.asyncio
async def test_get_daily_lesson_raises_when_translation_is_missing_for_anonymous_end_user():
    service = DevotionService(StubDevotionRepository(lesson=None, scheduled=True), StubEndUserRepository(None))

    with pytest.raises(NotFoundException) as error:
        await service.get_daily_lesson(date(2026, 9, 8), locale_id=None, locale_code="fr", include_authored_sections=False)

    assert error.value.error_code == DevotionErrorCode.TRANSLATION_NOT_FOUND


@pytest.mark.asyncio
async def test_get_daily_lesson_raises_when_translation_is_missing_for_signed_in_end_user():
    service = DevotionService(StubDevotionRepository(lesson=None, scheduled=True), StubEndUserRepository(None))

    with pytest.raises(NotFoundException) as error:
        await service.get_daily_lesson(date(2026, 9, 8), locale_id=None, locale_code="fr", include_authored_sections=True)

    assert error.value.error_code == DevotionErrorCode.TRANSLATION_NOT_FOUND


@pytest.mark.asyncio
async def test_record_encounter_starts_a_new_streak_after_a_missed_day():
    auth_user_id = UUID("11111111-1111-1111-1111-111111111111")
    end_user = EndUser(id=UUID("22222222-2222-2222-2222-222222222222"), auth_user_id=auth_user_id)
    previous_streak = EncounterStreak(user_id=end_user.id, longest_streak=4, current_streak_length=4, last_encounter_date=date(2026, 9, 6))
    repository = StubDevotionRepository(streak=previous_streak)
    service = DevotionService(repository, StubEndUserRepository(end_user))

    result = await service.record_encounter(auth_user_id=auth_user_id, encounter_date=date(2026, 9, 8))

    assert result.current_streak == 1
    assert result.longest_streak == 4
    assert result.welcome_back is True
    assert repository.saved_streak.current_streak_length == 1
    assert repository.saved_streak.last_encounter_date == date(2026, 9, 8)


@pytest.mark.asyncio
async def test_record_encounter_is_idempotent_for_the_same_day():
    auth_user_id = UUID("11111111-1111-1111-1111-111111111111")
    end_user = EndUser(id=UUID("22222222-2222-2222-2222-222222222222"), auth_user_id=auth_user_id)
    existing_streak = EncounterStreak(user_id=end_user.id, longest_streak=5, current_streak_length=5, last_encounter_date=date(2026, 9, 8))
    repository = StubDevotionRepository(inserted=False, streak=existing_streak)
    service = DevotionService(repository, StubEndUserRepository(end_user))

    result = await service.record_encounter(auth_user_id=auth_user_id, encounter_date=date(2026, 9, 8))

    assert result.current_streak == 5
    assert result.longest_streak == 5
    assert result.welcome_back is False
    assert repository.saved_streak is None


@pytest.mark.asyncio
async def test_record_encounter_extends_current_and_longest_streak_from_yesterday():
    auth_user_id = UUID("11111111-1111-1111-1111-111111111111")
    end_user = EndUser(id=UUID("22222222-2222-2222-2222-222222222222"), auth_user_id=auth_user_id)
    repository = StubDevotionRepository(
        streak=EncounterStreak(user_id=end_user.id, longest_streak=4, current_streak_length=4, last_encounter_date=date(2026, 9, 7))
    )
    service = DevotionService(repository, StubEndUserRepository(end_user))

    result = await service.record_encounter(auth_user_id=auth_user_id, encounter_date=date(2026, 9, 8))

    assert result.current_streak == 5
    assert result.longest_streak == 5
    assert result.welcome_back is False


@pytest.mark.asyncio
async def test_get_rhythm_treats_a_stored_streak_as_broken_after_two_days():
    auth_user_id = UUID("11111111-1111-1111-1111-111111111111")
    end_user = EndUser(id=UUID("22222222-2222-2222-2222-222222222222"), auth_user_id=auth_user_id)
    repository = StubDevotionRepository(
        streak=EncounterStreak(user_id=end_user.id, longest_streak=365, current_streak_length=365, last_encounter_date=date(2026, 1, 1)),
        recent_dates=[date(2026, 9, 5), date(2026, 9, 6)],
    )
    service = DevotionService(repository, StubEndUserRepository(end_user))

    result = await service.get_rhythm(auth_user_id=auth_user_id, reader_date=date(2026, 9, 8))

    assert result.current_streak == 0
    assert result.longest_streak == 365
    assert result.completed_dates == [date(2026, 9, 5), date(2026, 9, 6)]


@pytest.mark.asyncio
async def test_get_rhythm_keeps_current_streak_when_last_encounter_was_yesterday():
    auth_user_id = UUID("11111111-1111-1111-1111-111111111111")
    end_user = EndUser(id=UUID("22222222-2222-2222-2222-222222222222"), auth_user_id=auth_user_id)
    repository = StubDevotionRepository(
        streak=EncounterStreak(user_id=end_user.id, longest_streak=12, current_streak_length=5, last_encounter_date=date(2026, 9, 7))
    )
    service = DevotionService(repository, StubEndUserRepository(end_user))

    result = await service.get_rhythm(auth_user_id=auth_user_id, reader_date=date(2026, 9, 8))

    assert result.current_streak == 5


@pytest.mark.asyncio
async def test_upsert_lesson_note_replaces_the_existing_note_for_today():
    auth_user_id = UUID("11111111-1111-1111-1111-111111111111")
    end_user = EndUser(id=UUID("22222222-2222-2222-2222-222222222222"), auth_user_id=auth_user_id)
    repository = StubDevotionRepository()
    service = DevotionService(repository, StubEndUserRepository(end_user), now_provider=lambda: datetime(2026, 9, 10, 2, 30, tzinfo=timezone.utc))

    await service.upsert_lesson_note(
        auth_user_id=auth_user_id,
        command=UpsertLessonNoteCommand(date=date(2026, 9, 9), body="First thought", reflects=["First answer"]),
        time_zone="America/Toronto",
    )
    result = await service.upsert_lesson_note(
        auth_user_id=auth_user_id,
        command=UpsertLessonNoteCommand(date=date(2026, 9, 9), body="Revised thought", reflects=[None, "Second answer"]),
        time_zone="America/Toronto",
    )

    assert result == LessonNote(date=date(2026, 9, 9), body="Revised thought", reflects=[None, "Second answer"])
    assert repository.notes == {(end_user.id, date(2026, 9, 9)): result}


@pytest.mark.asyncio
async def test_upsert_lesson_note_rejects_a_date_other_than_the_current_header_timezone_date():
    auth_user_id = UUID("11111111-1111-1111-1111-111111111111")
    end_user = EndUser(id=UUID("22222222-2222-2222-2222-222222222222"), auth_user_id=auth_user_id)
    service = DevotionService(StubDevotionRepository(), StubEndUserRepository(end_user), now_provider=lambda: datetime(2026, 9, 10, 2, 30, tzinfo=timezone.utc))

    with pytest.raises(BadRequestException):
        await service.upsert_lesson_note(
            auth_user_id=auth_user_id, command=UpsertLessonNoteCommand(date=date(2026, 9, 10), body=None, reflects=[]), time_zone="America/Toronto"
        )


@pytest.mark.asyncio
async def test_upsert_lesson_note_allows_empty_body_and_partial_reflection_answers():
    auth_user_id = UUID("11111111-1111-1111-1111-111111111111")
    end_user = EndUser(id=UUID("22222222-2222-2222-2222-222222222222"), auth_user_id=auth_user_id)
    service = DevotionService(StubDevotionRepository(), StubEndUserRepository(end_user), now_provider=lambda: datetime(2026, 9, 10, 2, 30, tzinfo=timezone.utc))

    result = await service.upsert_lesson_note(
        auth_user_id=auth_user_id,
        command=UpsertLessonNoteCommand(date=date(2026, 9, 9), body=None, reflects=[None, "Only this answer"]),
        time_zone="America/Toronto",
    )

    assert result.body is None
    assert result.reflects == [None, "Only this answer"]


@pytest.mark.asyncio
async def test_get_daily_lesson_returns_the_callers_past_note():
    auth_user_id = UUID("11111111-1111-1111-1111-111111111111")
    end_user = EndUser(id=UUID("22222222-2222-2222-2222-222222222222"), auth_user_id=auth_user_id)
    note = LessonNote(date=date(2026, 9, 8), body="A past note", reflects=["A past answer"])
    lesson = DailyLesson(
        date=date(2026, 9, 8),
        passage=Passage(start="JHN.3.16", end="JHN.3.16", ref="John 3:16", verses=["For God so loved the world"]),
        reflect=["Reflect"],
        apply="Apply",
        pray="Pray",
    )
    service = DevotionService(StubDevotionRepository(lesson=lesson, notes={(end_user.id, note.date): note}), StubEndUserRepository(end_user))

    result = await service.get_daily_lesson(date(2026, 9, 8), locale_id=None, locale_code="en", include_authored_sections=True, auth_user_id=auth_user_id)

    assert result.note == note
