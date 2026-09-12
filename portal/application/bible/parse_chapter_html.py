"""
Parse YouVersion chapter HTML into structured verse fills.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

KNOWN_FRAGMENT_TYPES = frozenset({"nd", "wj", "pn"})
YV_CLASSES = frozenset({"yv-h", "yv-v", "yv-vlbl", "yv-n", "yv-clbl"})


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

    def ensure_verse(verse: int, verse_end: int | None = None) -> dict[str, Any]:
        nonlocal pending_headings
        fill = fills.get(verse)
        if fill is None:
            fill = {"verse": verse, "verse_end": verse_end, "lines": [], "search_text": ""}
            fills[verse] = fill
            if pending_headings:
                fill["lines"].extend(pending_headings)
                pending_headings = []
        elif verse_end is not None:
            fill["verse_end"] = verse_end
        return fill

    def append_line(verse: int | None, line: dict[str, Any]) -> None:
        nonlocal pending_headings
        if verse is None:
            if line["type"] == "heading":
                pending_headings.append(line)
            return
        fill = ensure_verse(verse)
        fill["lines"].append(line)

    def append_fragments(verse: int | None, style: str, fragments: list[dict[str, Any]]) -> None:
        if not fragments:
            return
        append_line(verse, {"type": "line", "style": style, "fragments": fragments})

    for block in list(root):
        classes = _classes(block)
        style = _publisher_style(classes)
        if "yv-h" in classes:
            text = "".join(block.itertext()).strip()
            fragments = [{"type": "text", "text": text}] if text else []
            append_line(current_verse, {"type": "heading", "style": style or "s", "fragments": fragments})
            continue

        fragments: list[dict[str, Any]] = []
        for event in _iter_block_events(block):
            if event["kind"] == "verse":
                append_fragments(current_verse, style, fragments)
                fragments = []
                current_verse = event["verse"]
                ensure_verse(current_verse, event.get("verse_end"))
                continue
            if event["kind"] == "fragment":
                fragment = event["fragment"]
                if fragment["type"] == "footnote":
                    footnote_seq += 1
                    if not fragment.get("label"):
                        fragment["label"] = str(footnote_seq)
                fragments.append(fragment)

        append_fragments(current_verse, style, fragments)

    if not fills:
        raise ChapterHtmlParseError("chapter HTML produced no verses")

    for fill in fills.values():
        fill["search_text"] = _build_search_text(fill["lines"])
        if not fill["lines"]:
            raise ChapterHtmlParseError(f"verse {fill['verse']} has no lines")

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
        text = block.text
        if text.strip() or text:
            stripped = text.strip()
            if stripped:
                yield {"kind": "fragment", "fragment": {"type": "text", "text": stripped}}

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
            text = "".join(child.itertext()).strip()
            if text:
                yield {"kind": "fragment", "fragment": {"type": fragment_type, "text": text}}
        else:
            text = "".join(child.itertext()).strip()
            if text:
                style = _publisher_style(classes)
                fragment: dict[str, Any] = {"type": "text", "text": text}
                if style and style != "p":
                    fragment["style"] = style
                yield {"kind": "fragment", "fragment": fragment}

        if child.tail:
            stripped = child.tail.strip()
            if stripped:
                yield {"kind": "fragment", "fragment": {"type": "text", "text": stripped}}


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
            text_parts.append("".join(child.itertext()).strip())
            continue
        if "ref" in child_classes:
            refs.append({"usfm": child.get("usfm") or "", "text": "".join(child.itertext()).strip()})

    return {"type": "footnote", "kind": kind, "label": label, "text": "".join(text_parts).strip(), "refs": refs}


def _build_search_text(lines: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for line in lines:
        if line.get("type") == "heading":
            continue
        for fragment in line.get("fragments") or []:
            fragment_type = fragment.get("type")
            if fragment_type in {"text", "nd", "wj", "pn"}:
                parts.append(fragment.get("text") or "")
    return "".join(parts)
