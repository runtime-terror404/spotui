# Baseline Audit and Phase 0 Record

- **Audit date:** 2026-10-26
- **Reference implementation:** `scrap/v0/` (immutable, read-only)
- **Architecture authority:** `scrap/refactor.md`

This record captures the observed starting point for the refactor. It does not
restate the target architecture or add requirements. Behavioral detail remains
in `scrap/v0_architecture.md` and `scrap/handoff.md`; the approved visual design
is `scrap/new_ui.md`. The legacy tree and reference notes are intentionally kept
outside version control under the local `scrap/` directory.

## 1. Source inventory

`v0/` was gitignored and untracked at audit time; it has since been archived at
`scrap/v0/`. None of these files were modified during this phase.

| File | Lines | SHA-256 | Parse check |
|---|---:|---|---|
| `v0/spotui.py` | 897 | `2cd0dde5c3c6300d67fdd87614a73f1fd1a497bed9cdedbd5d2ef851c783da95` | Python AST parses |
| `v0/spotui_ui.html` | 594 | `b4a34595518049f21cc1c1981594be2b1b3cb43bf32a830e5c813fc9b885254f` | — |
| `v0/spotgrab.py` | 300 | `84ec53c4216c0bb087fa61f1b9bfdfd82a0959f22a7cd79dde913312b15c4b20` | Python AST parses |
| `v0/sp2amz.py` | 323 | `283502c6e3a2451901feeb21ef0a628ceafc9fde445b720d953ebda9e95c3bb0` | Python AST parses |
| `v0/amzn_playlist.py` | 371 | `3cfccc592fc91dc426c08393a9488b462028e8d98d0c45325fee97f819838d4d` | Python AST parses |

`v0/session.txt` is unrelated session scratch data. The new `src/spotui/` and
`tests/` trees contain no imports from `v0/`.

## 2. Recorded baseline behavior

- HTTP service: `127.0.0.1:8765`, one `AmazonSearchWorker` Playwright thread,
  one sequential download worker, JSON queue at
  `~/.local/share/spotui/queue.json`.
- Downloader invocation: `lucida tracks -f <temporary-file> -s amazon -j 1
  --hidden`, one track URL per job. Success is parsed from the downloader's
  `Done — OK:X  skipped:Y  failed:Z` tally, not from the exit code alone.
- Queue statuses in `v0/`: `queued`, `running`, `downloading`, `done`,
  `failed`, `cancelled`. Completed jobs are pruned after roughly three
  seconds; failed and cancelled jobs remain.
- API surface in `v0/`: `/api/health`, `/api/now`, `/api/search`,
  `/api/detail`, `/api/queue`, `/api/download`, `/api/download-batch`,
  `/api/cancel`, `/api/retry`, plus `/` for the single-file UI.
- Search and detail resolution: Amazon website search/detail JSON via headless
  Chromium, lucida page resolution for albums and editorial playlists, DOM
  scrolling for community playlists.
- Library matching: lucidadl `state.json` ASIN match plus title/artist fallback
  from organized `Artists/<Artist>/<Album>/<Title>` paths.
- Launcher behavior: `spotui open` attempted a systemd user service, then used
  a detached fallback process, then opened `?now=1`.

At audit time the old server was not running (`curl` to port 8765 was refused),
and the sandbox could not query the user systemd bus. The handoff record is the
source for the last known deployment state; it was not re-verified live.

## 3. Runtime paths

| Data | Baseline location |
|---|---|
| Queue JSON | `~/.local/share/spotui/queue.json` |
| UI file | next to `v0/spotui.py` |
| lucidadl state | `~/.local/share/lucidadl/state.json` |
| lucidadl clearance/config/log | `~/.local/share/lucidadl/` |
| Music library | `/mnt/Shared/Music` (configured in lucidadl) |
| Watchlist | `/mnt/Shared/Music/inputs/tracks.txt` |
| Wrappers (outside repo) | `~/.local/bin/{amzn-playlist,sp2amz,spotgrab,spotui}` |
| systemd unit (outside repo) | `~/.config/systemd/user/spotui.service` |

The new application uses XDG-derived paths (see `spotui.paths`), not these
legacy locations. A legacy queue importer is deliberately deferred to the
documented migration phase.

## 4. Environment and capability audit

| Component | Observed |
|---|---|
| Host | Arch Linux, kernel 7.2.11 |
| System Python | 3.14.8 |
| uv | 0.13.5 |
| Node / npm | 26.12.0 / 12.2.1 (not used by the backend) |
| SQLite | 3.54.0 |
| pytest (system) | 9.1.1 |
| lucidadl | 1.0.0 in `~/.local/share/pipx/venvs/lucidadl` |
| Playwright in lucidadl env | 1.62.0 |
| mutagen in lucidadl env | 1.48.1 |
| Playwright Chromium cache | `~/.cache/ms-playwright/chromium-{1234,1248}` and headless shells |

`lucida --version`, `lucida --help`, and `lucida config` were verified. The
help output confirms the required commands (`setup`, `doctor`, `tracks`,
`retry`, `config`, and others). `lucida config` reported music
`/mnt/Shared/Music` and lucidadl data `~/.local/share/lucidadl`.

`lucida doctor` was attempted, but its Playwright launch failed inside the
execution sandbox (`socket() failed: Operation not permitted`, read-only
Chromium crash directories). This is an environment restriction rather than
evidence about the package. A live doctor/browser check and representative
download-output capture remain Phase 4 verification work.

No download was started during the audit. Downloader output shapes for success,
partial failure, already-downloaded, and cancellation still need to be captured
with the pinned release before progress parsing is implemented.

**Downloader pin:** `lucidadl 1.0.0` is pinned provisionally in
`spotui.deps.SUPPORTED_LUCIDADL_VERSION`. The release decision remains subject
to the Phase 4 output/behavior capture.

## 5. Phase 0 gate assessment

| Gate item | Status |
|---|---|
| Original implementations live in `v0/` | Pass (present, hashes above) |
| `v0/` unchanged by this work | Pass |
| New code imports nothing from `v0/` | Pass |
| Baseline behavior and runtime locations recorded | Pass (this document plus the referenced architecture/handoff docs) |
| Baseline fixtures captured | **Deferred** — provider fixtures require live capture; none exist in `v0/`. Capture in Phases 3 and 7. |
| Old server live-run verification | **Not performed** — service was down and sandbox blocks systemd/browser access. |

## 6. Phase 1 verification results

Phase 1 acceptance was checked with automated tests, a foreground process smoke
test, and a clean-wheel install:

- 117 pytest tests pass; `ruff check .` is clean; `uv lock --check` passes.
- XDG paths, configuration precedence, validation, structured/rotating logs,
  redaction, and process locking are covered by unit tests.
- Alembic upgrade/downgrade on an empty SQLite database is tested, including
  the partial unique active-track index, model/migration drift, and the
  developer `alembic.ini` workflow.
- FastAPI startup requires a current database, serves `/api/v1/health` and the
  packaged placeholder, attaches request IDs, and disposes resources on
  shutdown.
- Listener planning binds loopback only by default, adds LAN only for a
  matching configured IPv4 interface, and never uses `0.0.0.0`. A two-socket
  bind test covers the dual-listener mechanism.
- A subprocess test verifies foreground startup, health, one-instance refusal,
  graceful shutdown, lock release, and restart. A manual foreground smoke run
  additionally confirmed:
  - `spotui db upgrade`/`current` work;
  - health and the placeholder are served, and a supplied request ID is echoed;
  - a second process is refused with the running URL/pid;
  - a second data directory reports a clear port collision;
  - SIGTERM logs a clean uvicorn/lifespan shutdown, releases the OS lock, and
    leaves no listener (the shell observes the normal `143` signal exit).
- The wheel and sdist include the placeholder, Alembic environment, first
  migration, and migration template. Installing the wheel into a fresh venv
  and running `db upgrade` plus `serve` succeeded without the source tree.
- Only loopback was available in the sandbox, so live LAN binding was not
  exercised. LAN selection remains covered by injected-interface tests.

## 7. Known gaps carried forward

- No trusted-LAN interface was available in the audit sandbox; LAN bind behavior
  is covered by injected-interface unit tests, not a live network test.
- Amazon fixtures remain synthetic; routine tests use mocks rather than live
  provider responses. Spotify embed parsing has saved synthetic fixtures and
  was also exercised against live public pages.
- Appearance/accessibility preferences in Settings and the installer/release
  tooling are not implemented yet.
- `lucidadl` download output capture and the final release pin remain
  outstanding.
- Live MPRIS reads were exercised against a paused `spotifast` session during
  the clean-install check. Missing `playerctl`, no players, and player errors
  remain covered by tests and are non-fatal.
- Library roots are configured through TOML/environment settings; the approved
  UI design has no dedicated library-management screen. Root availability and
  scan progress are available through the library API.
- Legacy queue migration, systemd helper, and release automation are later
  phases.

## 8. Phase 2–8 completion

Phase 2 (persistence and API base) is complete for the base layer:

- The initial `download_jobs` schema and active-job uniqueness constraint are
  in place. Later migrations add job attempts, the library index, Spotify
  import/session/candidate tables, and paired-device credentials.
- API routing remains under `/api/v1`, with typed health and error schemas.
- API failures use RFC 9457 `application/problem+json` with stable error codes,
  a request-ID extension, safe validation details, and redacted logging.
- API fixtures and tests cover the problem contract, validation, HTTP errors,
  unexpected exceptions, and OpenAPI versioning.

Phase 3 (search and entity details) is complete for the adapter/UI layer:

- Strict Amazon URL parsing restricts https requests to `music.amazon.com` and
  `music.amazon.in` and classifies artist/album/playlist/community/track paths.
- A serialized Playwright worker handles Amazon search, artist detail, and
  community-playlist scrolling. Pure parsers are covered by synthetic fixtures.
- Album/editorial-playlist detail runs through a packaged JSON bridge executed
  by the managed lucidadl Python, preserving the environment separation.
- Search caching, typed catalog schemas, `/api/v1/search`, and
  `/api/v1/entities/detail` are implemented with provider error mapping.
- The React/TypeScript/Vite UI implements the search and entity-detail flows,
  inline loading/error/empty states, back-navigation restoration, keyboard
  focus, responsive layout, and light/dark tokens. Queue was enabled in Phase 4;
  Settings was enabled in Phase 8 for trusted-network access management.
- The Vite build writes into `src/spotui/web/dist/`; hatchling packages those
  generated assets into both wheel and sdist. A clean wheel install served the
  built frontend and assets successfully.

Routine tests use mocked providers; no live Amazon request was exercised in the
sandbox. The generated provider fixtures are synthetic, not captured live
responses. `spotui deps check` reports the SpotUI Playwright/Chromium runtime
and the managed downloader status.

Phase 4 (download queue and worker) is complete for the implementation layer:

- Migration `0002` adds job-attempt history with foreign-key cleanup, unique
  attempt numbers, terminal outcomes, and prior-schema upgrade coverage.
- A transactional repository enforces idempotent enqueue, active-track
  uniqueness, FIFO claiming, attempts, retry, cancellation requests, terminal
  states, and restart recovery. Interrupted active jobs never restart
  automatically; pending queued jobs remain queued.
- The managed lucidadl adapter starts only its exact executable/process group,
  parses documented phase/summary lines with bounded state, ignores unreliable
  percentages, escalates graceful cancellation to forced termination, preserves
  partial files, and never kills unrelated processes.
- The single worker supports bounded job timeout, shutdown grace, explicit
  cancellation, restart interruption, and explicit retry. One download runs at
  a time.
- Typed queue APIs cover snapshot/get/enqueue/batch/cancel/retry with
  problem-details mapping. Batch enqueue preserves the legacy library-skip
  behavior.
- A compatibility library index restored in-library badges and batch skip
  behavior from lucidadl's completed state without modifying media. This was
  superseded by the durable multi-root index in Phase 6.
- The React UI adds individual/bulk download actions, a compact desktop queue
  panel, a full queue manager, responsive mobile navigation, status messaging,
  cancellation/retry, and short-lived snackbars. It deliberately shows no
  percentages or unsupported removal/history controls.

Live downloader output capture and the final lucidadl pin remain outstanding:
no managed environment/download was run in the sandbox. The queue UI currently
polls every 1.5 seconds rather than using SSE. Tablet queue drawer and phone
bottom-sheet presentations remain UI-polish follow-ups; the queue workspace is
available on all sizes.

Phase 5 (MPRIS/Now Playing) is complete for the adapter/API/UI layer:

- A `playerctl` adapter discovers players, prefers Spotify-compatible names,
  supports `SPOTUI_MPRIS_PLAYER` (and legacy `SPOTGRAB_PLAYER`) overrides, and
  maps missing binaries, timeouts, and absent players to typed availability
  states instead of exceptions. No desktop session is required at startup.
- `NowPlayingService` and typed `GET /api/v1/now-playing` expose `available`,
  optional track title/artist/track ID, player, and reason. The API route omits
  absent fields while preserving explicit unavailability.
- The frontend header action refreshes current metadata every 10 seconds,
  displays the current title on desktop, and searches Amazon by track title when
  activated. Unavailable states surface a non-blocking snackbar.
- Backend tests cover player discovery, preference, overrides, parsing,
  timeouts, missing binary/player, and API responses. Frontend tests cover the
  client contract, current-track search, and unavailable feedback. The
  production build was also checked at desktop and mobile widths with a mocked
  current track.

Final checks: 271 backend tests and 20 frontend tests pass; `ruff`, the
TypeScript typecheck, and the Vite production build are clean. A clean wheel
install served the generated assets and returned the live paused `spotifast`
track through `/api/v1/now-playing`, confirming the real `playerctl` adapter
path. The missing-playerctl and idle-player branches remain mock-verified.

Phase 6 (durable library index) is complete for the persistence/scanner/API
layer:

- Migration `0003` adds `library_roots`, `library_files`, and
  `library_scan_runs`, including a single-active-scan invariant, root/file
  foreign-key cleanup, and prior-schema upgrade/downgrade coverage.
- Multiple absolute read-only roots are validated and reconciled from
  configuration. `refresh_seconds` supports startup, periodic, and explicit
  scans; `scan_on_startup` is configurable. Invalid relative/duplicate/file
  roots fail with actionable configuration errors.
- The Mutagen adapter reads title, artist, album, track number, duration, and
  Amazon track identity from lucida source-URL comments. Files without usable
  tags fall back to filename/path metadata. Files are opened read-only; no
  hashing, rename, move, write, or deletion occurs.
- The background scanner is single-threaded across roots, ignores hidden
  entries and symlinks, detects size/mtime changes, skips unchanged tag reads,
  records progress, and only removes stale index rows after a complete scan.
  An unavailable root remains unavailable with its previous index preserved;
  a missing match then reports `in_library: null`, never `false`.
- Library annotations expose `library_match: exact | likely`. Exact requires a
  normalized Amazon track identity; title/artist similarity is explicitly
  `likely`. Batch downloads skip only confirmed matches. The frontend reflects
  both badge states in text and accessible hover text.
- `GET /api/v1/library` reports root availability, file counts, active scan
  progress, and safe errors. `POST /api/v1/library/scan` requests a manual
  rescan. Missing library service wiring returns a stable 503 problem response.
- Tests cover multiple roots, missing mounts, tag fallback, filename fallback,
  unchanged/changed/deleted files, rescan cleanup, interrupted scan recovery,
  exact/likely/unknown matching, API contracts, and source-file immutability.

A read-only verification scan of the real `/mnt/Shared/Music` library indexed
364 audio files in 0.53 seconds: all had tag metadata and durations, 336 had
Amazon track identities, and an exact lookup succeeded. Final checks: 300
backend tests and 22 frontend tests pass; `ruff`, the TypeScript typecheck, and
the Vite production build are clean. A clean wheel install migrated through
`0003_library_index`, served the packaged frontend, completed the 364-file
startup scan and a manual API rescan, and logged no server errors.

Phase 7 (Spotify progressive matching) is complete for the extraction,
persistence, scheduler, API, SSE, and UI layers:

- Migration `0004` adds `import_sessions`, `source_tracks`, and
  `amazon_candidates`, including one-active-session enforcement, source
  position uniqueness, cascade cleanup, and queue-outcome provenance.
- The Spotify adapter accepts only public open.spotify.com album/playlist links
  and spotify.link/spotify.app.link short links. It uses bounded redirects,
  size/timeout limits, and the public embed page; no login or OAuth is used.
  Parsed occurrences retain source position and duplicates. Live extraction
  returned 50 tracks from a public playlist and 15 from a public album.
- Amazon match queries use bounded retries/backoff and the configured 1–5
  concurrency. Ranking is deterministic from title, artist, and version
  metadata; candidates are persisted as they arrive and are never
  auto-selected. A live Amazon query returned 10 ranked candidates in 4.24s.
- Session states cover extraction, matching, pause, and matching-complete.
  Paused sessions retain the active slot; matching completion releases it.
  Restart recovery deletes incomplete extraction sessions, requeues interrupted
  active searches, and preserves completed review data. Manual per-source
  searches work after completion without retaking the active slot.
- Explicit selection, skip, pause/resume/cancel, completed-session deletion,
  and add-selected are implemented. Add-selected is idempotent, works before
  all matching finishes, records queued/duplicate/library-skipped outcomes,
  preserves source occurrences, and never deletes jobs or media.
- `GET /api/v1/imports/{id}/events` streams revision events. The frontend
  refetches authoritative REST state and adds an Imports workspace with
  progressive candidate review, source-duplicate and library warnings, manual
  search, library override, lifecycle controls, and destructive confirmations.
- Tests cover URL safety, extraction fixtures, duplicate occurrences, ranking,
  retries, bounded concurrency, pause/resume, cancellation/deletion, one active
  import, manual search, no auto-selection, add-selected before matching
  completion, idempotency, library overrides, SSE, and API contracts.

Live API verification created a 50-track import, paused it with one search
in-flight, rejected a second active import with a stable conflict response,
read the SSE revision stream, and cancelled cleanly with no queued jobs deleted
or server errors. The import workspace was also rendered at desktop and mobile
widths with no horizontal overflow.

Final checks at the end of Phase 7: 361 backend tests and 25 frontend tests
passed; `ruff`, the TypeScript typecheck, the Vite production build, and
`uv lock --check` were clean. Clean-install checks verified migration through
`0004_spotify_imports`, live public Spotify extraction, the packaged Imports
UI, import creation, pause/cancel, SSE revisions, and no server errors.

Phase 8 (pairing and LAN hardening) is complete for the security/API/UI layer:

- Loopback plus one trusted-LAN listener remain one uvicorn server with one
  lifespan, worker, and database. LAN is selected only from the configured
  IPv4 CIDR; wildcard binding remains prohibited and a missing interface keeps
  localhost available.
- Listener-aware middleware validates Host against the actual accepted socket,
  validates Origin on writes, and enforces a double-submit CSRF token on every
  state-changing request. Requests to the LAN listener must also originate in
  the trusted subnet.
- A cryptographically random six-digit code is generated per service start.
  Only loopback Settings/API can read it; LAN status responses never include
  it, and LAN responses are marked `no-store`.
- Pairing is password-style rate-limited per source (5 failures/15 minutes) and
  globally (30 failures/15 minutes), with lockout and `Retry-After` responses.
  Only a SHA-256 hash of the persistent browser credential is stored.
- The device cookie is `HttpOnly`, `SameSite=Strict`, and intentionally omits
  `Secure` because LAN transport is plain HTTP. It persists across restarts
  until explicit revocation; IP observations are diagnostic only.
- LAN requests can load only the HTML shell, assets, health, and auth/pairing
  endpoints unauthenticated. Other APIs require a valid device cookie. Pairing
  code and paired-device list/revocation routes are loopback-only.
- Local and LAN Settings surfaces show pairing status, the LAN URL, the code
  (loopback only), device last-seen metadata, revocation confirmation, and the
  plain-HTTP warning. The frontend gates unpaired LAN browsers with a pairing
  screen and auto-attaches CSRF headers.
- Migration `0005` adds hashed paired-device credentials and revocation state.
- Tests cover Host/Origin/CSRF failures, untrusted subnet sources, loopback-only
  code/device routes, pairing success/failure, rate limits, cookie attributes,
  persistent cookies across app restarts, revocation invalidation, no raw token
  storage, and no pairing-code leakage through LAN responses or logs.

Final checks: 375 backend tests and 31 frontend tests pass; `ruff`, the
TypeScript typecheck, and the Vite production build are clean. A clean wheel
install migrated through `0005_paired_devices` and ran a real dual-socket
uvicorn server on loopback aliases (`127.0.0.1` local and `127.0.0.2` LAN):
invalid Host and missing CSRF were rejected, a LAN browser paired with the
loopback-only code, the credential was stored only as a 64-character hash,
LAN device management was denied, and local revocation invalidated the cookie.
The packaged pairing/settings UI was checked at desktop and phone widths with
no horizontal overflow. No external LAN interface was exposed; subnet selection
and wildcard rejection remain covered by injected-interface and binding tests.

Phase 9 (installer, legacy migration, and release tooling) is complete for the
application and automation layers:

- Migration `0006` adds `legacy_queue_imports`, a unique per-source/per-legacy-id
  ledger recording imported, skipped, ambiguous, and failed outcomes.
  `spotui migrate-legacy` supports `--dry-run`, interactive confirmation, and
  `--yes`. It imports queued, completed, failed, and cancelled jobs; maps
  running/downloading to `interrupted`; reports unknown states and invalid URLs;
  skips queued records that duplicate an active track; and never writes to the
  legacy JSON file, lucidadl state, or media. Deterministic job IDs require no
  sequence state, and reruns report prior outcomes without duplicating rows.
- `spotui db upgrade` refuses while the server holds the OS process lock. Before
  changing an existing schema it creates an online SQLite backup under
  `~/.local/share/spotui/backups/`, sets mode `0600`, verifies
  `PRAGMA integrity_check`, and retains five files by default. `spotui db backup`
  additionally supports a one-off explicit file and configurable retention.
- `scripts/install.sh` installs or updates a wheel in the uv-managed XDG
  environment, verifies downloaded wheel checksums, refuses to update a running
  server, applies migrations, registers/refreshes the launcher safely, and can
  install a systemd user unit. It never modifies system Python or downloader
  state. `scripts/uninstall.sh` removes only managed code/launcher/service by
  default; data removal requires `--purge-data` plus explicit confirmation.
- `spotui service install|enable|disable|uninstall|status` provides explicit
  systemd user-service operations. Units use the resolved installed executable,
  quote paths safely, and do not enable themselves implicitly.
- Python versioning is single-sourced from `src/spotui/__init__.py` via
  Hatchling; tests keep the frontend package/lock aligned. The lockfile records
  the project version as dynamic.
- `.github/workflows/ci.yml` covers Ubuntu 22.04 and a current Arch container,
  backend/frontend tests, lint, lockfile, Alembic drift, artifact builds,
  bundled-asset checks, a clean wheel install, server startup, and installer
  smoke tests. `.github/workflows/release.yml` gates publishing on CI, verifies
  tag/artifact names, generates `SHA256SUMS`, and creates the GitHub release.
  These workflows are authored but have not run on GitHub from this local
  checkout; no release was published.
- Local-testing adjustment: successful HTTP access logs now emit at `DEBUG`;
  slow requests over two seconds and server errors remain visible at
  `INFO`/`ERROR`. The Now Playing header control is an icon-only button that
  reads MPRIS only when clicked, so it never retains a stale track label. The
  compact queue panel removes completed jobs three seconds after completion
  while the Queue page retains history; idle queue polling backs off from 1.5
  seconds to 10 seconds. This avoids console/log-file noise and side-panel
  clutter without hiding failures or active queue updates.
- The supplied visual redesign was applied after preserving the previous
  frontend as the `scrap/frontend_0.1.0/` directory. The redesign adds the brand
  mark, favicon, brand styling layer, and refreshed navigation, search, and
  pairing surfaces. The FastAPI shell serves `/favicon.png`, including for
  unpaired LAN browsers. Desktop and mobile renders were exercised with
  Playwright: no console errors, no horizontal overflow, and all images loaded.
- The second redesign iteration was re-applied as the active frontend after the
  first redesign was retained as `scrap/frontend_0.1.1/` alongside
  `scrap/frontend_0.1.0/`. The active version includes the aurora background,
  floating chrome, immersive detail hero, and animated home screen mark. It was
  re-rendered at desktop and mobile widths with no console errors or horizontal
  overflow.
- Live Amazon checks exposed and fixed two detail-view defects:
  `lucidadl` returns album/playlist cover artwork as a size-ladder list, which
  the parser previously dropped; it now selects a moderate image for the hero
  and track thumbnails. The artwork fallback also used percentage padding that
  expanded 46 px track thumbnails to roughly 400 px when an image was missing;
  fallback sizing is now contained and icon-scaled. A live album (10 tracks) and
  editorial playlist (100 tracks) both rendered covers and compact 67 px rows,
  with a synthetic missing-image check also confirming 46 px fallbacks and the
  232 px hero. The same fixes were re-applied to the active second redesign.
- Public community playlists were also fixed: the browser adapter now captures
  the `music-detail-header` cover and each row's album artwork. A live public
  playlist (24 tracks) rendered its playlist cover and per-track covers at
  46×46 px with compact rows and no overflow.
- UI refinements: the desktop search field fills the header up to the icon-only
  Now Playing button; queue rows outside the Active section use a compact
  `title | artist` summary with icon-only state, retain completed filenames, and
  remove redundant text labels. Settings now includes a persisted
  System/Light/Dark theme, read-only download folder and application root,
  indexed library count, completed-download count, and library-root status.
  Read-only values come from the new `/api/v1/system/info` endpoint and existing
  queue/library APIs. Live renders confirmed the 16 px header gap, compact
  50–62 px non-active rows versus the full Active row, and working light/dark
  theme application.
- Downloader skip classification was corrected after a live queue report:
  `lucidadl` counts both dedup hits and unresolved items as "skipped". SpotUI
  previously marked every skip as completed, so a track that Amazon could not
  resolve appeared in History as "already in library" without a filename.
  Only an explicit "already downloaded / in progress" skip is now completed;
  not-found and unexplained skips fail with an actionable error and can be
  retried.
- Queue cleanup behavior was refined: the X action cancels an active download,
  deletes a waiting job before it can enter history, and dismisses a
  failed/interrupted job without retrying. Waiting removals use an optimistic
  client update so the compact panel drops them immediately, and cancelled jobs
  are excluded from the panel and History. History renders only the latest 50
  completed rows while the Completed aggregate continues to count every job.
  The new `DELETE /api/v1/queue/jobs/{id}` route accepts waiting, failed,
  interrupted, or cancelled jobs, rejects active jobs, and relies on the
  existing cascade to remove attempts.
- Application-owned paths are consolidated under one root
  (`~/.local/share/spotui` by default, relocatable with `SPOTUI_HOME`):
  configuration, database/WAL, backups, logs, cache, lock, legacy queue, and
  both managed environments. Only the optional PATH launcher and systemd user
  unit remain at their OS-required locations. The installer and uninstaller honor
  the same root; `--purge-data` also removes leftovers from the earlier scattered
  XDG layout.

Final checks: 430 backend tests and 45 frontend tests pass; `ruff`, the
TypeScript typecheck, `uv lock --check`, and the Vite production build are
clean. Local `uv build` produced the wheel and sdist; both contain the generated
frontend, and the sdist contains both installer scripts plus the frontend
version manifests needed to run its packaged tests. The release workflow
generates the authoritative `SHA256SUMS` for published artifacts. All 430
backend tests also pass from the wheel installed in a clean Python 3.11
environment. That
installed wheel migrated a fresh database, produced a verified backup, generated
a valid systemd unit with the pinned application root, imported a sample legacy
queue in dry-run and confirmed modes, reran without duplicates, left the source
file hash unchanged, served the packaged UI and asset, and shut down cleanly. A
clean-root smoke test confirmed all generated files (config, database, backup,
logs, cache, and run lock) stayed inside `SPOTUI_HOME` and that default-`INFO`
health/queue requests produced no access-log spam. The real installer was run
twice against the built wheel with a real uv environment: the second run was
idempotent and preserved data; uninstall removed only code and the launcher.

Not exercised here: an actual GitHub Actions run or tagged release publication,
live release-asset download (the checksum path is shell-tested with fixtures),
a physical phone on an external LAN, and a complete real playlist download
through the pinned downloader. The next step is the first tagged release and
those manual smoke checks; no release should be published until CI runs green
on the tagged commit.
