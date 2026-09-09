from fastapi.routing import APIRoute

from portal.routers.admin.v1.content.devotion import router


def test_admin_devotion_routes_require_the_matching_content_permissions():
    routes = {(route.path, frozenset(route.methods)): route for route in router.routes if isinstance(route, APIRoute)}

    assert set(routes) == {
        ("", frozenset({"GET"})),
        ("", frozenset({"POST"})),
        ("/{devotion_id}", frozenset({"GET"})),
        ("/{devotion_id}", frozenset({"PUT"})),
        ("/{devotion_id}", frozenset({"DELETE"})),
        ("/{devotion_id}/translations/{locale_code}", frozenset({"PUT"})),
        ("/{devotion_id}/publish", frozenset({"POST"})),
    }
    assert routes[("", frozenset({"GET"}))].endpoint.__auth_config__.permission_codes == ["content:devotion:read"]
    assert routes[("", frozenset({"POST"}))].endpoint.__auth_config__.permission_codes == ["content:devotion:create"]
    assert routes[("/{devotion_id}", frozenset({"GET"}))].endpoint.__auth_config__.permission_codes == ["content:devotion:read"]
    assert routes[("/{devotion_id}", frozenset({"PUT"}))].endpoint.__auth_config__.permission_codes == ["content:devotion:update"]
    assert routes[("/{devotion_id}", frozenset({"DELETE"}))].endpoint.__auth_config__.permission_codes == ["content:devotion:delete"]
    assert routes[("/{devotion_id}/translations/{locale_code}", frozenset({"PUT"}))].endpoint.__auth_config__.permission_codes == ["content:devotion:update"]
    assert routes[("/{devotion_id}/publish", frozenset({"POST"}))].endpoint.__auth_config__.permission_codes == ["content:devotion:update"]
