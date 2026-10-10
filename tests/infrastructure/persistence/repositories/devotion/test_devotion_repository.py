"""DevotionRepository JSONB reads and writes against a real PostgreSQL database."""

from datetime import date
from uuid import UUID, uuid4

import pytest

from portal.application.devotion.devotion_service import DevotionService
from portal.domain.bible.entities import BibleChapter, BibleVerse
from portal.domain.devotion.constants import DevotionStatus
from portal.domain.devotion.entities import DailyLesson, LessonNote
from portal.domain.locale.entities import Locale
from portal.infrastructure.persistence.repositories.app.end_user_repository import EndUserRepository
from portal.infrastructure.persistence.repositories.devotion.devotion_repository import DevotionRepository
from portal.libs.database import Session

LESSON_DATE = date(2199, 1, 1)
REFLECT = ["Where do you see God's love today?", "Who can you love practically?"]


async def _insert_end_user(session: Session) -> tuple[UUID, UUID]:
    auth_user_id = await session.fetchval(
        "INSERT INTO auth.\"user\" (email, created_by, updated_by) VALUES ($1, 'test', 'test') RETURNING id", f"{uuid4()}@example.test"
    )
    end_user_id = await session.fetchval(
        "INSERT INTO app.\"user\" (auth_user_id, created_by, updated_by) VALUES ($1, 'test', 'test') RETURNING id", auth_user_id
    )
    return auth_user_id, end_user_id


async def _schedule_ready_devotion(repository: DevotionRepository) -> tuple[UUID, Locale]:
    locale = await repository.resolve_locale("en")
    if locale is None:
        pytest.skip("Locale 'en' is not seeded")
    devotion_id = uuid4()
    await repository.insert_devotion(devotion_id, "JHN.3.16", "JHN.3.16")
    await repository.upsert_translation(devotion_id, locale.id, REFLECT, "Encourage one person today.", "Help me share your love.")
    await repository.update_devotion_status(devotion_id, DevotionStatus.READY)
    await repository.insert_daily_lesson_schedule(LESSON_DATE, devotion_id)
    return devotion_id, locale


@pytest.mark.asyncio
async def test_signed_in_daily_lesson_reads_reflect_as_a_list(db_session) -> None:
    repository = DevotionRepository(db_session)
    _, locale = await _schedule_ready_devotion(repository)

    lesson = await repository.fetch_daily_lesson(LESSON_DATE, locale.id, "en", include_authored_sections=True)

    assert lesson is not None
    assert lesson.reflect == REFLECT


@pytest.mark.asyncio
async def test_get_devotion_reads_translation_reflect_as_a_list(db_session) -> None:
    repository = DevotionRepository(db_session)
    devotion_id, _ = await _schedule_ready_devotion(repository)

    devotion = await repository.get_devotion(devotion_id)

    assert [translation.reflect for translation in devotion.translations] == [REFLECT]


@pytest.mark.asyncio
async def test_lesson_note_round_trips_reflect_answers(db_session) -> None:
    repository = DevotionRepository(db_session)
    _, end_user_id = await _insert_end_user(db_session)

    await repository.upsert_lesson_note(end_user_id, LessonNote(date=LESSON_DATE, body="First", reflects=["Answer", None]))
    await repository.upsert_lesson_note(end_user_id, LessonNote(date=LESSON_DATE, body="Second", reflects=[None, "Changed"]))

    assert await repository.get_lesson_note(end_user_id, LESSON_DATE) == LessonNote(date=LESSON_DATE, body="Second", reflects=[None, "Changed"])


class JohnThreeBibleService:
    """Serves John 3:16 for whichever book id the real repository resolved."""

    def __init__(self) -> None:
        self.verse = BibleVerse(passage_id="JHN.3.16", verse=16, lines=[{"type": "line", "fragments": [{"text": "For God so loved the world"}]}])

    async def get_chapter(self, book_id: UUID, chapter: int) -> BibleChapter:
        return BibleChapter(
            bible_version_id=uuid4(),
            youversion_bible_id="test",
            bible_title="Test",
            book_id=book_id,
            book_code="JHN",
            book_name="John",
            chapter=chapter,
            verses=[self.verse],
        )


@pytest.mark.asyncio
async def test_get_daily_lesson_for_a_signed_in_end_user_returns_reflect_and_lesson_note(db_session) -> None:
    repository = DevotionRepository(db_session)
    _, locale = await _schedule_ready_devotion(repository)
    auth_user_id, end_user_id = await _insert_end_user(db_session)
    note = LessonNote(date=LESSON_DATE, body="Thankful", reflects=["Answer", None])
    await repository.upsert_lesson_note(end_user_id, note)
    service = DevotionService(repository, EndUserRepository(db_session), bible_service=JohnThreeBibleService())

    lesson = await service.get_daily_lesson(LESSON_DATE, locale.id, "en", include_authored_sections=True, auth_user_id=auth_user_id)

    assert isinstance(lesson, DailyLesson)
    assert lesson.reflect == REFLECT
    assert lesson.note == note
