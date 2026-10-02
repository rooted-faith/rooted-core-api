"""Tests for the import-daily-devotions command, driven through the public Click command."""

import copy
import csv
import json
import operator
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from click.testing import CliRunner

from portal.cli import import_daily_devotions
from portal.cli.main import cli
from portal.domain.devotion.entities import DailyLessonSchedule
from portal.domain.locale.entities import Locale
from portal.models import Devotion, DevotionDailyLessonSchedule, DevotionTranslation, SystemLocale

TODAY = date(2026, 10, 1)
LOCALE_SPECS = [("zh", "Hant", "TW"), ("zh", "Hans", "CN"), ("en", None, None)]
LOCALE_SUFFIXES = ["zh_hant_tw", "zh_hans_cn", "en"]


def make_locale(language: str, script: str | None, region: str | None) -> Locale:
    return Locale(id=uuid4(), language_code=language, script_code=script, region_code=region)


class StubQuery:
    def __init__(self, session: "StubSession", model) -> None:
        self._session = session
        self._model = model
        self._values: dict = {}
        self._conditions: list = []
        self._on_conflict_nothing = False

    def values(self, **values):
        self._values = values
        return self

    def where(self, condition):
        self._conditions.append(condition)
        return self

    def order_by(self, *_args):
        return self

    def on_conflict_do_update(self, **_kwargs):
        return self

    def on_conflict_do_nothing(self, **_kwargs):
        self._on_conflict_nothing = True
        return self

    def matches(self, row: dict) -> bool:
        for condition in self._conditions:
            if condition.operator in (operator.eq, operator.ge, operator.le) and not condition.operator(row[condition.left.key], condition.right.value):
                return False
        return True


class StubSelect(StubQuery):
    def __init__(self, session: "StubSession", columns: tuple) -> None:
        super().__init__(session, columns[0].class_)
        self._columns = columns

    async def fetch(self, as_model=None):
        if self._model is SystemLocale:
            return list(self._session.locales)
        rows = [{c.key: row[c.key] for c in self._columns} for row in self._session.schedules_rows() if self.matches(row)]
        rows.sort(key=lambda row: row["date"])
        return [as_model(**row) for row in rows] if as_model else rows

    async def fetchvals(self):
        return [row[self._columns[0].key] for row in self._session.translations if self.matches(row)]


class StubInsert(StubQuery):
    async def execute(self):
        return self._session.apply_insert(self._model, self._values, self._on_conflict_nothing)


class StubUpdate(StubQuery):
    async def execute(self) -> int:
        return self._session.apply_update(self._model, self._values, self._conditions)


class StubSession:
    """In-memory stand-in for the database session with commit and rollback semantics."""

    def __init__(self, locales: list[Locale], schedules: dict[date, UUID] | None = None, devotions: dict[UUID, dict] | None = None) -> None:
        self.locales = locales
        self.devotions: dict[UUID, dict] = devotions or {}
        self.translations: list[dict] = []
        self.schedules: dict[date, UUID] = schedules or {}
        self.fail_on: tuple[type, int] | None = None
        self.insert_counts: dict[type, int] = {}
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self._snapshot = self._state()

    def _state(self):
        return copy.deepcopy((self.devotions, self.translations, self.schedules))

    def schedules_rows(self) -> list[dict]:
        return [{"date": lesson_date, "devotion_id": devotion_id} for lesson_date, devotion_id in self.schedules.items()]

    def select(self, *columns) -> StubSelect:
        return StubSelect(self, columns)

    def insert(self, model) -> StubInsert:
        return StubInsert(self, model)

    def update(self, model) -> StubUpdate:
        return StubUpdate(self, model)

    def apply_insert(self, model, values: dict, on_conflict_nothing: bool):
        self.insert_counts[model] = self.insert_counts.get(model, 0) + 1
        if self.fail_on == (model, self.insert_counts[model]):
            raise RuntimeError(f"simulated {model.__name__} insert failure")
        if model is Devotion:
            self.devotions[values["id"]] = dict(values)
        elif model is DevotionTranslation:
            if not isinstance(values["reflect"], str):  # asyncpg JSONB binds need JSON text
                raise TypeError("invalid input for JSONB argument (expected str, got list)")
            self.translations.append({**values, "reflect": json.loads(values["reflect"])})
        elif model is DevotionDailyLessonSchedule:
            if values["date"] in self.schedules:
                return "INSERT 0 0"
            self.schedules[values["date"]] = values["devotion_id"]
        return "INSERT 0 1"

    def apply_update(self, model, values: dict, conditions: list) -> int:
        key = conditions[0].right.value
        if model is Devotion and key in self.devotions:
            self.devotions[key]["status"] = values["status"]
            return 1
        if model is DevotionDailyLessonSchedule and key in self.schedules:
            self.schedules[key] = values["devotion_id"]
            return 1
        return 0

    async def commit(self) -> None:
        self.commits += 1
        self._snapshot = self._state()

    async def rollback(self) -> None:
        self.rollbacks += 1
        self.devotions, self.translations, self.schedules = copy.deepcopy(self._snapshot)

    async def close(self) -> None:
        self.closed = True


class StubContainer:
    def __init__(self, session: StubSession) -> None:
        self._session = session

    def db_session(self) -> StubSession:
        return self._session


def csv_row(source_date: str, **overrides: str) -> dict[str, str]:
    row = {"date": source_date, "passage_start": "GEN.1.1", "passage_end": "GEN.1.3"}
    for suffix in LOCALE_SUFFIXES:
        row[f"reflect_{suffix}"] = f"first prompt {suffix}|second prompt {suffix}"
        row[f"apply_{suffix}"] = f"apply {suffix}"
        row[f"pray_{suffix}"] = f"pray {suffix}"
    row.update(overrides)
    return row


def write_csv(tmp_path: Path, rows: list[dict[str, str]], drop_columns: tuple[str, ...] = ()) -> Path:
    path = tmp_path / "devotions.csv"
    fieldnames = [name for name in rows[0] if name not in drop_columns]
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> StubSession:
    stub = StubSession([make_locale(*spec) for spec in LOCALE_SPECS])
    monkeypatch.setattr(import_daily_devotions, "Container", lambda: StubContainer(stub))
    monkeypatch.setattr(import_daily_devotions, "current_date", lambda: TODAY)
    return stub


def run(*args: str):
    return CliRunner().invoke(cli, ["import-daily-devotions", *args])


def test_import_preserves_source_date_offsets_from_explicit_start_date(tmp_path: Path, session: StubSession) -> None:
    path = write_csv(tmp_path, [csv_row("2026-03-01"), csv_row("2026-03-02"), csv_row("2026-03-05", passage_start="PSA.23.1", passage_end="PSA.23.6")])

    result = run("--csv-path", str(path), "--start-date", "2026-11-10")

    assert result.exit_code == 0, result.output
    assert sorted(session.schedules) == [date(2026, 11, 10), date(2026, 11, 11), date(2026, 11, 14)]
    assert "Effective start date: 2026-11-10" in result.output
    assert "Target range: 2026-11-10 to 2026-11-14" in result.output
    assert "Created 3 Daily lessons, replaced 0" in result.output
    assert session.commits == 1 and session.rollbacks == 0 and session.closed


def test_import_creates_ready_devotions_with_complete_parsed_translations(tmp_path: Path, session: StubSession) -> None:
    path = write_csv(tmp_path, [csv_row("2026-03-01", reflect_en=" one | two\nlines ")])

    result = run("--csv-path", str(path), "--start-date", "2026-10-02")

    assert result.exit_code == 0, result.output
    (devotion,) = session.devotions.values()
    assert devotion["status"] == "ready"
    assert (devotion["passage_start"], devotion["passage_end"]) == ("GEN.1.1", "GEN.1.3")
    assert session.schedules == {date(2026, 10, 2): devotion["id"]}
    assert {t["locale_id"] for t in session.translations} == {locale.id for locale in session.locales}
    english = next(t for t in session.translations if t["locale_id"] == session.locales[2].id)
    assert english["reflect"] == ["one", "two\nlines"]
    assert english["apply"] == "apply en" and english["pray"] == "pray en"


def test_import_defaults_start_date_to_host_current_date(tmp_path: Path, session: StubSession) -> None:
    path = write_csv(tmp_path, [csv_row("2025-01-01"), csv_row("2025-01-03")])

    result = run("--csv-path", str(path))

    assert result.exit_code == 0, result.output
    assert "Effective start date: 2026-10-01" in result.output
    assert sorted(session.schedules) == [date(2026, 10, 1), date(2026, 10, 3)]


def test_dry_run_reports_plan_without_writing(tmp_path: Path, session: StubSession) -> None:
    session.schedules = {date(2026, 11, 11): uuid4()}
    session._snapshot = session._state()
    path = write_csv(tmp_path, [csv_row("2026-03-01"), csv_row("2026-03-02")])

    result = run("--csv-path", str(path), "--start-date", "2026-11-10", "--dry-run", "--replace-schedule")

    assert result.exit_code == 0, result.output
    assert "Effective start date: 2026-11-10" in result.output
    assert "Target range: 2026-11-10 to 2026-11-11" in result.output
    assert "Schedule conflicts: 1 (2026-11-11)" in result.output
    assert "Would create 1 Daily lessons, replace 1" in result.output
    assert session.devotions == {} and session.translations == [] and session.commits == 0
    assert session.insert_counts == {}


def test_schedule_conflict_aborts_batch_without_writes(tmp_path: Path, session: StubSession) -> None:
    existing = uuid4()
    session.schedules = {date(2026, 11, 11): existing}
    session._snapshot = session._state()
    path = write_csv(tmp_path, [csv_row("2026-03-01"), csv_row("2026-03-02")])

    result = run("--csv-path", str(path), "--start-date", "2026-11-10")

    assert result.exit_code != 0
    assert "2026-11-11" in result.output and "--replace-schedule" in result.output
    assert session.insert_counts == {} and session.commits == 0
    assert session.schedules == {date(2026, 11, 11): existing}


def test_replace_schedule_updates_only_conflicts_and_keeps_replaced_devotion(tmp_path: Path, session: StubSession) -> None:
    replaced = uuid4()
    untouched = uuid4()
    session.devotions = {replaced: {"id": replaced, "status": "ready"}}
    session.schedules = {date(2026, 11, 11): replaced, date(2026, 12, 25): untouched}
    session._snapshot = session._state()
    path = write_csv(tmp_path, [csv_row("2026-03-01"), csv_row("2026-03-02")])

    result = run("--csv-path", str(path), "--start-date", "2026-11-10", "--replace-schedule")

    assert result.exit_code == 0, result.output
    assert "Created 1 Daily lessons, replaced 1" in result.output
    assert replaced in session.devotions
    assert session.schedules[date(2026, 11, 11)] != replaced
    assert session.schedules[date(2026, 12, 25)] == untouched
    assert len(session.devotions) == 3  # replaced + two new
    assert session.commits == 1


def test_persistence_failure_rolls_back_whole_batch_with_row_context(tmp_path: Path, session: StubSession) -> None:
    session.fail_on = (DevotionDailyLessonSchedule, 2)
    path = write_csv(tmp_path, [csv_row("2026-03-01"), csv_row("2026-03-02"), csv_row("2026-03-03")])

    result = run("--csv-path", str(path), "--start-date", "2026-11-10")

    assert result.exit_code != 0
    assert "rolled back" in result.output and "row 2" in result.output and "2026-11-11" in result.output
    assert session.rollbacks == 1 and session.commits == 0
    assert session.devotions == {} and session.translations == [] and session.schedules == {}


@pytest.mark.parametrize(
    ("rows", "drop_columns", "message"),
    [
        ([csv_row("2026-3-1")], (), "malformed date"),
        ([csv_row("2026-02-30")], (), "malformed date"),
        ([csv_row("2026-03-01"), csv_row("2026-03-01")], (), "duplicate source date"),
        ([csv_row("2026-03-02"), csv_row("2026-03-01")], (), "is not after"),
        ([csv_row("2026-03-01", reflect_en="one||two")], (), "reflect_en"),
        ([csv_row("2026-03-01", reflect_en="one|  ")], (), "reflect_en"),
        ([csv_row("2026-03-01", reflect_zh_hans_cn="")], (), "reflect_zh_hans_cn"),
        ([csv_row("2026-03-01", apply_en="  ")], (), "apply_en is blank"),
        ([csv_row("2026-03-01", pray_zh_hant_tw="")], (), "pray_zh_hant_tw is blank"),
        ([csv_row("2026-03-01")], ("pray_en",), "Missing required column(s): pray_en"),
        ([csv_row("2026-03-01", passage_start="Genesis 1:1")], (), "invalid passage_start"),
        ([csv_row("2026-03-01", passage_end="GEN.1")], (), "invalid passage_end"),
        ([csv_row("2026-03-01", passage_end="EXO.1.1")], (), "spans books"),
        ([csv_row("2026-03-01", passage_start="GEN.2.1", passage_end="GEN.1.9")], (), "descending"),
        ([csv_row("2026-03-01", passage_start="GEN.1.5", passage_end="GEN.1.2")], (), "descending"),
    ],
)
def test_invalid_csv_is_rejected_before_any_write(tmp_path: Path, session: StubSession, rows, drop_columns, message: str) -> None:
    path = write_csv(tmp_path, rows, drop_columns)

    result = run("--csv-path", str(path), "--start-date", "2026-11-10")

    assert result.exit_code != 0
    assert message in result.output
    assert session.insert_counts == {} and session.commits == 0


def test_newly_active_locale_without_csv_columns_blocks_import(tmp_path: Path, session: StubSession) -> None:
    session.locales.append(make_locale("fr", None, "FR"))
    path = write_csv(tmp_path, [csv_row("2026-03-01")])

    result = run("--csv-path", str(path), "--start-date", "2026-11-10")

    assert result.exit_code != 0
    assert "reflect_fr_fr" in result.output and "apply_fr_fr" in result.output and "pray_fr_fr" in result.output
    assert session.insert_counts == {}


def test_target_dates_before_host_current_date_are_rejected(tmp_path: Path, session: StubSession) -> None:
    path = write_csv(tmp_path, [csv_row("2026-03-01"), csv_row("2026-03-02")])

    result = run("--csv-path", str(path), "--start-date", "2026-09-30")

    assert result.exit_code != 0
    assert "Row 1" in result.output and "2026-09-30" in result.output and "before today" in result.output
    assert session.insert_counts == {} and session.commits == 0


def test_missing_csv_file_is_reported(tmp_path: Path, session: StubSession) -> None:
    result = run("--csv-path", str(tmp_path / "missing.csv"))

    assert result.exit_code != 0
    assert "CSV file not found" in result.output
    assert session.insert_counts == {}


def test_dry_run_with_conflicts_reports_them_but_fails_without_replace_flag(tmp_path: Path, session: StubSession) -> None:
    session.schedules = {date(2026, 11, 11): uuid4()}
    session._snapshot = session._state()
    path = write_csv(tmp_path, [csv_row("2026-03-01"), csv_row("2026-03-02")])

    result = run("--csv-path", str(path), "--start-date", "2026-11-10", "--dry-run")

    assert result.exit_code != 0
    assert "Schedule conflicts: 1 (2026-11-11)" in result.output
    assert session.insert_counts == {} and session.commits == 0


def test_duplicate_locale_column_is_rejected(tmp_path: Path, session: StubSession) -> None:
    path = write_csv(tmp_path, [csv_row("2026-03-01")])
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    lines[0] += ",reflect_en"
    lines[1] += ',"extra"'
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")

    result = run("--csv-path", str(path), "--start-date", "2026-11-10")

    assert result.exit_code != 0
    assert "Duplicate column(s): reflect_en" in result.output
    assert session.insert_counts == {}
