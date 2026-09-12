"""
Member app application services.
"""

from dependency_injector import containers, providers

from portal.application.app.end_user_provisioning_service import EndUserProvisioningService
from portal.application.app.preferences_service import PreferencesService
from portal.application.auth.app_apple_auth_service import AppAppleAuthService
from portal.application.auth.app_auth_service import AppAuthService
from portal.application.auth.app_google_auth_service import AppGoogleAuthService
from portal.application.auth.member_login_service import MemberLoginService
from portal.application.bible.bible_service import BibleService
from portal.application.bible.chapter_fill_gate import ChapterFillGate
from portal.application.devotion.devotion_service import DevotionService
from portal.application.push.push_service import PushService
from portal.config import settings as app_settings
from portal.domain.auth.member_web_app import MemberWebAppRegistry, parse_member_web_apps
from portal.infrastructure.cache.otp_token_cache import OtpTokenCache
from portal.infrastructure.mail.otp_mailer import OtpMailer
from portal.infrastructure.persistence.repositories.app.end_user_repository import EndUserRepository, PreferencesRepository
from portal.infrastructure.persistence.repositories.bible.bible_repository import BibleRepository
from portal.infrastructure.persistence.repositories.devotion.devotion_repository import DevotionRepository
from portal.infrastructure.persistence.repositories.push.device_repository import DeviceRepository
from portal.infrastructure.persistence.repositories.push.notification_repository import NotificationRepository
from portal.infrastructure.persistence.repositories.user_repository import UserRepository
from portal.infrastructure.youversion.youversion_http_client import YouVersionHttpClient


class AppContainer(containers.DeclarativeContainer):
    """Member-facing API services."""

    core = providers.DependenciesContainer()

    bible_repository = providers.Factory(BibleRepository, session=core.request_session)
    youversion_client = providers.Factory(YouVersionHttpClient, app_key=app_settings.YVP_APP_KEY)
    chapter_fill_gate = providers.Singleton(ChapterFillGate)
    bible_service = providers.Factory(BibleService, bible_repository=bible_repository, youversion=youversion_client, chapter_fill_gate=chapter_fill_gate)
    devotion_repository = providers.Factory(DevotionRepository, session=core.request_session)

    user_repository = providers.Factory(UserRepository, session=core.request_session)
    end_user_repository = providers.Factory(EndUserRepository, session=core.request_session)
    preferences_repository = providers.Factory(PreferencesRepository, session=core.request_session)
    devotion_service = providers.Factory(DevotionService, devotion_repository=devotion_repository, end_user_repository=end_user_repository)

    device_repository = providers.Factory(DeviceRepository, session=core.request_session)
    notification_repository = providers.Factory(NotificationRepository, session=core.request_session)
    push_service = providers.Factory(
        PushService,
        device_repository=device_repository,
        end_user_repository=end_user_repository,
        notification_repository=notification_repository,
        push_gateway=core.push_gateway,
    )
    end_user_provisioning_service = providers.Factory(
        EndUserProvisioningService,
        user_repository=user_repository,
        end_user_repository=end_user_repository,
        preferences_repository=preferences_repository,
        password_provider=core.password_provider,
    )

    otp_token_store = providers.Factory(OtpTokenCache, redis_client=core.redis_client)
    otp_mailer = providers.Singleton(OtpMailer)

    preferences_service = providers.Factory(PreferencesService, end_user_repository=end_user_repository, preferences_repository=preferences_repository)

    member_web_app_registry = providers.Singleton(lambda: MemberWebAppRegistry(parse_member_web_apps(app_settings.MEMBER_WEB_APPS)))
    member_login_service = providers.Factory(
        MemberLoginService,
        user_repository=user_repository,
        preferences_repository=preferences_repository,
        jwt_provider=core.jwt_provider,
        refresh_token_provider=core.refresh_token_provider,
        member_refresh_app_binding_provider=core.member_refresh_app_binding_provider,
        member_web_app_registry=member_web_app_registry,
    )
    app_auth_service = providers.Factory(
        AppAuthService,
        provisioning_service=end_user_provisioning_service,
        user_repository=user_repository,
        end_user_repository=end_user_repository,
        otp_token_store=otp_token_store,
        otp_mailer=otp_mailer,
        member_login_service=member_login_service,
    )
    app_google_auth_service = providers.Factory(
        AppGoogleAuthService,
        provisioning_service=end_user_provisioning_service,
        user_repository=user_repository,
        end_user_repository=end_user_repository,
        google_id_token_verifier=core.google_id_token_verifier,
        member_login_service=member_login_service,
    )
    app_apple_auth_service = providers.Factory(
        AppAppleAuthService,
        provisioning_service=end_user_provisioning_service,
        user_repository=user_repository,
        end_user_repository=end_user_repository,
        apple_id_token_verifier=core.apple_id_token_verifier,
        member_login_service=member_login_service,
    )
