"""Read the legacy JSON queue and import it into the durable SQLite queue.

The migration is deliberately conservative:

* it never writes to the legacy file or any media;
* queued work remains queued, but was never resumed if it was active at export;
* running/downloading records become interrupted;
* unknown or malformed records are reported and skipped;
* a per-record ledger makes repeated runs idempotent.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from spotui.domain.amazon import AmazonUrlError, parse_amazon_track_url
from spotui.domain.jobs import JobState
from spotui.domain.legacy import (
    LEGACY_STATE_MAP,
    LegacyImportOutcome,
    LegacyImportResult,
    LegacyJobEntry,
    LegacyMigrationReport,
)
from spotui.persistence.repositories.legacy import (
    LegacyQueueRepository,
    PriorLegacyImport,
)

_MAX_LEGACY_FILE_BYTES = 5 * 1024 * 1024
_MAX_LEGACY_ID_LENGTH = 64
_MAX_RECORDS = 2000
_MAX_MESSAGE_LENGTH = 500


class LegacyMigrationError(RuntimeError):
    """The legacy queue cannot be read or migrated safely."""


@dataclass(frozen=True, slots=True)
class LegacyRecordFailure:
    index: int
    legacy_key: str
    legacy_id: str | None
    title: str
    outcome: LegacyImportOutcome
    reason: str


@dataclass(frozen=True, slots=True)
class ParsedLegacyQueue:
    source_path: str
    entries: tuple[LegacyJobEntry, ...]
    failures: tuple[LegacyRecordFailure, ...]


def _invalid_key(raw: Any, index: int) -> str:
    serialized = json.dumps(raw, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{index}:{serialized}".encode()).hexdigest()


def _legacy_key(legacy_id: str) -> str:
    return hashlib.sha256(legacy_id.encode("utf-8")).hexdigest()


def _job_id(source_path: str, legacy_id: str) -> str:
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"spotui-legacy:{source_path}:{legacy_id}",
    ).hex


def _safe_epoch(value: Any, fallback: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return fallback
    return value


def _safe_text(value: Any, *, limit: int | None = None) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if limit is not None:
        return text[:limit]
    return text


def _safe_optional_text(value: Any) -> str | None:
    text = _safe_text(value)
    return text or None


def _read_raw_queue(path: Path) -> list[Any]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise LegacyMigrationError(f"cannot inspect legacy queue {path}: {exc}") from exc
    if size > _MAX_LEGACY_FILE_BYTES:
        raise LegacyMigrationError(
            f"legacy queue {path} is larger than the {_MAX_LEGACY_FILE_BYTES} byte safety limit"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LegacyMigrationError(f"cannot read legacy queue {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise LegacyMigrationError("legacy queue must be a JSON object with a jobs list")
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        raise LegacyMigrationError("legacy queue does not contain a jobs list")
    if len(jobs) > _MAX_RECORDS:
        raise LegacyMigrationError(
            f"legacy queue contains {len(jobs)} records; the safety limit is {_MAX_RECORDS}"
        )
    return jobs


def _parse_record(
    raw: Any,
    *,
    index: int,
    now: int,
) -> LegacyJobEntry | LegacyRecordFailure:
    if not isinstance(raw, dict):
        return LegacyRecordFailure(
            index=index,
            legacy_key=_invalid_key(raw, index),
            legacy_id=None,
            title="",
            outcome=LegacyImportOutcome.AMBIGUOUS,
            reason="record is not a JSON object",
        )

    legacy_id_value = raw.get("id")
    legacy_id = (
        legacy_id_value.strip()
        if isinstance(legacy_id_value, str) and legacy_id_value.strip()
        else None
    )
    title = _safe_text(raw.get("title"))
    if legacy_id is None:
        return LegacyRecordFailure(
            index=index,
            legacy_key=_invalid_key(raw, index),
            legacy_id=None,
            title=title,
            outcome=LegacyImportOutcome.AMBIGUOUS,
            reason="record has no usable legacy job id",
        )
    if len(legacy_id) > _MAX_LEGACY_ID_LENGTH:
        return LegacyRecordFailure(
            index=index,
            legacy_key=_invalid_key(raw, index),
            legacy_id=legacy_id[:_MAX_LEGACY_ID_LENGTH],
            title=title,
            outcome=LegacyImportOutcome.AMBIGUOUS,
            reason="legacy job id is too long",
        )
    legacy_key = _legacy_key(legacy_id)

    raw_url = raw.get("url")
    url = raw_url.strip() if isinstance(raw_url, str) else ""
    if not url:
        return LegacyRecordFailure(
            index=index,
            legacy_key=legacy_key,
            legacy_id=legacy_id,
            title=title,
            outcome=LegacyImportOutcome.FAILED,
            reason="record has no track URL",
        )
    try:
        track = parse_amazon_track_url(url)
    except AmazonUrlError as exc:
        return LegacyRecordFailure(
            index=index,
            legacy_key=legacy_key,
            legacy_id=legacy_id,
            title=title,
            outcome=LegacyImportOutcome.FAILED,
            reason=f"unsupported track URL: {exc}",
        )

    raw_status = raw.get("status")
    legacy_status = raw_status.strip().lower() if isinstance(raw_status, str) else ""
    state = LEGACY_STATE_MAP.get(legacy_status)
    if state is None:
        return LegacyRecordFailure(
            index=index,
            legacy_key=legacy_key,
            legacy_id=legacy_id,
            title=title,
            outcome=LegacyImportOutcome.AMBIGUOUS,
            reason=f"unknown legacy status {raw_status!r}",
        )

    warnings: list[str] = []
    if not title:
        title = track.canonical_url
        warnings.append("title was missing; used the track URL")
    artist = _safe_text(raw.get("artist"))

    added_value = raw.get("added")
    added_at = _safe_epoch(added_value, now)
    if added_at == now and added_value != now:
        warnings.append("created timestamp was missing or invalid; used the migration time")
    updated_value = raw.get("updated")
    updated_at = _safe_epoch(updated_value, added_at)
    if updated_at == added_at and updated_value != added_at:
        warnings.append("updated timestamp was missing or invalid; used the created time")
    if updated_at < added_at:
        updated_at = added_at
        warnings.append("updated timestamp preceded created time; clamped")

    finished_at = raw.get("finished")
    finished_epoch = (
        finished_at
        if isinstance(finished_at, int)
        and not isinstance(finished_at, bool)
        and finished_at > 0
        else None
    )
    if state is JobState.COMPLETED and finished_epoch is None:
        finished_epoch = updated_at

    message = _safe_text(raw.get("message"), limit=_MAX_MESSAGE_LENGTH)

    return LegacyJobEntry(
        index=index,
        legacy_id=legacy_id,
        legacy_key=legacy_key,
        title=title,
        artist=artist,
        url=url,
        track_key=track.track_key,
        legacy_status=legacy_status,
        message=message,
        output_path=_safe_optional_text(raw.get("file")),
        added_at=added_at,
        updated_at=updated_at,
        finished_at=finished_epoch,
        state=state,
        warnings=tuple(warnings),
    )


def parse_legacy_queue(
    path: Path,
    *,
    now: int | None = None,
) -> ParsedLegacyQueue:
    """Validate every record without reading or writing any other state."""
    source = path.expanduser()
    try:
        source_path = str(source.resolve(strict=True))
    except OSError as exc:
        raise LegacyMigrationError(f"legacy queue not found: {source}") from exc
    if not source.is_file():
        raise LegacyMigrationError(f"legacy queue is not a regular file: {source_path}")

    current_time = int(time.time()) if now is None else now
    entries: list[LegacyJobEntry] = []
    failures: list[LegacyRecordFailure] = []
    for index, raw in enumerate(_read_raw_queue(source)):
        parsed = _parse_record(
            raw,
            index=index,
            now=current_time,
        )
        if isinstance(parsed, LegacyRecordFailure):
            failures.append(parsed)
        else:
            entries.append(parsed)
    return ParsedLegacyQueue(
        source_path=source_path,
        entries=tuple(entries),
        failures=tuple(failures),
    )


class LegacyMigrationService:
    def __init__(
        self,
        repository: LegacyQueueRepository,
        *,
        clock: Callable[[], int] = lambda: int(time.time()),
    ) -> None:
        self._repository = repository
        self._clock = clock

    def migrate(self, path: Path, *, dry_run: bool = False) -> LegacyMigrationReport:
        parsed = parse_legacy_queue(path, now=self._clock())
        report = LegacyMigrationReport(
            source_path=parsed.source_path,
            dry_run=dry_run,
        )
        prior = self._repository.existing_imports(parsed.source_path)
        active_jobs = self._repository.active_jobs_by_track_key()
        seen: set[str] = set()

        ordered: list[LegacyJobEntry | LegacyRecordFailure] = [
            *parsed.entries,
            *parsed.failures,
        ]
        for record in sorted(ordered, key=lambda item: item.index):
            if isinstance(record, LegacyRecordFailure):
                self._handle_failure(record, report, prior, seen, dry_run)
                continue
            self._handle_entry(
                record,
                source_path=parsed.source_path,
                report=report,
                prior=prior,
                active_jobs=active_jobs,
                seen=seen,
                dry_run=dry_run,
            )
        return report

    def _handle_failure(
        self,
        failure: LegacyRecordFailure,
        report: LegacyMigrationReport,
        prior: dict[str, PriorLegacyImport],
        seen: set[str],
        dry_run: bool,
    ) -> None:
        key = failure.legacy_key
        existing = prior.get(key)
        if existing is not None or key in seen:
            reason = _prior_reason(existing) if existing is not None else "duplicate record"
            report.add(
                LegacyImportResult(
                    index=failure.index,
                    legacy_id=failure.legacy_id,
                    title=failure.title,
                    outcome=LegacyImportOutcome.SKIPPED,
                    reason=reason,
                )
            )
            seen.add(key)
            return
        if not dry_run:
            try:
                self._repository.record_unparsed(
                    source_path=report.source_path,
                    legacy_key=key,
                    legacy_id=failure.legacy_id,
                    outcome=failure.outcome,
                    reason=failure.reason,
                )
            except SQLAlchemyError as exc:
                report.add(
                    LegacyImportResult(
                        index=failure.index,
                        legacy_id=failure.legacy_id,
                        title=failure.title,
                        outcome=LegacyImportOutcome.FAILED,
                        reason=f"could not record migration outcome: {exc}",
                    )
                )
                return
        report.add(
            LegacyImportResult(
                index=failure.index,
                legacy_id=failure.legacy_id,
                title=failure.title,
                outcome=failure.outcome,
                reason=failure.reason,
            )
        )
        seen.add(key)

    def _handle_entry(
        self,
        entry: LegacyJobEntry,
        *,
        source_path: str,
        report: LegacyMigrationReport,
        prior: dict[str, PriorLegacyImport],
        active_jobs: dict[str, str],
        seen: set[str],
        dry_run: bool,
    ) -> None:
        key = entry.legacy_key
        existing = prior.get(key)
        if existing is not None or key in seen:
            reason = _prior_reason(existing) if existing is not None else "duplicate record"
            report.add(
                LegacyImportResult(
                    index=entry.index,
                    legacy_id=entry.legacy_id,
                    title=entry.title,
                    outcome=LegacyImportOutcome.SKIPPED,
                    reason=reason,
                    job_id=existing.job_id if existing else None,
                )
            )
            seen.add(key)
            return

        job_id = _job_id(source_path, entry.legacy_id)
        if self._repository.job_exists(job_id):
            reason = "matching job already exists"
            error = _record_skip(
                self._repository,
                source_path=source_path,
                entry=entry,
                reason=reason,
                job_id=job_id,
                dry_run=dry_run,
            )
            report.add(
                LegacyImportResult(
                    index=entry.index,
                    legacy_id=entry.legacy_id,
                    title=entry.title,
                    outcome=(
                        LegacyImportOutcome.FAILED
                        if error
                        else LegacyImportOutcome.SKIPPED
                    ),
                    reason=error or reason,
                    job_id=job_id,
                )
            )
            seen.add(key)
            return

        if entry.state is JobState.QUEUED and entry.track_key in active_jobs:
            active_job_id = active_jobs[entry.track_key]
            reason = "an active job already exists for this track"
            error = _record_skip(
                self._repository,
                source_path=source_path,
                entry=entry,
                reason=reason,
                job_id=active_job_id,
                dry_run=dry_run,
            )
            report.add(
                LegacyImportResult(
                    index=entry.index,
                    legacy_id=entry.legacy_id,
                    title=entry.title,
                    outcome=(
                        LegacyImportOutcome.FAILED
                        if error
                        else LegacyImportOutcome.SKIPPED
                    ),
                    reason=error or reason,
                    job_id=active_job_id,
                )
            )
            seen.add(key)
            return

        if dry_run:
            report.add(
                LegacyImportResult(
                    index=entry.index,
                    legacy_id=entry.legacy_id,
                    title=entry.title,
                    outcome=LegacyImportOutcome.IMPORTED,
                    reason=_import_reason(entry),
                    job_id=job_id,
                )
            )
            seen.add(key)
            if entry.state is JobState.QUEUED:
                active_jobs[entry.track_key] = job_id
            return

        try:
            self._repository.import_entry(entry, source_path=source_path, job_id=job_id)
        except SQLAlchemyError as exc:
            report.add(
                LegacyImportResult(
                    index=entry.index,
                    legacy_id=entry.legacy_id,
                    title=entry.title,
                    outcome=LegacyImportOutcome.FAILED,
                    reason=f"database rejected the record: {exc}",
                )
            )
            return
        report.add(
            LegacyImportResult(
                index=entry.index,
                legacy_id=entry.legacy_id,
                title=entry.title,
                outcome=LegacyImportOutcome.IMPORTED,
                reason=_import_reason(entry),
                job_id=job_id,
            )
        )
        seen.add(key)
        if entry.state is JobState.QUEUED:
            active_jobs[entry.track_key] = job_id


def _prior_reason(existing: PriorLegacyImport | None) -> str:
    if existing is None:
        return "duplicate record"
    suffix = f"; job {existing.job_id}" if existing.job_id else ""
    detail = f": {existing.reason}" if existing.reason else ""
    return f"already processed as {existing.outcome.value}{suffix}{detail}"


def _import_reason(entry: LegacyJobEntry) -> str | None:
    parts = list(entry.warnings)
    if entry.interrupted:
        parts.append(
            f"legacy state {entry.legacy_status!r} was active; imported as interrupted"
        )
    return "; ".join(parts) or None


def _record_skip(
    repository: LegacyQueueRepository,
    *,
    source_path: str,
    entry: LegacyJobEntry,
    reason: str,
    job_id: str,
    dry_run: bool,
) -> str | None:
    if dry_run:
        return None
    try:
        repository.record_outcome(
            source_path=source_path,
            entry=entry,
            outcome=LegacyImportOutcome.SKIPPED,
            reason=reason,
            job_id=job_id,
        )
    except SQLAlchemyError as exc:
        return f"could not record migration outcome: {exc}"
    return None


def render_report(report: LegacyMigrationReport) -> str:
    mode = "Dry run" if report.dry_run else "Migration"
    lines = [
        f"{mode} for legacy queue: {report.source_path}",
        (
            f"Records: {report.total}  imported: {report.imported}  "
            f"skipped: {report.skipped}  ambiguous: {report.ambiguous}  "
            f"failed: {report.failed}"
        ),
    ]
    if report.results:
        lines.append("")
    for result in report.results:
        line = f"  [{result.outcome.value:<9}] {result.label}"
        if result.reason:
            line += f" — {result.reason}"
        lines.append(line)
    if report.dry_run:
        lines.append("")
        lines.append("No changes were written. Re-run with --yes to import.")
    return "\n".join(lines)


__all__ = [
    "LegacyMigrationError",
    "LegacyMigrationService",
    "ParsedLegacyQueue",
    "parse_legacy_queue",
    "render_report",
]
