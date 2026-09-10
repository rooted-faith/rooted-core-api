"""
Bible crawler CLI commands.
"""

import asyncio
import json
import os
import sqlite3
import time
from typing import Any

import click

from portal.config import settings
from portal.domain.bible.ports import YouVersionPort
from portal.infrastructure.youversion.youversion_http_client import YouVersionHttpClient, YouVersionHttpError
from portal.libs.logger import logger

YVP_APP_KEY_ENV = "YVP_APP_KEY"


def load_json(path: str, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def atomic_write_json(path: str, obj: Any):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def safe_filename(s: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in str(s))


class YouVersionDumper:
    def __init__(
        self,
        bible_id: str,
        out_dir: str,
        daily_limit: int,
        sleep_sec: float,
        timeout_sec: float,
        include_headings: bool,
        include_notes: bool,
        format_: str,
        youversion: YouVersionPort,
    ):
        self.bible_id = str(bible_id)
        self.out_dir = out_dir
        self.daily_limit = daily_limit
        self.sleep_sec = sleep_sec
        self.timeout_sec = timeout_sec
        self.include_headings = include_headings
        self.include_notes = include_notes
        self.format_ = format_
        self._youversion = youversion

        self.root_dir = os.path.join(out_dir, self.bible_id)
        self.state_path = os.path.join(self.root_dir, "state.json")
        self.meta_dir = os.path.join(self.root_dir, "meta")
        self.db_path = os.path.join(self.root_dir, "passages.db")

        self.state = load_json(
            self.state_path,
            {
                "bible_id": self.bible_id,
                "requests_today": 0,
                "last_book_index": 0,
                "last_chapter_index": 0,
                "last_verse_index": 0,
                "done": False,
                "updated_at": None,
                "rate_limit_info": None,
            },
        )

        if str(self.state.get("bible_id")) != self.bible_id:
            self.state = {
                "bible_id": self.bible_id,
                "requests_today": 0,
                "last_book_index": 0,
                "last_chapter_index": 0,
                "last_verse_index": 0,
                "done": False,
                "updated_at": None,
                "rate_limit_info": None,
            }

        self._init_database()

    def _save_state(self):
        self.state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        atomic_write_json(self.state_path, self.state)

    def _init_database(self):
        """Initialize SQLite database with verses table."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS verses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bible_id TEXT NOT NULL,
                book_id TEXT NOT NULL,
                chapter INTEGER NOT NULL,
                verse INTEGER NOT NULL,
                passage_id TEXT NOT NULL UNIQUE,
                format TEXT,
                include_headings INTEGER,
                include_notes INTEGER,
                data TEXT NOT NULL,
                created_at TEXT,
                UNIQUE(bible_id, book_id, chapter, verse)
            )
        """)

        cursor.execute("""CREATE INDEX IF NOT EXISTS idx_passage_id ON verses(passage_id)""")
        cursor.execute("""CREATE INDEX IF NOT EXISTS idx_book_chapter_verse ON verses(bible_id, book_id, chapter, verse)""")

        conn.commit()
        conn.close()

    def _insert_verse(self, book_id: str, chapter: Any, verse: Any, passage_id: str, params: dict[str, Any], data: Any):
        """Insert or replace a verse in the database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            chapter_int = int(chapter) if str(chapter).isdigit() else None
        except ValueError, TypeError:
            chapter_int = None

        try:
            verse_int = int(verse) if str(verse).isdigit() else None
        except ValueError, TypeError:
            verse_int = None

        chapter_value = chapter_int if chapter_int is not None else str(chapter)
        verse_value = verse_int if verse_int is not None else str(verse)

        cursor.execute(
            """
            INSERT OR REPLACE INTO verses (
                bible_id, book_id, chapter, verse, passage_id,
                format, include_headings, include_notes, data, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                self.bible_id,
                book_id,
                chapter_value,
                verse_value,
                passage_id,
                params.get("format"),
                1 if params.get("include_headings") == "true" else 0,
                1 if params.get("include_notes") == "true" else 0,
                json.dumps(data, ensure_ascii=False),
                time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            ),
        )

        conn.commit()
        conn.close()

    def _count_request(self):
        """Count request without stopping."""
        self.state["requests_today"] += 1
        self._save_state()

    async def _fetch(self, awaitable):
        self._count_request()
        try:
            result = await awaitable
        except YouVersionHttpError as exc:
            if exc.status_code == 429:
                error_message = "收到 429 (Too Many Requests) 狀態碼"
                logger.warning(error_message, extra={"status_code": 429, "url": exc.url})
                self._save_state()
                raise SystemExit(f"{error_message}。已保存 state, 請下次再跑。") from exc
            if exc.status_code == 0:
                error_msg = f"請求超時 (Read operation timed out) (timeout_sec={self.timeout_sec})"
                logger.error(error_msg, extra={"timeout_sec": self.timeout_sec, "url": exc.url})
                self._save_state()
                raise SystemExit(f"{error_msg}。已保存 state, 請下次再跑。") from exc
            error_details = str(exc)
            logger.error(error_details, extra={"status_code": exc.status_code, "url": exc.url})
            raise RuntimeError(error_details) from exc

        if self.sleep_sec:
            await asyncio.sleep(self.sleep_sec)
        return result

    async def dump_meta(self) -> dict[str, Any]:
        bible = await self._fetch(self._youversion.get_bible_metadata(self.bible_id))
        atomic_write_json(os.path.join(self.meta_dir, "bible.json"), bible)

        index = await self._fetch(self._youversion.get_bible_index(self.bible_id))
        atomic_write_json(os.path.join(self.meta_dir, "index.json"), index)
        return index

    def _books(self, index_obj: Any) -> list[dict[str, Any]]:
        if isinstance(index_obj, dict) and isinstance(index_obj.get("books"), list):
            return index_obj["books"]
        if isinstance(index_obj, dict) and isinstance(index_obj.get("data"), dict):
            v = index_obj["data"].get("books")
            if isinstance(v, list):
                return v
        raise ValueError("index 回傳格式找不到 books[]。")

    async def dump_passages_by_chapter_from_index(self, index_obj: dict[str, Any]):
        books = self._books(index_obj)

        start_bi = int(self.state.get("last_book_index", 0))
        start_ci = int(self.state.get("last_chapter_index", 0))

        params = {"format": "html", "include_headings": "true", "include_notes": "true"}

        for bi in range(start_bi, len(books)):
            book = books[bi]
            book_id = book.get("id")
            if not book_id:
                raise ValueError(f"book 缺少 id: {book}")

            chapters = book.get("chapters")
            if not isinstance(chapters, list):
                raise ValueError(f"book.chapters 不是 list: book_id={book_id}")

            ci0 = start_ci if bi == start_bi else 0

            for ci in range(ci0, len(chapters)):
                ch = chapters[ci]
                ch_num = ch.get("title") or ch.get("id") or (ci + 1)
                chapter_usfm = ch.get("passage_id") or f"{book_id}.{ch_num}"

                data = await self._fetch(self._youversion.get_chapter_passage(self.bible_id, chapter_usfm))

                verses = ch.get("verses")
                first_verse = verses[0] if isinstance(verses, list) and verses else {}
                verse_num = first_verse.get("title") or first_verse.get("id") or 1

                self._insert_verse(book_id=book_id, chapter=ch_num, verse=verse_num, passage_id=chapter_usfm, params=params, data=data)

                self.state["last_book_index"] = bi
                self.state["last_chapter_index"] = ci + 1
                self.state["last_verse_index"] = 0
                self.state["done"] = False
                self._save_state()

            self.state["last_book_index"] = bi + 1
            self.state["last_chapter_index"] = 0
            self.state["last_verse_index"] = 0
            self._save_state()

        self.state["done"] = True
        self._save_state()


def _build_youversion_client(timeout_sec: float) -> YouVersionHttpClient:
    app_key = settings.YVP_APP_KEY
    if not app_key:
        raise SystemExit(f"{YVP_APP_KEY_ENV} is required")
    return YouVersionHttpClient(app_key=app_key, timeout_sec=timeout_sec)


async def dump_bible(
    bible_id: str,
    out_dir: str,
    daily_limit: int,
    sleep_sec: float,
    timeout_sec: float,
    include_headings: bool,
    include_notes: bool,
    format_: str,
    meta_only: bool,
    youversion: YouVersionPort | None = None,
):
    """
    Dump YouVersion Bible metadata and passages.
    """
    if youversion is None:
        youversion = _build_youversion_client(timeout_sec)

    dumper = YouVersionDumper(
        bible_id=bible_id,
        out_dir=out_dir,
        daily_limit=daily_limit,
        sleep_sec=sleep_sec,
        timeout_sec=timeout_sec,
        include_headings=include_headings,
        include_notes=include_notes,
        format_=format_,
        youversion=youversion,
    )

    try:
        click.echo(click.style(f"Dumping Bible ID: {bible_id}", fg="cyan"))
        index_obj = await dumper.dump_meta()
        click.echo(click.style("Metadata dumped successfully.", fg="green"))

        if not meta_only:
            click.echo(click.style("Dumping passages...", fg="cyan"))
            await dumper.dump_passages_by_chapter_from_index(index_obj)
            click.echo(click.style("All passages dumped successfully.", fg="green"))
        else:
            click.echo(click.style("Meta-only mode: skipping passages.", fg="yellow"))
    except SystemExit as e:
        click.echo(click.style(str(e), fg="yellow"))
        logger.info(str(e))
        raise
    except Exception as e:
        click.echo(click.style(f"Error dumping Bible: {e}", fg="red"))
        logger.exception(e)
        raise


def dump_bible_process(
    bible_id: str,
    out_dir: str,
    daily_limit: int,
    sleep_sec: float,
    timeout_sec: float,
    include_headings: bool,
    include_notes: bool,
    format_: str,
    meta_only: bool,
):
    """Synchronous entry to run Bible dumping."""
    asyncio.run(
        dump_bible(
            bible_id=bible_id,
            out_dir=out_dir,
            daily_limit=daily_limit,
            sleep_sec=sleep_sec,
            timeout_sec=timeout_sec,
            include_headings=include_headings,
            include_notes=include_notes,
            format_=format_,
            meta_only=meta_only,
        )
    )
