"""Standalone lucidadl bridge executed with the managed downloader Python.

This file must not import SpotUI because it runs inside the separate lucidadl
environment. It prints one JSON object on success and one JSON error object on
stderr on failure.
"""

from __future__ import annotations

import asyncio
import json
import sys


def _fail(message: str, code: int = 2) -> None:
    print(json.dumps({"error": message}), file=sys.stderr)
    raise SystemExit(code)


def _names(artists) -> str:
    if not isinstance(artists, list):
        return ""
    names = []
    for artist in artists:
        if isinstance(artist, dict):
            name = artist.get("name")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
    return ", ".join(names)


async def _fetch(url: str) -> dict:
    try:
        from lucidadl import session
        from lucidadl.api import LucidaClient
    except Exception:
        _fail("lucidadl is not installed in the managed environment.")

    cf, ua = session.load_clearance()
    if not (cf and ua):
        _fail("Cloudflare clearance is missing; run 'lucida setup'.")

    client = LucidaClient(
        cf,
        ua,
        acquire=None,
        country=None,
        downscale="original",
        metadata=True,
        jobs=1,
        log=lambda *args, **kwargs: None,
    )
    await client.start_http()
    try:
        data = await client.fetch_page_data(url)
    finally:
        await client.aclose()

    info = data.get("info") if isinstance(data, dict) else None
    if not isinstance(info, dict):
        _fail("The catalog resolver returned no item information.")
    if info.get("type") not in ("album", "playlist"):
        _fail("This Amazon Music item has no downloadable track list.")

    album_artists = _names(info.get("artists"))
    tracks = []
    for track in info.get("tracks") or []:
        if not isinstance(track, dict):
            continue
        title = track.get("title")
        track_url = track.get("url")
        if not isinstance(title, str) or not title.strip():
            continue
        if not isinstance(track_url, str) or not track_url.strip():
            continue
        tracks.append(
            {
                "title": title.strip(),
                "artist": _names(track.get("artists")) or album_artists,
                "url": track_url.strip(),
            }
        )
    if not tracks:
        _fail("No downloadable tracks were returned for this item.")

    return {
        "type": info.get("type"),
        "title": info.get("title") or "",
        "artist": album_artists,
        "cover": info.get("coverArtwork") or "",
        "tracks": tracks,
    }


def main() -> None:
    if len(sys.argv) != 2:
        _fail("Expected exactly one Amazon Music URL.")
    url = sys.argv[1]
    try:
        payload = asyncio.run(_fetch(url))
    except SystemExit:
        raise
    except Exception as exc:
        _fail(f"Amazon catalog resolver failed ({type(exc).__name__}).")
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
