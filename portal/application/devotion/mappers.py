from portal.application.devotion.commands import (
    CreateDevotionCommand,
    DevotionPagesQuery,
    UpdateDevotionCommand,
    UpsertDevotionTranslationCommand,
    UpsertLessonNoteCommand,
)
from portal.application.devotion.results import (
    DevotionDetailResult,
    DevotionListItemResult,
    DevotionPageResult,
    DevotionTranslationResult,
    EncounterResult,
    RhythmResult,
)
from portal.domain.devotion.entities import AnonymousDailyLesson, DailyLesson, LessonNote
from portal.serializers.admin.v1.devotion import (
    AdminDevotionCreate,
    AdminDevotionDetail,
    AdminDevotionItem,
    AdminDevotionPages,
    AdminDevotionQuery,
    AdminDevotionTranslation,
    AdminDevotionTranslationUpsert,
    AdminDevotionUpdate,
)
from portal.serializers.apis.v1.devotion import (
    AnonymousDailyLessonResponse,
    DailyLessonResponse,
    EncounterResponse,
    LessonNoteResponse,
    LessonNoteUpsertRequest,
    PassageResponse,
    RhythmResponse,
)


def anonymous_daily_lesson_to_api(result: AnonymousDailyLesson) -> AnonymousDailyLessonResponse:
    return AnonymousDailyLessonResponse(date=result.date, passage=PassageResponse(**result.passage.model_dump()), locked=result.locked)


def daily_lesson_to_api(result: AnonymousDailyLesson | DailyLesson) -> AnonymousDailyLessonResponse | DailyLessonResponse:
    if isinstance(result, DailyLesson):
        return DailyLessonResponse(
            date=result.date,
            passage=PassageResponse(**result.passage.model_dump()),
            reflect=result.reflect,
            apply=result.apply,
            pray=result.pray,
            note=lesson_note_to_api(result.note) if result.note else None,
            locked=result.locked,
        )
    return anonymous_daily_lesson_to_api(result)


def encounter_result_to_api(result: EncounterResult) -> EncounterResponse:
    return EncounterResponse.model_validate(result, from_attributes=True)


def lesson_note_to_api(result: LessonNote) -> LessonNoteResponse:
    return LessonNoteResponse.model_validate(result, from_attributes=True)


def upsert_lesson_note_to_command(model: LessonNoteUpsertRequest) -> UpsertLessonNoteCommand:
    return UpsertLessonNoteCommand(date=model.date, body=model.body, reflects=model.reflects)


def rhythm_result_to_api(result: RhythmResult) -> RhythmResponse:
    return RhythmResponse.model_validate(result, from_attributes=True)


def create_devotion_to_command(model: AdminDevotionCreate) -> CreateDevotionCommand:
    return CreateDevotionCommand(passage_start=model.passage_start, passage_end=model.passage_end)


def update_devotion_to_command(model: AdminDevotionUpdate) -> UpdateDevotionCommand:
    return UpdateDevotionCommand(passage_start=model.passage_start, passage_end=model.passage_end)


def upsert_devotion_translation_to_command(model: AdminDevotionTranslationUpsert) -> UpsertDevotionTranslationCommand:
    return UpsertDevotionTranslationCommand(reflect=model.reflect, apply=model.apply, pray=model.pray)


def devotion_pages_query_to_command(model: AdminDevotionQuery) -> DevotionPagesQuery:
    return DevotionPagesQuery(page=model.page, page_size=model.page_size, status=model.status, missing_locale=model.missing_locale)


def devotion_translation_to_api(result: DevotionTranslationResult) -> AdminDevotionTranslation:
    return AdminDevotionTranslation.model_validate(result)


def devotion_item_to_api(result: DevotionListItemResult) -> AdminDevotionItem:
    return AdminDevotionItem.model_validate(result)


def devotion_detail_to_api(result: DevotionDetailResult) -> AdminDevotionDetail:
    return AdminDevotionDetail(
        id=result.id,
        passage_start=result.passage_start,
        passage_end=result.passage_end,
        status=result.status,
        translations=[devotion_translation_to_api(item) for item in result.translations],
    )


def devotion_page_to_api(result: DevotionPageResult) -> AdminDevotionPages:
    return AdminDevotionPages(
        page=result.page,
        page_size=result.page_size,
        total=result.total,
        total_pages=result.total_pages,
        items=[devotion_item_to_api(item) for item in result.items],
    )
