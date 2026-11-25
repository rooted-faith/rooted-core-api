"""Tests for the legacy Bible chapter refill commands, driven through the public Click commands."""

import pytest
from click.testing import CliRunner
from dependency_injector import providers

from portal.cli import refill_bible
from portal.cli.main import cli
from portal.container import Container
from portal.domain.bible.entities import BibleChapterAddress
from portal.infrastructure.youversion.youversion_http_client import YouVersionHttpError
from tests.fixtures.bible_chapter_fill import StubBibleRepository, StubYouVersion, legacy_chapter, load_passage


class CliRepository(StubBibleRepository):
    """One legacy book with several chapters and commit / rollback semantics."""

    def __init__(self, chapters: dict[int, list[int]]) -> None:
        self.committed = {number: legacy_chapter(book_code="GEN", chapter=number, verses=verses) for number, verses in chapters.items()}
        super().__init__(next(iter(self.committed.values())))
        self.pending: dict = {}
        self.fail_after_write = False
        self.list_calls: list = []

    async def fetch_chapter(self, book_id, chapter):
        self._chapter = self.pending.get(chapter) or self.committed.get(chapter)
        return await super().fetch_chapter(book_id, chapter) if self._chapter else None

    async def write_chapter_fill(self, book_id, chapter, fills):
        self._chapter = self.committed[chapter]
        await super().write_chapter_fill(book_id, chapter, fills)
        self.pending[chapter] = self._chapter
        if self.fail_after_write:
            raise RuntimeError("simulated database failure")

    async def find_book_id(self, bible_version_id, book_code):
        return self.committed[min(self.committed)].book_id if book_code == "GEN" else None

    async def find_active_version_id(self, youversion_bible_id):
        return self.version_id if youversion_bible_id == "1392" else None

    async def list_legacy_chapters(self, bible_version_id, book_code=None):
        self.list_calls.append((bible_version_id, book_code))
        return [BibleChapterAddress(book_code="GEN", chapter=number) for number in self.committed]


class StubSession:
    def __init__(self, repository: CliRepository) -> None:
        self._repository = repository
        self.closed = False

    async def commit(self) -> None:
        self._repository.committed.update(self._repository.pending)
        self._repository.pending.clear()

    async def rollback(self) -> None:
        self._repository.pending.clear()

    async def close(self) -> None:
        self.closed = True


GEN2 = {"1392:GEN.2": load_passage("gen2")}


@pytest.fixture
def repository() -> CliRepository:
    return CliRepository({2: list(range(1, 26)), 3: [1]})


@pytest.fixture
def run(monkeypatch, repository):
    def _run(*args: str, youversion: StubYouVersion | None = None):
        container = Container()
        session = StubSession(repository)
        container.app.bible_repository.override(providers.Object(repository))
        container.app.youversion_client.override(providers.Object(youversion or StubYouVersion(passages=GEN2)))
        container.db_session.override(providers.Object(session))
        monkeypatch.setattr(refill_bible, "Container", lambda: container)
        result = CliRunner().invoke(cli, list(args))
        assert session.closed or result.exit_code == 2
        return result

    return _run


def _upgraded(repository: CliRepository, chapter: int) -> bool:
    return all("continues" in line for verse in repository.committed[chapter].verses for line in verse.lines)


def test_refill_upgrades_only_the_selected_chapter(run, repository):
    result = run("refill-bible-chapters", "--bible-id", "1392", "--chapter", "GEN.2")

    assert result.exit_code == 0, result.output
    assert "GEN.2: upgraded" in result.output
    assert _upgraded(repository, 2)
    assert not _upgraded(repository, 3)


def test_refill_is_safe_to_repeat(run):
    run("refill-bible-chapters", "--bible-id", "1392", "--chapter", "GEN.2")
    youversion = StubYouVersion(passages=GEN2)

    result = run("refill-bible-chapters", "--bible-id", "1392", "--chapter", "GEN.2", youversion=youversion)

    assert result.exit_code == 0
    assert "GEN.2: already_upgraded" in result.output
    assert youversion.calls == []


def test_one_failed_chapter_keeps_its_old_body_and_does_not_undo_the_others(run, repository):
    result = run("refill-bible-chapters", "--bible-id", "1392", "--chapter", "GEN.3", "--chapter", "GEN.2")

    assert result.exit_code == 1
    assert "GEN.3: failed" in result.output
    assert "GEN.2: upgraded" in result.output
    assert not _upgraded(repository, 3)
    assert _upgraded(repository, 2)


def test_write_failure_rolls_the_whole_chapter_back(run, repository):
    repository.fail_after_write = True

    result = run("refill-bible-chapters", "--bible-id", "1392", "--chapter", "GEN.2")

    assert result.exit_code == 1
    assert repository.pending == {}
    assert not _upgraded(repository, 2)


def test_upstream_failure_reports_the_reason(run):
    youversion = StubYouVersion(error=YouVersionHttpError(429, "/passages/GEN.2"))

    result = run("refill-bible-chapters", "--bible-id", "1392", "--chapter", "GEN.2", youversion=youversion)

    assert result.exit_code == 1
    assert "YouVersion chapter fetch failed" in result.output
    assert "429" in result.output


@pytest.mark.parametrize("chapter", ["GEN", "GEN.2.1", "GEN.x", "gen.2", "GEN.0", "GEN.²"])
def test_malformed_chapter_is_refused_before_anything_runs(run, repository, chapter):
    youversion = StubYouVersion(passages=GEN2)

    result = run("refill-bible-chapters", "--bible-id", "1392", "--chapter", "GEN.2", "--chapter", chapter, youversion=youversion)

    assert result.exit_code == 2
    assert youversion.calls == []
    assert not _upgraded(repository, 2)


def test_refill_requires_an_explicit_chapter(run):
    result = run("refill-bible-chapters", "--bible-id", "1392")

    assert result.exit_code == 2
    assert "--chapter" in result.output


def test_list_prints_selectable_chapters_without_fetching(run, repository):
    youversion = StubYouVersion(passages=GEN2)

    result = run("list-legacy-bible-chapters", "--bible-id", "1392", "--book", "GEN", youversion=youversion)

    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == ["GEN.2", "GEN.3"]
    assert repository.list_calls == [(repository.version_id, "GEN")]
    assert youversion.calls == []


def test_list_rejects_an_unknown_version(run):
    result = run("list-legacy-bible-chapters", "--bible-id", "9999")

    assert result.exit_code == 1
    assert "9999" in result.output
