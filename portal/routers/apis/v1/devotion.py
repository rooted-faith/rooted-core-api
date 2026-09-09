from datetime import date

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, Path, Query
from starlette import status

from portal.application.devotion.devotion_service import DevotionService
from portal.application.devotion.mappers import (
    daily_lesson_to_api,
    encounter_result_to_api,
    lesson_note_to_api,
    rhythm_result_to_api,
    upsert_lesson_note_to_command,
)
from portal.container import Container
from portal.exceptions.responses import UnauthorizedException
from portal.libs.contexts.request_context import get_request_context, get_resolved_locale_code, get_resolved_locale_id
from portal.libs.contexts.user_context import get_user_context
from portal.routers.auth_router import AuthRouter
from portal.serializers.apis.v1.devotion import (
    AnonymousDailyLessonResponse,
    DailyLessonResponse,
    EncounterRequest,
    EncounterResponse,
    LessonNoteResponse,
    LessonNoteUpsertRequest,
    RhythmResponse,
)

router: AuthRouter = AuthRouter(require_auth=False, optional_auth=True)


def _auth_user_id():
    user_context = get_user_context()
    if user_context is None or user_context.user_id is None:
        raise UnauthorizedException()
    return user_context.user_id


async def _read_daily_lesson(lesson_date: date, devotion_service: DevotionService) -> AnonymousDailyLessonResponse | DailyLessonResponse:
    locale_id = get_resolved_locale_id()
    locale_code = get_resolved_locale_code()
    request_context = get_request_context()
    if request_context and request_context.locale_candidates and locale_code:
        resolved_language = locale_code.split("-", maxsplit=1)[0].lower()
        accepted_languages = {candidate.split("-", maxsplit=1)[0].lower() for candidate in request_context.locale_candidates if candidate != "*"}
        if "*" not in request_context.locale_candidates and resolved_language not in accepted_languages:
            locale_id = None
            locale_code = None
    user_context = get_user_context()
    auth_user_id = user_context.user_id if user_context else None
    result = await devotion_service.get_daily_lesson(
        lesson_date=lesson_date, locale_id=locale_id, locale_code=locale_code, include_authored_sections=bool(auth_user_id), auth_user_id=auth_user_id
    )
    return daily_lesson_to_api(result)


@router.get(
    path="/today",
    response_model=AnonymousDailyLessonResponse | DailyLessonResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    operation_id="get_anonymous_daily_lesson",
    summary="Get today's Daily lesson",
)
@inject
async def get_today_daily_lesson(
    date_: date = Query(alias="date"), devotion_service: DevotionService = Depends(Provide[Container.devotion_service])
) -> AnonymousDailyLessonResponse | DailyLessonResponse:
    return await _read_daily_lesson(date_, devotion_service)


@router.get(
    path="/lessons/{date}",
    response_model=AnonymousDailyLessonResponse | DailyLessonResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    operation_id="get_daily_lesson",
    summary="Get a Daily lesson by date",
)
@inject
async def get_daily_lesson(
    date_: date = Path(alias="date"), devotion_service: DevotionService = Depends(Provide[Container.devotion_service])
) -> AnonymousDailyLessonResponse | DailyLessonResponse:
    return await _read_daily_lesson(date_, devotion_service)


@router.post(
    path="/encounters",
    require_auth=True,
    optional_auth=False,
    response_model=EncounterResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    operation_id="record_encounter",
    summary="Record today's Encounter day",
)
@inject
async def record_encounter(request: EncounterRequest, devotion_service: DevotionService = Depends(Provide[Container.devotion_service])) -> EncounterResponse:
    result = await devotion_service.record_encounter(auth_user_id=_auth_user_id(), encounter_date=request.date)
    return encounter_result_to_api(result)


@router.put(
    path="/notes",
    require_auth=True,
    optional_auth=False,
    response_model=LessonNoteResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    operation_id="upsert_lesson_note",
    summary="Create or replace today's private lesson note",
)
@inject
async def upsert_lesson_note(
    request: LessonNoteUpsertRequest, devotion_service: DevotionService = Depends(Provide[Container.devotion_service])
) -> LessonNoteResponse:
    request_context = get_request_context()
    result = await devotion_service.upsert_lesson_note(
        auth_user_id=_auth_user_id(), command=upsert_lesson_note_to_command(request), time_zone=request_context.headers.time_zone if request_context else None
    )
    return lesson_note_to_api(result)


@router.get(
    path="/rhythm",
    require_auth=True,
    optional_auth=False,
    response_model=RhythmResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
    operation_id="get_encounter_rhythm",
    summary="Get the End user's Encounter rhythm",
)
@inject
async def get_rhythm(date_: date = Query(alias="date"), devotion_service: DevotionService = Depends(Provide[Container.devotion_service])) -> RhythmResponse:
    result = await devotion_service.get_rhythm(auth_user_id=_auth_user_id(), reader_date=date_)
    return rhythm_result_to_api(result)
