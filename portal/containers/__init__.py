"""
Root DI container: composes core, admin, app, and events sub-containers.
"""

from dependency_injector import containers, providers

from portal.containers.admin import AdminContainer
from portal.containers.app import AppContainer
from portal.containers.core import CoreContainer
from portal.containers.events import EventsContainer
from portal.events.bus import EventBus


class RootContainer(containers.DeclarativeContainer):
    """Application composition root."""

    wiring_config = containers.WiringConfiguration(modules=[], packages=["portal.application", "portal.routers", "portal.routers.admin", "portal.middlewares"])

    core = providers.Container(CoreContainer)
    admin: AdminContainer = providers.Container(AdminContainer, core=core)
    app: AppContainer = providers.Container(AppContainer, core=core)
    events = providers.Container(EventsContainer, core=core)

    config = core.config
    postgres_connection = core.postgres_connection
    db_session = core.db_session
    request_session = core.request_session
    redis_client = core.redis_client
    jwt_provider = core.jwt_provider
    password_provider = core.password_provider
    refresh_token_provider = core.refresh_token_provider
    token_blacklist_provider = core.token_blacklist_provider
    member_refresh_app_binding_provider = core.member_refresh_app_binding_provider

    user_repository = admin.user_repository
    user_read_service = admin.user_read_service
    admin_user_service = admin.admin_user_service
    login_service = admin.login_service
    admin_google_auth_service = admin.admin_google_auth_service
    refresh_token_service = admin.refresh_token_service
    member_web_app_registry = admin.member_web_app_registry
    locale_service = admin.locale_service
    setting_service = admin.setting_service
    permission_service = admin.permission_service
    resource_service = admin.resource_service
    role_service = admin.role_service
    verb_service = admin.verb_service
    permission_checker = admin.permission_checker
    rbac_audit_service = admin.rbac_audit_service

    file_service = admin.content.file_service
    legal_document_service = admin.content.legal_document_service

    bible_service = app.bible_service
    end_user_provisioning_service = app.end_user_provisioning_service
    app_auth_service = app.app_auth_service
    end_user_repository = app.end_user_repository
    push_service = app.push_service

    event_bus = events.event_bus

    @staticmethod
    def register_event_handlers(event_bus_instance: EventBus, container: "RootContainer") -> None:
        """
        Register event handlers via events sub-container.
        :param event_bus_instance:
        :param container:
        :return:
        """
        EventsContainer.register_event_handlers(event_bus_instance, container.events)
