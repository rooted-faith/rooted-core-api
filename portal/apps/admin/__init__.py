"""
DEPRECATED: Legacy admin sub-app pattern.

Use portal.apps.get_admin_application() mount via get_main_application() instead.
This module is kept temporarily for reference during migration and will be removed in Phase 4+.
"""

from fastapi import FastAPI

from portal.container import Container
from portal.libs.utils.lifespan import lifespan

from .routers import register_routers


def create_admin_app(container: Container) -> FastAPI:
    """
    Create admin sub application (deprecated).
    :param container: Dependency injection container
    :return: FastAPI application instance
    """
    admin_app = FastAPI(
        title="Rooted Portal Admin API",
        description="Admin API for Rooted Portal",
        version="1.0.0",
        lifespan=lifespan,
    )

    admin_app.container = container
    register_routers(admin_app)

    return admin_app
