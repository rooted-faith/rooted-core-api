"""
Member app application services.
"""

from dependency_injector import containers, providers

from portal.application.bible.bible_service import BibleService
from portal.infrastructure.persistence.repositories.bible.bible_repository import BibleRepository


class AppContainer(containers.DeclarativeContainer):
    """Member-facing API services."""

    core = providers.DependenciesContainer()

    bible_repository = providers.Factory(BibleRepository, session=core.request_session)
    bible_service = providers.Factory(BibleService, bible_repository=bible_repository)
