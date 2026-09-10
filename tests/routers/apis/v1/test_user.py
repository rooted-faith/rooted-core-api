"""Member Users API contract tests."""

import pytest
from fastapi.routing import APIRoute
from pydantic import ValidationError

from portal.routers.apis.v1.user import router
from portal.serializers.apis.v1.user import UpdateMemberPreferences


def test_preferences_routes_are_available() -> None:
    routes = [route for route in router.routes if isinstance(route, APIRoute)]

    assert any(route.path == "/me" and "GET" in route.methods for route in routes)
    assert any(route.path == "/me" and "PATCH" in route.methods for route in routes)


def test_member_user_routes_only_expose_preferences() -> None:
    routes = [route for route in router.routes if isinstance(route, APIRoute)]

    assert {(route.path, frozenset(route.methods)) for route in routes} == {("/me", frozenset({"GET"})), ("/me", frozenset({"PATCH"}))}


def test_update_preferences_rejects_invalid_week_start() -> None:
    with pytest.raises(ValidationError):
        UpdateMemberPreferences(week_start="tuesday")

    with pytest.raises(ValidationError):
        UpdateMemberPreferences(week_start=None)
