"""Tests for metadata-only Bible publisher-name backfill."""

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from click.testing import CliRunner

from portal.cli import backfill_bible_publisher_names as backfill_module
from portal.cli.main import cli
from portal.models import BibleVersion


def _clause_literal(condition) -> str | None:
    right = getattr(condition, "right", None)
    if right is None:
        return None
    if hasattr(right, "value"):
        return right.value
    return getattr(right, "effective_value", None)


class StubUpdate:
    def __init__(self, session: "StubSession", model) -> None:
        self._session = session
        self._model = model
        self._values: dict = {}
        self._youversion_bible_id: str | None = None

    def values(self, **values):
        self._values = values
        return self

    def where(self, condition):
        self._youversion_bible_id = _clause_literal(condition)
        return self

    async def execute(self):
        self._session.updates.append((self._model, self._values, self._youversion_bible_id))
        return None


class StubSelect:
    def __init__(self, session: "StubSession", column) -> None:
        self._session = session
        self._column = column
        self._youversion_bible_id: str | None = None

    def where(self, condition):
        self._youversion_bible_id = _clause_literal(condition)
        return self

    async def fetchval(self):
        if self._youversion_bible_id is None:
            return None
        return self._session.existing_versions.get(self._youversion_bible_id)


class StubSession:
    def __init__(self, existing_versions: dict[str, UUID] | None = None, publisher_names: dict[str, str | None] | None = None) -> None:
        self.existing_versions = existing_versions or {}
        self.publisher_names = publisher_names or {}
        self.updates: list[tuple[type, dict, str | None]] = []
        self.inserts: list = []

    def update(self, model) -> StubUpdate:
        return StubUpdate(self, model)

    def select(self, *columns) -> StubSelect:
        return StubSelect(self, columns[0] if columns else None)

    def insert(self, model):
        raise AssertionError("metadata-only backfill must not insert rows")

    async def commit(self) -> None:
        for model, values, youversion_bible_id in self.updates:
            if model is BibleVersion and youversion_bible_id is not None and "publisher_name" in values:
                self.publisher_names[youversion_bible_id] = values["publisher_name"]

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        return None


class StubContainer:
    def __init__(self, session: StubSession) -> None:
        self._session = session

    def db_session(self) -> StubSession:
        return self._session


def _write_meta(tmp_path: Path, bible_id: str, publisher_name: str | None, *, omit_key: bool = False) -> None:
    meta_dir = tmp_path / bible_id / "meta"
    meta_dir.mkdir(parents=True)
    payload = {
        "id": int(bible_id) if bible_id.isdigit() else bible_id,
        "abbreviation": "TEST",
        "title": "Test Bible",
        "localized_title": "Test Bible",
        "language_tag": "en",
        "copyright": "Do not use as publisher",
        "publisher_url": "https://example.test",
    }
    if not omit_key:
        payload["publisher_name"] = publisher_name
    (meta_dir / "bible.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.asyncio
async def test_backfill_sets_publisher_name_for_matching_youversion_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    version_id = uuid4()
    session = StubSession(existing_versions={"111": version_id}, publisher_names={"111": None})
    _write_meta(tmp_path, "111", "Biblica, Inc.")
    monkeypatch.setattr(backfill_module, "Container", lambda: StubContainer(session))

    await backfill_module.backfill_bible_publisher_names(data_dir=str(tmp_path), bible_id="111")

    assert session.updates == [(BibleVersion, {"publisher_name": "Biblica, Inc."}, "111")]
    assert session.publisher_names["111"] == "Biblica, Inc."
    assert session.inserts == []


@pytest.mark.asyncio
async def test_backfill_skips_missing_or_empty_source_without_erasing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    version_id = uuid4()
    session = StubSession(existing_versions={"113": version_id, "1392": uuid4()}, publisher_names={"113": "Already Kept", "1392": None})
    _write_meta(tmp_path, "113", "   ")
    _write_meta(tmp_path, "1392", None, omit_key=True)
    monkeypatch.setattr(backfill_module, "Container", lambda: StubContainer(session))

    await backfill_module.backfill_bible_publisher_names(data_dir=str(tmp_path))

    assert session.updates == []
    assert session.publisher_names["113"] == "Already Kept"
    assert session.publisher_names["1392"] is None


@pytest.mark.asyncio
async def test_backfill_matches_only_the_named_youversion_bible_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = StubSession(existing_versions={"111": uuid4(), "36": uuid4()}, publisher_names={"111": None, "36": None})
    _write_meta(tmp_path, "111", "Biblica, Inc.")
    _write_meta(tmp_path, "36", "Should Not Apply When Filtered")
    monkeypatch.setattr(backfill_module, "Container", lambda: StubContainer(session))

    await backfill_module.backfill_bible_publisher_names(data_dir=str(tmp_path), bible_id="111")

    assert session.updates == [(BibleVersion, {"publisher_name": "Biblica, Inc."}, "111")]
    assert session.publisher_names["36"] is None


@pytest.mark.asyncio
async def test_backfill_repeat_run_is_stable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = StubSession(existing_versions={"111": uuid4()}, publisher_names={"111": None})
    _write_meta(tmp_path, "111", "Biblica, Inc.")
    monkeypatch.setattr(backfill_module, "Container", lambda: StubContainer(session))

    await backfill_module.backfill_bible_publisher_names(data_dir=str(tmp_path), bible_id="111")
    await backfill_module.backfill_bible_publisher_names(data_dir=str(tmp_path), bible_id="111")

    assert [values for _, values, _ in session.updates] == [{"publisher_name": "Biblica, Inc."}, {"publisher_name": "Biblica, Inc."}]
    assert session.publisher_names["111"] == "Biblica, Inc."


def test_backfill_cli_invokes_metadata_only_entry_point(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = StubSession(existing_versions={"111": uuid4()}, publisher_names={"111": None})
    _write_meta(tmp_path, "111", "Biblica, Inc.")
    monkeypatch.setattr(backfill_module, "Container", lambda: StubContainer(session))

    result = CliRunner().invoke(cli, ["backfill-bible-publisher-names", "--data-dir", str(tmp_path), "--bible-id", "111"])

    assert result.exit_code == 0, result.output
    assert "publisher_name='Biblica, Inc.'" in result.output
    assert session.updates == [(BibleVersion, {"publisher_name": "Biblica, Inc."}, "111")]
