# HANDOFF — Music pipeline (test_vlsi)

> **Read this first in a new session.** It captures the full state of the
> project as of 2026-10-24: architecture, every file/wrapper/service, verified
> commands, Amazon/lucida internals discovered the hard way, known issues, and
> the refactor checklist for moving everything into `v0/`.
>
> **Context note:** the previous session ended at ~69% context (541k/786k).
> This file exists so a fresh session does not need to re-derive anything.

---

## 1. What this project is

A local **lossless music pipeline**: take playlists/tracks from Spotify,
YouTube, or Amazon Music and download them as FLAC from Amazon's catalog via
[lucida.to](https://lucida.to), organized under `/mnt/Shared/Music`.

Four tools + one download engine:

| Tool | Entry point | Purpose |
|---|---|---|
| `amzn-playlist` | `amzn_playlist.py` | Parse a share link → text list (`Artist - Title` or exact Amazon URLs) |
| `sp2amz` | `sp2amz.py` | Interactive converter: search Amazon per track, human picks version → exact-URL watchlist |
| `spotgrab` | `spotgrab.py` | CLI: grab the currently-playing Spotify track as FLAC (MPRIS) |
| `spotui` | `spotui.py` + `spotui_ui.html` | **Primary UI** (Meta+S): categorized Amazon search, drill-downs, Download all, persistent queue |
| engine | `lucidadl` (pipx) | Actual downloads: parallel jobs, dedup, tags, transcode |

**Unrelated/scratch files** may also sit in the project root (`main.v` VLSI
work, `session.txt`, copied dotfiles, `spotui.tar.gz`) — only
the pipeline files listed above belong to this project.

---

## 2. Paths — absolute truth

| What | Where |
|---|---|
| Project | `/home/divine/Projects/test_vlsi` |
| Music library | `/mnt/Shared/Music` (NTFS, shared with Win11/Ubuntu triple-boot; tooling is Arch-only) |
| Watchlist | `/mnt/Shared/Music/inputs/tracks.txt` |
| lucidadl venv (has Playwright + lucidadl) | `/home/divine/.local/share/pipx/venvs/lucidadl/bin/python` |
| Playwright Chromium | `~/.cache/ms-playwright/chromium_headless_shell-1234` |
| lucidadl state/config/logs | `~/.local/share/lucidadl/` — `state.json`, `clearance.json`, `run.log`, `failed.txt`, `config.json` |
| spotui queue | `~/.local/share/spotui/queue.json` |
| Wrappers | `~/.local/bin/{amzn-playlist,sp2amz,spotgrab,spotui}` |
| systemd user unit | `~/.config/systemd/user/spotui.service` (enabled, active) |
| KDE desktop entry for Meta+S | `~/.local/share/applications/net.local.spotgrab.desktop` (`Exec=/home/divine/.local/bin/spotui open`, `Name=SpotUI`) |
| KDE binding | `~/.config/kglobalshortcutsrc` → `[services][net.local.spotgrab.desktop] _launch=Meta+S` |
| spotgrab debug log | `/tmp/spotgrab-debug.log` |
| Project memory (for Claude) | `~/.claude/projects/-home-divine-Projects-test-vlsi/memory/music-downloader-pipeline.md` |

**Critical:** every script that imports `playwright` or `lucidadl` must run with
the **lucidadl venv python**, not system python. All wrappers already do this
by absolute path.

---

## 3. Quick health check (new session)

```bash
systemctl --user is-active spotui.service          # expect: active
curl -s http://127.0.0.1:8765/api/health           # expect: {"ok": true}
curl -s http://127.0.0.1:8765/api/queue            # current jobs
lucida doctor                                      # lucida.to reachable?
```

UI: <http://127.0.0.1:8765> — Meta+S runs `spotui open`.

**Known pending state at handoff:** queue had **3 failed Tame Impala jobs**
(`Ethereal Connection`, `See You On Monday (You're Lost)`, `Taxi's Here`) from
a user batch — they stay visible with retry buttons (failed jobs are not
auto-pruned). Retry from the UI.

---

## 4. Architecture / data flow

```
Batch:
  share link ─► amzn-playlist / sp2amz ─► /mnt/Shared/Music/inputs/tracks.txt
                ─► lucida tracks -s amazon -j N ─► /mnt/Shared/Music/Artists/...

UI (Meta+S):
  browser ─► spotui (127.0.0.1:8765)
               ├─ search: headless Chromium on music.amazon.in (showSearch JSON)
               ├─ detail: artist = showCatalogArtist JSON
               │           album/editorial playlist = lucida fetch_page_data
               │           community playlist = DOM scrape (scroll)
               └─ queue: persistent JSON, single worker running lucida -j 1
                         ─► notify-send on start/done, auto-prune done after 3s

Instant CLI:
  spotgrab ─► MPRIS (spotifast/Spotify) ─► Amazon resolve ─► lucida ─► notify
```

### Wrapper commands

```bash
amzn-playlist "<url>" [--urls] [--dry-run]  # pinned output /mnt/Shared/Music/inputs/tracks.txt
sp2amz "<url>" | sp2amz -f list.txt         # interactive picker → exact URLs
spotgrab [--dry-run|--status|--to mp3]      # current MPRIS track
spotui open | spotui serve                  # UI launcher / foreground server
```

---

## 5. File-by-file

### `amzn_playlist.py` (`amzn-playlist`)
Extracts track lists. Host-routed:
- **Amazon Music playlist** (`user-playlists/…`): Playwright DOM scrape of
  `music-image-row[primary-text]`, accumulates across scroll passes
  (virtualized list). `--urls` emits exact `/albums/<asin>?trackAsin=<asin>`
  URLs; otherwise `Artist - Title`.
- **Spotify** (`open.spotify.com/...`, `spotify.link`): pure HTTP; parses
  `__NEXT_DATA__` from `open.spotify.com/embed/<kind>/<id>`. Artist = first
  from `subtitle`.
- **YouTube Music** (`music.youtube.com/playlist`): pure HTTP; hex-escaped JSON
  in `initialData.push()` → `musicResponsiveListItemRenderer` flexColumns
  `[title, artists, album]`.
- **YouTube mix** (`youtube.com/watch?list=RD…`): `ytInitialData` →
  `playlistPanelVideoRenderer`; strips `|`-delimited SEO noise.
- `--debug` saves `./debug/page.html` (Amazon only).

### `sp2amz.py` (`sp2amz`)
Interactive converter. Reuses `/home/divine/.local/share/pipx/venvs/lucidadl/lib/python3.14/site-packages/lucidadl/`:
- `downloader._query_variants` — variant walk (full → title-only → primary-artist)
- `api.LucidaClient.search()` — Amazon search
- `AmazonFallbackSearch` — loads `music.amazon.in/search/<q>` in Playwright and
  parses the `showSearch` response (site ranking; finds tracks lucida's search
  misses)
Picker keys: `Enter` = pick #1, `n` = next variant, `s` = skip, `q` = quit.

### `spotgrab.py` (`spotgrab`)
Instant MPRIS grab:
- Player auto-detect via `playerctl -l` (prefers `spotify`, `spotifast`, `spot*`);
  `$SPOTGRAB_PLAYER` override.
- spotifast puts the Spotify URI in `xesam:url`, not `mpris:trackid` — both read.
- Resolve: lucida variants → variant-keyword check (`lofi/unplugged/chillout/…`
  that lucidadl's scorer misses) → Amazon website ranking fallback.
- Download via `lucida tracks -f <tmp> -s amazon -j 1 --hidden`; parses the
  **`Done — OK:X  skipped:Y  failed:Z`** tally (note **double spaces**).
- Start-of-download notification uses `Popen` + `PYTHONUNBUFFERED=1` and the
  `Downloading stream for … to add metadata` line.
- `LUCIDA_BIN` is absolute — KDE shortcuts do not inherit shell PATH.

### `spotui.py` + `spotui_ui.html` (`spotui`)
Local web UI + JSON API. Vanilla HTML/CSS/JS, no build step. Aesthetic:
Fraunces display serif + Archivo, espresso/amber dark theme, grain overlay.

Backend:
- `AmazonSearchWorker` — one headless Chromium pinned to one thread;
  `_capture(url, api_key)` returns the first JSON response matching the API key;
  exposes `search()`, `artist_detail()`, `user_playlist_detail()`.
- Search sections from `showSearch` widget headers:
  **Artists / Albums / Playlists / Community Playlists / Songs** (skips
  Top Results, Stations, Podcasts).
- Details:
  - artist → `showCatalogArtist` (top tracks + albums; strip `^\d+\.\s*`).
  - album + editorial playlist → `lucida_detail()` → `fetch_page_data()` →
    canonical `music.amazon.com/tracks/<ASIN>` URLs.
  - community/user playlist → DOM scrape (lucida can't read those URLs —
    returns `type=None`).
- `LibraryIndex` — reads lucidadl `state.json`; ASIN match (only if a recorded
  path still exists) + title/artist fallback parsed from
  `Artists/<Artist>/<Album>/<Title>.flac`. Refreshed every 10 s.
- `JobQueue` — persistent FIFO (`~/.local/share/spotui/queue.json`), one worker
  runs `lucida tracks -s amazon -j 1 --hidden`, parses phases
  (`Ripping…`, `Fetching…`, `Downloading stream…`, `Fixing…`, `stuck`), tally
  with `OK:(\d+)\s+skipped:(\d+)\s+failed:(\d+)`. Done jobs auto-prune 3 s
  after completion (persisted too). Failed/cancelled stay.
- Notifications via `notify-send` (start + completion).

API (all on `127.0.0.1:8765`):
```
GET  /api/health                     {"ok":true}
GET  /api/now                        MPRIS track or null
GET  /api/search?q=…                 {"sections":[{title,kind,items:[{title,subtitle,url,image,in_library}]}]}
GET  /api/detail?url=…               {"detail":{kind,title,subtitle,image,tracks:[{title,artist,url,image,in_library}],albums:[…]}}
GET  /api/queue                      {"jobs":[{id,title,artist,url,status,message,file,added,updated,finished}]}
POST /api/download                   {url,title,artist} → {id,duplicate}
POST /api/download-batch             {items:[{url,title,artist}]} → {added,duplicates,skipped_library,invalid}
POST /api/cancel                     {id}
POST /api/retry                      {id}
```
`is_track_url` accepts both page URLs (`…?trackAsin=`) and canonical
`music.amazon.com/tracks/<ASIN>/`.

UI: categorized sections; circular artist cards; clickable album/playlist
cards; artist view = hero + Download top tracks + Albums grid + Top tracks;
album/playlist view = hero + Download all + track rows; IN LIBRARY badges;
queue panel with keyed DOM reconciliation (no blinking), cancel/retry,
auto-removal; `?now=1` pre-searches the current MPRIS track.

### Required lucidadl internals (for future work)
Package path: `/home/divine/.local/share/pipx/venvs/lucidadl/lib/python3.14/site-packages/lucidadl/`
- `api.py`: `LucidaClient.search()`, `fetch_page_data()`, `tracks_from_pd()`,
  `start_download()` (POST `/api/load` → `{handoff, server}`),
  `run_job()` (poll `https://<server>.lucida.to/api/fetch/request/<handoff>`
  every 1 s; final `GET <base>/download`).
- `downloader.py`: `_query_variants()`, `_resolve_url()`.
- `matching.py`: `score()`, `pick_best()`; `_BAD_TOKENS` **misses**
  `lofi/lo-fi/unplugged/chillout/mashup/edit` — hence spotgrab's own check.
- `progress.py`: `Reporter`; `run.log` flushes every line; when stdout is a
  pipe Python block-buffers it → set `PYTHONUNBUFFERED=1` for live reads.
- `session.py`: `load_clearance()`, `acquire_clearance()`, `save_clearance()`.

---

## 6. Amazon Music internals (discovered live)

- **Search**: `POST https://eu.web.skill.music.a2z.com/api/showSearch`; response
  `methods[0].template.widgets` with headers **Top Results, Artists, Albums,
  Playlists, Community Playlists, Songs, Stations, Podcasts, Podcast Episodes**.
  Items use `primaryText.text`, `secondaryText`, `primaryLink.deeplink`,
  `image`. Deplinks: `/artists/<id>/<slug>`, `/albums/<asin>`,
  `/albums/<asin>?trackAsin=<asin>`, `/playlists/<id>`, `/user-playlists/<id>`.
- **Album pages**: DOM `music-image-row` elements are empty shells; the payload
  arrives via the generic **`showHome`** response (contains the album tracks).
  We avoid parsing it by using lucida's `fetch_page_data` instead.
- **Artist pages**: `showCatalogArtist` (~3 MB) → top tracks (titles prefixed
  `"1. "`) + albums (subtitles `Album • 2026`, `Single • 2026`).
- **Editorial playlists**: lucida `fetch_page_data` returns `type="playlist"`
  with all tracks and canonical URLs (tested: 100 tracks).
- **Community/user playlists**: lucida returns `type=None, tracks=0` → DOM
  scrape with scroll accumulation is required.
- **ASIN nuance**: a page's `trackAsin` can differ from lucida's canonical
  track ASIN (e.g. Metallica – One: page `B07GT4S98X`, canonical
  `B07XY3RZLC` high-res variant). Hence LibraryIndex's title/artist fallback.
- Amazon Music India domain used: `music.amazon.in`; canonical URLs returned by
  lucida are `music.amazon.com/tracks/<ASIN>`.

---

## 7. Hard-won gotchas (do not relearn these)

1. **Cloudflare cookie** (`~/.local/share/lucidadl/clearance.json`) nominally
   lasts ~2 h. Stale → lucida search silently returns 0 results, or rips fail.
   Fix: `lucida setup` (opens a real browser briefly).
2. **`-F flac` (server-side) is broken on lucida** — `FFMPEG error: Invalid
   downscaling option`. Always use local **`--to flac`** / `--to mp3`.
3. **lucida exits 0 even when tracks fail.** Never trust the exit code; parse
   `Done — OK:X  skipped:Y  failed:Z` (double spaces!). A wrong single-space
   regex marked successful rips as failed once — fixed in both scripts.
4. **`lucida tracks` defaults are CWD-relative** (`./inputs/tracks.txt`); use
   `-f /mnt/Shared/Music/inputs/tracks.txt` or run from `/mnt/Shared/Music`.
5. **KDE Plasma 6 ignores hand-written `kglobalshortcutsrc` / DBus
   registration** for command shortcuts. Bind via *System Settings → Keyboard →
   Shortcuts* only. Meta+S now runs `spotui open` via the desktop entry named
   `net.local.spotgrab.desktop` (keep that filename; the binding points at it).
6. **KDE shortcuts lack shell PATH** → scripts must use absolute paths
   (`LUCIDA_BIN`, wrapper exec paths).
7. **spotifast MPRIS** name is `spotifast`; URI in `xesam:url`; player
   auto-detect handles it.
8. **lucida rate limits / "stuck (>40s without progress)"** are transient
   Amazon-side stalls. Retry the job (UI button) or `lucida retry`.
9. **NTFS** rejects filenames containing `: * ? < > |`; deleted files are
   re-downloaded (dedup only counts existing paths).
10. **Dedup is URL-keyed per service** (qobuz vs amazon = two downloads); page
    `trackAsin` vs canonical ASIN can differ (see §6).
11. **Amazon title/credit mismatch**: Spotify/Bollywood credits the composer
    (`Pritam - Teri Ore`), Amazon credits the singer. Title-only variants fix
    it (`_query_variants`); the UI picker / Amazon-website fallback is the
    reliable path for obscure tracks.
12. **`pipx` venv path on this machine** is
    `~/.local/share/pipx/venvs/lucidadl` (not `~/.local/pipx/venvs`).
13. **NVIDIA/Ozone** etc. irrelevant; UI is a browser tab.
14. **`main.v`** is unrelated VLSI work.

---

## 8. Verified commands / testing recipes

```bash
# UI + queue
systemctl --user restart spotui.service
curl -s "http://127.0.0.1:8765/api/search?q=arijit%20singh" | python3 -m json.tool
curl -s "http://127.0.0.1:8765/api/detail?url=https%3A%2F%2Fmusic.amazon.in%2Fartists%2FB006ZO8YNU%2Farijit-singh" | python3 -m json.tool

# Batch behavior (library + invalid filtering; no downloads)
python3 - <<'EOF'
import json, urllib.request, urllib.parse
B="http://127.0.0.1:8765"
d=json.load(urllib.request.urlopen(B+"/api/detail?url="+urllib.parse.quote("https://music.amazon.in/artists/B006ZO8YNU/arijit-singh")))["detail"]
items=[{"url":t["url"],"title":t["title"],"artist":t["artist"]} for t in d["tracks"] if t["in_library"]][:2]
items.append({"url":"not-a-url","title":"x","artist":"y"})
r=urllib.request.Request(B+"/api/download-batch",data=json.dumps({"items":items}).encode(),headers={"Content-Type":"application/json"})
print(json.load(urllib.request.urlopen(r)))   # expect added 0, skipped_library 2, invalid 1
EOF

# UI screenshots via Playwright (venv python)
~/.local/share/pipx/venvs/lucidadl/bin/python - <<'EOF'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={"width":1280,"height":1000}, device_scale_factor=2)
    pg.goto("http://127.0.0.1:8765/", wait_until="networkidle")
    pg.fill("#q","arijit singh"); pg.press("#q","Enter")
    pg.wait_for_selector(".card.artist", timeout=60000); pg.wait_for_timeout(2000)
    pg.screenshot(path="/tmp/spotui.png", full_page=True); b.close()
EOF

# Batch pipeline (existing)
cd /mnt/Shared/Music && lucida tracks -s amazon -j 8
lucida retry
```

Screenshots from the previous session: `/tmp/spotui_search.png`,
`/tmp/spotui_artist.png`, `/tmp/spotui_album.png`, `/tmp/spotui_batch.png`.

---

## 9. Tools / skills / MCPs used in the build

- **Shell/tools:** Bash (`dangerouslyDisableSandbox: true` was required for
  network, `~/.local`, `/mnt/Shared`, systemd, browsers), Read/Write/Edit,
  TaskCreate/TaskUpdate, AskUserQuestion, WebSearch/WebFetch (initial research),
  `curl`, `python3` stdlib, `pipx`, `systemctl --user`, `notify-send`,
  `playerctl`, `kwriteconfig6`/`qdbus6` (failed route — do not repeat),
  `xdg-open`.
- **Playwright** (via lucidadl venv) for: Amazon scraping in all tools, UI
  screenshot testing, and network-response capture.
- **Skill used:** `frontend-design:frontend-design` — guided the spotui dark
  hi-fi aesthetic (Fraunces + Archivo, espresso/amber, grain overlay).
- **No handoff-specific skill is registered in this environment.**
- **REA MCP** (170 tools, rea 6.4.0, Ghidra/Hopper/IDA providers) is installed
  and was health-checked, **but not used** for project work — Amazon's data was
  obtained via Playwright network capture, which is the better tool here.
  Ghidra was never invoked.
- **Project memory** (already updated):
  `~/.claude/projects/-home-divine-Projects-test-vlsi/memory/music-downloader-pipeline.md`
  → read it in a new session; it mirrors the essentials of this file.
- **Graphics/browser skills unused:** graphify, ui-ux-pro-max, dataviz, etc.
- No test framework; verification was live HTTP/API/Playwright/manual.

---

## 10. Planned refactor → `v0/` (NOT done)

User will move the project files into `/home/divine/Projects/test_vlsi/v0/`.
Do **not** assume paths in this handoff remain valid afterwards. Refactor
checklist:

1. Move `amzn_playlist.py`, `sp2amz.py`, `spotgrab.py`, `spotui.py`,
   `spotui_ui.html`, `readme_v0.md`, `readme_lucidiadl.md`, `handoff.md` (and
   `inputs/` if present) into
   `v0/`. Leave `main.v` where the user wants it.
2. Update wrapper scripts in `~/.local/bin/`:
   - `amzn-playlist` → new `v0/amzn_playlist.py` path
   - `sp2amz` → new `v0/sp2amz.py`
   - `spotgrab` → new `v0/spotgrab.py`
   - `spotui` → new `v0/spotui.py`
3. Update `~/.config/systemd/user/spotui.service`:
   `WorkingDirectory=` and `ExecStart=` → new `v0` paths; then
   `systemctl --user daemon-reload && systemctl --user restart spotui`.
4. KDE desktop entry can stay pointed at `~/.local/bin/spotui open` (wrapper),
   so no rebind needed if wrappers are updated. Do not rename the desktop file
   (`net.local.spotgrab.desktop`) or the Meta+S binding is lost.
5. `spotui.py` resolves `UI_FILE = ROOT / "spotui_ui.html"` and
   `sys.path.insert(0, ROOT)` (imports `spotgrab`) — moving both together keeps
   this working.
6. Update this handoff and the Claude memory file with the new paths.
7. Re-verify: health endpoint, a search, an artist detail, a batch skip test,
   and one real download.

---

## 11. Known issues / TODO

- Failed jobs (3 Tame Impala) linger in the queue until retried — by design.
- `amzn-playlist` wrapper's **comment** still says `~/Music/inputs` while the
  actual path is `/mnt/Shared/Music/inputs` (cosmetic only).
- spotgrab's start-of-download notification was implemented but the Meta+S
  path is now spotui; spotgrab is CLI-only. Consider re-testing its two-notify
  behavior after any changes.
- The UI depends on the lucida cookie only for album/editorial-playlist detail
  and all downloads. Search, artist detail, and community-playlist detail work
  without it.
- `LibraryIndex` matches by title+artist from organized paths; playlist-organized
  files (`Playlists/…`) are intentionally skipped for the title fallback (no
  artist in path). If the user starts organizing by playlists, revisit.
- Music library uses NTFS; 41 state paths were missing at handoff (files
  deleted by the user) — that is correct dedup behavior, not a bug.
- Amazon playlist detail (editorial) returns up to 100 tracks; very large
  playlists may need pagination (not implemented).
- No auth on the local server (bound to 127.0.0.1 only).

---

## 12. Session results worth keeping

- First playlist (17 tracks) downloaded → 1.1 GB FLAC; later verified
  Spotify, YouTube Music, YouTube mix, editorial playlist, community playlist,
  artist, and album flows.
- UI fixes verified live: keyed reconciliation (same DOM node across polls — no
  blinking), done-job auto-prune (~3 s + prune tick), duplicate prevention,
  cancel, retry, batch library skipping.
- Version-accuracy fix verified with `Suna Suna`: lucida picked
  `(Raahi LoFi)`; variant detection + Amazon ranking returned the original
  (`Suna Suna (From "Krishna Cottage")`, 43.6 MB FLAC).
- Architecture choice proven: Amazon website search (`showSearch`) has the
  correct ranking; lucida's search does not. The UI picks human-verified exact
  tracks and queues canonical URLs, eliminating search guessing.
