"""
List and refill Bible chapters that were filled before paragraph boundaries were stored.
"""

import asyncio
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import click

from portal.application.bible.bible_service import BibleService
from portal.application.bible.commands import ListLegacyChaptersQuery, RefillChapterCommand
from portal.container import Container
from portal.domain.bible.entities import BibleChapterAddress
from portal.exceptions.responses import ApiBaseException
from portal.libs.contexts.request_session_context import reset_request_session, set_request_session
from portal.libs.database import Session
from portal.libs.logger import logger

_CHAPTER_PATTERN = re.compile(r"([A-Z0-9]{3})\.([1-9][0-9]*)")


def parse_chapters(_ctx: click.Context, _param: click.Parameter, values: tuple[str, ...]) -> list[BibleChapterAddress]:
    """Click callback: turn repeated BOOK.CHAPTER options into addresses, dropping repeats."""
    chapters: dict[str, BibleChapterAddress] = {}
    for value in values:
        match = _CHAPTER_PATTERN.fullmatch(value)
        if match is None:
            raise click.BadParameter(f"{value!r} is not BOOK.CHAPTER, e.g. REV.21")
        chapters[value] = BibleChapterAddress(book_code=match.group(1), chapter=int(match.group(2)))
    return list(chapters.values())


@asynccontextmanager
async def _bible_service() -> AsyncIterator[tuple[BibleService, Session]]:
    container = Container()
    session = container.db_session()
    token = set_request_session(session)
    try:
        yield container.bible_service(), session
    except BaseException:
        await session.rollback()
        raise
    finally:
        reset_request_session(token)
        await session.close()


async def list_legacy_bible_chapters(bible_id: str, book_code: str | None) -> None:
    async with _bible_service() as (service, _session):
        try:
            chapters = await service.list_legacy_chapters(ListLegacyChaptersQuery(youversion_bible_id=bible_id, book_code=book_code))
        except ApiBaseException as e:
            raise click.ClickException(_error_message(e)) from e
        for address in chapters:
            click.echo(_label(address))


async def refill_bible_chapters(bible_id: str, chapters: list[BibleChapterAddress]) -> None:
    """Each chapter is its own transaction: a failure keeps that chapter's old body and leaves the others alone."""
    failed: list[str] = []
    async with _bible_service() as (service, session):
        for address in chapters:
            label = _label(address)
            try:
                outcome = await service.refill_chapter(RefillChapterCommand(youversion_bible_id=bible_id, book_code=address.book_code, chapter=address.chapter))
                await session.commit()
            except Exception as e:
                await session.rollback()
                if not isinstance(e, ApiBaseException):
                    logger.exception(e)
                failed.append(label)
                click.echo(f"{label}: failed ({_error_message(e)})", err=True)
                continue
            click.echo(f"{label}: {outcome}")
    if failed:
        raise click.ClickException(f"{len(failed)} of {len(chapters)} chapters were not refilled and keep their previous content: {' '.join(failed)}")


def _label(address: BibleChapterAddress) -> str:
    return f"{address.book_code}.{address.chapter}"


def _error_message(error: Exception) -> str:
    if isinstance(error, ApiBaseException):
        return ": ".join(str(part) for part in (error.detail, error.debug_detail) if part)
    return str(error)


def list_legacy_bible_chapters_process(bible_id: str, book_code: str | None = None) -> None:
    """Synchronous entry point for listing legacy chapters"""
    asyncio.run(list_legacy_bible_chapters(bible_id=bible_id, book_code=book_code))


def refill_bible_chapters_process(bible_id: str, chapters: list[BibleChapterAddress]) -> None:
    """Synchronous entry point for refilling chapters"""
    asyncio.run(refill_bible_chapters(bible_id=bible_id, chapters=chapters))
