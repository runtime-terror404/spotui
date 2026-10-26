"""Download-job states and the rules that define an active job."""

from __future__ import annotations

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


def active_states_sql() -> str:
    """SQL predicate shared by the model and the initial migration."""
    values = ", ".join(f"'{state.value}'" for state in ACTIVE_JOB_STATES)
    return f"state IN ({values})"
