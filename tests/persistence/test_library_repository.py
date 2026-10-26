from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from spotui.domain.library import (
    LibraryFileMetadata,
    LibraryMatch,
    LibraryMetadataSource,
    LibraryScanStatus,
    normalize_library_text,
)
from spotui.persistence.database import Database
from spotui.persistence.models import LibraryFile, LibraryRoot, LibraryScanRun
from spotui.persistence.repositories.library import LibraryRepository


class TickClock:
    def __init__(self) -> None:
        self.value = 1_700_000_000

    def __call__(self) -> int:
        self.value += 1
        return self.value


@pytest.fixture
def library_database(migrated_database_url: str):
    database = Database.from_url(migrated_database_url)
    try:
        yield database
    finally:
        database.dispose()


@pytest.fixture
def repository(library_database: Database) -> LibraryRepository:
    return LibraryRepository(library_database.session_factory, clock=TickClock())


def file_metadata(
    root: Path,
    relative: str,
    *,
    title: str,
    artist: str,
    amazon_key: str | None = None,
) -> LibraryFileMetadata:
    path = root / relative
    return LibraryFileMetadata(
        path=str(path),
        filename=path.name,
        extension=path.suffix.lstrip("."),
        size_bytes=100,
        modified_at_ns=1_700_000_000_000_000_000,
        title=title,
        artist=artist,
        album="Album",
        track_number="1",
        duration_seconds=180.0,
        metadata_source=LibraryMetadataSource.TAGS,
        normalized_title=normalize_library_text(title),
        normalized_artist=normalize_library_text(artist),
        amazon_track_key=amazon_key,
    )


def scan(
    repository: LibraryRepository,
    root_id: int,
    files: list[LibraryFileMetadata],
    *,
    available: bool = True,
) -> None:
    scan_run = repository.begin_scan(root_id)
    repository.apply_scan_batch(
        scan_run.id,
        root_id,
        files=files,
        unchanged_ids=[],
        files_seen=len(files),
        files_indexed=len(files),
        files_failed=0,
    )
    repository.finish_scan(
        scan_run.id,
        root_id,
        status=LibraryScanStatus.COMPLETED,
        files_seen=len(files),
        files_indexed=len(files),
        files_failed=0,
        available=available,
        error=None,
        remove_unseen=True,
    )


def test_reconcile_multiple_roots_and_remove_unconfigured_roots(
    repository: LibraryRepository, library_database: Database
) -> None:
    roots = repository.reconcile_roots(["/music/one", "/music/two"])

    assert [root.path for root in roots] == ["/music/one", "/music/two"]
    assert all(not root.available and not root.index_complete for root in roots)

    roots = repository.reconcile_roots(["/music/two"])

    assert [root.path for root in roots] == ["/music/two"]
    with library_database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(LibraryRoot)) == 1


def test_exact_and_likely_matches_are_confidence_aware(
    repository: LibraryRepository, tmp_path: Path
) -> None:
    empty = repository.lookup(
        amazon_track_key=None,
        normalized_title="song",
        artist_tokens=frozenset({"artist"}),
    )
    assert empty.complete is True
    assert empty.match is None

    root = repository.reconcile_roots([str(tmp_path / "Music")])[0]
    incomplete = repository.lookup(
        amazon_track_key="amazon:B002TRACK1",
        normalized_title="song",
        artist_tokens=frozenset({"artist"}),
    )
    assert incomplete.complete is False
    assert incomplete.match is None

    media = file_metadata(
        tmp_path / "Music",
        "Artists/Artist/Album/Song.flac",
        title="Song (Live)",
        artist="Artist, Other",
        amazon_key="amazon:B002TRACK1",
    )
    scan(repository, root.id, [media])

    exact = repository.lookup(
        amazon_track_key="amazon:B002TRACK1",
        normalized_title="no title",
        artist_tokens=frozenset(),
    )
    likely = repository.lookup(
        amazon_track_key="amazon:OTHER",
        normalized_title="song",
        artist_tokens=frozenset({"other", "someone"}),
    )
    absent = repository.lookup(
        amazon_track_key="amazon:OTHER",
        normalized_title="song",
        artist_tokens=frozenset({"different"}),
    )

    assert exact.match is LibraryMatch.EXACT
    assert likely.match is LibraryMatch.LIKELY
    assert absent.match is None
    assert absent.complete is True


def test_unavailable_root_is_not_treated_as_empty(
    repository: LibraryRepository, tmp_path: Path
) -> None:
    root = repository.reconcile_roots([str(tmp_path / "Music")])[0]
    media = file_metadata(
        tmp_path / "Music",
        "Song.flac",
        title="Song",
        artist="Artist",
        amazon_key="amazon:B002TRACK1",
    )
    scan(repository, root.id, [media])
    repository.update_root_availability(
        root.id,
        available=False,
        error="Library root is unavailable.",
    )

    exact = repository.lookup(
        amazon_track_key="amazon:B002TRACK1",
        normalized_title="song",
        artist_tokens=frozenset({"artist"}),
    )
    absent = repository.lookup(
        amazon_track_key="amazon:OTHER",
        normalized_title="unknown",
        artist_tokens=frozenset({"artist"}),
    )

    assert exact.match is LibraryMatch.EXACT
    assert exact.complete is False
    assert absent.match is None
    assert absent.complete is False
    assert repository.list_roots()[0].file_count == 1


def test_successful_rescan_updates_and_removes_unseen_files(
    repository: LibraryRepository, library_database: Database, tmp_path: Path
) -> None:
    root = repository.reconcile_roots([str(tmp_path / "Music")])[0]
    first = file_metadata(
        tmp_path / "Music", "First.flac", title="First", artist="Artist"
    )
    second = file_metadata(
        tmp_path / "Music", "Second.flac", title="Second", artist="Artist"
    )
    scan(repository, root.id, [first, second])

    updated = replace(first, title="First Updated", normalized_title="first updated")
    scan(repository, root.id, [updated])

    root_state = repository.list_roots()[0]
    first_match = repository.lookup(
        amazon_track_key=None,
        normalized_title="first updated",
        artist_tokens=frozenset({"artist"}),
    )
    second_match = repository.lookup(
        amazon_track_key=None,
        normalized_title="second",
        artist_tokens=frozenset({"artist"}),
    )
    with library_database.session_factory() as session:
        last_scan = session.scalars(
            select(LibraryScanRun).order_by(LibraryScanRun.id.desc()).limit(1)
        ).one()

    assert root_state.file_count == 1
    assert first_match.match is LibraryMatch.LIKELY
    assert second_match.match is None
    assert last_scan.files_removed == 1


def test_recover_interrupted_scan_clears_active_state(
    repository: LibraryRepository, library_database: Database
) -> None:
    root = repository.reconcile_roots(["/music"])[0]
    scan_run = repository.begin_scan(root.id)

    with pytest.raises(IntegrityError):
        repository.begin_scan(root.id)

    assert repository.recover_interrupted_scans() == 1
    assert repository.active_scan() is None
    with library_database.session_factory() as session:
        recovered = session.get(LibraryScanRun, scan_run.id)
        root_row = session.get(LibraryRoot, root.id)
        assert recovered is not None
        assert recovered.status == LibraryScanStatus.INTERRUPTED.value
        assert root_row is not None
        assert root_row.index_complete is False


def test_deleting_a_root_cascades_its_index_data(
    repository: LibraryRepository, library_database: Database, tmp_path: Path
) -> None:
    root = repository.reconcile_roots([str(tmp_path / "Music")])[0]
    media = file_metadata(
        tmp_path / "Music", "Song.flac", title="Song", artist="Artist"
    )
    scan(repository, root.id, [media])

    with library_database.session_factory.begin() as session:
        root_row = session.get(LibraryRoot, root.id)
        assert root_row is not None
        session.delete(root_row)

    with library_database.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(LibraryFile)) == 0
        assert session.scalar(select(func.count()).select_from(LibraryScanRun)) == 0
