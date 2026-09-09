from datetime import date, timedelta
from uuid import UUID

import sqlalchemy as sa

from portal.domain.devotion.constants import DevotionStatus
from portal.domain.devotion.entities import AnonymousDailyLesson, DailyLesson, EncounterStreak, LessonNote, Passage
from portal.domain.devotion.entities import Devotion as DevotionEntity
from portal.domain.devotion.entities import DevotionTranslation as DevotionTranslationEntity
from portal.domain.locale.entities import Locale
from portal.libs.database import Session
from portal.libs.database.execute_result import affected_rows
from portal.models import BibleBook, BibleVerse, BibleVersion, Devotion, DevotionDailyLessonSchedule, DevotionTranslation, EncounterDay, SystemLocale
from portal.models import EncounterStreak as EncounterStreakModel
from portal.models import LessonNote as LessonNoteModel


class DevotionRepository:
    def __init__(self, session: Session):
        self._session = session

    async def daily_lesson_exists(self, lesson_date: date) -> bool:
        schedule_id = await self._session.select(DevotionDailyLessonSchedule.id).where(DevotionDailyLessonSchedule.date == lesson_date).fetchval()
        return schedule_id is not None

    async def insert_encounter_day(self, user_id: UUID, encounter_date: date) -> bool:
        status = await (
            self._session.insert(EncounterDay).values(user_id=user_id, date=encounter_date).on_conflict_do_nothing(index_elements=["user_id", "date"]).execute()
        )
        return status == "INSERT 0 1"

    async def get_encounter_streak(self, user_id: UUID) -> EncounterStreak | None:
        return await (
            self._session.select(
                EncounterStreakModel.user_id,
                EncounterStreakModel.longest_streak,
                EncounterStreakModel.current_streak_length,
                EncounterStreakModel.last_encounter_date,
            )
            .where(EncounterStreakModel.user_id == user_id)
            .fetchrow(as_model=EncounterStreak)
        )

    async def save_encounter_streak(self, streak: EncounterStreak) -> None:
        await (
            self._session.insert(EncounterStreakModel)
            .values(**streak.model_dump())
            .on_conflict_do_update(
                index_elements=["user_id"],
                set_={
                    "longest_streak": sa.func.greatest(EncounterStreakModel.longest_streak, streak.longest_streak),
                    "current_streak_length": streak.current_streak_length,
                    "last_encounter_date": streak.last_encounter_date,
                    "updated_at": sa.func.now(),
                },
            )
            .execute()
        )

    async def list_recent_encounter_dates(self, user_id: UUID, through_date: date) -> list[date]:
        return await (
            self._session.select(EncounterDay.date)
            .where(EncounterDay.user_id == user_id)
            .where(EncounterDay.date >= through_date - timedelta(days=34))
            .where(EncounterDay.date <= through_date)
            .order_by(EncounterDay.date)
            .fetchvals()
        )

    async def get_lesson_note(self, user_id: UUID, note_date: date) -> LessonNote | None:
        return await (
            self._session.select(LessonNoteModel.date, LessonNoteModel.body, LessonNoteModel.reflect_answers.label("reflects"))
            .where(LessonNoteModel.user_id == user_id)
            .where(LessonNoteModel.date == note_date)
            .fetchrow(as_model=LessonNote)
        )

    async def upsert_lesson_note(self, user_id: UUID, note: LessonNote) -> None:
        await (
            self._session.insert(LessonNoteModel)
            .values(user_id=user_id, date=note.date, body=note.body, reflect_answers=note.reflects)
            .on_conflict_do_update(
                index_elements=["user_id", "date"],
                set_={
                    "body": sa.literal_column("excluded.body"),
                    "reflect_answers": sa.literal_column("excluded.reflect_answers"),
                    "updated_at": sa.func.now(),
                },
            )
            .execute()
        )

    async def get_devotion(self, devotion_id: UUID) -> DevotionEntity | None:
        devotion = await (
            self._session.select(Devotion.id, Devotion.passage_start, Devotion.passage_end, Devotion.status)
            .where(Devotion.id == devotion_id)
            .fetchrow(as_model=DevotionEntity)
        )
        if devotion is None:
            return None
        translations = await (
            self._session.select(
                DevotionTranslation.locale_id,
                sa.func.concat_ws("-", SystemLocale.language_code, SystemLocale.script_code, SystemLocale.region_code).label("locale_code"),
                DevotionTranslation.reflect,
                DevotionTranslation.apply,
                DevotionTranslation.pray,
            )
            .join(SystemLocale, SystemLocale.id == DevotionTranslation.locale_id)
            .where(DevotionTranslation.devotion_id == devotion_id)
            .order_by(SystemLocale.sequence)
            .fetch(as_model=DevotionTranslationEntity)
        )
        return devotion.model_copy(update={"translations": translations or []})

    async def insert_devotion(self, devotion_id: UUID, passage_start: str, passage_end: str) -> None:
        await (
            self._session.insert(Devotion)
            .values(id=devotion_id, passage_start=passage_start, passage_end=passage_end, status=DevotionStatus.DRAFT.value)
            .execute()
        )

    async def update_devotion(self, devotion_id: UUID, passage_start: str, passage_end: str) -> int:
        result = await self._session.update(Devotion).values(passage_start=passage_start, passage_end=passage_end).where(Devotion.id == devotion_id).execute()
        return affected_rows(result)

    async def update_devotion_status(self, devotion_id: UUID, status: DevotionStatus) -> int:
        result = await self._session.update(Devotion).values(status=status.value).where(Devotion.id == devotion_id).execute()
        return affected_rows(result)

    async def is_devotion_scheduled(self, devotion_id: UUID) -> bool:
        schedule_id = await self._session.select(DevotionDailyLessonSchedule.id).where(DevotionDailyLessonSchedule.devotion_id == devotion_id).fetchval()
        return schedule_id is not None

    async def delete_devotion(self, devotion_id: UUID) -> int:
        result = await self._session.delete(Devotion).where(Devotion.id == devotion_id).execute()
        return affected_rows(result)

    async def resolve_locale(self, locale_code: str) -> Locale | None:
        return await (
            self._session.select(
                SystemLocale.id,
                SystemLocale.language_code,
                SystemLocale.script_code,
                SystemLocale.region_code,
                SystemLocale.name,
                SystemLocale.native_name,
                SystemLocale.is_active,
                SystemLocale.is_default,
            )
            .where(SystemLocale.is_deleted == False)
            .where(sa.func.lower(sa.func.concat_ws("-", SystemLocale.language_code, SystemLocale.script_code, SystemLocale.region_code)) == locale_code.lower())
            .fetchrow(as_model=Locale)
        )

    async def list_active_locales(self) -> list[Locale]:
        locales = await (
            self._session.select(
                SystemLocale.id,
                SystemLocale.language_code,
                SystemLocale.script_code,
                SystemLocale.region_code,
                SystemLocale.name,
                SystemLocale.native_name,
                SystemLocale.is_active,
                SystemLocale.is_default,
            )
            .where(SystemLocale.is_deleted == False)
            .where(SystemLocale.is_active == True)
            .order_by(SystemLocale.sequence)
            .fetch(as_model=Locale)
        )
        return locales or []

    async def list_translation_locale_ids(self, devotion_id: UUID) -> set[UUID]:
        locale_ids = await self._session.select(DevotionTranslation.locale_id).where(DevotionTranslation.devotion_id == devotion_id).fetchvals()
        return set(locale_ids)

    async def upsert_translation(self, devotion_id: UUID, locale_id: UUID, reflect: list[str], apply: str, pray: str) -> None:
        await (
            self._session.insert(DevotionTranslation)
            .values(devotion_id=devotion_id, locale_id=locale_id, reflect=reflect, apply=apply, pray=pray)
            .on_conflict_do_update(
                index_elements=["devotion_id", "locale_id"],
                set_={
                    "reflect": sa.literal_column("excluded.reflect"),
                    "apply": sa.literal_column("excluded.apply"),
                    "pray": sa.literal_column("excluded.pray"),
                    "updated_at": sa.func.now(),
                },
            )
            .execute()
        )

    async def fetch_devotion_pages(
        self, page: int, page_size: int, status: DevotionStatus | None, missing_locale_id: UUID | None
    ) -> tuple[list[DevotionEntity], int]:
        query = self._session.select(Devotion.id, Devotion.passage_start, Devotion.passage_end, Devotion.status).select_from(Devotion)
        if missing_locale_id is not None:
            query = query.outerjoin(
                DevotionTranslation, sa.and_(DevotionTranslation.devotion_id == Devotion.id, DevotionTranslation.locale_id == missing_locale_id)
            ).where(DevotionTranslation.id.is_(None))
        if status is not None:
            query = query.where(Devotion.status == status.value)
        items, total = (
            await query.order_by(Devotion.updated_at.desc()).limit(page_size).offset(page * page_size).fetchpages(no_order_by=False, as_model=DevotionEntity)
        )
        return items or [], total

    async def fetch_daily_lesson(
        self, lesson_date: date, locale_id: UUID | None, locale_code: str | None, include_authored_sections: bool
    ) -> AnonymousDailyLesson | DailyLesson | None:
        if locale_id is None or locale_code is None:
            return None

        language = locale_code.split("-", maxsplit=1)[0]
        selected_columns = [Devotion.passage_start, Devotion.passage_end]
        if include_authored_sections:
            selected_columns.extend([DevotionTranslation.reflect, DevotionTranslation.apply, DevotionTranslation.pray])
        scheduled_passage = await (
            self._session.select(*selected_columns)
            .join(DevotionDailyLessonSchedule, DevotionDailyLessonSchedule.devotion_id == Devotion.id)
            .join(DevotionTranslation, DevotionTranslation.devotion_id == Devotion.id)
            .where(DevotionDailyLessonSchedule.date == lesson_date)
            .where(DevotionTranslation.locale_id == locale_id)
            .where(Devotion.status == DevotionStatus.READY.value)
            .fetchrow()
        )
        if not scheduled_passage:
            return None

        start_book, start_chapter, start_verse = self._parse_passage_id(scheduled_passage["passage_start"])
        end_book, end_chapter, end_verse = self._parse_passage_id(scheduled_passage["passage_end"])
        if start_book != end_book:
            return None

        bible_version_id = await (
            self._session.select(BibleVersion.id)
            .where(BibleVersion.is_active == True)  # noqa: E712
            .where(BibleVersion.language_tag.ilike(f"{language}%"))
            .order_by(BibleVersion.youversion_bible_id)
            .fetchval()
        )
        if bible_version_id is None:
            return None

        verses = await (
            self._session.select(BibleBook.title.label("book_name"), BibleVerse.chapter, BibleVerse.verse, BibleVerse.content)
            .join(BibleBook, BibleVerse.book_id == BibleBook.id)
            .join(BibleVersion, BibleBook.bible_version_id == BibleVersion.id)
            .where(BibleVersion.id == bible_version_id)
            .where(BibleBook.book_code == start_book)
            .where(sa.or_(BibleVerse.chapter > start_chapter, sa.and_(BibleVerse.chapter == start_chapter, BibleVerse.verse >= start_verse)))
            .where(sa.or_(BibleVerse.chapter < end_chapter, sa.and_(BibleVerse.chapter == end_chapter, BibleVerse.verse <= end_verse)))
            .order_by(BibleVersion.youversion_bible_id, BibleVerse.chapter, BibleVerse.verse)
            .fetch()
        )
        if not verses:
            return None

        first = verses[0]
        last = verses[-1]
        verse_ref = f"{first['book_name']} {first['chapter']}:{first['verse']}"
        if (last["chapter"], last["verse"]) != (first["chapter"], first["verse"]):
            verse_ref += f"–{last['chapter']}:{last['verse']}"
        passage = Passage(
            start=scheduled_passage["passage_start"], end=scheduled_passage["passage_end"], ref=verse_ref, verses=[row["content"] for row in verses]
        )
        if include_authored_sections:
            return DailyLesson(
                date=lesson_date, passage=passage, reflect=scheduled_passage["reflect"], apply=scheduled_passage["apply"], pray=scheduled_passage["pray"]
            )
        return AnonymousDailyLesson(date=lesson_date, passage=passage)

    @staticmethod
    def _parse_passage_id(passage_id: str) -> tuple[str, int, int]:
        book_code, chapter, verse = passage_id.split(".", maxsplit=2)
        return book_code, int(chapter), int(verse)
