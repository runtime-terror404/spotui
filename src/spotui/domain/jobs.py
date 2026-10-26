"""Download-job states, DTOs, and the rules that define an active job."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class JobState(StrEnum):
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


#: States that reserve the normalized Amazon track identity. The database uses
#: this same set in a partial unique index.
ACTIVE_JOB_STATES: frozenset[JobState] = frozenset(
    {
        JobState.QUEUED,
        JobState.STARTING,
        JobState.RUNNING,
        JobState.CANCELLING,
    }
)

#: States with no further automatic work.
TERMINAL_JOB_STATES: frozenset[JobState] = frozenset(
    {
        JobState.COMPLETED,
        JobState.FAILED,
        JobState.CANCELLED,
        JobState.INTERRUPTED,
    }
)

#: States in which a subprocess may be owned by the worker.
PROCESS_JOB_STATES: frozenset[JobState] = frozenset(
    {
        JobState.STARTING,
        JobState.RUNNING,
        JobState.CANCELLING,
    }
)


def active_states_sql() -> str:
    """SQL predicate shared by the model and migrations."""
    values = ", ".join(f"'{state.value}'" for state in ACTIVE_JOB_STATES)
    return f"state IN ({values})"


@dataclass(frozen=True, slots=True)
class DownloadJob:
    id: str
    track_url: str
    track_key: str
    title: str
    artist: str
    state: JobState
    status_message: str
    progress_phase: str | None
    progress_percent: float | None
    attempt_count: int
    last_error: str | None
    output_path: str | None
    source_import_id: str | None
    source_occurrence_id: str | None
    source_playlist_title: str | None
    created_at: int
    updated_at: int
    started_at: int | None
    completed_at: int | None


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    job: DownloadJob
    attempt_id: int


@dataclass(frozen=True, slots=True)
class EnqueueResult:
    job: DownloadJob
    duplicate: bool


@dataclass(frozen=True, slots=True)
class DownloadRequest:
    url: str
    title: str
    artist: str = ""
    source_import_id: str | None = None
    source_occurrence_id: str | None = None
    source_playlist_title: str | None = None


@dataclass(frozen=True, slots=True)
class BatchEnqueueResult:
    added: int = 0
    duplicates: int = 0
    skipped_library: int = 0
    invalid: int = 0


@dataclass(frozen=True, slots=True)
class QueueCounts:
    queued: int = 0
    active: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    interrupted: int = 0

    @property
    def total(self) -> int:
        return (
            self.queued
            + self.active
            + self.completed
            + self.failed
            + self.cancelled
            + self.interrupted
        )


@dataclass(frozen=True, slots=True)
class QueueSnapshot:
    jobs: tuple[DownloadJob, ...]
    counts: QueueCounts
