# Music Pipeline — Spotify/YouTube/Amazon → Lossless FLAC

> **New session / after moving files? Read [`handoff.md`](./handoff.md) first** —
> it has the full architecture, paths, commands, gotchas, and the `v0/` refactor
> checklist.

Turn playlists from any streaming service — and individual songs the moment you
hear them — into a local **lossless FLAC** collection in `/mnt/Shared/Music`
(an NTFS partition shared with your Windows/Ubuntu boots), without any
subscription. Everything downloads from Amazon's lossless catalog via
[lucida.to](https://lucida.to).

Four tools, one pipeline:

| Tool | What it does | When you use it |
|------|--------------|-----------------|
| **`amzn-playlist`** (`amzn_playlist.py`) | Parses a share link → `Artist - Title` list (or exact Amazon URLs) | Batch: pull a whole playlist/album |
| **`sp2amz`** (`sp2amz.py`) | Interactive converter: searches each track on Amazon, you pick the right version → exact-URL `tracks.txt` | Batch, when search matching matters |
| **`spotgrab`** (`spotgrab.py`) | CLI: grabs the song currently playing in your Spotify client as FLAC | Single track, instant (terminal) |
| **`spotui`** (`spotui.py` + `spotui_ui.html`) | Local web UI: categorized Amazon search (artists/albums/playlists/songs), drill-downs, Download all, queue | **Meta+S** — the everyday path |

All of them download via **[lucidadl](https://github.com/Jude-A/lucidadl)** — the
`yt-dlp` of lucida.to (parallel downloads, dedup, retries, tags, transcode).

Why Spotify → Amazon: Spotify's own streams aren't lossless. Re-ripping via
Amazon gives you FLAC copies of your Spotify collection.

```
Batch flow:
  share link ──► amzn-playlist / sp2amz ──► /mnt/Shared/Music/inputs/tracks.txt
                    ──► lucida tracks -s amazon ──► /mnt/Shared/Music/Artists/...

Hotkey flow (Meta+S in KDE):
  press Meta+S ──► spotui opens (pre-searched for the playing track)
  pick the exact Amazon result ──► queued ──► FLAC + notification

Instant CLI flow:
  spotgrab ──► resolve on Amazon ──► FLAC + notification
```

---

## Why this exists

Amazon Music's playlist page is a JavaScript-only app (`ssr: false`) — there is
**no public API**. The legacy `/api/playlists/<id>` endpoint returns 404, and
track data arrives via private internal calls. The scraper bypasses all of that
by driving a headless browser and reading the rendered `<music-image-row>` web
components (which carry title/artist/album/ASIN in their attributes),
auto-scrolling because the list is *virtualized* (rows exist only while visible).

The other sources are lighter:
- **Spotify** — the public `/embed/` page ships the full track list in its
  `__NEXT_DATA__` JSON. Pure HTTP, no browser.
- **YouTube Music** — the page bundles data as hex-escaped JSON in
  `initialData.push()` calls; entries are `musicResponsiveListItemRenderer`
  with clean `[title, artists, album]`. Pure HTTP.
- **YouTube mixes** — `ytInitialData` blob; titles carry pipe-delimited SEO
  noise (`Song | Movie | Actor | Label`), stripped to the first segment.

lucida.to itself has no playlist support for Amazon (only tracks/albums) — the
text-list bridge is the missing piece.

---

## Prerequisites

- **Arch/KDE desktop session** — for the Cloudflare pass and the hotkey
- **Python 3.10+**, **pipx**
- **`playerctl` + `libnotify`** (for `spotgrab`): `sudo pacman -S playerctl libnotify`
- A Spotify client that speaks MPRIS — the official client, or a FOSS fork
  like [spotifast](https://github.com/crmne/spotifast) (both work; `spotgrab`
  auto-detects the player)

## Installation

```bash
# 1. Install lucidadl (brings the `lucida` command + the Playwright library)
pipx install lucidadl

# 2. Download the headless Chromium browser (~115 MB) into the lucidadl venv
~/.local/share/pipx/venvs/lucidadl/bin/python -m playwright install chromium

# 3. Verify
lucida doctor        # should print "✓ lucida.to reachable"
```

> If pipx put the venv elsewhere (`pipx environment` shows `PIPX_LOCAL_VENVS`),
> adjust step 2 accordingly. All three wrapper commands already invoke the venv
> python by absolute path, so nothing else to configure.

## One-time setup

**1. Cloudflare pass** — lucida.to sits behind Cloudflare; plain HTTP gets a
`403`. lucidadl solves the challenge once in a real browser and caches the
cookie:

```bash
lucida setup
```

A browser window opens and closes automatically. Re-run if you ever see
*"Cloudflare not cleared"*. ⚠️ **The cookie expires after ~2 hours** — a stale
cookie makes lucida's search silently return 0 results (the tell-tale sign).

**2. spotui service + KDE hotkey** — the hotkey opens the picker UI, which is
already wired to a systemd user service:

```bash
systemctl --user enable --now spotui.service
```

*System Settings → Keyboard → Shortcuts → Add New… → Command or URL*
- Comment: `SpotUI`
- Trigger: `Meta+S`
- Action: `/home/divine/.local/bin/spotui open`

(The current install already has this bound — the desktop entry is
`~/.local/share/applications/net.local.spotgrab.desktop`.)

> Plasma 6 ignores hand-written `kglobalshortcutsrc` entries — the GUI is the
> only reliable way to bind a new command shortcut.

---

## Quick start — batch (whole playlists)

```bash
# 1a. Fire-and-forget: scrape + auto-pick every track
amzn-playlist "<link>" --urls            # Amazon playlist — exact URLs, best precision
amzn-playlist "<spotify/ytmusic/yt-mix link>"   # Spotify/YouTube — Artist - Title lines

# 1b. Interactive: for each track, pick the right version from candidates
sp2amz "<spotify/ytmusic/amazon link>"   # Enter = first candidate, n = next variant,
                                         # s = skip, q = quit → exact Amazon URLs

# 2. Download everything (dedup: only new tracks come down)
cd /mnt/Shared/Music && lucida tracks -s amazon -j 8
```

Files land in `/mnt/Shared/Music/Artists/<Artist>/<Album>/` as FLAC with tags.
`--to flac` is implicit in nothing — lucida's default is `original`, which for
Amazon is FLAC whenever the catalog has it. (`-F flac` server-side is **broken**
on lucida; always use local `--to flac` if you want a guaranteed container.)

## Quick start — hotkey (single tracks & more)

Play a song in your Spotify client → press **Meta+S** → the UI opens with the
song pre-searched on Amazon → click **↓** on the exact version you want → it's
queued and downloads in the background. The queue runs one job at a time, so
clicking another song never interrupts the one in flight.

The same window is a full Amazon Music browser: search any **artist, album, or
playlist**, click a card to open it, then grab individual tracks or hit
**Download all / Download top tracks** (tracks already in the library are
badged and skipped). Nothing downloads unless you click — autoplay is ignored.

```bash
spotui open          # what Meta+S runs: ensure server + open the UI
spotui serve         # run the server in the foreground (debug)
```

Instant, no-picker CLI alternative (auto-picks the best search match):

```bash
spotgrab             # grab the currently playing song as FLAC
spotgrab --status    # show what MPRIS currently reports (debug)
spotgrab --dry-run   # resolve only, print the Amazon URL, no download
spotgrab --to mp3 --bitrate 320k
```

Both auto-detect the player via `playerctl -l` (prefers `spotify`,
`spotifast`, then any `spot*`). Override with `SPOTGRAB_PLAYER=<name>`.

---

## Tool reference — `amzn-playlist`

```
amzn-playlist "<link URL>" [options]

  -o, --out PATH   output file (default: /mnt/Shared/Music/inputs/tracks.txt)
  --dry-run        print the list instead of writing it
  --urls           emit Amazon track URLs (…/albums/X?trackAsin=Y) instead of
                   "Artist - Title" (Amazon links only)
  --debug          save the rendered page to ./debug/page.html (Amazon only)
```

- **Inputs:** Amazon Music playlist · Spotify album/playlist (`open.spotify.com`
  or `spotify.link`) · YouTube Music playlist (`music.youtube.com/playlist`) ·
  YouTube mix (`youtube.com/watch?list=RD…`). Host-routed automatically.
- **`--urls` (Amazon only)**: search-based matching can pick the wrong version
  (a real case: `Metallica - One` matched a James Newton Howard cover). Exact
  URLs from the page's own `trackAsin` attributes resolve the exact track.
- YouTube mixes cap at ~25 tracks per page load; YT Music lists 50.
- Getting an Amazon share link: playlist → `⋯` → **Share** (viewing the list
  needs no login; downloads go through lucida, no Amazon account at all).

## Tool reference — `sp2amz`

The interactive "Spotify/YouTube → Amazon converter". For every track in the
source it searches Amazon (lucida search with lucidadl's own query-variant walk
— full "Artist - Title", then title-only, then primary-artist — which fixes the
Bollywood composer-vs-singer credit mismatch), shows up to 10 candidates, and
you pick. Output is exact `music.amazon.com/tracks/<ASIN>` URLs — what you pick
is what downloads, no re-search.

```
sp2amz "<link>"            # parse + pick everything
sp2amz -f some_tracks.txt  # re-pick from an existing title list (fix stragglers)
sp2amz --dry-run "<link>"  # list queries without prompting

pick prompt:  Enter = pick #1 · n = next search variant · s = skip · q = quit
```

**Amazon website fallback:** when lucida's search finds nothing (its API misses
tracks Amazon's own site search returns — e.g. `Bulleya`, `Teri Ore`), `sp2amz`
loads Amazon's own search page in the background and offers its results — the
same list you see typing into the box on music.amazon.in.

## Tool reference — `spotui`

The everyday path: a local web UI at `http://127.0.0.1:8765` that searches
**Amazon's own website** (headless Chromium, same results you see searching
manually) so the right version is one click away. Downloads use a persistent
single-worker queue.

**Categorized search** — results are grouped like Amazon Music itself:
**Artists** (circular cards), **Albums**, **Playlists**, **Community
Playlists**, and **Songs** (with individual ↓ buttons). Already-owned tracks
carry an **IN LIBRARY** badge (matched by canonical ASIN, falling back to
title + artist from the organized file paths — page-level `trackAsin`s can
differ from lucida's canonical high-res ASIN).

**Drill-downs** — click any card:
- **Artist** → top tracks + album grid; *Download top tracks (N)* at the top
  (skips tracks already in the library).
- **Album** / **editorial playlist** → full track list via lucida's own
  resolver (canonical `music.amazon.com/tracks/<ASIN>` URLs — no search
  guessing); *Download all (N)* at the top.
- **Community/user playlist** → scraped from the rendered rows (lucida can't
  read those URLs), same Download-all behavior.

**Queue** — every ↓ / Download-all pushes exact URLs onto
`~/.local/share/spotui/queue.json` (survives restarts). The worker runs
`lucida tracks -s amazon -j 1` one job at a time, so a new request never
interrupts the download in flight. Batch adds skip library tracks; duplicates
while active are rejected.

**Statuses** — queued → ripping → downloading → done/failed, parsed from
lucida's own phase output. Failed jobs get a retry button; queued jobs can be
cancelled. Finished jobs remove themselves after ~3 s (server-side, so they
don't reappear on refresh); failed jobs stay until retried.

**Notifications** — `notify-send` on download start and completion, so the UI
can stay in the background.

The server is a systemd user service (`spotui.service`); `spotui open` ensures
it's running and opens the UI. `spotui serve` runs it in the foreground for
debugging.

## Tool reference — `spotgrab`

Single-track hotkey grabber: MPRIS metadata → resolve on Amazon → download.

**Version accuracy** (learned the hard way): lucidadl's scorer doesn't penalize
`lofi / unplugged / chillout / mashup / edit`, so it picked `Suna Suna (Raahi
LoFi)` over the original. `spotgrab` re-checks the pick against its own variant
keyword list and, on suspicion, defers to **Amazon's website ranking** (which
puts the original first). The notification shows the *actual* grabbed title,
and parses lucida's `Done — OK:X failed:Y` tally (lucida exits 0 even when a
rip fails — never trust its exit code).

**Timing:** the grab is silent while working — resolve ~5–10 s, rip 30 s–2 min,
notification at the end. Output is mirrored to `/tmp/spotgrab-debug.log` (the
only record for hotkey invocations, which have no terminal).

## Downloading — `lucida` commands

Singular commands (`track`, `album`) download immediately; plural ones
(`tracks`, `albums`) are *watchlists*: read a file, skip what's done, meant for
repeat runs. `tracks` reads `./inputs/tracks.txt` relative to CWD (override
with `-f`).

```bash
cd /mnt/Shared/Music && lucida tracks -s amazon          # the main command
cd /mnt/Shared/Music && lucida tracks -s amazon -j 8     # 8 parallel (default 3, max 20)
lucida retry                                             # retry failed items (anywhere)
lucida ui                                                # interactive menu
lucida album "https://music.amazon.in/albums/B074W6SYVJ" -s amazon   # albums work natively
```

### Useful options

| Flag | Effect |
|------|--------|
| `-s, --service` | `qobuz` (default) or `amazon`; falls back to the other automatically |
| `-j, --jobs N` | parallel downloads, 1–20 (default 3; 5–8 is the practical sweet spot) |
| `-F, --format` | lucida **server-side** conversion — `flac` is broken, stick with `original` |
| `--to FMT` | **local ffmpeg transcode** (the reliable one): `flac` · `mp3` · `aac` · `opus` · `ogg` · `wav`. No-op if the source is already that format. |
| `--bitrate` | e.g. `320k` (only with `--to`) |
| `--keep-original` | keep the source next to the transcoded file |
| `--force` | ignore dedup memory, re-download |
| `--organize / --flat` | `Artists/<Artist>/<Album>/` (default) vs. flat |

Example: 320 kbps MP3s instead of FLAC:
`lucida tracks -s amazon --to mp3 --bitrate 320k -j 8`

## Where files live

| What | Where |
|------|-------|
| Music | `/mnt/Shared/Music` (NTFS, shared with Win11/Ubuntu — all OSes can play the library; the *tooling* is Arch-only) |
| State/dedup/log | `~/.local/share/lucidadl/` — `state.json`, `run.log`, `clearance.json`, browser profile |
| Watchlist inputs | `/mnt/Shared/Music/inputs/tracks.txt` (pinned by the wrappers) |
| spotui queue | `~/.local/share/spotui/queue.json` (survives restarts) |
| Tool sources | `~/Projects/test_vlsi/` — `amzn_playlist.py`, `sp2amz.py`, `spotgrab.py`, `spotui.py`, `spotui_ui.html` |
| Tool wrappers | `~/.local/bin/` — `amzn-playlist`, `sp2amz`, `spotgrab`, `spotui` |
| spotui service | `~/.config/systemd/user/spotui.service` (enabled at login) |

**NTFS notes:** case-insensitive (harmless here); filenames with `: * ? < > |`
are rejected by the ntfs3 driver — rare, but a song titled `Who?` fails to
write.

## Watchlists & dedup

- `lucida tracks` records every finished download in `state.json`. Re-running
  downloads **only what's new** — re-scrape after editing a playlist and only
  new tracks come down.
- Dedup keys are lucida's canonical per-service URLs — the same song resolved
  from qobuz vs amazon counts as two downloads.
- A file you *deleted* is re-downloaded (dedup tracks files, not history).
- `--force` ignores the memory; collisions on disk get `(1)` suffixes, never
  overwrites.
- Amazon playlists: 2,500 tracks max — the scraper handles any size (scroll
  passes ~4 s each).

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `"Cloudflare not cleared"` | `lucida setup` (cookie expired after ~2 h) |
| Search suddenly returns 0 for everything | Stale Cloudflare cookie — same fix |
| `"Executable doesn't exist"` | `playwright install chromium` in the lucidadl venv |
| `ERROR: no track rows found` | Amazon changed its UI → `--debug`, inspect `./debug/page.html` |
| Everything in `Unknown Artist/Unknown Album` | `mutagen` missing: `<venv-python> -m pip install mutagen` |
| Meta+S does nothing | `systemctl --user status spotui`; try `spotui open` in a terminal. If the service is down, `systemctl --user restart spotui` |
| spotui search fails | The service needs Playwright Chromium in the lucidadl venv — same install step as above; check `journalctl --user -u spotui -n 50` |
| Queue job stuck at "queued" | Only one worker runs; a previous job is still active. Check the queue panel or `systemctl --user status spotui` |
| Queue job failed | Transient lucida/Amazon stall — click retry in the UI, or `lucida retry` |
| "Now" does nothing | No MPRIS player — start spotifast/Spotify, then retry. `playerctl -l` should list it |
| Instant grab "takes forever" | Normal — resolve 5–10 s, rip 30 s–2 min, notification only at the end |
| Wrong version downloaded | Use **spotui** and pick the exact Amazon result (this is why the UI exists) |
| Playlist shows in browser but scrape gets 0 | Playlist must be **public** (the share link must work in a private window) |

## Extending: one-command playlists

If you want `lucida playlist "<amazon url>"` natively (no script step), lucidadl
documents the extension points: scraping lives in `lucidadl/api.py` —
`playlist_tracklist()` picks a scraper by link host, `applemusic_tracklist()` is
the reference, and `_scrape_playlist()` + `_PLAYLIST_SOURCES` is a generic
selector table gated behind `_PLAYLIST_OTHERS_ENABLED`. The DOM extraction in
`amzn_playlist.py` (`music-image-row[primary-text]` + scroll accumulation) ports
into that file almost verbatim.

## Legal

Personal-use software in the spirit of `yt-dlp`. lucida.to is a third-party
service with its own terms; ripping DRM streams from streaming platforms is a
gray area in most jurisdictions. Use for content you're entitled to download
and don't distribute what you download. Not affiliated with lucida.to, Amazon,
Spotify, or YouTube.
