"""
Metadata-only backfill of bible.versions.publisher_name from dumped bible.json files.
"""

import asyncio
import json
from pathlib import Path

import click

from portal.container import Container
from portal.libs.logger import logger
from portal.models import BibleVersion

from .constants import DEFAULT_BIBLE_DATA_DIR
from .import_bible import normalize_publisher_name


def _discover_bible_ids(data_dir: Path, bible_id: str | None) -> list[str]:
    if bible_id is not None:
        return [str(bible_id)]
    if not data_dir.is_dir():
        return []
    bible_ids: list[str] = []
    for child in sorted(data_dir.iterdir()):
        if child.is_dir() and (child / "meta" / "bible.json").is_file():
            bible_ids.append(child.name)
    return bible_ids


async def backfill_bible_publisher_names(data_dir: str = DEFAULT_BIBLE_DATA_DIR, bible_id: str | None = None) -> None:
    """
    Update publisher_name on existing Bible versions from local metadata only.

    Matches versions by immutable YouVersion Bible ID. Does not import books or verses.
    Missing or empty source names leave existing stored values unchanged.
    """
    container = Container()
    session = container.db_session()
    root = Path(data_dir)
    updated = 0
    skipped = 0
    missing = 0

    try:
        for source_bible_id in _discover_bible_ids(root, bible_id):
            bible_json_path = root / source_bible_id / "meta" / "bible.json"
            if not bible_json_path.is_file():
                click.echo(f"{source_bible_id}: skipped (metadata not found: {bible_json_path})")
                skipped += 1
                continue

            with open(bible_json_path, encoding="utf-8") as handle:
                bible_meta = json.load(handle)

            youversion_bible_id = str(bible_meta["id"])
            publisher_name = normalize_publisher_name(bible_meta.get("publisher_name"))
            if publisher_name is None:
                click.echo(f"{youversion_bible_id}: skipped (no publisher_name in source)")
                skipped += 1
                continue

            version_id = await session.select(BibleVersion.id).where(BibleVersion.youversion_bible_id == youversion_bible_id).fetchval()
            if version_id is None:
                click.echo(f"{youversion_bible_id}: skipped (version not in database)")
                missing += 1
                continue

            await session.update(BibleVersion).values(publisher_name=publisher_name).where(BibleVersion.youversion_bible_id == youversion_bible_id).execute()
            click.echo(f"{youversion_bible_id}: publisher_name={publisher_name!r}")
            updated += 1

        await session.commit()
        click.echo(f"Backfill complete: updated={updated} skipped={skipped} missing={missing}")
    except Exception as error:
        click.echo(f"Error backfilling publisher names: {error}", err=True)
        logger.exception(error)
        await session.rollback()
        raise
    finally:
        await session.close()


def backfill_bible_publisher_names_process(data_dir: str = DEFAULT_BIBLE_DATA_DIR, bible_id: str | None = None) -> None:
    """Synchronous entry point for metadata-only publisher-name backfill."""
    asyncio.run(backfill_bible_publisher_names(data_dir=data_dir, bible_id=bible_id))
