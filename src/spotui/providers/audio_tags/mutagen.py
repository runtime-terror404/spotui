"""Read-only audio metadata extraction through Mutagen."""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import mutagen

from spotui.domain.amazon import AmazonUrlError, parse_amazon_track_url
from spotui.providers.audio_tags.base import AudioTagMetadata

logger = logging.getLogger("spotui.audio_tags")

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_TRACK_NUMBER_KEYS = ("tracknumber", "trck", "trkn")
_TITLE_KEYS = ("title", "tit2", "©nam")
_ARTIST_KEYS = ("artist", "tpe1", "©art")
_ALBUM_KEYS = ("album", "talb", "©alb")


def _flatten(value: Any) -> list[str]:
    if value is None:
        return []
    text = getattr(value, "text", None)
    if text is not None:
        return _flatten(text)
    if isinstance(value, (list, tuple)):
        if len(value) == 2 and all(isinstance(item, int) for item in value):
            return [f"{value[0]}/{value[1]}"]
        items: list[str] = []
        for item in value:
            items.extend(_flatten(item))
        return items
    if isinstance(value, bytes):
        return [value.decode("utf-8", errors="replace")]
    return [str(value)]


def _tag_values(tags: Mapping[str, Any], keys: Iterable[str]) -> list[str]:
    values: list[str] = []
    for key in keys:
        raw = tags.get(key.casefold())
        if raw is not None:
            values.extend(_flatten(raw))
    return values


def _joined(values: list[str]) -> str:
    return "; ".join(part.strip() for part in values if part.strip())


def _amazon_track_key(tags: Mapping[str, Any]) -> str | None:
    for value in tags.values():
        for text in _flatten(value):
            for match in _URL_RE.findall(text):
                candidate = match.rstrip("),.;]}")
                try:
                    return parse_amazon_track_url(candidate).track_key
                except AmazonUrlError:
                    continue
    return None


class MutagenTagReader:
    """Read available tags without ever modifying the audio file."""

    def read(self, path: Path) -> AudioTagMetadata:
        try:
            audio = mutagen.File(path)
        except Exception as exc:  # Mutagen raises format-specific exceptions.
            logger.debug("cannot read audio tags from %s: %s", path, type(exc).__name__)
            return AudioTagMetadata()
        if audio is None or audio.tags is None:
            return AudioTagMetadata()

        try:
            tags = {str(key).casefold(): value for key, value in audio.tags.items()}
            title = _joined(_tag_values(tags, _TITLE_KEYS))
            artist = _joined(_tag_values(tags, _ARTIST_KEYS))
            album = _joined(_tag_values(tags, _ALBUM_KEYS))
            track_number = _joined(_tag_values(tags, _TRACK_NUMBER_KEYS))
            raw_duration = getattr(getattr(audio, "info", None), "length", None)
            duration = float(raw_duration) if raw_duration is not None else None
            if duration is not None and (
                not math.isfinite(duration) or duration < 0
            ):
                duration = None
            return AudioTagMetadata(
                title=title,
                artist=artist,
                album=album,
                track_number=track_number,
                duration_seconds=duration,
                amazon_track_key=_amazon_track_key(tags),
            )
        except Exception as exc:
            logger.debug("cannot parse audio tags from %s: %s", path, type(exc).__name__)
            return AudioTagMetadata()
