from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import pytest

from portal.application.devotion.commands import DailyLessonScheduleQuery, ScheduleDailyLessonCommand
from portal.application.devotion.devotion_service import DevotionService
from portal.domain.devotion.constants import DevotionErrorCode, DevotionStatus
from portal.domain.devotion.entities import DailyLessonSchedule, Devotion
from portal.exceptions.responses import ConflictErrorException


class StubDailyLessonScheduleRepository:
    def __init__(self, *, devotions: dict[UUID, Devotion], schedules: dict[date, UUID] | None = None):
        self.devotions = devotions
        self.schedules = schedules or {}

    async def get_devotion(self, devotion_id: UUID) -> Devotion | None:
        return self.devotions.get(devotion_id)

    async def insert_daily_lesson_schedule(self, lesson_date: date, devotion_id: UUID) -> bool:
        if lesson_date in self.schedules:
            return False
        self.schedules[lesson_date] = devotion_id
        return True

    async def update_daily_lesson_schedule(self, lesson_date: date, devotion_id: UUID) -> int:
        if lesson_date not in self.schedules:
            return 0
        self.schedules[lesson_date] = devotion_id
        return 1

    async def delete_daily_lesson_schedule(self, lesson_date: date) -> int:
        if lesson_date not in self.schedules:
            return 0
        del self.schedules[lesson_date]
        return 1

    async def list_daily_lesson_schedules(self, from_date: date, to_date: date):
        return [
            DailyLessonSchedule(date=lesson_date, devotion_id=devotion_id)
            for lesson_date, devotion_id in sorted(self.schedules.items())
            if from_date <= lesson_date <= to_date
        ]


READY_DEVOTION_ID = UUID("11111111-1111-1111-1111-111111111111")
DRAFT_DEVOTION_ID = UUID("22222222-2222-2222-2222-222222222222")
OTHER_READY_DEVOTION_ID = UUID("33333333-3333-3333-3333-333333333333")
TODAY = date(2026, 9, 10)


def devotion(devotion_id: UUID, status: DevotionStatus) -> Devotion:
    return Devotion(id=devotion_id, passage_start="JHN.3.16", passage_end="JHN.3.16", status=status)


def service(repository: StubDailyLessonScheduleRepository) -> DevotionService:
    return DevotionService(repository, None, now_provider=lambda: datetime(2026, 9, 10, tzinfo=timezone.utc))


@pytest.mark.asyncio
async def test_schedule_daily_lesson_adds_a_ready_devotion_to_a_future_date():
    repository = StubDailyLessonScheduleRepository(devotions={READY_DEVOTION_ID: devotion(READY_DEVOTION_ID, DevotionStatus.READY)})

    result = await service(repository).schedule_daily_lesson(TODAY, ScheduleDailyLessonCommand(devotion_id=READY_DEVOTION_ID))

    assert result.date == TODAY
    assert result.devotion_id == READY_DEVOTION_ID


@pytest.mark.asyncio
async def test_schedule_daily_lesson_reuses_a_ready_devotion_on_another_date():
    repository = StubDailyLessonScheduleRepository(devotions={READY_DEVOTION_ID: devotion(READY_DEVOTION_ID, DevotionStatus.READY)})
    schedule_service = service(repository)

    await schedule_service.schedule_daily_lesson(TODAY, ScheduleDailyLessonCommand(devotion_id=READY_DEVOTION_ID))
    result = await schedule_service.schedule_daily_lesson(TODAY + timedelta(days=365), ScheduleDailyLessonCommand(devotion_id=READY_DEVOTION_ID))

    assert result.devotion_id == READY_DEVOTION_ID
    assert repository.schedules == {TODAY: READY_DEVOTION_ID, TODAY + timedelta(days=365): READY_DEVOTION_ID}


@pytest.mark.asyncio
async def test_schedule_daily_lesson_rejects_an_occupied_date():
    repository = StubDailyLessonScheduleRepository(
        devotions={
            READY_DEVOTION_ID: devotion(READY_DEVOTION_ID, DevotionStatus.READY),
            OTHER_READY_DEVOTION_ID: devotion(OTHER_READY_DEVOTION_ID, DevotionStatus.READY),
        },
        schedules={TODAY: READY_DEVOTION_ID},
    )

    with pytest.raises(ConflictErrorException) as error:
        await service(repository).schedule_daily_lesson(TODAY, ScheduleDailyLessonCommand(devotion_id=OTHER_READY_DEVOTION_ID))

    assert error.value.error_code == DevotionErrorCode.DAILY_LESSON_DATE_ALREADY_SCHEDULED


@pytest.mark.asyncio
async def test_schedule_daily_lesson_rejects_a_draft_devotion():
    repository = StubDailyLessonScheduleRepository(devotions={DRAFT_DEVOTION_ID: devotion(DRAFT_DEVOTION_ID, DevotionStatus.DRAFT)})

    with pytest.raises(ConflictErrorException) as error:
        await service(repository).schedule_daily_lesson(TODAY, ScheduleDailyLessonCommand(devotion_id=DRAFT_DEVOTION_ID))

    assert error.value.error_code == DevotionErrorCode.DEVOTION_NOT_READY


@pytest.mark.asyncio
async def test_daily_lesson_schedule_changes_reject_past_dates():
    repository = StubDailyLessonScheduleRepository(
        devotions={READY_DEVOTION_ID: devotion(READY_DEVOTION_ID, DevotionStatus.READY)}, schedules={TODAY - timedelta(days=1): READY_DEVOTION_ID}
    )
    schedule_service = service(repository)

    for operation in (
        lambda: schedule_service.schedule_daily_lesson(TODAY - timedelta(days=1), ScheduleDailyLessonCommand(devotion_id=READY_DEVOTION_ID)),
        lambda: schedule_service.reschedule_daily_lesson(TODAY - timedelta(days=1), ScheduleDailyLessonCommand(devotion_id=READY_DEVOTION_ID)),
        lambda: schedule_service.unschedule_daily_lesson(TODAY - timedelta(days=1)),
    ):
        with pytest.raises(ConflictErrorException) as error:
            await operation()

        assert error.value.error_code == DevotionErrorCode.DAILY_LESSON_DATE_IN_PAST


@pytest.mark.asyncio
async def test_reschedule_and_unschedule_allow_future_dates():
    future_date = TODAY + timedelta(days=1)
    repository = StubDailyLessonScheduleRepository(
        devotions={
            READY_DEVOTION_ID: devotion(READY_DEVOTION_ID, DevotionStatus.READY),
            OTHER_READY_DEVOTION_ID: devotion(OTHER_READY_DEVOTION_ID, DevotionStatus.READY),
        },
        schedules={future_date: READY_DEVOTION_ID},
    )
    schedule_service = service(repository)

    rescheduled = await schedule_service.reschedule_daily_lesson(future_date, ScheduleDailyLessonCommand(devotion_id=OTHER_READY_DEVOTION_ID))
    await schedule_service.unschedule_daily_lesson(future_date)

    assert rescheduled.devotion_id == OTHER_READY_DEVOTION_ID
    assert future_date not in repository.schedules


@pytest.mark.asyncio
async def test_get_daily_lesson_schedule_marks_holes_and_reports_contiguous_horizon():
    repository = StubDailyLessonScheduleRepository(
        devotions={READY_DEVOTION_ID: devotion(READY_DEVOTION_ID, DevotionStatus.READY)},
        schedules={TODAY: READY_DEVOTION_ID, TODAY + timedelta(days=1): READY_DEVOTION_ID, TODAY + timedelta(days=3): READY_DEVOTION_ID},
    )

    result = await service(repository).get_daily_lesson_schedule(DailyLessonScheduleQuery(from_date=TODAY, to_date=TODAY + timedelta(days=3)))

    assert [(item.date, item.devotion_id) for item in result.items] == [
        (TODAY, READY_DEVOTION_ID),
        (TODAY + timedelta(days=1), READY_DEVOTION_ID),
        (TODAY + timedelta(days=2), None),
        (TODAY + timedelta(days=3), READY_DEVOTION_ID),
    ]
    assert result.scheduled_through == TODAY + timedelta(days=1)
