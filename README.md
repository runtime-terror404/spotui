# SpotUI

SpotUI is a local music search and download application. It searches Amazon
Music through a headless browser, lets you pick the exact release, and queues
downloads through the `lucidadl` downloader.

This repository is being migrated incrementally from the reference
implementation in `v0/` to a modular FastAPI + React application. The migration
plan is in [`refactor.md`](refactor.md); `v0/` is a read-only behavioral
reference and is never imported by the new package.

## Current status

**Phases 1–9: the complete first-release feature set.** The package includes
search and entity details, a durable download queue with cancellation, retry
and recovery, Now Playing, a read-only multi-root library index, progressive
Spotify imports with explicit matching, trusted LAN pairing and security, the
installer/uninstaller, safe legacy queue migration, database backups, systemd
user-service helpers, and CI/release packaging with bundled frontend assets.
Settings now includes a persisted System/Light/Dark theme, download
destination, library track count, completed-download count, application paths,
and library-root status. Remaining optional work is limited to broader queue
SSE, verified live downloader capture, and physical-LAN field testing. The
baseline audit and verification evidence are recorded in
[`docs/baseline-audit.md`](docs/baseline-audit.md).

## Requirements

- 64-bit Linux: Ubuntu 22.04 LTS and newer, or rolling Arch Linux
- [`uv`](https://docs.astral.sh/uv/) for the isolated runtime
- `bash`, `curl`, and `sha256sum` for release installation
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

## Installation

Release installs use the isolated environment and register `~/.local/bin/spotui`.
Download and verify the installer from the tagged release, then:

```bash
VERSION=0.1.0
BASE="https://github.com/runtime-terror404/spotui/releases/download/v${VERSION}"
curl -fLO "$BASE/install.sh"
curl -fLO "$BASE/uninstall.sh"
curl -fLO "$BASE/SHA256SUMS"
sha256sum --check --ignore-missing SHA256SUMS
chmod +x install.sh uninstall.sh
./install.sh --version "$VERSION"
```

The installer verifies the wheel against the release checksum, applies database
migrations after backing up an existing database, and is safe to re-run. It
does not install the downloader or start the server. Then run explicitly:

```bash
spotui deps install
spotui deps check
spotui serve
```

Optional systemd user service:

```bash
spotui service install
spotui service enable
```

Import the old JSON queue, if present, with a dry run first:

```bash
spotui migrate-legacy --dry-run
spotui migrate-legacy --yes
```

Updates are manual: stop the service, rerun `install.sh` with the new
`--version`, and use `spotui deps upgrade` only when release notes require it.
Create a verified backup with `spotui db backup`; migrations also back up an
existing database automatically. `scripts/uninstall.sh` removes installed code
and the service while preserving configuration, database, logs, caches,
downloader environment, library roots, and music. Add `--purge-data` to remove
SpotUI-owned data explicitly.

See [`docs/installation.md`](docs/installation.md) for platform packages,
backup/restore and rollback boundaries, legacy migration rules, and full
update/uninstall instructions. Release engineering is documented in
[`docs/release-process.md`](docs/release-process.md).

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
uv run spotui db backup         # verified backup before maintenance
uv run spotui migrate-legacy --dry-run
uv run spotui deps check        # SpotUI browser plus managed lucidadl status
uv run spotui deps install      # explicit install/reconcile of pinned dependencies
uv run pytest
uv run ruff check .
(cd frontend && npm test && npm run typecheck && npm run build)
```

API routes:

```text
GET  /api/v1/health
GET  /api/v1/system/info
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
GET  /api/v1/auth/status
POST /api/v1/auth/pair
GET  /api/v1/devices/pairing             # desktop/loopback only
GET  /api/v1/devices                     # desktop/loopback only
DELETE /api/v1/devices/{device_id}       # desktop/loopback only
GET  /api/v1/queue
GET  /api/v1/queue/jobs/{id}
POST /api/v1/queue/jobs
POST /api/v1/queue/batch
POST /api/v1/queue/jobs/{id}/cancel
POST /api/v1/queue/jobs/{id}/retry
DELETE /api/v1/queue/jobs/{id}          # remove a waiting or finished job
```

Interactive OpenAPI documentation is available at `/docs` in development.
Import updates use SSE and authoritative REST refreshes. Queue and library-scan
updates currently use polling; broader SSE integration is planned for a later
phase.

State-changing API requests use a double-submit CSRF check. A normal browser is
primed by the app bootstrap; scripts must first request a safe GET (for example
`/api/v1/auth/status`), retain the `spotui_csrf` cookie, echo it in
`X-CSRF-Token`, and include the `spotui_device` cookie when using the LAN
listener. The device credential is `HttpOnly`, `SameSite=Strict`, and persists
for one year; only its SHA-256 hash is stored in SQLite.

## Configuration

All application-owned files live under one root:
`~/.local/share/spotui/` by default. Configuration is read from
`<root>/config.toml`, which is `~/.local/share/spotui/config.toml` with the
default root. Set `SPOTUI_HOME` to an absolute dedicated directory to relocate
the whole root, including configuration, database, logs, cache, lock, backups,
and managed environments. Precedence for settings is defaults → config file →
`SPOTUI_*` environment variables → CLI flags. Invalid ports, CIDRs, or log
settings fail startup with an actionable message.

```toml
[server]
port = 8765
# Set this only to your home IPv4 CIDR. Find it with `ip -4 addr` / `ip route`.
# trusted_subnet = "192.168.1.0/24"
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
`SPOTUI_MATCHING_CONCURRENCY`, `SPOTUI_HOME` (absolute application root), and
`SPOTUI_CONFIG` (config file path).

## Data locations

**Root:** `~/.local/share/spotui/` (parent selected by `XDG_DATA_HOME`;
override the complete path with `SPOTUI_HOME`).

| Data | Default under the root |
|---|---|
| Configuration | `config.toml` |
| Database | `spotui.sqlite3` (plus `-wal`/`-shm`) |
| Database backups | `backups/` |
| Logs and rotations | `logs/spotui.log` |
| Cache | `cache/` |
| Lock file | `run/server-<root-hash>.lock` |
| Managed environments | `envs/{spotui,lucidadl}/` |
| Legacy JSON queue | `queue.json` — read-only |

Two optional integration files remain outside the root because the OS requires
fixed locations: the PATH launcher (`~/.local/bin/spotui`, or `XDG_BIN_HOME`)
and the systemd user unit (`~/.config/systemd/user/spotui.service`).
Downloaded media stays at the destination configured in `lucidadl`; SpotUI does
not move or modify existing media. Library roots are a separate, read-only
setting.

## Trusted LAN access and pairing

LAN access is off unless `server.trusted_subnet` is set and an active local IPv4
interface falls inside that CIDR. SpotUI then serves loopback plus that exact
interface address; it never binds `0.0.0.0`. If no matching interface exists,
localhost remains available and `spotui status` reports LAN as unavailable.

To pair a phone:

1. Open SpotUI on the desktop at <http://127.0.0.1:8765/> and go to Settings.
2. Note the LAN URL and current six-digit pairing code.
3. Open the LAN URL on the phone while connected to the trusted home network.
4. Enter the code; the browser receives a persistent paired-device cookie.

The code changes on every server restart. Paired devices survive restarts until
revoked from desktop Settings. Pairing attempts are rate-limited per source and
globally. Device IP addresses are displayed for diagnostics only and are never
used as authentication.

LAN traffic is plain HTTP and is **not encrypted**. Do not forward the port
from your router, expose SpotUI to the public Internet, or use it on untrusted
Wi‑Fi. The persistent cookie intentionally omits the `Secure` attribute so it
can work over this plain-HTTP LAN mode. Use a DHCP reservation for the server's
LAN address; cookies are scoped to the host used in the browser, so opening a
different IP may require pairing again. Host and Origin validation, CSRF
protection, and the trusted-subnet source check remain enforced.

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
  only the owned process group and never deletes partial output. Because
  `lucidadl` reports both dedup hits and unresolved tracks as "skipped", only
  its explicit already-downloaded skip counts as completed; not-found and
  unexplained skips are failures with actionable errors.
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
  The icon-only header button reads the player only when clicked, then searches
  Amazon by the current track title; it does not poll in the background or
  retain stale track text in the button.
- Spotify imports validate public album/playlist hosts and bounded redirects,
  then read the public embed page. Source occurrences retain order, position,
  and duplicates. One active import owns the matching slot; a bounded worker
  searches Amazon progressively and never auto-selects a candidate. Pause,
  resume, cancellation, manual search, explicit selection, skip, and
  add-selected actions are persisted. Add-selected is idempotent, blocks
  duplicate active Amazon jobs, and warns about library matches before an
  explicit override. Per-import SSE carries revision numbers; the React client
  refreshes authoritative state from REST.
- Loopback and LAN listeners share the same app, worker, and database. LAN
  requests are accepted only from the configured subnet and a matching local
  interface, require Host/Origin and CSRF checks, and need a paired-device
  cookie. Pairing codes exist only in memory and are exposed only through
  loopback Settings; credential hashes persist in SQLite.
- Settings exposes read-only application, downloader, and library information
  plus a browser-local System/Light/Dark theme preference. It does not edit
  server configuration. Queue rows are compact outside the active section:
  status is conveyed by the leading icon, completed rows show the downloaded
  filename, and waiting/history metadata is summarized as title | artist.
- REST and SQLite are authoritative; the queue UI polls every 1.5 seconds while
  work is active and every 10 seconds when idle, with broader SSE planned for a
  later phase. The compact side panel drops cancelled jobs immediately and
  completed jobs three seconds after completion. The X action removes waiting
  jobs without creating history and dismisses failed/interrupted jobs; a retry
  remains available for failures. The Queue page shows only the latest 50
  completed history rows while Completed remains an SQL aggregate over all
  persisted jobs. The snapshot returns up to 500 recent jobs. Successful HTTP
  access logs are emitted at `DEBUG`; slow requests (over two seconds) and
  server errors remain visible at `INFO`/`ERROR`, so set
  `logging.level = "DEBUG"` only when full request tracing is needed.
- The legacy JSON queue migration is read-only toward the source file and uses
  a per-record ledger for repeat-safe imports. Active legacy jobs become
  `interrupted`; unknown or malformed records are reported and skipped.
- Database upgrades refuse while a server holds the process lock and create a
  verified online SQLite backup before changing schema. The application version
  has one Python source of truth and is checked against the frontend package.
- Install and uninstall scripts operate only on the managed uv environment,
  launcher, and optional systemd user unit. Normal uninstall preserves user
  configuration, database, logs, downloader environment, and media.

See [`refactor.md`](refactor.md) for the full phase plan and acceptance gates.
CI, release, and artifact verification steps are in
[`docs/release-process.md`](docs/release-process.md).
