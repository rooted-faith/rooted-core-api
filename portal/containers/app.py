"""
Member app application services.
"""

from dependency_injector import containers, providers

from portal.application.app.end_user_provisioning_service import EndUserProvisioningService
from portal.application.auth.app_auth_service import AppAuthService
from portal.application.bible.bible_service import BibleService
from portal.application.push.push_service import PushService
from portal.config import settings as app_settings
from portal.domain.auth.member_web_app import MemberWebAppRegistry, parse_member_web_apps
from portal.infrastructure.cache.magic_link_token_cache import MagicLinkTokenCache
from portal.infrastructure.mail.magic_link_mailer import MagicLinkMailer
from portal.infrastructure.persistence.repositories.app.end_user_repository import EndUserRepository, PreferencesRepository
from portal.infrastructure.persistence.repositories.bible.bible_repository import BibleRepository
from portal.infrastructure.persistence.repositories.push.device_repository import DeviceRepository
from portal.infrastructure.persistence.repositories.user_repository import UserRepository


class AppContainer(containers.DeclarativeContainer):
    """Member-facing API services."""

    core = providers.DependenciesContainer()

    bible_repository = providers.Factory(BibleRepository, session=core.request_session)
    bible_service = providers.Factory(BibleService, bible_repository=bible_repository)

    user_repository = providers.Factory(UserRepository, session=core.request_session)
    end_user_repository = providers.Factory(EndUserRepository, session=core.request_session)
    preferences_repository = providers.Factory(PreferencesRepository, session=core.request_session)

    device_repository = providers.Factory(DeviceRepository, session=core.request_session)
    push_service = providers.Factory(PushService, device_repository=device_repository, end_user_repository=end_user_repository)
    end_user_provisioning_service = providers.Factory(
        EndUserProvisioningService,
        user_repository=user_repository,
        end_user_repository=end_user_repository,
        preferences_repository=preferences_repository,
        password_provider=core.password_provider,
    )

    magic_link_token_store = providers.Factory(MagicLinkTokenCache, redis_client=core.redis_client)
    magic_link_mailer = providers.Singleton(MagicLinkMailer)

    member_web_app_registry = providers.Singleton(lambda: MemberWebAppRegistry(parse_member_web_apps(app_settings.MEMBER_WEB_APPS)))
    app_auth_service = providers.Factory(
        AppAuthService,
        provisioning_service=end_user_provisioning_service,
        user_repository=user_repository,
        end_user_repository=end_user_repository,
        preferences_repository=preferences_repository,
        magic_link_token_store=magic_link_token_store,
        magic_link_mailer=magic_link_mailer,
        jwt_provider=core.jwt_provider,
        refresh_token_provider=core.refresh_token_provider,
        member_refresh_app_binding_provider=core.member_refresh_app_binding_provider,
        member_web_app_registry=member_web_app_registry,
    )
