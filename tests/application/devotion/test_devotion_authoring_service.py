from uuid import UUID, uuid4

import pytest

from portal.application.devotion.devotion_service import DevotionService
from portal.application.devotion.results import DevotionDetailResult
from portal.domain.devotion.constants import DevotionErrorCode, DevotionStatus
from portal.domain.locale.entities import Locale
from portal.exceptions.responses import ConflictErrorException, NotFoundException


class StubAuthoringDevotionRepository:
    def __init__(self, *, active_locales: list[Locale], translation_locale_ids: set[UUID]):
        self.active_locales = active_locales
        self.translation_locale_ids = translation_locale_ids
        self.devotion_id = uuid4()
        self.status = DevotionStatus.DRAFT

    async def get_devotion(self, devotion_id: UUID):
        return DevotionDetailResult(id=devotion_id, passage_start="JHN.3.16", passage_end="JHN.3.16", status=self.status)

    async def list_active_locales(self):
        return self.active_locales

    async def list_translation_locale_ids(self, devotion_id: UUID):
        return self.translation_locale_ids

    async def update_devotion_status(self, devotion_id: UUID, status: str):
        self.status = status


class StubDeletableDevotionRepository:
    def __init__(self, *, scheduled: bool = False):
        self.devotion_id = uuid4()
        self.deleted = False
        self.scheduled = scheduled

    async def get_devotion(self, devotion_id: UUID):
        if self.deleted:
            return None
        return DevotionDetailResult(id=devotion_id, passage_start="JHN.3.16", passage_end="JHN.3.16", status=DevotionStatus.DRAFT)

    async def is_devotion_scheduled(self, devotion_id: UUID):
        return self.scheduled

    async def delete_devotion(self, devotion_id: UUID):
        self.deleted = True
        return 1


def locale(identifier: str, language_code: str) -> Locale:
    return Locale(id=UUID(identifier), language_code=language_code, is_active=True)


@pytest.mark.asyncio
async def test_publish_devotion_rejects_when_an_active_locale_has_no_translation():
    english = locale("11111111-1111-1111-1111-111111111111", "en")
    japanese = locale("22222222-2222-2222-2222-222222222222", "ja")
    repository = StubAuthoringDevotionRepository(active_locales=[english, japanese], translation_locale_ids={english.id})
    service = DevotionService(repository, None)

    with pytest.raises(ConflictErrorException) as error:
        await service.publish_devotion(repository.devotion_id)

    assert error.value.error_code == DevotionErrorCode.TRANSLATIONS_INCOMPLETE
    assert error.value.detail == {
        "message": "Devotion cannot be marked ready until every active locale has a translation",
        "errorCode": "TRANSLATIONS_INCOMPLETE",
        "missingLocales": ["ja"],
    }


@pytest.mark.asyncio
async def test_publish_devotion_marks_a_complete_devotion_ready():
    english = locale("11111111-1111-1111-1111-111111111111", "en")
    japanese = locale("22222222-2222-2222-2222-222222222222", "ja")
    repository = StubAuthoringDevotionRepository(active_locales=[english, japanese], translation_locale_ids={english.id, japanese.id})
    service = DevotionService(repository, None)

    result = await service.publish_devotion(repository.devotion_id)

    assert result.status == "ready"


@pytest.mark.asyncio
async def test_publish_devotion_rechecks_the_live_catalog_after_a_locale_is_activated():
    english = locale("11111111-1111-1111-1111-111111111111", "en")
    japanese = locale("22222222-2222-2222-2222-222222222222", "ja")
    repository = StubAuthoringDevotionRepository(active_locales=[english], translation_locale_ids={english.id})
    service = DevotionService(repository, None)

    repository.active_locales.append(japanese)

    with pytest.raises(ConflictErrorException) as error:
        await service.publish_devotion(repository.devotion_id)

    assert error.value.detail["missingLocales"] == ["ja"]


@pytest.mark.asyncio
async def test_delete_devotion_removes_an_unscheduled_draft_from_the_authoring_pool():
    repository = StubDeletableDevotionRepository()
    service = DevotionService(repository, None)

    await service.delete_devotion(repository.devotion_id)

    with pytest.raises(NotFoundException):
        await service.get_devotion(repository.devotion_id)


@pytest.mark.asyncio
async def test_delete_devotion_rejects_a_scheduled_devotion():
    repository = StubDeletableDevotionRepository(scheduled=True)
    service = DevotionService(repository, None)

    with pytest.raises(ConflictErrorException) as error:
        await service.delete_devotion(repository.devotion_id)

    assert error.value.error_code == DevotionErrorCode.DEVOTION_SCHEDULED
