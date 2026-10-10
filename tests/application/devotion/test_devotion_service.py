from datetime import date, datetime, timezone
from uuid import UUID

import pytest

from portal.application.devotion.commands import UpsertLessonNoteCommand
from portal.application.devotion.devotion_service import DevotionService
from portal.domain.app.entities import EndUser
from portal.domain.bible.entities import BibleChapter, BibleVerse
from portal.domain.devotion.constants import DevotionErrorCode
from portal.domain.devotion.entities import AnonymousDailyLesson, DailyLesson, EncounterStreak, LessonNote, Passage, ScheduledDailyLesson
from portal.exceptions.responses import BadRequestException, NotFoundException

BOOK_ID = UUID("33333333-3333-3333-3333-333333333333")
VERSION_ID = UUID("44444444-4444-4444-4444-444444444444")
LOVED_LINES = [{"type": "line", "style": "p", "fragments": [{"type": "text", "text": "For God so loved the world"}]}]


class StubDevotionRepository:
    def __init__(self, lesson=None, scheduled=True, *, inserted=True, streak=None, recent_dates=None, notes=None):
        self.lesson = lesson
        self.scheduled = scheduled
        self.inserted = inserted
        self.streak = streak
        self.recent_dates = recent_dates or []
        self.saved_streak = None
        self.inserted_dates = []
        self.notes = notes or {}

    async def fetch_daily_lesson(self, lesson_date, locale_id, locale_code, include_authored_sections):
        return self.lesson

    async def daily_lesson_exists(self, lesson_date):
        return self.scheduled

    async def insert_encounter_day(self, user_id, encounter_date):
        self.inserted_dates.append(encounter_date)
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


class StubBibleService:
    def __init__(self, chapters):
        self.chapters = chapters
        self.calls = []

    async def get_chapter(self, book_id, chapter):
        self.calls.append((book_id, chapter))
        return self.chapters[(book_id, chapter)]


def _chapter(book_id, book_code, chapter, book_name, verses):
    return BibleChapter(
        bible_version_id=VERSION_ID,
        youversion_bible_id="1392",
        bible_title="CCBT",
        book_id=book_id,
        book_code=book_code,
        book_name=book_name,
        chapter=chapter,
        verses=verses,
    )


class StubEndUserRepository:
    def __init__(self, end_user):
        self.end_user = end_user

    async def get_by_auth_user_id(self, auth_user_id):
        return self.end_user


@pytest.mark.asyncio
async def test_get_daily_lesson_returns_the_cited_verse_after_reading_the_whole_chapter():
    verse_15 = BibleVerse(
        passage_id="JHN.3.15", verse=15, lines=[{"type": "line", "style": "p", "fragments": [{"type": "text", "text": "that whoever believes"}]}]
    )
    verse_16 = BibleVerse(passage_id="JHN.3.16", verse=16, lines=LOVED_LINES)
    bible = StubBibleService(chapters={(BOOK_ID, 3): _chapter(BOOK_ID, "JHN", 3, "John", [verse_15, verse_16])})
    source = ScheduledDailyLesson(date=date(2026, 9, 8), passage_start="JHN.3.16", passage_end="JHN.3.16", book_id=BOOK_ID)
    service = DevotionService(StubDevotionRepository(lesson=source), StubEndUserRepository(None), bible_service=bible)

    result = await service.get_daily_lesson(date(2026, 9, 8), locale_id=None, locale_code="en", include_authored_sections=False)

    assert bible.calls == [(BOOK_ID, 3)]
    assert result.passage.verses == [verse_16]
    assert result.passage.ref == "John 3:16"


@pytest.mark.asyncio
async def test_get_daily_lesson_reads_each_chapter_of_a_same_book_range():
    genesis_30 = BibleVerse(
        passage_id="GEN.1.30", verse=30, lines=[{"type": "line", "style": "p", "fragments": [{"type": "text", "text": "and to everything"}]}]
    )
    genesis_31 = BibleVerse(
        passage_id="GEN.1.31", verse=31, lines=[{"type": "line", "style": "p", "fragments": [{"type": "text", "text": "God saw all that he had made"}]}]
    )
    genesis_1 = BibleVerse(passage_id="GEN.2.1", verse=1, lines=[{"type": "line", "style": "p", "fragments": [{"type": "text", "text": "Thus the heavens"}]}])
    genesis_2 = BibleVerse(
        passage_id="GEN.2.2", verse=2, verse_end=3, lines=[{"type": "line", "style": "p", "fragments": [{"type": "text", "text": "By the seventh day"}]}]
    )
    genesis_4 = BibleVerse(
        passage_id="GEN.2.4", verse=4, lines=[{"type": "line", "style": "p", "fragments": [{"type": "text", "text": "This is the account"}]}]
    )
    bible = StubBibleService(
        chapters={
            (BOOK_ID, 1): _chapter(BOOK_ID, "GEN", 1, "Genesis", [genesis_30, genesis_31]),
            (BOOK_ID, 2): _chapter(BOOK_ID, "GEN", 2, "Genesis", [genesis_1, genesis_2, genesis_4]),
        }
    )
    source = ScheduledDailyLesson(date=date(2026, 9, 8), passage_start="GEN.1.31", passage_end="GEN.2.2", book_id=BOOK_ID)
    service = DevotionService(StubDevotionRepository(lesson=source), StubEndUserRepository(None), bible_service=bible)

    result = await service.get_daily_lesson(date(2026, 9, 8), locale_id=None, locale_code="en", include_authored_sections=False)

    assert bible.calls == [(BOOK_ID, 1), (BOOK_ID, 2)]
    assert result.passage.verses == [genesis_31, genesis_1, genesis_2]
    assert result.passage.ref == "Genesis 1:31–2:2"


@pytest.mark.asyncio
async def test_get_daily_lesson_does_not_read_a_cross_book_range():
    bible = StubBibleService(chapters={(BOOK_ID, 3): _chapter(BOOK_ID, "JHN", 3, "John", [])})
    source = ScheduledDailyLesson(date=date(2026, 9, 8), passage_start="JHN.3.16", passage_end="ACT.1.1", book_id=BOOK_ID)
    service = DevotionService(StubDevotionRepository(lesson=source), StubEndUserRepository(None), bible_service=bible)

    with pytest.raises(NotFoundException) as error:
        await service.get_daily_lesson(date(2026, 9, 8), locale_id=None, locale_code="en", include_authored_sections=False)

    assert bible.calls == []
    assert error.value.error_code == DevotionErrorCode.BIBLE_PASSAGE_NOT_FOUND


@pytest.mark.asyncio
async def test_get_daily_lesson_names_the_bible_lookup_when_no_bible_book_matches_the_language():
    source = ScheduledDailyLesson(date=date(2026, 9, 8), passage_start="JHN.3.16", passage_end="JHN.3.16", book_id=None)
    service = DevotionService(StubDevotionRepository(lesson=source), StubEndUserRepository(None), bible_service=StubBibleService(chapters={}))

    with pytest.raises(NotFoundException) as error:
        await service.get_daily_lesson(date(2026, 9, 8), locale_id=None, locale_code="en", include_authored_sections=False)

    assert error.value.error_code == DevotionErrorCode.BIBLE_PASSAGE_NOT_FOUND


@pytest.mark.asyncio
async def test_get_daily_lesson_names_the_bible_lookup_when_the_chapter_has_no_cited_verses():
    bible = StubBibleService(chapters={(BOOK_ID, 3): _chapter(BOOK_ID, "JHN", 3, "John", [])})
    source = ScheduledDailyLesson(date=date(2026, 9, 8), passage_start="JHN.3.16", passage_end="JHN.3.16", book_id=BOOK_ID)
    service = DevotionService(StubDevotionRepository(lesson=source), StubEndUserRepository(None), bible_service=bible)

    with pytest.raises(NotFoundException) as error:
        await service.get_daily_lesson(date(2026, 9, 8), locale_id=None, locale_code="en", include_authored_sections=True)

    assert error.value.error_code == DevotionErrorCode.BIBLE_PASSAGE_NOT_FOUND


@pytest.mark.asyncio
async def test_get_daily_lesson_returns_verse_and_locked_sections_for_anonymous_end_user():
    verse = BibleVerse(passage_id="JHN.3.16", verse=16, lines=LOVED_LINES)
    bible = StubBibleService(chapters={(BOOK_ID, 3): _chapter(BOOK_ID, "JHN", 3, "John", [verse])})
    source = ScheduledDailyLesson(
        date=date(2026, 9, 8), passage_start="JHN.3.16", passage_end="JHN.3.16", book_id=BOOK_ID, reflect=["Hidden"], apply="Hidden", pray="Hidden"
    )
    service = DevotionService(StubDevotionRepository(lesson=source), StubEndUserRepository(None), bible_service=bible)

    result = await service.get_daily_lesson(date(2026, 9, 8), locale_id=None, locale_code="en", include_authored_sections=False)

    assert isinstance(result, AnonymousDailyLesson)
    assert result.passage == Passage(start="JHN.3.16", end="JHN.3.16", ref="John 3:16", verses=[verse])
    assert result.locked == ["reflect", "apply", "pray", "note"]


@pytest.mark.asyncio
async def test_get_daily_lesson_returns_all_authored_sections_for_signed_in_end_user():
    verse = BibleVerse(passage_id="JHN.3.16", verse=16, lines=LOVED_LINES)
    bible = StubBibleService(chapters={(BOOK_ID, 3): _chapter(BOOK_ID, "JHN", 3, "John", [verse])})
    source = ScheduledDailyLesson(
        date=date(2026, 9, 8),
        passage_start="JHN.3.16",
        passage_end="JHN.3.16",
        book_id=BOOK_ID,
        reflect=["Where do you see God's love today?", "Who can you love practically?"],
        apply="Encourage one person today.",
        pray="God, help me receive and share your love.",
    )
    service = DevotionService(StubDevotionRepository(lesson=source), StubEndUserRepository(None), bible_service=bible)

    result = await service.get_daily_lesson(date(2026, 9, 8), locale_id=None, locale_code="en", include_authored_sections=True)

    assert isinstance(result, DailyLesson)
    assert result.locked == []
    assert result.reflect == ["Where do you see God's love today?", "Who can you love practically?"]
    assert result.apply == "Encourage one person today."
    assert result.pray == "God, help me receive and share your love."


@pytest.mark.asyncio
async def test_get_daily_lesson_anonymous_result_withholds_authored_sections():
    verse = BibleVerse(
        passage_id="PSA.23.1", verse=1, lines=[{"type": "line", "style": "p", "fragments": [{"type": "text", "text": "The Lord is my shepherd"}]}]
    )
    bible = StubBibleService(chapters={(BOOK_ID, 23): _chapter(BOOK_ID, "PSA", 23, "Psalm", [verse])})
    source = ScheduledDailyLesson(
        date=date(2026, 9, 7), passage_start="PSA.23.1", passage_end="PSA.23.1", book_id=BOOK_ID, reflect=["Hidden"], apply="Hidden", pray="Hidden"
    )
    service = DevotionService(StubDevotionRepository(lesson=source), StubEndUserRepository(None), bible_service=bible)

    result = await service.get_daily_lesson(date(2026, 9, 7), locale_id=None, locale_code="en", include_authored_sections=False)

    assert isinstance(result, AnonymousDailyLesson)
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
    service = DevotionService(repository, StubEndUserRepository(end_user), now_provider=lambda: datetime(2026, 9, 8, 16, 0, tzinfo=timezone.utc))

    result = await service.record_encounter(auth_user_id=auth_user_id, encounter_date=date(2026, 9, 8), time_zone="America/Toronto")

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
    service = DevotionService(repository, StubEndUserRepository(end_user), now_provider=lambda: datetime(2026, 9, 8, 16, 0, tzinfo=timezone.utc))

    result = await service.record_encounter(auth_user_id=auth_user_id, encounter_date=date(2026, 9, 8), time_zone="America/Toronto")

    assert result.current_streak == 5
    assert result.longest_streak == 5
    assert result.welcome_back is False
    assert repository.saved_streak is None


@pytest.mark.asyncio
async def test_record_encounter_rejects_a_past_date_without_advancing_the_streak():
    auth_user_id = UUID("11111111-1111-1111-1111-111111111111")
    end_user = EndUser(id=UUID("22222222-2222-2222-2222-222222222222"), auth_user_id=auth_user_id)
    previous_streak = EncounterStreak(user_id=end_user.id, longest_streak=4, current_streak_length=4, last_encounter_date=date(2026, 9, 6))
    repository = StubDevotionRepository(streak=previous_streak)
    service = DevotionService(repository, StubEndUserRepository(end_user), now_provider=lambda: datetime(2026, 9, 8, 16, 0, tzinfo=timezone.utc))

    with pytest.raises(BadRequestException) as error:
        await service.record_encounter(auth_user_id=auth_user_id, encounter_date=date(2026, 9, 7), time_zone="America/Toronto")

    assert error.value.status_code == 400
    assert error.value.error_code == DevotionErrorCode.ENCOUNTER_DATE_NOT_TODAY
    assert repository.saved_streak is None
    assert repository.inserted_dates == []


@pytest.mark.asyncio
async def test_record_encounter_rejects_a_future_date_without_advancing_the_streak():
    auth_user_id = UUID("11111111-1111-1111-1111-111111111111")
    end_user = EndUser(id=UUID("22222222-2222-2222-2222-222222222222"), auth_user_id=auth_user_id)
    repository = StubDevotionRepository()
    service = DevotionService(repository, StubEndUserRepository(end_user), now_provider=lambda: datetime(2026, 9, 8, 16, 0, tzinfo=timezone.utc))

    with pytest.raises(BadRequestException) as error:
        await service.record_encounter(auth_user_id=auth_user_id, encounter_date=date(2026, 9, 9), time_zone="America/Toronto")

    assert error.value.status_code == 400
    assert error.value.error_code == DevotionErrorCode.ENCOUNTER_DATE_NOT_TODAY
    assert repository.saved_streak is None
    assert repository.inserted_dates == []


@pytest.mark.asyncio
async def test_record_encounter_rejects_a_missing_time_zone_without_writing():
    auth_user_id = UUID("11111111-1111-1111-1111-111111111111")
    end_user = EndUser(id=UUID("22222222-2222-2222-2222-222222222222"), auth_user_id=auth_user_id)
    repository = StubDevotionRepository()
    service = DevotionService(repository, StubEndUserRepository(end_user), now_provider=lambda: datetime(2026, 9, 8, 16, 0, tzinfo=timezone.utc))

    with pytest.raises(BadRequestException) as error:
        await service.record_encounter(auth_user_id=auth_user_id, encounter_date=date(2026, 9, 8), time_zone=None)

    assert error.value.status_code == 400
    assert error.value.error_code == DevotionErrorCode.INVALID_TIME_ZONE
    assert repository.inserted_dates == []


@pytest.mark.asyncio
async def test_record_encounter_rejects_an_invalid_time_zone_name_without_writing():
    auth_user_id = UUID("11111111-1111-1111-1111-111111111111")
    end_user = EndUser(id=UUID("22222222-2222-2222-2222-222222222222"), auth_user_id=auth_user_id)
    repository = StubDevotionRepository()
    service = DevotionService(repository, StubEndUserRepository(end_user), now_provider=lambda: datetime(2026, 9, 8, 16, 0, tzinfo=timezone.utc))

    with pytest.raises(BadRequestException) as error:
        await service.record_encounter(auth_user_id=auth_user_id, encounter_date=date(2026, 9, 8), time_zone="Not/AZone")

    assert error.value.status_code == 400
    assert error.value.error_code == DevotionErrorCode.INVALID_TIME_ZONE
    assert repository.inserted_dates == []


@pytest.mark.asyncio
async def test_record_encounter_uses_the_header_zone_when_it_differs_from_the_server_date():
    auth_user_id = UUID("11111111-1111-1111-1111-111111111111")
    end_user = EndUser(id=UUID("22222222-2222-2222-2222-222222222222"), auth_user_id=auth_user_id)
    repository = StubDevotionRepository()
    service = DevotionService(repository, StubEndUserRepository(end_user), now_provider=lambda: datetime(2026, 9, 10, 2, 30, tzinfo=timezone.utc))

    result = await service.record_encounter(auth_user_id=auth_user_id, encounter_date=date(2026, 9, 9), time_zone="America/Toronto")

    assert result.date == date(2026, 9, 9)
    assert result.current_streak == 1
    assert repository.inserted_dates == [date(2026, 9, 9)]

    with pytest.raises(BadRequestException) as error:
        await service.record_encounter(auth_user_id=auth_user_id, encounter_date=date(2026, 9, 10), time_zone="America/Toronto")

    assert error.value.error_code == DevotionErrorCode.ENCOUNTER_DATE_NOT_TODAY
    assert repository.inserted_dates == [date(2026, 9, 9)]


@pytest.mark.asyncio
async def test_record_encounter_extends_current_and_longest_streak_from_yesterday():
    auth_user_id = UUID("11111111-1111-1111-1111-111111111111")
    end_user = EndUser(id=UUID("22222222-2222-2222-2222-222222222222"), auth_user_id=auth_user_id)
    repository = StubDevotionRepository(
        streak=EncounterStreak(user_id=end_user.id, longest_streak=4, current_streak_length=4, last_encounter_date=date(2026, 9, 7))
    )
    service = DevotionService(repository, StubEndUserRepository(end_user), now_provider=lambda: datetime(2026, 9, 8, 16, 0, tzinfo=timezone.utc))

    result = await service.record_encounter(auth_user_id=auth_user_id, encounter_date=date(2026, 9, 8), time_zone="America/Toronto")

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
    verse = BibleVerse(passage_id="JHN.3.16", verse=16, lines=LOVED_LINES)
    bible = StubBibleService(chapters={(BOOK_ID, 3): _chapter(BOOK_ID, "JHN", 3, "John", [verse])})
    source = ScheduledDailyLesson(
        date=date(2026, 9, 8), passage_start="JHN.3.16", passage_end="JHN.3.16", book_id=BOOK_ID, reflect=["Reflect"], apply="Apply", pray="Pray"
    )
    service = DevotionService(
        StubDevotionRepository(lesson=source, notes={(end_user.id, note.date): note}), StubEndUserRepository(end_user), bible_service=bible
    )

    result = await service.get_daily_lesson(date(2026, 9, 8), locale_id=None, locale_code="en", include_authored_sections=True, auth_user_id=auth_user_id)

    assert result.note == note
