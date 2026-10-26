from __future__ import annotations

import wave
from pathlib import Path

from mutagen.id3 import COMM, TALB, TIT2, TPE1, TRCK
from mutagen.wave import WAVE

from spotui.providers.audio_tags.mutagen import MutagenTagReader

AMAZON_URL = "https://music.amazon.com/tracks/B0HG9XV8Q9?musicTerritory=US"


def write_wav(path: Path, *, tags: bool = False) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 800)
    if tags:
        tagged = WAVE(path)
        tagged.add_tags()
        tagged.tags.add(TIT2(encoding=3, text="Tum Hi Ho"))
        tagged.tags.add(TPE1(encoding=3, text="Arijit Singh"))
        tagged.tags.add(TALB(encoding=3, text="Aashiqui 2"))
        tagged.tags.add(TRCK(encoding=3, text="2/10"))
        tagged.tags.add(
            COMM(
                encoding=3,
                lang="eng",
                desc="",
                text=f"downloaded from lucida.to: {AMAZON_URL}",
            )
        )
        tagged.save()
    return path.read_bytes()


def test_reads_tags_and_amazon_identity_without_modifying_file(tmp_path: Path) -> None:
    path = tmp_path / "Artists" / "Arijit Singh" / "Aashiqui 2" / "Tum Hi Ho.wav"
    before = write_wav(path, tags=True)

    metadata = MutagenTagReader().read(path)

    assert metadata.title == "Tum Hi Ho"
    assert metadata.artist == "Arijit Singh"
    assert metadata.album == "Aashiqui 2"
    assert metadata.track_number == "2/10"
    assert metadata.duration_seconds is not None
    assert metadata.duration_seconds > 0
    assert metadata.amazon_track_key == "amazon:B0HG9XV8Q9"
    assert path.read_bytes() == before


def test_untagged_file_returns_empty_metadata(tmp_path: Path) -> None:
    path = tmp_path / "untagged.wav"
    write_wav(path)

    assert MutagenTagReader().read(path).title == ""


def test_unreadable_or_unsupported_file_falls_back_to_empty(tmp_path: Path) -> None:
    path = tmp_path / "broken.flac"
    path.write_bytes(b"not an audio file")

    metadata = MutagenTagReader().read(path)

    assert metadata.title == ""
    assert metadata.amazon_track_key is None
