"""
Read-time fill on BibleService.get_chapter (issue #74).

Seam: get_chapter with stub YouVersionPort + stub BibleRepositoryPort.
HTML fixtures are the stub YouVersion return value — no live YVP_APP_KEY.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest

from portal.application.bible.bible_service import BibleService
from portal.domain.bible.entities import BibleChapter, BibleVerse
from portal.exceptions.responses import ApiBaseException
from portal.infrastructure.youversion.youversion_http_client import YouVersionHttpError

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "bible"


@pytest.fixture
def gen2_passage() -> dict:
    return json.loads((FIXTURES / "gen2_html.json").read_text(encoding="utf-8"))


@pytest.fixture
def psa1_passage() -> dict:
    return json.loads((FIXTURES / "psa1_html.json").read_text(encoding="utf-8"))


@pytest.fixture
def mat5_passage() -> dict:
    return json.loads((FIXTURES / "mat5_html.json").read_text(encoding="utf-8"))


class StubYouVersion:
    def __init__(self, passages: dict[str, dict] | None = None, error: Exception | None = None, delay_sec: float = 0.0):
        self._passages = passages or {}
        self._error = error
        self._delay_sec = delay_sec
        self.calls: list[tuple[str, str]] = []

    async def get_bible_metadata(self, bible_id: str) -> dict:
        raise NotImplementedError

    async def get_bible_index(self, bible_id: str) -> dict:
        raise NotImplementedError

    async def get_chapter_passage(self, bible_id: str, chapter_usfm: str) -> dict:
        self.calls.append((bible_id, chapter_usfm))
        if self._delay_sec:
            await asyncio.sleep(self._delay_sec)
        if self._error is not None:
            raise self._error
        key = f"{bible_id}:{chapter_usfm}"
        if key not in self._passages:
            raise YouVersionHttpError(404, f"/v1/bibles/{bible_id}/passages/{chapter_usfm}")
        return self._passages[key]


class StubBibleRepository:
    def __init__(self, chapter: BibleChapter):
        self._chapter = chapter
        self.write_calls: list[list[dict]] = []
        self.fetch_calls = 0

    async def fetch_active_versions(self, language=None):
        return []

    async def version_is_active(self, bible_version_id):
        return True

    async def fetch_books(self, bible_version_id):
        return []

    async def fetch_chapter(self, book_id, chapter):
        self.fetch_calls += 1
        if self._chapter is None:
            return None
        return BibleChapter(
            bible_version_id=self._chapter.bible_version_id,
            youversion_bible_id=self._chapter.youversion_bible_id,
            bible_title=self._chapter.bible_title,
            book_id=self._chapter.book_id,
            book_code=self._chapter.book_code,
            book_name=self._chapter.book_name,
            chapter=self._chapter.chapter,
            verses=[BibleVerse(passage_id=verse.passage_id, verse=verse.verse, verse_end=verse.verse_end, lines=verse.lines) for verse in self._chapter.verses],
        )

    async def search_verses(self, q, bible_version_id, book_id, limit, offset):
        raise NotImplementedError

    async def write_chapter_fill(self, book_id, chapter, fills: list[dict]) -> None:
        self.write_calls.append(fills)
        by_verse = {item["verse"]: item for item in fills}
        updated = []
        for verse in self._chapter.verses:
            fill = by_verse.get(verse.verse)
            if fill is None:
                updated.append(verse)
                continue
            updated.append(BibleVerse(passage_id=verse.passage_id, verse=verse.verse, verse_end=fill.get("verse_end"), lines=fill["lines"]))
        self._chapter = BibleChapter(
            bible_version_id=self._chapter.bible_version_id,
            youversion_bible_id=self._chapter.youversion_bible_id,
            bible_title=self._chapter.bible_title,
            book_id=self._chapter.book_id,
            book_code=self._chapter.book_code,
            book_name=self._chapter.book_name,
            chapter=self._chapter.chapter,
            verses=updated,
        )


def _unfilled_chapter(*, book_code: str, chapter: int, verses: list[int], youversion_bible_id: str = "1392") -> BibleChapter:
    book_id = uuid4()
    return BibleChapter(
        bible_version_id=uuid4(),
        youversion_bible_id=youversion_bible_id,
        bible_title="當代譯本修訂版",
        book_id=book_id,
        book_code=book_code,
        book_name=book_code,
        chapter=chapter,
        verses=[BibleVerse(passage_id=f"{book_code}.{chapter}.{verse}", verse=verse, lines=None) for verse in verses],
    )


def _verse(result: BibleChapter, number: int) -> BibleVerse:
    return next(item for item in result.verses if item.verse == number)


@pytest.mark.asyncio
async def test_get_chapter_fills_mid_verse_heading_in_gen_2(gen2_passage):
    chapter = _unfilled_chapter(book_code="GEN", chapter=2, verses=list(range(1, 26)))
    youversion = StubYouVersion(passages={"1392:GEN.2": gen2_passage})
    service = BibleService(StubBibleRepository(chapter), youversion)

    result = await service.get_chapter(book_id=chapter.book_id, chapter=2)

    verse_4 = _verse(result, 4)
    assert verse_4.lines is not None
    assert any(line["type"] == "heading" and line["style"] == "s1" for line in verse_4.lines)
    heading_index = next(i for i, line in enumerate(verse_4.lines) if line["type"] == "heading")
    assert heading_index > 0
    assert heading_index < len(verse_4.lines) - 1
    assert "記載" in verse_4.lines[0]["fragments"][0]["text"]
    assert "亞當" in verse_4.lines[heading_index]["fragments"][0]["text"]
    assert "耶和華" in verse_4.lines[heading_index + 1]["fragments"][0]["text"]
    assert youversion.calls == [("1392", "GEN.2")]
    assert any("伊甸" == fragment.get("text") for line in _verse(result, 8).lines for fragment in line["fragments"] if fragment.get("type") == "pn")


@pytest.mark.asyncio
async def test_get_chapter_sets_verse_end_for_merged_psalm_verse(psa1_passage):
    chapter = _unfilled_chapter(book_code="PSA", chapter=1, verses=[1, 3, 4, 5, 6])
    youversion = StubYouVersion(passages={"1392:PSA.1": psa1_passage})
    service = BibleService(StubBibleRepository(chapter), youversion)

    result = await service.get_chapter(book_id=chapter.book_id, chapter=1)

    verse_1 = _verse(result, 1)
    assert verse_1.verse_end == 2
    assert any(line["type"] == "heading" and line["style"] == "ms" for line in verse_1.lines)
    assert any(line["type"] == "heading" and line["style"] == "cl" for line in verse_1.lines)
    assert any(line["style"] == "q1" for line in verse_1.lines)
    assert all(verse.verse != 2 for verse in result.verses)


@pytest.mark.asyncio
async def test_get_chapter_keeps_footnote_and_styles_inline(mat5_passage):
    chapter = _unfilled_chapter(book_code="MAT", chapter=5, verses=list(range(1, 49)))
    html = {
        **mat5_passage,
        "content": mat5_passage["content"].replace(
            "但我告訴你們，凡無緣無故",
            '但我告訴你們，凡無緣無故<span class="nd">耶和華</span><span class="wj">你們要愛</span><span class="rare">未知</span>',
            1,
        ),
    }
    youversion = StubYouVersion(passages={"1392:MAT.5": html})
    repo = StubBibleRepository(chapter)
    service = BibleService(repo, youversion)

    result = await service.get_chapter(book_id=chapter.book_id, chapter=5)

    verse_22 = _verse(result, 22)
    fragment_types = [fragment["type"] for line in verse_22.lines for fragment in line["fragments"]]
    assert "footnote" in fragment_types
    assert "nd" in fragment_types
    assert "wj" in fragment_types
    footnote = next(fragment for line in verse_22.lines for fragment in line["fragments"] if fragment["type"] == "footnote")
    assert footnote["kind"] == "f"
    assert footnote["label"]
    assert "無緣無故" in footnote["text"] or footnote["text"]
    assert isinstance(footnote["refs"], list)
    unknown = next(fragment for line in verse_22.lines for fragment in line["fragments"] if fragment.get("style") == "rare")
    assert unknown["type"] == "text"
    assert unknown["text"] == "未知"
    fill = repo.write_calls[0]
    verse_fill = next(item for item in fill if item["verse"] == 22)
    assert "無緣無故" in verse_fill["search_text"] or "耶和華" in verse_fill["search_text"]
    assert "footnote" not in verse_fill["search_text"]
    assert "未知" in verse_fill["search_text"]
    assert "耶和華" in verse_fill["search_text"]
    assert "你們要愛" in verse_fill["search_text"]


@pytest.mark.asyncio
async def test_get_chapter_concurrent_miss_shares_one_youversion_call(gen2_passage):
    from portal.application.bible.chapter_fill_gate import ChapterFillGate

    chapter = _unfilled_chapter(book_code="GEN", chapter=2, verses=list(range(1, 26)))
    youversion = StubYouVersion(passages={"1392:GEN.2": gen2_passage}, delay_sec=0.05)
    repo = StubBibleRepository(chapter)
    gate = ChapterFillGate()
    service = BibleService(repo, youversion, chapter_fill_gate=gate)

    results = await asyncio.gather(service.get_chapter(book_id=chapter.book_id, chapter=2), service.get_chapter(book_id=chapter.book_id, chapter=2))

    assert len(youversion.calls) == 1
    assert len(repo.write_calls) == 2
    assert results[0].verses[0].lines is not None
    assert results[1].verses[0].lines is not None


@pytest.mark.asyncio
async def test_get_chapter_youversion_timeout_fails_request():
    chapter = _unfilled_chapter(book_code="GEN", chapter=2, verses=list(range(1, 26)))
    youversion = StubYouVersion(error=YouVersionHttpError(0, "/v1/bibles/1392/passages/GEN.2", message="timeout"))
    service = BibleService(StubBibleRepository(chapter), youversion)

    with pytest.raises(ApiBaseException) as exc_info:
        await service.get_chapter(book_id=chapter.book_id, chapter=2)

    assert exc_info.value.status_code == 502
    assert youversion.calls == [("1392", "GEN.2")]


@pytest.mark.asyncio
async def test_get_chapter_second_read_skips_youversion(gen2_passage):
    chapter = _unfilled_chapter(book_code="GEN", chapter=2, verses=list(range(1, 26)))
    youversion = StubYouVersion(passages={"1392:GEN.2": gen2_passage})
    service = BibleService(StubBibleRepository(chapter), youversion)

    first = await service.get_chapter(book_id=chapter.book_id, chapter=2)
    second = await service.get_chapter(book_id=chapter.book_id, chapter=2)

    assert first.verses[3].lines is not None
    assert second.verses[3].lines is not None
    assert youversion.calls == [("1392", "GEN.2")]
