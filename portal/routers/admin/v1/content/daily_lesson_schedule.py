"""Admin Daily lesson schedule routes."""

from datetime import date
from typing import Annotated

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, Query, status

from portal.application.devotion.devotion_service import DevotionService
from portal.application.devotion.mappers import (
    daily_lesson_schedule_query_to_command,
    daily_lesson_schedule_range_to_api,
    daily_lesson_schedule_to_api,
    daily_lesson_schedule_upsert_to_command,
)
from portal.container import Container
from portal.libs.consts.permission import Permission
from portal.routers.auth_router import AuthRouter
from portal.serializers.admin.v1.devotion import (
    AdminDailyLessonScheduleItem,
    AdminDailyLessonScheduleQuery,
    AdminDailyLessonScheduleRange,
    AdminDailyLessonScheduleUpsert,
)

router: AuthRouter = AuthRouter(is_admin=True)


@router.get(path="", response_model=AdminDailyLessonScheduleRange, response_model_by_alias=True, permissions=[Permission.CONTENT_DEVOTION.read])
@inject
async def get_daily_lesson_schedule(
    query: Annotated[AdminDailyLessonScheduleQuery, Query()], devotion_service: DevotionService = Depends(Provide[Container.devotion_service])
) -> AdminDailyLessonScheduleRange:
    return daily_lesson_schedule_range_to_api(await devotion_service.get_daily_lesson_schedule(daily_lesson_schedule_query_to_command(query)))


@router.post(
    path="/{lesson_date}",
    status_code=status.HTTP_201_CREATED,
    response_model=AdminDailyLessonScheduleItem,
    response_model_by_alias=True,
    permissions=[Permission.CONTENT_DEVOTION.create],
)
@inject
async def schedule_daily_lesson(
    lesson_date: date, body: AdminDailyLessonScheduleUpsert, devotion_service: DevotionService = Depends(Provide[Container.devotion_service])
) -> AdminDailyLessonScheduleItem:
    return daily_lesson_schedule_to_api(await devotion_service.schedule_daily_lesson(lesson_date, daily_lesson_schedule_upsert_to_command(body)))


@router.put(path="/{lesson_date}", response_model=AdminDailyLessonScheduleItem, response_model_by_alias=True, permissions=[Permission.CONTENT_DEVOTION.modify])
@inject
async def reschedule_daily_lesson(
    lesson_date: date, body: AdminDailyLessonScheduleUpsert, devotion_service: DevotionService = Depends(Provide[Container.devotion_service])
) -> AdminDailyLessonScheduleItem:
    return daily_lesson_schedule_to_api(await devotion_service.reschedule_daily_lesson(lesson_date, daily_lesson_schedule_upsert_to_command(body)))


@router.delete(path="/{lesson_date}", status_code=status.HTTP_204_NO_CONTENT, permissions=[Permission.CONTENT_DEVOTION.delete])
@inject
async def unschedule_daily_lesson(lesson_date: date, devotion_service: DevotionService = Depends(Provide[Container.devotion_service])) -> None:
    await devotion_service.unschedule_daily_lesson(lesson_date)
