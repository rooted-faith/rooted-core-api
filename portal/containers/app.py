"""
Member app application services.
"""

from dependency_injector import containers, providers

from portal.application.app.end_user_provisioning_service import EndUserProvisioningService
from portal.application.bible.bible_service import BibleService
from portal.infrastructure.persistence.repositories.app.end_user_repository import EndUserRepository, PreferencesRepository
from portal.infrastructure.persistence.repositories.bible.bible_repository import BibleRepository
from portal.infrastructure.persistence.repositories.user_repository import UserRepository


class AppContainer(containers.DeclarativeContainer):
    """Member-facing API services."""

    core = providers.DependenciesContainer()

    bible_repository = providers.Factory(BibleRepository, session=core.request_session)
    bible_service = providers.Factory(BibleService, bible_repository=bible_repository)

    user_repository = providers.Factory(UserRepository, session=core.request_session)
    end_user_repository = providers.Factory(EndUserRepository, session=core.request_session)
    preferences_repository = providers.Factory(PreferencesRepository, session=core.request_session)
    end_user_provisioning_service = providers.Factory(
        EndUserProvisioningService,
        user_repository=user_repository,
        end_user_repository=end_user_repository,
        preferences_repository=preferences_repository,
        password_provider=core.password_provider,
    )
