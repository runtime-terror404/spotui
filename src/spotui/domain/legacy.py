"""Value types and state mapping for the legacy JSON queue migration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from spotui.domain.jobs import JobState


class LegacyImportOutcome(StrEnum):
    IMPORTED = "imported"
    SKIPPED = "skipped"
    AMBIGUOUS = "ambiguous"
    FAILED = "failed"


#: Legacy states with a lossless or safely conservative new state.
LEGACY_STATE_MAP: dict[str, JobState] = {
    "queued": JobState.QUEUED,
    "running": JobState.INTERRUPTED,
    "downloading": JobState.INTERRUPTED,
    "done": JobState.COMPLETED,
    "failed": JobState.FAILED,
    "cancelled": JobState.CANCELLED,
}


@dataclass(frozen=True, slots=True)
class LegacyJobEntry:
    """One validated legacy queue record, independent of persistence."""

    index: int
    legacy_id: str
    legacy_key: str
    title: str
    artist: str
    url: str
    track_key: str
    legacy_status: str
    message: str
    output_path: str | None
    added_at: int
    updated_at: int
    finished_at: int | None
    state: JobState
    warnings: tuple[str, ...] = ()

    @property
    def interrupted(self) -> bool:
        return self.legacy_status in ("running", "downloading")

    @property
    def status_message(self) -> str:
        if self.interrupted:
            return (
                "Imported from the legacy queue while "
                f"{self.legacy_status}; not resumed automatically"
            )
        if self.state is JobState.QUEUED:
            return "queued (imported from legacy queue)"
        if self.state is JobState.COMPLETED:
            return "completed (imported from legacy queue)"
        if self.state is JobState.CANCELLED:
            return "cancelled (imported from legacy queue)"
        if self.state is JobState.FAILED:
            return self.message or "failed (imported from legacy queue)"
        return self.message or f"{self.legacy_status} (imported from legacy queue)"


@dataclass(frozen=True, slots=True)
class LegacyImportResult:
    index: int
    legacy_id: str | None
    title: str
    outcome: LegacyImportOutcome
    reason: str | None = None
    job_id: str | None = None

    @property
    def label(self) -> str:
        legacy_id = self.legacy_id or "-"
        return f"{legacy_id:<8} {self.title or '(untitled)'}"


@dataclass(slots=True)
class LegacyMigrationReport:
    source_path: str
    dry_run: bool
    results: list[LegacyImportResult] = field(default_factory=list)

    def add(self, result: LegacyImportResult) -> None:
        self.results.append(result)

    def count(self, outcome: LegacyImportOutcome) -> int:
        return sum(1 for result in self.results if result.outcome is outcome)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def imported(self) -> int:
        return self.count(LegacyImportOutcome.IMPORTED)

    @property
    def skipped(self) -> int:
        return self.count(LegacyImportOutcome.SKIPPED)

    @property
    def ambiguous(self) -> int:
        return self.count(LegacyImportOutcome.AMBIGUOUS)

    @property
    def failed(self) -> int:
        return self.count(LegacyImportOutcome.FAILED)


__all__ = [
    "LEGACY_STATE_MAP",
    "LegacyImportOutcome",
    "LegacyImportResult",
    "LegacyJobEntry",
    "LegacyMigrationReport",
]
