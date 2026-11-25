"""
Read-time fill on BibleService.get_chapter (issue #74).

Seam: get_chapter with stub YouVersionPort + stub BibleRepositoryPort.
HTML fixtures are the stub YouVersion return value — no live YVP_APP_KEY.
"""

from __future__ import annotations

import asyncio

import pytest

from portal.application.bible.bible_service import BibleService
from portal.application.bible.commands import RefillChapterCommand
from portal.application.bible.results import ChapterRefillOutcome
from portal.domain.bible.entities import BibleChapter, BibleVerse
from portal.exceptions.responses import ApiBaseException, NotFoundException
from portal.infrastructure.youversion.youversion_http_client import YouVersionHttpError
from tests.fixtures.bible_chapter_fill import StubBibleRepository, StubYouVersion, legacy_chapter, load_passage, unfilled_chapter


@pytest.fixture
def gen2_passage() -> dict:
    return load_passage("gen2")


@pytest.fixture
def psa1_passage() -> dict:
    return load_passage("psa1")


@pytest.fixture
def mat5_passage() -> dict:
    return load_passage("mat5")


def _verse(result: BibleChapter, number: int) -> BibleVerse:
    return next(item for item in result.verses if item.verse == number)


@pytest.mark.asyncio
async def test_get_chapter_fills_mid_verse_heading_in_gen_2(gen2_passage):
    chapter = unfilled_chapter(book_code="GEN", chapter=2, verses=list(range(1, 26)))
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
    chapter = unfilled_chapter(book_code="PSA", chapter=1, verses=[1, 3, 4, 5, 6])
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
    chapter = unfilled_chapter(book_code="MAT", chapter=5, verses=list(range(1, 49)))
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

    chapter = unfilled_chapter(book_code="GEN", chapter=2, verses=list(range(1, 26)))
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
    chapter = unfilled_chapter(book_code="GEN", chapter=2, verses=list(range(1, 26)))
    youversion = StubYouVersion(error=YouVersionHttpError(0, "/v1/bibles/1392/passages/GEN.2", message="timeout"))
    service = BibleService(StubBibleRepository(chapter), youversion)

    with pytest.raises(ApiBaseException) as exc_info:
        await service.get_chapter(book_id=chapter.book_id, chapter=2)

    assert exc_info.value.status_code == 502
    assert youversion.calls == [("1392", "GEN.2")]


@pytest.mark.asyncio
async def test_get_chapter_second_read_skips_youversion(gen2_passage):
    chapter = unfilled_chapter(book_code="GEN", chapter=2, verses=list(range(1, 26)))
    youversion = StubYouVersion(passages={"1392:GEN.2": gen2_passage})
    service = BibleService(StubBibleRepository(chapter), youversion)

    first = await service.get_chapter(book_id=chapter.book_id, chapter=2)
    second = await service.get_chapter(book_id=chapter.book_id, chapter=2)

    assert first.verses[3].lines is not None
    assert second.verses[3].lines is not None
    assert youversion.calls == [("1392", "GEN.2")]


GEN2_VERSES = list(range(1, 26))
REFILL_GEN2 = RefillChapterCommand(youversion_bible_id="1392", book_code="GEN", chapter=2)
FORCE_REFILL_GEN2 = RefillChapterCommand(youversion_bible_id="1392", book_code="GEN", chapter=2, force=True)


@pytest.mark.asyncio
async def test_refill_chapter_upgrades_a_legacy_chapter_and_keeps_its_addresses(gen2_passage):
    chapter = legacy_chapter(book_code="GEN", chapter=2, verses=GEN2_VERSES)
    youversion = StubYouVersion(passages={"1392:GEN.2": gen2_passage})
    repo = StubBibleRepository(chapter)
    service = BibleService(repo, youversion)

    outcome = await service.refill_chapter(REFILL_GEN2)
    result = await service.get_chapter(book_id=chapter.book_id, chapter=2)

    assert outcome == ChapterRefillOutcome.UPGRADED
    assert all("continues" in line for verse in result.verses for line in verse.lines)
    assert (result.book_id, result.bible_version_id) == (chapter.book_id, chapter.bible_version_id)
    assert [verse.passage_id for verse in result.verses] == [verse.passage_id for verse in chapter.verses]
    assert len(youversion.calls) == 1


@pytest.mark.asyncio
async def test_refill_chapter_twice_fetches_once(gen2_passage):
    chapter = legacy_chapter(book_code="GEN", chapter=2, verses=GEN2_VERSES)
    youversion = StubYouVersion(passages={"1392:GEN.2": gen2_passage})
    service = BibleService(StubBibleRepository(chapter), youversion)

    outcomes = [await service.refill_chapter(REFILL_GEN2), await service.refill_chapter(REFILL_GEN2)]

    assert outcomes == [ChapterRefillOutcome.UPGRADED, ChapterRefillOutcome.ALREADY_UPGRADED]
    assert len(youversion.calls) == 1


@pytest.mark.asyncio
async def test_refill_chapter_leaves_an_unfilled_chapter_to_read_time_fill(gen2_passage):
    chapter = unfilled_chapter(book_code="GEN", chapter=2, verses=GEN2_VERSES)
    youversion = StubYouVersion(passages={"1392:GEN.2": gen2_passage})
    repo = StubBibleRepository(chapter)

    outcome = await BibleService(repo, youversion).refill_chapter(REFILL_GEN2)

    assert outcome == ChapterRefillOutcome.UNFILLED
    assert youversion.calls == []
    assert repo.write_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "youversion",
    [
        StubYouVersion(error=YouVersionHttpError(503, "/v1/bibles/1392/passages/GEN.2")),
        StubYouVersion(passages={"1392:GEN.2": {"content": ""}}),
        StubYouVersion(passages={"1392:GEN.2": {"content": "<div><div"}}),
        StubYouVersion(passages={"1392:GEN.2": {"content": '<div><div class="p"><span class="yv-v" v="1"></span>one</div></div>'}}),
    ],
    ids=["http-error", "empty-content", "invalid-html", "verse-set-mismatch"],
)
async def test_failed_refill_keeps_the_legacy_chapter_readable(youversion):
    chapter = legacy_chapter(book_code="GEN", chapter=2, verses=GEN2_VERSES)
    repo = StubBibleRepository(chapter)
    service = BibleService(repo, youversion)

    with pytest.raises(ApiBaseException) as exc_info:
        await service.refill_chapter(REFILL_GEN2)

    assert exc_info.value.status_code == 502
    assert repo.write_calls == []
    assert (await service.get_chapter(book_id=chapter.book_id, chapter=2)).verses == chapter.verses


@pytest.mark.asyncio
async def test_concurrent_refill_and_read_share_one_youversion_call(gen2_passage):
    chapter = legacy_chapter(book_code="GEN", chapter=2, verses=GEN2_VERSES)
    youversion = StubYouVersion(passages={"1392:GEN.2": gen2_passage}, delay_sec=0.05)
    service = BibleService(StubBibleRepository(chapter), youversion)

    _, _, read = await asyncio.gather(
        service.refill_chapter(REFILL_GEN2), service.refill_chapter(REFILL_GEN2), service.get_chapter(book_id=chapter.book_id, chapter=2)
    )

    assert len(youversion.calls) == 1
    assert read.verses == chapter.verses


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command",
    [
        RefillChapterCommand(youversion_bible_id="9999", book_code="GEN", chapter=2),
        RefillChapterCommand(youversion_bible_id="1392", book_code="XXX", chapter=2),
    ],
    ids=["version", "book"],
)
async def test_refill_chapter_rejects_an_unknown_address(command):
    service = BibleService(StubBibleRepository(legacy_chapter(book_code="GEN", chapter=2, verses=GEN2_VERSES)), StubYouVersion())

    with pytest.raises(NotFoundException):
        await service.refill_chapter(command)


@pytest.mark.asyncio
async def test_refill_chapter_rejects_a_chapter_without_verses():
    service = BibleService(StubBibleRepository(legacy_chapter(book_code="GEN", chapter=2, verses=[])), StubYouVersion())

    with pytest.raises(NotFoundException):
        await service.refill_chapter(REFILL_GEN2)


@pytest.mark.asyncio
async def test_forced_refill_replaces_an_upgraded_chapter_with_one_fetch(gen2_passage):
    chapter = legacy_chapter(book_code="GEN", chapter=2, verses=GEN2_VERSES)
    repo = StubBibleRepository(chapter)
    await BibleService(repo, StubYouVersion(passages={"1392:GEN.2": gen2_passage})).refill_chapter(REFILL_GEN2)
    revised = {"content": gen2_passage["content"].replace("伊甸", "修訂", 1)}
    youversion = StubYouVersion(passages={"1392:GEN.2": revised})
    service = BibleService(repo, youversion)

    outcome = await service.refill_chapter(FORCE_REFILL_GEN2)

    result = await service.get_chapter(book_id=chapter.book_id, chapter=2)
    assert outcome == ChapterRefillOutcome.UPGRADED
    assert any(fragment["text"] == "修訂" for verse in result.verses for line in verse.lines for fragment in line["fragments"])
    assert len(youversion.calls) == 1


@pytest.mark.asyncio
async def test_forced_refill_leaves_an_unfilled_chapter_to_read_time_fill(gen2_passage):
    youversion = StubYouVersion(passages={"1392:GEN.2": gen2_passage})
    repo = StubBibleRepository(unfilled_chapter(book_code="GEN", chapter=2, verses=GEN2_VERSES))

    assert await BibleService(repo, youversion).refill_chapter(FORCE_REFILL_GEN2) == ChapterRefillOutcome.UNFILLED
    assert youversion.calls == []
