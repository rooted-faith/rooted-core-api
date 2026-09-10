"""
dump-bible writes YouVersion metadata and index through the YouVersion port.
"""

import json
import sqlite3
from pathlib import Path

import pytest

from portal.cli.bible import dump_bible


class StubYouVersion:
    def __init__(self):
        self.metadata_calls: list[str] = []
        self.index_calls: list[str] = []
        self.chapter_calls: list[tuple[str, str]] = []
        self.metadata = {"id": 1392, "abbreviation": "CCBT", "title": "Chinese Contemporary Bible"}
        self.index = {
            "books": [
                {
                    "id": "GEN",
                    "title": "Genesis",
                    "chapters": [{"id": "1", "passage_id": "GEN.1", "title": "1", "verses": [{"id": "1", "passage_id": "GEN.1.1", "title": "1"}]}],
                }
            ]
        }
        self.chapter = {"content": "<div class=\"p\">In the beginning</div>"}

    async def get_bible_metadata(self, bible_id: str):
        self.metadata_calls.append(bible_id)
        return self.metadata

    async def get_bible_index(self, bible_id: str):
        self.index_calls.append(bible_id)
        return self.index

    async def get_chapter_passage(self, bible_id: str, chapter_usfm: str):
        self.chapter_calls.append((bible_id, chapter_usfm))
        return self.chapter


@pytest.mark.asyncio
async def test_dump_bible_meta_only_writes_metadata_and_index(tmp_path: Path):
    stub = StubYouVersion()

    await dump_bible(
        bible_id="1392",
        out_dir=str(tmp_path),
        daily_limit=5000,
        sleep_sec=0.0,
        timeout_sec=30.0,
        include_headings=False,
        include_notes=False,
        format_="text",
        meta_only=True,
        youversion=stub,
    )

    bible_path = tmp_path / "1392" / "meta" / "bible.json"
    index_path = tmp_path / "1392" / "meta" / "index.json"
    assert json.loads(bible_path.read_text(encoding="utf-8"))["abbreviation"] == "CCBT"
    assert json.loads(index_path.read_text(encoding="utf-8"))["books"][0]["id"] == "GEN"
    assert stub.metadata_calls == ["1392"]
    assert stub.index_calls == ["1392"]
    assert stub.chapter_calls == []


@pytest.mark.asyncio
async def test_dump_passages_fetches_each_chapter_through_the_port(tmp_path: Path):
    stub = StubYouVersion()

    await dump_bible(
        bible_id="1392",
        out_dir=str(tmp_path),
        daily_limit=5000,
        sleep_sec=0.0,
        timeout_sec=30.0,
        include_headings=False,
        include_notes=False,
        format_="text",
        meta_only=False,
        youversion=stub,
    )

    assert stub.chapter_calls == [("1392", "GEN.1")]
    conn = sqlite3.connect(tmp_path / "1392" / "passages.db")
    row = conn.execute("SELECT passage_id, data FROM verses").fetchone()
    conn.close()
    assert row[0] == "GEN.1"
    assert json.loads(row[1]) == stub.chapter


@pytest.mark.asyncio
async def test_dump_bible_requires_yvp_app_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("portal.cli.bible.settings.YVP_APP_KEY", "")

    with pytest.raises(SystemExit, match="YVP_APP_KEY is required"):
        await dump_bible(
            bible_id="1392",
            out_dir=str(tmp_path),
            daily_limit=5000,
            sleep_sec=0.0,
            timeout_sec=30.0,
            include_headings=False,
            include_notes=False,
            format_="text",
            meta_only=True,
        )
