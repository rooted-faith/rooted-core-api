"""
Publisher paragraph boundaries and Headings in the chapter response (issues #128, #130).

Seam: the serialized chapter response over the real BibleService chapter fill,
with controlled repository and YouVersion dependencies.
"""

import pytest

from portal.application.bible.bible_service import BibleService
from portal.domain.bible.entities import BibleChapter
from portal.exceptions.responses import ApiBaseException
from portal.routers.apis.v1.bible import get_bible_chapter
from tests.fixtures.bible_chapter_fill import StubBibleRepository, StubYouVersion, load_passage, unfilled_chapter


def _service(chapter: BibleChapter, content: str) -> BibleService:
    key = f"{chapter.youversion_bible_id}:{chapter.book_code}.{chapter.chapter}"
    return BibleService(StubBibleRepository(chapter), StubYouVersion(passages={key: {"content": content}}))


async def _read(service: BibleService, chapter: BibleChapter) -> dict:
    response = await get_bible_chapter(book_id=chapter.book_id, chapter=chapter.chapter, bible_service=service)
    return response.model_dump(mode="json", by_alias=True)


async def _read_html(content: str, verses: list[int]) -> dict:
    chapter = unfilled_chapter(book_code="TST", chapter=1, verses=verses)
    return await _read(_service(chapter, content), chapter)


def _paragraphs(payload: dict) -> list[list[int]]:
    """Group verse numbers the way a client would: body lines only, split wherever a line does not continue."""
    paragraphs: list[list[int]] = []
    for verse in payload["verses"]:
        for line in verse["lines"]:
            if line["type"] == "heading":
                continue
            if not line["continues"]:
                paragraphs.append([])
            if verse["verse"] not in paragraphs[-1]:
                paragraphs[-1].append(verse["verse"])
    return paragraphs


def _text(line: dict) -> str:
    return "".join(fragment["text"] for fragment in line["fragments"] if fragment["type"] != "footnote")


def _lines(payload: dict, verse: int) -> list[dict]:
    return next(item["lines"] for item in payload["verses"] if item["verse"] == verse)


@pytest.mark.asyncio
async def test_revelation_21_keeps_publisher_paragraphs_and_headings():
    chapter = unfilled_chapter(book_code="REV", chapter=21, verses=[*range(1, 13), *range(14, 28)])
    service = _service(chapter, load_passage("rev21")["content"])

    payload = await _read(service, chapter)

    assert _paragraphs(payload) == [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12, 14], [15, 16, 17, 18, 19, 20], [21], [22, 23, 24, 25, 26, 27]]
    assert next(verse["verseEnd"] for verse in payload["verses"] if verse["verse"] == 12) == 13
    headings = [(verse["verse"], index, _text(line)) for verse in payload["verses"] for index, line in enumerate(verse["lines"]) if line["type"] == "heading"]
    assert headings == [(1, 0, "新天新地"), (9, 0, "新耶路撒冷")]
    footnotes = [fragment for verse in payload["verses"] for line in verse["lines"] for fragment in line["fragments"] if fragment["type"] == "footnote"]
    assert [(note["label"], note["text"]) for note in footnotes] == [
        ("21·1", "以賽亞書65·17。"),
        ("21·4", "以賽亞書25·8。"),
        ("21·16", "「兩千二百公里」希臘文是「一萬二千司他町」。"),
        ("21·17", "「六十五米」希臘文是「一百四十四肘」。"),
    ]


@pytest.mark.asyncio
async def test_adjacent_paragraphs_with_the_same_style_stay_distinguishable():
    payload = await _read_html(
        '<div><div class="p"><span class="yv-v" v="1"></span><span class="yv-vlbl">1</span>甲。 <span class="yv-v" v="2"></span>乙。</div>'
        '<div class="p"><span class="yv-v" v="3"></span>丙。</div></div>',
        verses=[1, 2, 3],
    )

    assert _paragraphs(payload) == [[1, 2], [3]]
    assert {line["style"] for verse in payload["verses"] for line in verse["lines"]} == {"p"}


@pytest.mark.asyncio
async def test_paragraph_break_inside_one_verse_is_kept():
    payload = await _read_html(
        '<div><div class="p"><span class="yv-v" v="1"></span>甲。 <span class="yv-v" v="2"></span>乙上。</div>'
        '<div class="p">乙下。 <span class="yv-v" v="3"></span>丙。</div></div>',
        verses=[1, 2, 3],
    )

    assert _paragraphs(payload) == [[1, 2], [2, 3]]
    assert [(_text(line), line["continues"]) for line in _lines(payload, 2)] == [("乙上。", True), ("乙下。 ", False)]


@pytest.mark.asyncio
async def test_mid_verse_heading_stays_between_the_two_parts_of_its_verse():
    chapter = unfilled_chapter(book_code="GEN", chapter=2, verses=list(range(1, 26)))
    payload = await _read(_service(chapter, load_passage("gen2")["content"]), chapter)

    assert [(line["type"], line["continues"]) for line in _lines(payload, 4)] == [("line", True), ("heading", False), ("line", False)]
    assert _lines(payload, 5)[0]["continues"] is True


@pytest.mark.asyncio
async def test_heading_waits_for_the_verse_marker_that_shares_the_next_paragraph():
    payload = await _read_html(
        '<div><div class="p"><span class="yv-v" v="1"></span>甲。</div><div class="s1 yv-h">上</div><div class="r yv-h">下</div>'
        '<div class="p"><span class="yv-v" v="2"></span>乙。</div></div>',
        verses=[1, 2],
    )

    assert [line["type"] for line in _lines(payload, 1)] == ["line"]
    assert [(line["type"], line["style"], _text(line)) for line in _lines(payload, 2)] == [
        ("heading", "s1", "上"),
        ("heading", "r", "下"),
        ("line", "p", "乙。"),
    ]


@pytest.mark.asyncio
async def test_heading_after_the_last_verse_is_not_lost():
    payload = await _read_html('<div><div class="p"><span class="yv-v" v="1"></span>甲。</div><div class="s1 yv-h">尾</div></div>', verses=[1])

    assert [(line["type"], _text(line)) for line in _lines(payload, 1)] == [("line", "甲。"), ("heading", "尾")]


@pytest.mark.asyncio
async def test_each_poetry_line_starts_a_block_and_keeps_its_indentation_style():
    payload = await _read_html(
        '<div><div class="q1"><span class="yv-v" ev="2" v="1"></span><span class="yv-vlbl">1-2</span>Blessed is the one</div>'
        '<div class="q2">who does not walk,</div><div class="q1"><span class="yv-v" v="3"></span>but delights.</div></div>',
        verses=[1, 3],
    )

    assert [(line["style"], line["continues"], _text(line)) for line in _lines(payload, 1)] == [
        ("q1", False, "Blessed is the one"),
        ("q2", False, "who does not walk,"),
    ]
    assert payload["verses"][0]["verseEnd"] == 2
    assert _lines(payload, 3)[0]["continues"] is False


@pytest.mark.asyncio
async def test_english_word_separation_survives_inline_styles_footnotes_and_verse_joins():
    payload = await _read_html(
        '<div>\n  <div class="p">\n    <span class="yv-v" v="1"></span>\n    <span class="yv-vlbl">1</span>Then the <span class="nd">Lord</span> God\n'
        '      said to <span class="pn">Abram</span> <span class="add">again</span>,<span class="yv-n f"><span class="fr">1:1 </span>'
        '<span class="ft">Or </span><span class="fqa">spoke</span> <span class="ft">to him</span></span> “Go.”\n'
        '    <span class="yv-v" v="2"></span>\n    <span class="yv-vlbl">2</span>So he <span class="yv-n f"><span class="ft">Hebrew</span></span> went.\n  </div>\n</div>',
        verses=[1, 2],
    )

    [first], [second] = _lines(payload, 1), _lines(payload, 2)
    assert _text(first) + _text(second) == "Then the Lord God said to Abram again, “Go.” So he went."
    footnote = next(fragment for fragment in first["fragments"] if fragment["type"] == "footnote")
    assert (footnote["label"], footnote["text"]) == ("1:1", "Or spoke to him")
    assert [fragment["type"] for fragment in first["fragments"] if fragment["type"] in {"nd", "pn"}] == ["nd", "pn"]


@pytest.mark.asyncio
async def test_search_text_separates_english_words_across_lines():
    chapter = unfilled_chapter(book_code="PSA", chapter=1, verses=[1])
    repository = StubBibleRepository(chapter)
    content = '<div><div class="q1"><span class="yv-v" v="1"></span>Blessed is <span class="nd">Lord</span> </div><div class="q2">who walks</div></div>'
    service = BibleService(repository, StubYouVersion(passages={"1392:PSA.1": {"content": content}}))

    await _read(service, chapter)

    assert repository.write_calls[0][0]["search_text"] == "Blessed is Lord who walks"


@pytest.mark.asyncio
async def test_legacy_filled_chapter_stays_readable_and_has_no_boundary_metadata():
    chapter = unfilled_chapter(book_code="GEN", chapter=1, verses=[1])
    legacy_lines = [{"type": "line", "style": "p", "fragments": [{"type": "text", "text": "太初"}]}]
    chapter.verses[0].lines = legacy_lines
    youversion = StubYouVersion()

    payload = await _read(BibleService(StubBibleRepository(chapter), youversion), chapter)

    assert _lines(payload, 1) == legacy_lines
    assert youversion.calls == []


@pytest.mark.asyncio
async def test_boundary_metadata_survives_a_second_read_without_another_fetch():
    chapter = unfilled_chapter(book_code="REV", chapter=21, verses=[*range(1, 13), *range(14, 28)])
    youversion = StubYouVersion(passages={"1392:REV.21": load_passage("rev21")})
    service = BibleService(StubBibleRepository(chapter), youversion)

    first = await _read(service, chapter)
    second = await _read(service, chapter)

    assert second == first
    assert all("continues" in line for verse in second["verses"] for line in verse["lines"])
    assert len(youversion.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "before_marker", ["&#160;", "\u3000", '<span class="yv-n f"><span class="ft">note</span></span>'], ids=["nbsp", "ideographic-space", "footnote"]
)
async def test_invisible_content_before_a_verse_marker_does_not_claim_its_paragraph(before_marker):
    payload = await _read_html(
        '<div><div class="p"><span class="yv-v" v="1"></span>甲。</div><div class="s1 yv-h">題</div>'
        f'<div class="p">{before_marker}<span class="yv-v" v="2"></span>乙。</div></div>',
        verses=[1, 2],
    )

    assert [(line["type"], line["continues"], _text(line)) for line in _lines(payload, 1)] == [("line", False, "甲。")]
    assert [(line["type"], line["continues"], _text(line).strip()) for line in _lines(payload, 2)] == [("heading", False, "題"), ("line", False, "乙。")]
    assert any(fragment["type"] == "footnote" for fragment in _lines(payload, 2)[1]["fragments"]) == ("yv-n" in before_marker)


@pytest.mark.asyncio
async def test_verse_holding_only_a_heading_fails_the_fill():
    chapter = unfilled_chapter(book_code="TST", chapter=1, verses=[1, 2, 3])
    content = (
        '<div><div class="p"><span class="yv-v" v="1"></span>甲。</div><div class="s1 yv-h">題</div>'
        '<div class="p"><span class="yv-v" v="2"></span></div><div class="p"><span class="yv-v" v="3"></span>丙。</div></div>'
    )

    with pytest.raises(ApiBaseException) as exc_info:
        await _read(_service(chapter, content), chapter)

    assert exc_info.value.status_code == 502


PSALM_3 = (
    '<div><div class="cl yv-h">Psalm 3<span class="yv-n f"><span class="ft">In Hebrew texts 3:1-8 is numbered 3:2-9.</span></span></div>'
    '<div class="d">A psalm of David. When he fled from his son Absalom.</div>'
    '<div class="q1"><span class="yv-v" v="1"></span><span class="yv-vlbl">1</span><span class="sc">Lord</span>, how many are my foes!</div></div>'
)


@pytest.mark.asyncio
async def test_footnote_in_a_heading_is_not_part_of_the_heading_text():
    payload = await _read_html(PSALM_3, verses=[1])

    heading = _lines(payload, 1)[0]
    assert (heading["type"], heading["style"], heading["continues"]) == ("heading", "cl", False)
    assert heading["fragments"] == [
        {"type": "text", "text": "Psalm 3"},
        {"type": "footnote", "kind": "f", "label": "1", "text": "In Hebrew texts 3:1-8 is numbered 3:2-9.", "refs": []},
    ]


@pytest.mark.asyncio
async def test_psalm_superscription_is_a_heading_before_the_first_verse():
    chapter = unfilled_chapter(book_code="PSA", chapter=3, verses=[1])
    repository = StubBibleRepository(chapter)

    payload = await _read(BibleService(repository, StubYouVersion(passages={"1392:PSA.3": {"content": PSALM_3}})), chapter)

    assert [(line["type"], line["style"], line["continues"], _text(line)) for line in _lines(payload, 1)] == [
        ("heading", "cl", False, "Psalm 3"),
        ("heading", "d", False, "A psalm of David. When he fled from his son Absalom."),
        ("line", "q1", False, "Lord, how many are my foes!"),
    ]
    assert [line["fragments"] for line in _lines(payload, 1)[1:]] == [
        [{"type": "text", "text": "A psalm of David. When he fled from his son Absalom."}],
        [{"type": "text", "text": "Lord", "style": "sc"}, {"type": "text", "text": ", how many are my foes!"}],
    ]
    assert repository.write_calls[0][0]["search_text"] == "Lord, how many are my foes!"


@pytest.mark.asyncio
async def test_superscription_keeps_its_inline_styles_and_footnote():
    payload = await _read_html(
        '<div><div class="d">For the <span class="nd">Lord</span><span class="yv-n f"><span class="fr">3:1 </span>'
        '<span class="ft">Or for God</span></span>, a psalm.</div><div class="q1"><span class="yv-v" v="1"></span>one</div></div>',
        verses=[1],
    )

    assert _lines(payload, 1)[0]["fragments"] == [
        {"type": "text", "text": "For the "},
        {"type": "nd", "text": "Lord"},
        {"type": "footnote", "kind": "f", "label": "3:1", "text": "Or for God", "refs": []},
        {"type": "text", "text": ", a psalm."},
    ]


@pytest.mark.asyncio
async def test_superscription_is_decided_by_position_and_keeps_publisher_order():
    payload = await _read_html(
        '<div><div class="s1 yv-h">one</div><div class="iex">two</div><div class="b"></div><div class="r yv-h">three</div>'
        '<div class="d">four</div><div class="q1"><span class="yv-v" v="1"></span>body</div></div>',
        verses=[1],
    )

    assert [(line["type"], line["style"], _text(line)) for line in _lines(payload, 1)] == [
        ("heading", "s1", "one"),
        ("heading", "iex", "two"),
        ("heading", "r", "three"),
        ("heading", "d", "four"),
        ("line", "q1", "body"),
    ]


@pytest.mark.asyncio
async def test_d_block_that_holds_a_verse_or_follows_scripture_is_scripture():
    payload = await _read_html(
        '<div><div class="d"><span class="yv-v" v="1"></span>A prayer of Habakkuk.</div><div class="q1"><span class="yv-v" v="2"></span>body</div>'
        '<div class="d">For the director of music.</div></div>',
        verses=[1, 2],
    )

    assert [(line["type"], line["style"], line["continues"]) for line in _lines(payload, 1)] == [("line", "d", False)]
    assert [(line["type"], line["style"], _text(line)) for line in _lines(payload, 2)] == [("line", "q1", "body"), ("line", "d", "For the director of music.")]


@pytest.mark.asyncio
async def test_heading_whitespace_is_collapsed_around_its_footnote():
    payload = await _read_html(
        '<div>\n  <div class="s1 yv-h">\n    The <span class="nd">Lord</span><span class="yv-n f">\n      <span class="ft">note</span>\n    </span>\n'
        '    reigns\n  </div>\n  <div class="p"><span class="yv-v" v="1"></span>one</div></div>',
        verses=[1],
    )

    fragments = _lines(payload, 1)[0]["fragments"]
    assert [(fragment["type"], fragment["text"]) for fragment in fragments] == [("text", "The Lord"), ("footnote", "note"), ("text", " reigns")]


@pytest.mark.asyncio
async def test_generated_footnote_labels_follow_document_order_across_headings_and_scripture():
    note = '<span class="yv-n f"><span class="ft">note</span></span>'
    payload = await _read_html(
        f'<div><div class="p"><span class="yv-v" v="1"></span>one{note}</div><div class="s1 yv-h">title{note}</div>'
        f'<div class="p"><span class="yv-v" v="2"></span>two{note}</div></div>',
        verses=[1, 2],
    )

    footnotes = [fragment for verse in payload["verses"] for line in verse["lines"] for fragment in line["fragments"] if fragment["type"] == "footnote"]
    assert [footnote["label"] for footnote in footnotes] == ["1", "2", "3"]
