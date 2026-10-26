from __future__ import annotations

import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from sqlalchemy import select

from spotui.domain.library import LibraryMatch, LibraryMetadataSource
from spotui.persistence.database import Database
from spotui.persistence.models import LibraryFile
from spotui.persistence.repositories.library import LibraryRepository
from spotui.providers.audio_tags.base import AudioTagMetadata
from spotui.workers.library_scanner import LibraryScanWorker


@dataclass
class FakeTagReader:
    metadata: dict[str, AudioTagMetadata] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def read(self, path: Path) -> AudioTagMetadata:
        self.calls.append(str(path))
        return self.metadata.get(path.name, AudioTagMetadata())


def write_track(path: Path, content: bytes = b"audio") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


@pytest.fixture
def database(migrated_database_url: str):
    db = Database.from_url(migrated_database_url)
    try:
        yield db
    finally:
        db.dispose()


@pytest.fixture
def repository(database: Database) -> LibraryRepository:
    return LibraryRepository(database.session_factory)


def test_scan_indexes_multiple_roots_with_tags_and_filename_fallback(
    repository: LibraryRepository,
    database: Database,
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "Music One"
    second_root = tmp_path / "Music Two"
    tagged = write_track(
        first_root / "Artists" / "Arijit Singh" / "Aashiqui 2" / "Tum Hi Ho.flac"
    )
    write_track(second_root / "Artists" / "Artist" / "Album" / "01 - Untagged Song.mp3")
    write_track(first_root / "notes.txt", b"not audio")
    write_track(first_root / ".incoming" / "partial.flac")
    write_track(first_root / ".hidden.flac")
    symlink = first_root / "linked.flac"
    try:
        symlink.symlink_to(tagged)
    except OSError:
        symlink = None

    reader = FakeTagReader(
        metadata={
            tagged.name: AudioTagMetadata(
                title="Tum Hi Ho",
                artist="Arijit Singh",
                album="Aashiqui 2",
                track_number="2/10",
                duration_seconds=180.0,
                amazon_track_key="amazon:B002TRACK1",
            )
        }
    )
    scanner = LibraryScanWorker(
        repository,
        reader,
        [str(first_root), str(second_root)],
        refresh_seconds=0,
    )
    scanner.prepare()

    assert scanner.scan_all() is True

    roots = repository.list_roots()
    exact = repository.lookup(
        amazon_track_key="amazon:B002TRACK1",
        normalized_title="tum hi ho",
        artist_tokens=frozenset({"arijit", "singh"}),
    )
    fallback_match = repository.lookup(
        amazon_track_key=None,
        normalized_title="untagged song",
        artist_tokens=frozenset({"artist"}),
    )
    with database.session_factory() as session:
        rows = session.scalars(select(LibraryFile)).all()
        sources = {row.filename: row.metadata_source for row in rows}

    assert [root.path for root in roots] == [str(first_root), str(second_root)]
    assert all(root.available and root.index_complete for root in roots)
    assert [root.file_count for root in roots] == [1, 1]
    assert exact.match is LibraryMatch.EXACT
    assert fallback_match.match is LibraryMatch.LIKELY
    assert sources == {
        "Tum Hi Ho.flac": LibraryMetadataSource.TAGS.value,
        "01 - Untagged Song.mp3": LibraryMetadataSource.FILENAME.value,
    }
    if symlink is not None:
        assert str(symlink) not in reader.calls


def test_rescan_skips_unchanged_files_and_updates_changed_metadata(
    repository: LibraryRepository,
    tmp_path: Path,
) -> None:
    root = tmp_path / "Music"
    track = write_track(root / "Artists" / "Artist" / "Album" / "Song.flac")
    reader = FakeTagReader(
        metadata={track.name: AudioTagMetadata(title="Original", artist="Artist")}
    )
    scanner = LibraryScanWorker(repository, reader, [str(root)], refresh_seconds=0)
    scanner.prepare()
    scanner.scan_all()
    assert len(reader.calls) == 1

    scanner.scan_all()
    assert len(reader.calls) == 1

    track.write_bytes(b"changed audio content")
    reader.metadata[track.name] = AudioTagMetadata(
        title="Updated Song", artist="Artist"
    )
    scanner.scan_all()

    updated = repository.lookup(
        amazon_track_key=None,
        normalized_title="updated song",
        artist_tokens=frozenset({"artist"}),
    )
    original = repository.lookup(
        amazon_track_key=None,
        normalized_title="original",
        artist_tokens=frozenset({"artist"}),
    )
    assert len(reader.calls) == 2
    assert updated.match is LibraryMatch.LIKELY
    assert original.match is None
    assert repository.list_roots()[0].file_count == 1


def test_rescan_removes_files_that_no_longer_exist(
    repository: LibraryRepository, tmp_path: Path
) -> None:
    root = tmp_path / "Music"
    first = write_track(root / "First.flac")
    second = write_track(root / "Second.flac")
    reader = FakeTagReader(
        metadata={
            first.name: AudioTagMetadata(title="First", artist="Artist"),
            second.name: AudioTagMetadata(title="Second", artist="Artist"),
        }
    )
    scanner = LibraryScanWorker(repository, reader, [str(root)], refresh_seconds=0)
    scanner.prepare()
    scanner.scan_all()

    second.unlink()
    scanner.scan_all()

    assert repository.list_roots()[0].file_count == 1
    assert repository.lookup(
        amazon_track_key=None,
        normalized_title="second",
        artist_tokens=frozenset({"artist"}),
    ).match is None


def test_unavailable_mount_preserves_the_existing_index_and_is_not_empty(
    repository: LibraryRepository,
    tmp_path: Path,
) -> None:
    root = tmp_path / "Music"
    track = write_track(root / "Song.flac")
    reader = FakeTagReader(
        metadata={
            track.name: AudioTagMetadata(
                title="Song",
                artist="Artist",
                amazon_track_key="amazon:B002TRACK1",
            )
        }
    )
    scanner = LibraryScanWorker(repository, reader, [str(root)], refresh_seconds=0)
    scanner.prepare()
    scanner.scan_all()

    shutil.rmtree(root)
    scanner.scan_all()

    root_state = repository.list_roots()[0]
    exact = repository.lookup(
        amazon_track_key="amazon:B002TRACK1",
        normalized_title="song",
        artist_tokens=frozenset({"artist"}),
    )
    unknown = repository.lookup(
        amazon_track_key="amazon:OTHER",
        normalized_title="missing",
        artist_tokens=frozenset({"artist"}),
    )

    assert root_state.available is False
    assert root_state.index_complete is False
    assert root_state.file_count == 1
    assert exact.match is LibraryMatch.EXACT
    assert exact.complete is False
    assert unknown.match is None
    assert unknown.complete is False


def test_background_scanner_indexes_at_startup_and_on_manual_request(
    repository: LibraryRepository, tmp_path: Path
) -> None:
    root = tmp_path / "Music"
    write_track(root / "First.flac")
    scanner = LibraryScanWorker(
        repository,
        FakeTagReader(),
        [str(root)],
        refresh_seconds=0,
        scan_on_startup=True,
    )
    scanner.start()
    try:
        wait_until(
            lambda: bool(repository.list_roots())
            and repository.list_roots()[0].index_complete
            and repository.list_roots()[0].file_count == 1
        )

        write_track(root / "Second.flac")
        assert scanner.request_scan() is True
        wait_until(
            lambda: bool(repository.list_roots())
            and repository.list_roots()[0].file_count == 2
            and repository.active_scan() is None
        )
    finally:
        scanner.close()


def test_periodic_refresh_scans_without_startup_scan(
    repository: LibraryRepository, tmp_path: Path
) -> None:
    root = tmp_path / "Music"
    write_track(root / "First.flac")
    scanner = LibraryScanWorker(
        repository,
        FakeTagReader(),
        [str(root)],
        refresh_seconds=0.1,
        scan_on_startup=False,
    )
    scanner.start()
    try:
        wait_until(
            lambda: bool(repository.list_roots())
            and repository.list_roots()[0].file_count == 1
        )
    finally:
        scanner.close()


def wait_until(predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was not met before the timeout")
