"""
Parse YouVersion chapter HTML into structured verse fills.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from portal.domain.bible.constants import CONTINUES_KEY

KNOWN_FRAGMENT_TYPES = frozenset({"nd", "wj", "pn"})
YV_CLASSES = frozenset({"yv-h", "yv-v", "yv-vlbl", "yv-n", "yv-clbl"})
# HTML whitespace only: NBSP and ideographic spaces are publisher content.
_HTML_WHITESPACE = re.compile(r"[ \t\r\n\f]+")


class ChapterHtmlParseError(ValueError):
    """YouVersion HTML could not be mapped into verse fills."""


def parse_chapter_html(content: str) -> list[dict[str, Any]]:
    """Return fills: {verse, verse_end, lines, search_text} ordered by verse."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ChapterHtmlParseError(f"invalid chapter HTML: {exc}") from exc

    fills: dict[int, dict[str, Any]] = {}
    current_verse: int | None = None
    pending_headings: list[dict[str, Any]] = []
    footnote_seq = 0
    block_started = False

    def ensure_verse(verse: int, verse_end: int | None = None) -> dict[str, Any]:
        nonlocal pending_headings
        fill = fills.get(verse)
        if fill is None:
            fill = {"verse": verse, "verse_end": verse_end, "lines": [], "search_text": ""}
            fills[verse] = fill
        elif verse_end is not None:
            fill["verse_end"] = verse_end
        if pending_headings:
            fill["lines"].extend(pending_headings)
            pending_headings = []
        return fill

    def number_footnote(fragment: dict[str, Any]) -> None:
        nonlocal footnote_seq
        footnote_seq += 1
        if not fragment["label"]:
            fragment["label"] = str(footnote_seq)

    def append_line(style: str, fragments: list[dict[str, Any]]) -> None:
        nonlocal block_started
        fragments = _collapse_fragment_whitespace(fragments)
        if current_verse is None or not (_has_visible_text(fragments) or _footnotes(fragments)):
            return
        ensure_verse(current_verse)["lines"].append({"type": "line", "style": style, CONTINUES_KEY: block_started, "fragments": fragments})
        block_started = True

    def append_unversed_block(style: str, fragments: list[dict[str, Any]]) -> None:
        """A block before the first verse marker has no verse of its own, so it waits for one as a heading does."""
        fragments = _collapse_fragment_whitespace(fragments)
        if _has_visible_text(fragments) or _footnotes(fragments):
            pending_headings.append({"type": "heading", "style": style, CONTINUES_KEY: False, "fragments": fragments})

    for block in list(root):
        classes = _classes(block)
        style = _publisher_style(classes)
        if "yv-h" in classes:
            fragments = _collapse_fragment_whitespace(_trim_trailing_whitespace(_heading_fragments(block)))
            for footnote in _footnotes(fragments):
                number_footnote(footnote)
            # A heading belongs to whatever Scripture follows it: the next verse, or the rest of the current one.
            pending_headings.append({"type": "heading", "style": style or "s", CONTINUES_KEY: False, "fragments": fragments})
            continue

        block_started = False
        marker_seen = False
        fragments = []
        for event in _iter_block_events(block):
            if event["kind"] == "verse":
                if marker_seen or _has_visible_text(fragments):
                    append_line(style, fragments)
                    fragments = []
                else:
                    fragments = _footnotes(fragments)
                marker_seen = True
                current_verse = event["verse"]
                ensure_verse(current_verse, event.get("verse_end"))
                continue
            if event["kind"] == "fragment":
                fragment = event["fragment"]
                if fragment["type"] == "footnote":
                    number_footnote(fragment)
                fragments.append(fragment)

        fragments = _trim_trailing_whitespace(fragments)
        if current_verse is None:
            append_unversed_block(style, fragments)
        else:
            append_line(style, fragments)

    if pending_headings and current_verse is not None:
        ensure_verse(current_verse)

    if not fills:
        raise ChapterHtmlParseError("chapter HTML produced no verses")

    for fill in fills.values():
        fill["search_text"] = _build_search_text(fill["lines"])
        if all(line["type"] == "heading" for line in fill["lines"]):
            raise ChapterHtmlParseError(f"verse {fill['verse']} has no Scripture lines")

    return [fills[verse] for verse in sorted(fills)]


def _classes(element: ET.Element) -> set[str]:
    return {item for item in (element.get("class") or "").split() if item}


def _publisher_style(classes: set[str]) -> str:
    styles = sorted(item for item in classes if item not in YV_CLASSES)
    if not styles:
        return "p"
    return " ".join(styles)


def _iter_block_events(block: ET.Element):
    if block.text:
        yield _text_event(block.text)

    for child in list(block):
        classes = _classes(child)
        if "yv-v" in classes:
            verse = child.get("v")
            if verse is None:
                raise ChapterHtmlParseError("yv-v missing v attribute")
            verse_end_raw = child.get("ev")
            yield {"kind": "verse", "verse": int(verse), "verse_end": int(verse_end_raw) if verse_end_raw else None}
        elif "yv-vlbl" in classes:
            pass
        elif "yv-n" in classes:
            yield {"kind": "fragment", "fragment": _parse_footnote(child, classes)}
        elif classes & KNOWN_FRAGMENT_TYPES:
            fragment_type = next(item for item in sorted(classes) if item in KNOWN_FRAGMENT_TYPES)
            yield _text_event("".join(child.itertext()), fragment_type)
        else:
            event = _text_event("".join(child.itertext()))
            style = _publisher_style(classes)
            if style and style != "p":
                event["fragment"]["style"] = style
            yield event

        if child.tail:
            yield _text_event(child.tail)


def _heading_fragments(block: ET.Element) -> list[dict[str, Any]]:
    """Plain text with inline styles flattened, broken only where a Footnote sits."""
    fragments: list[dict[str, Any]] = []
    text = block.text or ""
    for child in list(block):
        classes = _classes(child)
        if "yv-n" in classes:
            fragments += [{"type": "text", "text": text}, _parse_footnote(child, classes)]
            text = ""
        else:
            text += "".join(child.itertext())
        text += child.tail or ""
    return [*fragments, {"type": "text", "text": text}]


def _text_event(text: str, fragment_type: str = "text") -> dict[str, Any]:
    return {"kind": "fragment", "fragment": {"type": fragment_type, "text": text}}


def _collapse_whitespace(text: str) -> str:
    return _HTML_WHITESPACE.sub(" ", text)


def _collapse_fragment_whitespace(fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse whitespace as HTML does across inline fragments, dropping the line's leading space but keeping word separators."""
    kept: list[dict[str, Any]] = []
    ends_with_space = True
    for fragment in fragments:
        if fragment["type"] == "footnote":
            kept.append(fragment)
            continue
        text = _collapse_whitespace(fragment["text"])
        if ends_with_space:
            text = text.removeprefix(" ")
        if text:
            kept.append({**fragment, "text": text})
            ends_with_space = text.endswith(" ")
    return kept


def _has_visible_text(fragments: list[dict[str, Any]]) -> bool:
    return any(fragment["text"].strip() for fragment in fragments if fragment["type"] != "footnote")


def _footnotes(fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [fragment for fragment in fragments if fragment["type"] == "footnote"]


def _trim_trailing_whitespace(fragments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trimmed = list(fragments)
    while trimmed and trimmed[-1]["type"] != "footnote":
        text = _collapse_whitespace(trimmed[-1]["text"]).removesuffix(" ")
        if text:
            trimmed[-1] = {**trimmed[-1], "text": text}
            break
        trimmed.pop()
    return trimmed


def _parse_footnote(element: ET.Element, classes: set[str]) -> dict[str, Any]:
    kind = "f"
    for candidate in ("f", "x", "fe", "ef", "ex"):
        if candidate in classes:
            kind = candidate
            break

    label = ""
    text_parts: list[str] = []
    refs: list[dict[str, str]] = []

    label_el = element.find("./span[@class='label']")
    if label_el is not None:
        label = "".join(label_el.itertext()).strip()

    for child in list(element):
        child_classes = _classes(child)
        if "fr" in child_classes and not label:
            label = "".join(child.itertext()).strip()
            continue
        if "ft" in child_classes or "fqa" in child_classes or "body" in child_classes:
            for ref_el in child.findall(".//span"):
                if "ref" in _classes(ref_el):
                    refs.append({"usfm": ref_el.get("usfm") or "", "text": "".join(ref_el.itertext()).strip()})
            # Build note text from this node, excluding nested ref element text duplication preference:
            # keep full visible text including refs' display text.
            text_parts.append("".join(child.itertext()) + (child.tail or ""))
            continue
        if "ref" in child_classes:
            refs.append({"usfm": child.get("usfm") or "", "text": "".join(child.itertext()).strip()})

    return {"type": "footnote", "kind": kind, "label": label, "text": _collapse_whitespace("".join(text_parts)).strip(" "), "refs": refs}


def _build_search_text(lines: list[dict[str, Any]]) -> str:
    texts = []
    for line in lines:
        if line.get("type") == "heading":
            continue
        fragments = line.get("fragments") or []
        texts.append("".join(fragment.get("text") or "" for fragment in fragments if fragment.get("type") in {"text", *KNOWN_FRAGMENT_TYPES}))
    return _collapse_whitespace(" ".join(texts)).strip(" ")
