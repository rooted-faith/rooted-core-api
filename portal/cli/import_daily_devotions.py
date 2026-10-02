"""
Import the rebased daily devotion CSV into Devotions, translations, and Daily lesson schedules.
"""

import asyncio
import csv
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from uuid import uuid4

import click

from portal.container import Container
from portal.domain.devotion.constants import DevotionStatus
from portal.domain.locale.entities import Locale
from portal.infrastructure.persistence.repositories.devotion.devotion_repository import DevotionRepository
from portal.libs.logger import logger

DEFAULT_CSV_PATH = Path(__file__).resolve().parents[2] / "docs" / "daily_devotion.csv"

_SOURCE_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PASSAGE_ID_PATTERN = re.compile(r"^([A-Z0-9]{3})\.(\d+)\.(\d+)$")
_AUTHORED_FIELDS = ("reflect", "apply", "pray")


class ImportPlanError(click.ClickException):
    """Raised when the CSV cannot become a valid import plan."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("Import plan is invalid:\n" + "\n".join(f"  - {problem}" for problem in problems))


@dataclass(frozen=True)
class PlannedLesson:
    row_number: int
    source_date: date
    target_date: date
    passage_start: str
    passage_end: str
    translations: dict[str, tuple[list[str], str, str]]  # locale code -> (reflect, apply, pray)


def current_date() -> date:
    """Host local calendar date; the CLI is content-operations, not device-date based."""
    return date.today()


def locale_column_suffix(locale_code: str) -> str:
    return locale_code.lower().replace("-", "_")


def required_columns(locales: list[Locale]) -> list[str]:
    columns = ["date", "passage_start", "passage_end"]
    for locale in locales:
        columns.extend(f"{field}_{locale_column_suffix(locale.code)}" for field in _AUTHORED_FIELDS)
    return columns


def _parse_source_date(raw: str) -> date | None:
    if not _SOURCE_DATE_PATTERN.match(raw):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _parse_passage(raw: str) -> tuple[str, int, int] | None:
    match = _PASSAGE_ID_PATTERN.match(raw)
    if match is None:
        return None
    return match.group(1), int(match.group(2)), int(match.group(3))


def _parse_reflect(raw: str) -> list[str] | None:
    prompts = [segment.strip() for segment in raw.split("|")]
    if any(not prompt for prompt in prompts):
        return None
    return prompts


def read_csv_rows(csv_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with open(csv_path, encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            return list(reader.fieldnames or []), list(reader)
    except FileNotFoundError:
        raise click.ClickException(f"CSV file not found: {csv_path}") from None
    except UnicodeDecodeError as error:
        raise click.ClickException(f"CSV file is not valid UTF-8: {csv_path} ({error})") from None


def plan_lessons(csv_path: Path, locales: list[Locale], start_date: date, today: date) -> list[PlannedLesson]:
    """Validate the whole CSV and map source dates onto target Daily lesson dates."""
    if not locales:
        raise click.ClickException("No active System Locales; refusing to import Devotions without a locale catalog")

    fieldnames, rows = read_csv_rows(csv_path)
    missing_columns = [column for column in required_columns(locales) if column not in fieldnames]
    if missing_columns:
        raise ImportPlanError([f"Missing required column(s): {', '.join(missing_columns)}"])
    duplicated_columns = sorted({column for column in required_columns(locales) if fieldnames.count(column) > 1})
    if duplicated_columns:
        raise ImportPlanError([f"Duplicate column(s): {', '.join(duplicated_columns)}"])
    if not rows:
        raise ImportPlanError(["CSV has no data rows"])

    problems: list[str] = []
    planned: list[PlannedLesson] = []
    first_source_date: date | None = None
    previous_source_date: date | None = None
    seen_source_dates: set[date] = set()

    for index, row in enumerate(rows, start=1):
        label = f"Row {index}"
        raw_date = (row.get("date") or "").strip()
        source_date = _parse_source_date(raw_date)
        if source_date is None:
            problems.append(f"{label}: malformed date {raw_date!r} (expected YYYY-MM-DD)")
        elif source_date in seen_source_dates:
            problems.append(f"{label}: duplicate source date {source_date}")
        elif previous_source_date is not None and source_date < previous_source_date:
            problems.append(f"{label}: source date {source_date} is not after {previous_source_date}")
        if source_date is not None:
            seen_source_dates.add(source_date)
            if first_source_date is None:
                first_source_date = source_date
            previous_source_date = source_date if previous_source_date is None else max(previous_source_date, source_date)

        raw_start = (row.get("passage_start") or "").strip()
        raw_end = (row.get("passage_end") or "").strip()
        start = _parse_passage(raw_start)
        end = _parse_passage(raw_end)
        if start is None:
            problems.append(f"{label}: invalid passage_start {raw_start!r} (expected BOOK.chapter.verse, e.g. GEN.1.1)")
        if end is None:
            problems.append(f"{label}: invalid passage_end {raw_end!r} (expected BOOK.chapter.verse, e.g. GEN.1.1)")
        if start is not None and end is not None:
            if start[0] != end[0]:
                problems.append(f"{label}: passage range spans books ({raw_start} to {raw_end})")
            elif start[1:] > end[1:]:
                problems.append(f"{label}: passage range is descending ({raw_start} to {raw_end})")

        translations: dict[str, tuple[list[str], str, str]] = {}
        for locale in locales:
            suffix = locale_column_suffix(locale.code)
            raw_reflect = row.get(f"reflect_{suffix}") or ""
            apply = (row.get(f"apply_{suffix}") or "").strip()
            pray = (row.get(f"pray_{suffix}") or "").strip()
            reflect = _parse_reflect(raw_reflect) if raw_reflect.strip() else None
            if reflect is None:
                problems.append(f"{label}: reflect_{suffix} is blank or has an empty prompt segment")
            if not apply:
                problems.append(f"{label}: apply_{suffix} is blank")
            if not pray:
                problems.append(f"{label}: pray_{suffix} is blank")
            if reflect is not None and apply and pray:
                translations[locale.code] = (reflect, apply, pray)

        if source_date is not None and start is not None and end is not None:
            planned.append(
                PlannedLesson(
                    row_number=index,
                    source_date=source_date,
                    target_date=source_date,  # rebased below once the first source date is known
                    passage_start=raw_start,
                    passage_end=raw_end,
                    translations=translations,
                )
            )

    if problems:
        raise ImportPlanError(problems)

    assert first_source_date is not None
    lessons = [
        PlannedLesson(
            row_number=lesson.row_number,
            source_date=lesson.source_date,
            target_date=start_date + (lesson.source_date - first_source_date),
            passage_start=lesson.passage_start,
            passage_end=lesson.passage_end,
            translations=lesson.translations,
        )
        for lesson in planned
    ]
    past = [lesson for lesson in lessons if lesson.target_date < today]
    if past:
        raise ImportPlanError([f"Row {lesson.row_number}: target Daily lesson date {lesson.target_date} is before today ({today})" for lesson in past])
    return lessons


async def import_daily_devotions(csv_path: Path | None = None, start_date: date | None = None, dry_run: bool = False, replace_schedule: bool = False) -> None:
    """
    Create ready Devotions, complete translations, and Daily lesson schedules from the CSV.

    :param csv_path: Source CSV (default: docs/daily_devotion.csv)
    :param start_date: Date for the first CSV row (default: host current date)
    :param dry_run: Validate and report only; never write
    :param replace_schedule: Update conflicting Daily lesson schedules instead of aborting
    """
    csv_path = csv_path or DEFAULT_CSV_PATH
    today = current_date()
    effective_start = start_date or today
    click.echo(f"Effective start date: {effective_start}")

    container = Container()
    session = container.db_session()
    try:
        repository = DevotionRepository(session)
        locales = await repository.list_active_locales()
        lessons = plan_lessons(csv_path, locales, effective_start, today)

        first_date, last_date = lessons[0].target_date, lessons[-1].target_date
        existing = await repository.list_daily_lesson_schedules(first_date, last_date)
        target_dates = {lesson.target_date for lesson in lessons}
        conflicts = sorted(schedule.date for schedule in existing if schedule.date in target_dates)
        replacing = len(conflicts) if replace_schedule else 0
        creating = len(lessons) - replacing

        click.echo(f"Target range: {first_date} to {last_date} ({len(lessons)} Daily lessons)")
        click.echo(f"Active locales: {', '.join(locale.code for locale in locales)}")
        click.echo(f"Schedule conflicts: {len(conflicts)}" + (f" ({', '.join(str(d) for d in conflicts)})" if conflicts else ""))
        click.echo(f"Would create {creating} Daily lessons, replace {replacing}" if dry_run else f"Planned {creating} Daily lessons, replace {replacing}")

        if conflicts and not replace_schedule:
            raise click.ClickException("Daily lesson schedules already exist for the conflicting dates above; rerun with --replace-schedule to replace them")
        if dry_run:
            click.echo("Dry run: no changes written")
            return

        conflict_dates = set(conflicts)
        for lesson in lessons:
            await _write_lesson(repository, locales, lesson, lesson.target_date in conflict_dates)
        await session.commit()
        click.echo(f"Created {creating} Daily lessons, replaced {replacing}")
    except click.ClickException, click.Abort:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        logger.exception(e)
        raise click.ClickException(f"Import failed and was rolled back; no changes were written: {e}") from e
    finally:
        await session.close()


async def _write_lesson(repository: DevotionRepository, locales: list[Locale], lesson: PlannedLesson, replace: bool) -> None:
    context = f"row {lesson.row_number} (source {lesson.source_date}, target {lesson.target_date})"
    try:
        devotion_id = uuid4()
        await repository.insert_devotion(devotion_id, lesson.passage_start, lesson.passage_end)
        for locale in locales:
            reflect, apply, pray = lesson.translations[locale.code]
            await repository.upsert_translation(devotion_id, locale.id, reflect, apply, pray)

        translated = await repository.list_translation_locale_ids(devotion_id)
        missing = [locale.code for locale in locales if locale.id not in translated]
        if missing:
            raise RuntimeError(f"translations incomplete for locales: {', '.join(missing)}")
        await repository.update_devotion_status(devotion_id, DevotionStatus.READY)

        if replace:
            if await repository.update_daily_lesson_schedule(lesson.target_date, devotion_id) < 1:
                raise RuntimeError("expected an existing Daily lesson schedule to replace")
        elif not await repository.insert_daily_lesson_schedule(lesson.target_date, devotion_id):
            raise RuntimeError("a Daily lesson is already scheduled for this date")
    except Exception as e:
        raise RuntimeError(f"{context}: {e}") from e


def import_daily_devotions_process(csv_path: str | None = None, start_date: date | None = None, dry_run: bool = False, replace_schedule: bool = False) -> None:
    """Synchronous entry point for importing daily devotions"""
    asyncio.run(
        import_daily_devotions(csv_path=Path(csv_path) if csv_path else None, start_date=start_date, dry_run=dry_run, replace_schedule=replace_schedule)
    )
