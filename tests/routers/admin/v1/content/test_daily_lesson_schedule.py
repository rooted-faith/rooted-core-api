from fastapi.routing import APIRoute

from portal.routers.admin.v1.content.daily_lesson_schedule import router


def test_daily_lesson_schedule_routes_require_content_devotion_permissions():
    routes = {(route.path, frozenset(route.methods)): route for route in router.routes if isinstance(route, APIRoute)}

    assert set(routes) == {
        ("", frozenset({"GET"})),
        ("/{lesson_date}", frozenset({"POST"})),
        ("/{lesson_date}", frozenset({"PUT"})),
        ("/{lesson_date}", frozenset({"DELETE"})),
    }
    assert routes[("", frozenset({"GET"}))].endpoint.__auth_config__.permission_codes == ["content:devotion:read"]
    assert routes[("/{lesson_date}", frozenset({"POST"}))].endpoint.__auth_config__.permission_codes == ["content:devotion:create"]
    assert routes[("/{lesson_date}", frozenset({"PUT"}))].endpoint.__auth_config__.permission_codes == ["content:devotion:update"]
    assert routes[("/{lesson_date}", frozenset({"DELETE"}))].endpoint.__auth_config__.permission_codes == ["content:devotion:delete"]
