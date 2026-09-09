from datetime import date

import pytest
from fastapi.routing import APIRoute

from portal.application.auth.results import HeaderInfo
from portal.application.devotion.results import EncounterResult, RhythmResult
from portal.domain.devotion.entities import AnonymousDailyLesson, DailyLesson, LessonNote, Passage
from portal.libs.contexts.request_context import RequestContext
from portal.libs.contexts.user_context import UserContext
from portal.routers.apis.v1 import devotion as devotion_router_module
from portal.routers.apis.v1.devotion import get_daily_lesson, get_rhythm, get_today_daily_lesson, record_encounter, router, upsert_lesson_note
from portal.serializers.apis.v1.devotion import EncounterRequest, LessonNoteUpsertRequest


class StubDevotionService:
    async def get_daily_lesson(self, lesson_date, locale_id, locale_code, include_authored_sections, auth_user_id=None):
        assert locale_code == "en"
        if include_authored_sections:
            return DailyLesson(
                date=lesson_date,
                passage=Passage(start="JHN.3.16", end="JHN.3.16", ref="John 3:16", verses=["Verse text"]),
                reflect=["Reflect"],
                apply="Apply",
                pray="Pray",
            )
        return AnonymousDailyLesson(date=lesson_date, passage=Passage(start="JHN.3.16", end="JHN.3.16", ref="John 3:16", verses=["Verse text"]))

    async def record_encounter(self, *, auth_user_id, encounter_date):
        return EncounterResult(date=encounter_date, current_streak=5, longest_streak=12, welcome_back=False)

    async def get_rhythm(self, *, auth_user_id, reader_date):
        return RhythmResult(current_streak=5, longest_streak=12, completed_dates=[date(2026, 9, 7), reader_date])

    async def upsert_lesson_note(self, *, auth_user_id, command, time_zone):
        assert time_zone == "America/Toronto"
        return LessonNote(date=command.date, body=command.body, reflects=command.reflects)


def stub_request_context(monkeypatch, user_context=None):
    monkeypatch.setattr(devotion_router_module, "get_resolved_locale_id", lambda: None)
    monkeypatch.setattr(devotion_router_module, "get_resolved_locale_code", lambda: "en")
    monkeypatch.setattr(devotion_router_module, "get_request_context", lambda: None)
    monkeypatch.setattr(devotion_router_module, "get_user_context", lambda: user_context)


def test_devotion_today_route_is_available_as_get():
    routes = [route for route in router.routes if isinstance(route, APIRoute)]
    assert any(route.path == "/today" and "GET" in route.methods for route in routes)
    assert any(route.path == "/lessons/{date}" and "GET" in route.methods for route in routes)
    for route in routes:
        if route.path not in {"/today", "/lessons/{date}"}:
            continue
        auth_config = route.endpoint.__auth_config__
        assert auth_config.require_auth is False
        assert auth_config.optional_auth is True


def test_encounter_routes_require_authentication():
    routes = [route for route in router.routes if isinstance(route, APIRoute)]
    encounter_route = next(route for route in routes if route.path == "/encounters")
    rhythm_route = next(route for route in routes if route.path == "/rhythm")

    assert encounter_route.methods == {"POST"}
    assert rhythm_route.methods == {"GET"}
    assert encounter_route.endpoint.__auth_config__.require_auth is True
    assert rhythm_route.endpoint.__auth_config__.require_auth is True


def test_lesson_note_upsert_route_requires_authentication():
    routes = [route for route in router.routes if isinstance(route, APIRoute)]
    note_route = next(route for route in routes if route.path == "/notes")

    assert note_route.methods == {"PUT"}
    assert note_route.endpoint.__auth_config__.require_auth is True


@pytest.mark.asyncio
async def test_anonymous_today_response_omits_authored_sections(monkeypatch):
    stub_request_context(monkeypatch)

    response = await get_today_daily_lesson(date_=date(2026, 9, 8), devotion_service=StubDevotionService())
    payload = response.model_dump(mode="json", by_alias=True)

    assert payload["locked"] == ["reflect", "apply", "pray", "note"]
    assert not {"reflect", "apply", "pray", "note"} & payload.keys()
    assert "data" not in payload


@pytest.mark.asyncio
async def test_signed_in_today_response_includes_authored_sections(monkeypatch):
    stub_request_context(monkeypatch, UserContext(user_id="11111111-1111-1111-1111-111111111111"))

    response = await get_today_daily_lesson(date_=date(2026, 9, 8), devotion_service=StubDevotionService())
    payload = response.model_dump(mode="json", by_alias=True)

    assert payload["locked"] == []
    assert payload["reflect"] == ["Reflect"]
    assert payload["apply"] == "Apply"
    assert payload["pray"] == "Pray"


@pytest.mark.asyncio
async def test_past_date_uses_same_anonymous_gating(monkeypatch):
    stub_request_context(monkeypatch)

    response = await get_daily_lesson(date_=date(2026, 9, 7), devotion_service=StubDevotionService())
    payload = response.model_dump(mode="json", by_alias=True)

    assert payload["date"] == "2026-09-07"
    assert payload["locked"] == ["reflect", "apply", "pray", "note"]
    assert not {"reflect", "apply", "pray"} & payload.keys()


@pytest.mark.asyncio
async def test_past_date_uses_same_signed_in_gating(monkeypatch):
    stub_request_context(monkeypatch, UserContext(user_id="11111111-1111-1111-1111-111111111111"))

    response = await get_daily_lesson(date_=date(2026, 9, 7), devotion_service=StubDevotionService())
    payload = response.model_dump(mode="json", by_alias=True)

    assert payload["date"] == "2026-09-07"
    assert payload["locked"] == []
    assert payload["reflect"] == ["Reflect"]
    assert payload["apply"] == "Apply"
    assert payload["pray"] == "Pray"


@pytest.mark.asyncio
async def test_unaccepted_default_locale_is_not_used_as_translation_fallback(monkeypatch):
    captured = {}

    class CapturingService(StubDevotionService):
        async def get_daily_lesson(self, lesson_date, locale_id, locale_code, include_authored_sections, auth_user_id=None):
            captured.update(locale_id=locale_id, locale_code=locale_code)
            return await super().get_daily_lesson(lesson_date, locale_id, "en", include_authored_sections, auth_user_id)

    monkeypatch.setattr(devotion_router_module, "get_resolved_locale_id", lambda: object())
    monkeypatch.setattr(devotion_router_module, "get_resolved_locale_code", lambda: "en")
    monkeypatch.setattr(
        devotion_router_module, "get_request_context", lambda: RequestContext(headers=HeaderInfo(), locale_candidates=["fr"], resolved_locale_code="en")
    )

    monkeypatch.setattr(devotion_router_module, "get_user_context", lambda: None)

    await get_today_daily_lesson(date_=date(2026, 9, 8), devotion_service=CapturingService())

    assert captured == {"locale_id": None, "locale_code": None}


@pytest.mark.asyncio
async def test_record_encounter_response_uses_camel_case_without_data_wrapper(monkeypatch):
    stub_request_context(monkeypatch, UserContext(user_id="11111111-1111-1111-1111-111111111111"))

    response = await record_encounter(request=EncounterRequest(date=date(2026, 9, 8)), devotion_service=StubDevotionService())
    payload = response.model_dump(mode="json", by_alias=True)

    assert payload == {"date": "2026-09-08", "currentStreak": 5, "longestStreak": 12, "welcomeBack": False, "message": "今日已與主相遇"}


@pytest.mark.asyncio
async def test_get_rhythm_response_uses_camel_case_without_data_wrapper(monkeypatch):
    stub_request_context(monkeypatch, UserContext(user_id="11111111-1111-1111-1111-111111111111"))

    response = await get_rhythm(date_=date(2026, 9, 8), devotion_service=StubDevotionService())
    payload = response.model_dump(mode="json", by_alias=True)

    assert payload == {"currentStreak": 5, "longestStreak": 12, "completedDates": ["2026-09-07", "2026-09-08"]}


@pytest.mark.asyncio
async def test_upsert_lesson_note_uses_the_timezone_header_and_returns_the_replacement(monkeypatch):
    stub_request_context(monkeypatch, UserContext(user_id="11111111-1111-1111-1111-111111111111"))
    monkeypatch.setattr(devotion_router_module, "get_request_context", lambda: RequestContext(headers=HeaderInfo(time_zone="America/Toronto")))

    response = await upsert_lesson_note(
        request=LessonNoteUpsertRequest(date=date(2026, 9, 8), body="My note", reflects=[None, "My answer"]), devotion_service=StubDevotionService()
    )

    assert response.model_dump(mode="json", by_alias=True) == {"date": "2026-09-08", "body": "My note", "reflects": [None, "My answer"]}
