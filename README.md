# SpotUI

SpotUI is a local music search and download application. It searches Amazon
Music through a headless browser, lets you pick the exact release, and queues
downloads through the `lucidadl` downloader.

This repository is being migrated incrementally from the reference
implementation in `v0/` to a modular FastAPI + React application. The migration
plan is in [`refactor.md`](refactor.md); `v0/` is a read-only behavioral
reference and is never imported by the new package.

## Current status

**Phases 1–7: foundation, search/details, the download queue, Now Playing,
the library index, and progressive Spotify imports.** The package,
configuration, logging, process lock, SQLite/Alembic setup, FastAPI lifecycle,
dual-listener foundation, versioned API, RFC 9457 error contract, Amazon
adapters, React search/detail/import views, persisted download queue, managed
worker, cancellation/retry/recovery, queue UI, optional MPRIS current-track
shortcut, read-only multi-root library index, and Spotify candidate-review
workspace are in place. Settings, pairing, full queue SSE, and the installer
remain for later phases. The baseline audit and verification evidence are
recorded in [`docs/baseline-audit.md`](docs/baseline-audit.md).

## Requirements

- Linux (Arch Linux or Ubuntu 22.04 LTS and newer)
- [`uv`](https://docs.astral.sh/uv/)
- Playwright Chromium for SpotUI's Amazon adapter (`spotui deps check`)
- For album/editorial-playlist details and downloads, the managed `lucidadl`
  environment plus its Cloudflare setup (`lucida setup`). Run
  `spotui deps install` explicitly; startup never installs anything.
- Optional: `playerctl` and a running MPRIS-compatible media player for the
  Now Playing shortcut. Missing `playerctl` or no active player is reported as
  an availability state and never blocks startup, search, or downloads.
- Internet access to public Spotify embed pages and Amazon Music for imports.
  Spotify import uses public album/playlist pages only; no Spotify login,
  OAuth token, or API key is required.

SpotUI itself runs from a uv-managed environment. It never modifies system
Python. `lucidadl` is managed in a separate environment under the SpotUI data
directory; album/editorial-playlist resolution calls it through a packaged
subprocess bridge. Node.js is needed only to build the frontend, not to run the
installed application.

## Development quick start

```bash
uv sync --all-groups
(cd frontend && npm ci && npm run build)
uv run spotui db upgrade
uv run spotui serve
```

Then open <http://127.0.0.1:8765/>. If `src/spotui/web/dist/` has not been
built, the server serves the packaged placeholder instead. The default listener
is loopback-only. A LAN listener is added only after `server.trusted_subnet` is
configured and a matching active IPv4 interface exists; SpotUI never binds
`0.0.0.0`.

For frontend iteration, run the backend on port 8765 and `npm run dev` in
`frontend/`; Vite proxies `/api` to the backend.

```bash
uv run spotui status            # effective paths, URLs, lock and health state
uv run spotui db current        # applied migration revision
uv run spotui deps check        # SpotUI browser plus managed lucidadl status
uv run spotui deps install      # explicit install/reconcile of pinned dependencies
uv run pytest
uv run ruff check .
(cd frontend && npm test && npm run typecheck && npm run build)
```

API routes:

```text
GET  /api/v1/health
GET  /api/v1/search?q=...
GET  /api/v1/entities/detail?url=...
GET  /api/v1/now-playing
GET  /api/v1/library
POST /api/v1/library/scan
GET  /api/v1/imports
POST /api/v1/imports
GET  /api/v1/imports/{id}
GET  /api/v1/imports/{id}/events        # server-sent revisions
POST /api/v1/imports/{id}/pause
POST /api/v1/imports/{id}/resume
POST /api/v1/imports/{id}/cancel
DELETE /api/v1/imports/{id}
POST /api/v1/imports/{id}/sources/{source_id}/select
POST /api/v1/imports/{id}/sources/{source_id}/skip
POST /api/v1/imports/{id}/sources/{source_id}/search
POST /api/v1/imports/{id}/enqueue
GET  /api/v1/queue
GET  /api/v1/queue/jobs/{id}
POST /api/v1/queue/jobs
POST /api/v1/queue/batch
POST /api/v1/queue/jobs/{id}/cancel
POST /api/v1/queue/jobs/{id}/retry
```

Interactive OpenAPI documentation is available at `/docs` in development.
Import updates use SSE and authoritative REST refreshes. Queue and library-scan
updates currently use polling; broader SSE integration is planned for a later
phase.

## Configuration

Configuration is read from `$XDG_CONFIG_HOME/spotui/config.toml` (usually
`~/.config/spotui/config.toml`). Precedence is defaults → config file →
`SPOTUI_*` environment variables → CLI flags. Invalid ports, CIDRs, or log
settings fail startup with an actionable message.

```toml
[server]
port = 8765
# trusted_subnet = "192.168.1.0/24"  # enables LAN listening
shutdown_grace_seconds = 5.0

[logging]
level = "INFO"
max_bytes = 5242880
backup_count = 5

[queue]
cancel_grace_seconds = 5.0
shutdown_grace_seconds = 5.0
job_timeout_seconds = 900.0

[library]
# Multiple read-only roots are supported. Existing files are never modified.
# roots = ["/mnt/Shared/Music", "/mnt/Archive/Music"]
refresh_seconds = 3600  # 0 disables periodic refresh
scan_on_startup = true

[matching]
concurrency = 3  # bounded Amazon searches per active import, range 1–5
```

Library roots are configured explicitly; SpotUI does not infer them from
`lucidadl`. In-library badges and batch skipping remain disabled until at least
one root is configured.

Supported environment overrides are `SPOTUI_PORT`, `SPOTUI_TRUSTED_SUBNET`,
`SPOTUI_SHUTDOWN_GRACE_SECONDS`, `SPOTUI_LOG_LEVEL`, `SPOTUI_LOG_MAX_BYTES`,
`SPOTUI_LOG_BACKUP_COUNT`, `SPOTUI_CANCEL_GRACE_SECONDS`,
`SPOTUI_QUEUE_SHUTDOWN_GRACE_SECONDS`, `SPOTUI_JOB_TIMEOUT_SECONDS`,
`SPOTUI_LIBRARY_ROOTS` (OS path separator-delimited absolute directories),
`SPOTUI_LIBRARY_REFRESH_SECONDS`, `SPOTUI_LIBRARY_SCAN_ON_STARTUP`,
`SPOTUI_MATCHING_CONCURRENCY`, and `SPOTUI_CONFIG` (config file path).

## Data locations

| Data | Default |
|---|---|
| Configuration | `~/.config/spotui/config.toml` |
| Database | `~/.local/share/spotui/spotui.sqlite3` |
| Logs | `~/.local/state/spotui/logs/spotui.log` |
| Cache | `~/.cache/spotui/` |
| Lock file | `$XDG_RUNTIME_DIR/spotui/server-<data-dir-hash>.lock` |
| Managed environments | `~/.local/share/spotui/envs/{spotui,lucidadl}/` |

All XDG variables are respected. Downloaded media stays at the destination
configured in `lucidadl`; SpotUI does not move or modify existing media. Library
roots are a separate, read-only setting.

## Architecture

- API routes under `/api/v1` validate contracts and call services.
- API errors use RFC 9457 `application/problem+json` with stable `code` and
  `request_id` extensions; request IDs also appear in redacted logs.
- Services own use cases; provider adapters wrap Amazon, Spotify, the
  downloader, MPRIS, and audio tags.
- Amazon search, artist, and community-playlist reads use one serialized
  Playwright browser thread. Album/editorial-playlist detail uses the managed
  `lucidadl` environment through a JSON subprocess bridge.
- The frontend is React + TypeScript + Vite with TanStack Query for server
  state and Zustand for client-only view state. The production build writes to
  `src/spotui/web/dist/` and is bundled into the wheel/sdist.
- SQLAlchemy/Alembic owns persistence; Pydantic schemas are separate.
- One in-process download worker owns exactly one managed `lucidadl` process at
  a time. Jobs and attempts persist in SQLite; active jobs interrupted by a
  restart become `interrupted` and require explicit Retry. Cancellation signals
  only the owned process group and never deletes partial output.
- The durable library index scans configured read-only roots into SQLite. A
  background scanner supports startup, periodic, and API-triggered refreshes.
  It reads Mutagen tags, falls back to filenames, extracts Amazon track identity
  from lucida's source-URL comments, and never writes to media files. Missing
  roots are reported as unavailable while preserving their previous index.
  Track annotations distinguish exact Amazon matches from likely
  title/artist matches, and batch downloads skip only confirmed matches.
- Now Playing reads MPRIS metadata through an adapter. It detects players with
  `playerctl -l`, prefers Spotify-compatible players, and returns an explicit
  non-fatal availability state when `playerctl` or a player is absent. Set
  `SPOTUI_MPRIS_PLAYER` (legacy: `SPOTGRAB_PLAYER`) to force a player name.
  The header action searches Amazon by the current track title.
- Spotify imports validate public album/playlist hosts and bounded redirects,
  then read the public embed page. Source occurrences retain order, position,
  and duplicates. One active import owns the matching slot; a bounded worker
  searches Amazon progressively and never auto-selects a candidate. Pause,
  resume, cancellation, manual search, explicit selection, skip, and
  add-selected actions are persisted. Add-selected is idempotent, blocks
  duplicate active Amazon jobs, and warns about library matches before an
  explicit override. Per-import SSE carries revision numbers; the React client
  refreshes authoritative state from REST.
- REST and SQLite are authoritative; the queue UI currently polls, with broader
  SSE planned for a later phase.

See [`refactor.md`](refactor.md) for the full phase plan and acceptance gates.
