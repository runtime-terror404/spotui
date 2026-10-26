# Installation and Maintenance

SpotUI runs on 64-bit Linux. The release targets Ubuntu 22.04 LTS and newer and
rolling Arch Linux. The current release is tested on x86_64; other Linux
architectures are not yet verified. Windows and macOS are not supported. The
installer never modifies system Python.

## Prerequisites

Required:

- `bash`, `curl`, and `sha256sum` (coreutils) for release installation.
- [`uv`](https://docs.astral.sh/uv/) for the isolated Python runtime.
- The native libraries used by Playwright Chromium.
- Internet access to download releases, Python dependencies, and the browser.

On Ubuntu 22.04:

```bash
sudo apt-get update
sudo apt-get install -y bash curl coreutils \
  libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libatspi2.0-0 \
  libdbus-1-3 libglib2.0-0 libcups2 libdrm2 libgbm1 libx11-6 libxcb1 \
  libxext6 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
  libasound2 libpango-1.0-0 libcairo2
```

On Arch Linux:

```bash
sudo pacman -S --needed bash curl coreutils nss at-spi2-core dbus glib2 \
  cups libdrm mesa libx11 libxcb libxext libxkbcommon libxcomposite \
  libxdamage libxfixes libxrandr alsa-lib pango cairo
```

`playerctl` is optional and only powers the Now Playing shortcut:

```bash
sudo apt-get install playerctl   # Ubuntu
sudo pacman -S playerctl         # Arch
```

Install `uv` using its official installer or distribution package. Confirm
`uv --version` works before continuing.

## Install a release

SpotUI release assets include `install.sh`, `uninstall.sh`, a wheel, a source
distribution, and `SHA256SUMS`.

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

The installer downloads the wheel, verifies it against the release checksum,
creates a uv-managed environment under the SpotUI root
(`~/.local/share/spotui/envs/spotui` by default), installs SpotUI there, and
registers `${XDG_BIN_HOME:-~/.local/bin}/spotui` as a symlink. Set
`SPOTUI_HOME` before running the installer to use a different absolute root;
configuration, database, logs, cache, lock, backups, and managed environments
all move with it. The installer preserves an existing non-SpotUI launcher at
the launcher path by renaming it with a `.legacy-<timestamp>` suffix. Re-running
the same command is safe and idempotent.

If `~/.local/bin` is not on `PATH`, add it in your shell configuration.

To install from a wheel you built locally instead:

```bash
uv build
./scripts/install.sh --wheel dist/spotui-0.1.0-py3-none-any.whl
```

Installation does not start SpotUI and does not install the downloader. It does
apply database migrations; an existing database is backed up first.

## Downloader and browser setup

SpotUI keeps `lucidadl` in a separate environment. Install it only when you
choose to:

```bash
spotui deps install
spotui deps check
```

This installs the pinned `lucidadl` release, SpotUI's Playwright Chromium, and
the downloader's Chromium. The downloader may still need its one-time
Cloudflare/browser setup. Run it from a desktop session, using the executable
path printed by `spotui deps check`:

```bash
ROOT="${SPOTUI_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/spotui}"
"$ROOT/envs/lucidadl/bin/lucida" setup
```

SpotUI never installs or updates dependencies during server startup.

## First run

```bash
spotui db upgrade     # no-op after install; safe to repeat
spotui serve          # foreground server on http://127.0.0.1:8765/
```

Edit `<root>/config.toml` — by default
`~/.local/share/spotui/config.toml` — for the port, trusted LAN subnet, library
roots, logging, and matching concurrency. See the README for the complete
annotated example. Invalid configuration fails before any listener binds.

## Optional systemd user service

The installer can write the unit, and systemd operations remain explicit:

```bash
spotui service install            # write ~/.config/systemd/user/spotui.service
spotui service enable             # enable and start it
spotui service status
spotui service disable            # disable and stop it
spotui service uninstall          # remove the unit; data remains
```

`spotui service install --exec PATH` selects another installed launcher. Without
`--exec`, the command uses the managed SpotUI environment and refuses to write
a development-checkout path. The unit runs `spotui serve` in the foreground
under systemd. Do not run a second foreground server at the same time.

Installation with `--service` writes the unit. `--enable-service` additionally
enables and starts it. Installation refuses to proceed while SpotUI is running.

## Legacy queue migration

The old implementation stores its JSON queue at
`~/.local/share/spotui/queue.json`. The new application uses the same directory
for its SQLite data, so the original file remains in place and is never
modified.

```bash
spotui db upgrade
spotui migrate-legacy --dry-run       # validate and report only
spotui migrate-legacy                 # print the report and ask for confirmation
spotui migrate-legacy --yes           # non-interactive
```

Migration rules:

- `queued` becomes `queued`.
- `running` and `downloading` become `interrupted` and are never resumed
  automatically.
- `done` becomes `completed`; `failed` becomes `failed`; `cancelled` becomes
  `cancelled`.
- Malformed URLs are reported as failed. Unknown states and records without a
  stable legacy id are reported as ambiguous and skipped.
- Queued records are skipped when an active new job already exists for the same
  Amazon track key.
- A per-record ledger makes repeated runs safe. Re-running reports prior
  outcomes as skipped and never duplicates jobs.
- Media files, `lucidadl` state, configuration, and the legacy JSON file are not
  modified.

The v0 application had no settings file; its port and paths were code constants.
No settings are migrated. Re-enter the server port, trusted subnet, library
roots, and any other choices in `config.toml`. The command prints this reminder
along with the per-record report.

Stop the server before migrating. Use `--source PATH` to inspect a copied queue
file.

## Updates

Updates are manual. There is no automatic update path.

1. Stop the systemd service, if used: `spotui service disable`.
2. Optionally take an immediate backup: `spotui db backup`.
3. Run the new installer with the new `--version`, or install the new wheel.
4. Run `spotui deps upgrade` if the release notes call for a downloader update.
5. Start the service or foreground server again.

The installer refuses to update while SpotUI is running. `spotui db upgrade`
refuses while the process lock is held and creates a verified backup before
applying a schema change. Keep the previous release's wheel or reinstall its
published version for an application rollback.

## Backup, restore, and rollback

Managed backups are written under `<root>/backups/` as
`spotui-<UTC timestamp>.sqlite3` with mode `0600`. Five are retained by
default. Each copy is verified with `PRAGMA integrity_check`.

```bash
spotui db backup                         # managed backup, prune to five
spotui db backup --output /safe/path.sqlite3   # explicit new file
spotui db backup --keep 10               # managed retention
```

The SQLite online backup API makes a consistent copy while the server is
running, but stop the server before restoring or migrating.

To restore a backup:

```bash
ROOT="${SPOTUI_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/spotui}"
spotui service disable                   # or stop the foreground server
rm -f "$ROOT/spotui.sqlite3-wal" "$ROOT/spotui.sqlite3-shm"
cp /path/to/verified-backup.sqlite3 "$ROOT/spotui.sqlite3"
chmod 600 "$ROOT/spotui.sqlite3"
spotui db current
```

Application rollback and database rollback are separate decisions:

- Reinstalling an older SpotUI release is safe only while the database schema is
  compatible with it.
- Alembic downgrades are not guaranteed to preserve data added by newer
  features. Do not assume every migration can be reversed.
- If an older application cannot open the newer schema, restore the backup made
  before the update. This is the only supported general rollback path.
- Keep configuration and paired-device data: they live in the SpotUI root and
  survive reinstalls. Restoring an older database also restores its paired
  devices and import sessions.

## Uninstall

```bash
./uninstall.sh
```

The uninstaller stops and removes the optional systemd user unit, removes the
managed SpotUI environment, and removes the launcher symlink if it points at
that environment. It leaves the entire SpotUI root — configuration, database,
logs, cache, lock, backups, the managed `lucidadl` environment — along with
library roots and all music untouched. An unrelated launcher at the same path
is left in place.

To remove the whole SpotUI root as well:

```bash
./uninstall.sh --purge-data --yes
```

Data removal requires explicit confirmation. `--purge-data` also removes
SpotUI-owned directories left by the earlier scattered XDG layout. Downloaded
music and configured library roots are outside the root and are never touched.
The optional launcher and systemd unit remain separate OS integration paths and
are removed by the normal uninstall step.

## Paths

**Root:** `${SPOTUI_HOME:-${XDG_DATA_HOME:-~/.local/share}/spotui}` — by default
`~/.local/share/spotui/`.

| Data | Default under the root |
|---|---|
| Configuration | `config.toml` |
| Database | `spotui.sqlite3` |
| Database backups | `backups/` |
| Logs and rotations | `logs/spotui.log` |
| Cache | `cache/` |
| Lock file | `run/server-<root-hash>.lock` |
| Managed environments | `envs/{spotui,lucidadl}/` |
| Legacy queue | `queue.json` |

Only the optional PATH launcher
(`${XDG_BIN_HOME:-~/.local/bin}/spotui`) and systemd user unit
(`${XDG_CONFIG_HOME:-~/.config}/systemd/user/spotui.service`) remain outside
the root because the operating system requires those locations. `XDG_DATA_HOME`
selects the default root parent, and `XDG_BIN_HOME` selects the launcher
directory. All other SpotUI-owned data follows `SPOTUI_HOME`.

### Earlier scattered layout

The database was already stored at the root, so it does not move. Earlier local
builds also placed configuration in `~/.config/spotui/`, logs in
`~/.local/state/spotui/`, cache in `~/.cache/spotui/`, and the lock in
`$XDG_RUNTIME_DIR/spotui/`. Move an existing config file to
`~/.local/share/spotui/config.toml` (or point `SPOTUI_CONFIG` at it). The old
log/cache/lock directories are no longer used and can be removed once you no
longer need their contents. `uninstall.sh --purge-data` also removes those old
leftovers explicitly.
