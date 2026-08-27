"""
CLI main entry point
"""
import click

from .bible import dump_bible_process
from .import_bible import import_bible_data_process


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
    bible_id: str,
    out: str,
    daily_limit: int,
    sleep: float,
    timeout: float,
    format_: str,
    include_headings: bool,
    include_notes: bool,
    meta_only: bool,
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


def main() -> int:
    cli()
    return 0

