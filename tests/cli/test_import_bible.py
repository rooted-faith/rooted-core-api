"""Tests for importing a Bible catalog index without downloaded passages."""

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from portal.cli import import_bible
from portal.models import BibleBook, BibleVerse, BibleVersion


class StubInsert:
    def __init__(self, session: "StubSession", model) -> None:
        self._session = session
        self._model = model
        self._values: dict = {}

    def values(self, **values):
        self._values = values
        self._session.inserts.append((self._model, values))
        return self

    def on_conflict_do_update(self, **kwargs):
        self._session.updates.append((self._model, kwargs["set_"]))
        return self

    async def execute(self) -> None:
        return None


class StubSelect:
    def __init__(self, value: UUID) -> None:
        self._value = value

    def where(self, _condition):
        return self

    async def fetchval(self) -> UUID:
        return self._value


class StubSession:
    def __init__(self, values: list[UUID]) -> None:
        self._values = iter(values)
        self.inserts: list[tuple[type, dict]] = []
        self.updates: list[tuple[type, dict]] = []

    def insert(self, model) -> StubInsert:
        return StubInsert(self, model)

    def select(self, _column) -> StubSelect:
        return StubSelect(next(self._values))

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        return None


class StubContainer:
    def __init__(self, session: StubSession) -> None:
        self._session = session

    def db_session(self) -> StubSession:
        return self._session


def _write_bible_fixture(tmp_path: Path, *, bible_id: str, bible_meta: dict, books: list[dict] | None = None) -> None:
    meta_dir = tmp_path / bible_id / "meta"
    meta_dir.mkdir(parents=True)
    (meta_dir / "bible.json").write_text(json.dumps(bible_meta), encoding="utf-8")
    (meta_dir / "index.json").write_text(
        json.dumps(
            {
                "books": books
                or [
                    {
                        "id": "GEN",
                        "title": "Genesis",
                        "chapters": [{"id": "1", "verses": [{"id": "1", "passage_id": "GEN.1.1"}, {"id": "2", "passage_id": "GEN.1.2"}]}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_import_bible_loads_index_as_empty_verse_shells_without_passages_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bible_id = "1392"
    version_id = uuid4()
    genesis_id = uuid4()
    session = StubSession(values=[version_id, genesis_id])
    _write_bible_fixture(
        tmp_path,
        bible_id=bible_id,
        bible_meta={"id": bible_id, "abbreviation": "CCBT", "title": "Chinese Contemporary Bible", "localized_title": "當代譯本", "language_tag": "zh-Hant-TW"},
    )
    monkeypatch.setattr(import_bible, "Container", lambda: StubContainer(session))

    await import_bible.import_bible_data(bible_id=bible_id, data_dir=str(tmp_path))

    assert [model for model, _ in session.inserts] == [BibleVersion, BibleBook, BibleVerse, BibleVerse]
    assert [values for model, values in session.inserts if model is BibleVerse] == [
        {"book_id": genesis_id, "chapter": 1, "verse": 1, "verse_end": None, "passage_id": "GEN.1.1", "lines": None, "search_text": None},
        {"book_id": genesis_id, "chapter": 1, "verse": 2, "verse_end": None, "passage_id": "GEN.1.2", "lines": None, "search_text": None},
    ]
    assert [values for model, values in session.updates if model is BibleVerse] == [
        {"chapter": 1, "verse": 1, "verse_end": None, "lines": None, "search_text": None},
        {"chapter": 1, "verse": 2, "verse_end": None, "lines": None, "search_text": None},
    ]


@pytest.mark.asyncio
async def test_import_bible_retains_publisher_name_from_source_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bible_id = "111"
    version_id = uuid4()
    genesis_id = uuid4()
    session = StubSession(values=[version_id, genesis_id])
    _write_bible_fixture(
        tmp_path,
        bible_id=bible_id,
        bible_meta={
            "id": bible_id,
            "abbreviation": "NIV11",
            "title": "New International Version 2011",
            "localized_title": "New International Version",
            "language_tag": "en",
            "publisher_name": "Biblica, Inc.",
            "publisher_url": "https://www.biblica.com/yv-learn-more/",
            "copyright": "Copyright © Biblica, Inc.",
        },
    )
    monkeypatch.setattr(import_bible, "Container", lambda: StubContainer(session))

    await import_bible.import_bible_data(bible_id=bible_id, data_dir=str(tmp_path))

    version_insert = next(values for model, values in session.inserts if model is BibleVersion)
    version_update = next(values for model, values in session.updates if model is BibleVersion)
    assert version_insert["publisher_name"] == "Biblica, Inc."
    assert version_update["publisher_name"] == "Biblica, Inc."
    assert version_insert["youversion_bible_id"] == bible_id
    assert version_insert["publisher_url"] == "https://www.biblica.com/yv-learn-more/"
    assert version_insert["copyright"] == "Copyright © Biblica, Inc."


@pytest.mark.asyncio
async def test_import_bible_stores_null_publisher_name_when_source_missing_or_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bible_id = "1392"
    version_id = uuid4()
    genesis_id = uuid4()
    session = StubSession(values=[version_id, genesis_id])
    _write_bible_fixture(
        tmp_path,
        bible_id=bible_id,
        bible_meta={
            "id": bible_id,
            "abbreviation": "CCBT",
            "title": "Chinese Contemporary Bible",
            "localized_title": "當代譯本",
            "language_tag": "zh-Hant-TW",
            "publisher_name": "   ",
        },
    )
    monkeypatch.setattr(import_bible, "Container", lambda: StubContainer(session))

    await import_bible.import_bible_data(bible_id=bible_id, data_dir=str(tmp_path))

    version_insert = next(values for model, values in session.inserts if model is BibleVersion)
    version_update = next(values for model, values in session.updates if model is BibleVersion)
    assert version_insert["publisher_name"] is None
    assert "publisher_name" not in version_update


@pytest.mark.asyncio
async def test_import_bible_upsert_omits_publisher_name_when_source_blank(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-import without a source publisher name must not clear a stored name via conflict update."""
    bible_id = "111"
    version_id = uuid4()
    genesis_id = uuid4()
    session = StubSession(values=[version_id, genesis_id])
    _write_bible_fixture(
        tmp_path,
        bible_id=bible_id,
        bible_meta={
            "id": bible_id,
            "abbreviation": "NIV11",
            "title": "New International Version 2011",
            "localized_title": "New International Version",
            "language_tag": "en",
        },
    )
    monkeypatch.setattr(import_bible, "Container", lambda: StubContainer(session))

    await import_bible.import_bible_data(bible_id=bible_id, data_dir=str(tmp_path))

    version_update = next(values for model, values in session.updates if model is BibleVersion)
    assert "publisher_name" not in version_update
