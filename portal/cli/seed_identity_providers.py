"""
Identity provider catalog seed CLI.
"""

import asyncio

import click

from portal.application.cli.identity_provider_seed_service import IdentityProviderSeedService
from portal.cli.datas.identity_provider_seed_data import seed_identity_providers
from portal.container import Container
from portal.libs.logger import logger


async def seed_identity_providers_async() -> None:
    """Seed auth.identity_provider rows (insert-if-missing)."""
    container = Container()
    session = container.db_session()
    try:
        service = IdentityProviderSeedService(session)
        await service.run(seed_identity_providers)
    except Exception as e:
        await session.rollback()
        click.echo(click.style(f"Identity provider seed failed: {e}", fg="red"))
        logger.exception(e)
        raise
    finally:
        await session.close()


def seed_identity_providers_process() -> None:
    """Synchronous entry for Identity provider seed."""
    asyncio.run(seed_identity_providers_async())
