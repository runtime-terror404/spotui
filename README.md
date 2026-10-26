# SpotUI

SpotUI is a local music search and download application. It searches Amazon
Music through a headless browser, lets you pick the exact release, and queues
downloads through the `lucidadl` downloader.

This repository is being migrated incrementally from the reference
implementation in `v0/` to a modular FastAPI + React application. The migration
plan is in [`refactor.md`](refactor.md); `v0/` is a read-only behavioral
reference and is never imported by the new package.

## Current status

**Phases 1–4: foundation, search/details, and the download queue.** The
package, configuration, logging, process lock, SQLite/Alembic setup, FastAPI
lifecycle, dual-listener foundation, versioned API, RFC 9457 error contract,
Amazon adapters, React search/detail views, persisted download queue, managed
worker, cancellation/retry/recovery, and queue UI are in place. Spotify import,
Now Playing, full library indexing, settings, pairing, and SSE remain for later
phases. The baseline audit and verification evidence are recorded in
[`docs/baseline-audit.md`](docs/baseline-audit.md).

## Requirements

- Linux (Arch Linux or Ubuntu 22.04 LTS and newer)
- [`uv`](https://docs.astral.sh/uv/)
- Playwright Chromium for SpotUI's Amazon adapter (`spotui deps check`)
- For album/editorial-playlist details and downloads, the managed `lucidadl`
  environment plus its Cloudflare setup (`lucida setup`). Run
  `spotui deps install` explicitly; startup never installs anything.

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
GET  /api/v1/queue
GET  /api/v1/queue/jobs/{id}
POST /api/v1/queue/jobs
POST /api/v1/queue/batch
POST /api/v1/queue/jobs/{id}/cancel
POST /api/v1/queue/jobs/{id}/retry
```

Interactive OpenAPI documentation is available at `/docs` in development.
Queue updates currently use short-interval polling; SSE integration is planned
for a later phase.

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
```

Supported environment overrides are `SPOTUI_PORT`, `SPOTUI_TRUSTED_SUBNET`,
`SPOTUI_SHUTDOWN_GRACE_SECONDS`, `SPOTUI_LOG_LEVEL`, `SPOTUI_LOG_MAX_BYTES`,
`SPOTUI_LOG_BACKUP_COUNT`, `SPOTUI_CANCEL_GRACE_SECONDS`,
`SPOTUI_QUEUE_SHUTDOWN_GRACE_SECONDS`, `SPOTUI_JOB_TIMEOUT_SECONDS`, and
`SPOTUI_CONFIG` (config file path).

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
configured in `lucidadl`; SpotUI does not move or modify existing media.

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
- The compatibility library index reads lucidadl's completed `state.json` for
  in-library badges and batch skipping until the durable library index phase.
- REST and SQLite are authoritative; the queue UI currently polls, with SSE
  planned for a later phase.

See [`refactor.md`](refactor.md) for the full phase plan and acceptance gates.
