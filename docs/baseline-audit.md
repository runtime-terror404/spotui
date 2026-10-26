# Baseline Audit and Phase 0 Record

**Audit date:** 2026-10-26  
**Reference implementation:** `v0/` (immutable, read-only)  
**Architecture authority:** [`refactor.md`](../refactor.md)

This record captures the observed starting point for the refactor. It does not
restate the target architecture or add requirements. Behavioral detail remains
in [`v0_architecture.md`](../v0_architecture.md) and
[`handoff.md`](../handoff.md); the approved visual design is
[`new_ui.md`](../new_ui.md).

## 1. Source inventory

`v0/` is gitignored and was untracked at audit time. None of these files were
modified during this phase.

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
| lucidadl | 1.0.0 in `/home/divine/.local/share/pipx/venvs/lucidadl` |
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
- Spotify/Amazon fixtures are not yet captured.
- The React frontend, search/detail services, queue worker, import matching,
  and pairing are not implemented in this phase.
- `lucidadl` download output capture and the final release pin remain Phase 4
  work.
- Legacy queue migration, installer, systemd helper, and release automation are
  later phases.

## 8. Phase 2 completion and next phase

Phase 2 (persistence and API base) is complete for the base layer:

- The initial `download_jobs` schema and active-job uniqueness constraint are
  in place. Feature-owned tables (import/session/candidates, library index, and
  paired devices) are deliberately added with their respective phases.
- API routing remains under `/api/v1`, with typed health and error schemas.
- API failures use RFC 9457 `application/problem+json` with stable error codes,
  a request-ID extension, safe validation details, and redacted logging.
- API fixtures and tests cover the problem contract, validation, HTTP errors,
  unexpected exceptions, and OpenAPI versioning.

Next is Phase 3: Amazon search and entity details behind adapters, followed by
the React search/detail views and Vite asset packaging. Phase 3 must also
establish the separate Playwright/Chromium runtime check for the Amazon web
adapter before live search work is considered complete.
