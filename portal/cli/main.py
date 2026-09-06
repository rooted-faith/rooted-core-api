"""
CLI main entry point
"""

import click

from .bible import dump_bible_process
from .import_bible import import_bible_data_process
from .init_all import init_all_process
from .init_locale import init_locales_process
from .rbac import init_rbac_process, reset_rbac_process
from .seed_identity_providers import seed_identity_providers_process
from .seed_legal_documents import seed_legal_documents_process
from .seed_system_settings import seed_system_settings_process
from .superuser import create_superuser_process


@click.group()
def cli():
    """Rooted Core API CLI"""


@cli.command(name="dump-bible")
@click.option("--bible-id", required=True, help="Bible ID (e.g., 1392)")
@click.option("--out", default="dump", help="Output directory")
@click.option("--daily-limit", type=int, default=5000, help="Maximum requests allowed per run (to comply with daily limit)")
@click.option("--sleep", type=float, default=0.0, help="Sleep seconds after each request (throttling)")
@click.option("--timeout", type=float, default=30.0, help="HTTP timeout seconds")
@click.option("--format", "format_", default="text", help="Passages format (platform-dependent; default: text)")
@click.option("--include-headings", default=False, is_flag=True, help="Passages include_headings=true")
@click.option("--include-notes", default=False, is_flag=True, help="Passages include_notes=true")
@click.option("--meta-only", is_flag=True, help="Only fetch bible/index, not passages")
def dump_bible_cmd(
    bible_id: str, out: str, daily_limit: int, sleep: float, timeout: float, format_: str, include_headings: bool, include_notes: bool, meta_only: bool
):
    """Dump YouVersion Bible metadata + passages with resume support.

    Note: API key is automatically loaded from YVP_APP_KEY environment variable.
    """
    dump_bible_process(
        bible_id=bible_id,
        out_dir=out,
        daily_limit=daily_limit,
        sleep_sec=sleep,
        timeout_sec=timeout,
        include_headings=include_headings,
        include_notes=include_notes,
        format_=format_,
        meta_only=meta_only,
    )


@cli.command(name="import-bible")
@click.option("--bible-id", required=True, help="Bible ID (e.g., 1392)")
@click.option("--data-dir", default="bible_data", help="Bible data directory (default: bible_data)")
def import_bible_cmd(bible_id: str, data_dir: str):
    """
    Import Bible data from bible_data directory to database.
    This command imports:
    1. Bible version metadata from bible_data/{bible_id}/meta/bible.json
    2. Bible books from bible_data/{bible_id}/meta/index.json
    3. Bible verses from bible_data/{bible_id}/passages.db
    """
    import_bible_data_process(bible_id=bible_id, data_dir=data_dir)


@cli.command(name="seed-identity-providers")
def seed_identity_providers_cmd():
    """Seed auth.identity_provider catalog (google + apple only; insert-if-missing)."""
    seed_identity_providers_process()


@cli.command(name="create-superuser")
def create_superuser_cmd():
    """Create a superuser account via interactive prompts."""
    create_superuser_process()


@cli.command(name="init-rbac")
def init_rbac_cmd():
    """Seed verbs, resources, permissions, roles, and role-permission mappings."""
    init_rbac_process()


@cli.command(name="reset-rbac")
@click.option("--force", is_flag=True, default=False, help="Skip the IS_DEV guard and confirmation prompt.")
def reset_rbac_cmd(force: bool):
    """Delete all RBAC data and re-seed from rbac_seed_data."""
    reset_rbac_process(force=force)


@cli.command(name="init-locales")
def init_locales_cmd():
    """Seed locales into SystemLocale table."""
    init_locales_process()


@cli.command(name="seed-legal-documents")
def seed_legal_documents_cmd():
    """Seed content.legal_document rows (insert-if-missing)."""
    seed_legal_documents_process()


@cli.command(name="seed-system-settings")
def seed_system_settings_cmd():
    """Seed public.system_setting rows (insert-if-missing)."""
    seed_system_settings_process()


@cli.command(name="init-all")
def init_all_cmd():
    """Seed locale, identity provider, legal document, system setting, and RBAC data, then create a superuser."""
    init_all_process()


def main() -> int:
    cli()
    return 0


if __name__ == "__main__":
    main()
