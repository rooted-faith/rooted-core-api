"""
Init-all CLI command: seed every kind of backend bootstrap data in one shot.
"""

import click

from .init_locale import init_locales_process
from .rbac import init_rbac_process
from .seed_identity_providers import seed_identity_providers_process
from .seed_legal_documents import seed_legal_documents_process
from .seed_system_settings import seed_system_settings_process
from .superuser import create_superuser_process


def init_all_process() -> None:
    """Seed locale, identity provider, legal document, system setting, and RBAC data, then create a superuser."""
    click.echo(click.style("Running init-all...", fg="cyan"))
    init_locales_process()
    seed_identity_providers_process()
    seed_legal_documents_process()
    seed_system_settings_process()
    init_rbac_process()
    create_superuser_process()
    click.echo(click.style("init-all complete.", fg="bright_green"))
