"""Admin End-user route contract."""

from portal.middlewares.auth_middleware import AuthMiddleware
from portal.routers.admin.v1 import router


def test_admin_api_does_not_expose_end_user_routes() -> None:
    routes = list(AuthMiddleware._iter_matchable_routes(router.routes))

    assert not any(route.path.startswith("/end-user/") for route in routes)
