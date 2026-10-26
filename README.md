# SpotUI

SpotUI is a local music search and download application. It searches Amazon
Music through a headless browser, lets you pick the exact release, and queues
downloads through the `lucidadl` downloader.

This repository is being migrated incrementally from the reference
implementation in `v0/` to a modular FastAPI + React application. The migration
plan is in [`refactor.md`](refactor.md); `v0/` is a read-only behavioral
reference and is never imported by the new package.

## Current status

**Phase 1: application foundation.** The package, configuration, logging,
process lock, SQLite/Alembic setup, FastAPI lifecycle, dual-listener
foundation, placeholder frontend, and management CLI are in place. Search,
details, queue processing, imports, and the React UI are not implemented yet.
The baseline audit and Phase 1 verification evidence are recorded in
[`docs/baseline-audit.md`](docs/baseline-audit.md).

## Requirements

- Linux (Arch Linux or Ubuntu 22.04 LTS and newer)
- [`uv`](https://docs.astral.sh/uv/)
- For downloads, a managed or existing `lucidadl` installation and its
  Cloudflare setup (`lucida setup`)

SpotUI itself runs from a uv-managed environment. It never modifies system
Python. `lucidadl` is managed in a separate environment under the SpotUI data
directory.

## Development quick start

```bash
uv sync --all-groups
uv run spotui db upgrade
uv run spotui serve
```

Then open <http://127.0.0.1:8765/>. The default listener is loopback-only. A
LAN listener is added only after `server.trusted_subnet` is configured and a
matching active IPv4 interface exists; SpotUI never binds `0.0.0.0`.

```bash
uv run spotui status            # effective paths, URLs, lock and health state
uv run spotui db current        # applied migration revision
uv run spotui deps check        # managed lucidadl environment and browser status
uv run pytest
uv run ruff check .
```

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
```

Supported environment overrides are `SPOTUI_PORT`, `SPOTUI_TRUSTED_SUBNET`,
`SPOTUI_SHUTDOWN_GRACE_SECONDS`, `SPOTUI_LOG_LEVEL`, `SPOTUI_LOG_MAX_BYTES`,
`SPOTUI_LOG_BACKUP_COUNT`, and `SPOTUI_CONFIG` (config file path).

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
- Services own use cases; provider adapters wrap Amazon, Spotify, the
  downloader, MPRIS, and audio tags.
- SQLAlchemy/Alembic owns persistence; Pydantic schemas are separate.
- One in-process download worker will own the only downloader subprocess.
- REST and SQLite are authoritative; SSE will publish live updates later.

See [`refactor.md`](refactor.md) for the full phase plan and acceptance gates.
