#!/usr/bin/env bash
# Install or update SpotUI in an isolated uv-managed environment.
set -euo pipefail
umask 077

REPOSITORY="${SPOTUI_REPOSITORY:-runtime-terror404/spotui}"
PYTHON_VERSION="${SPOTUI_PYTHON:-3.11}"
VERSION=""
WHEEL=""
INSTALL_SERVICE=false
ENABLE_SERVICE=false
RUN_MIGRATIONS=true

usage() {
    cat <<'EOF'
Usage: install.sh [options]

Installs or updates SpotUI without touching system Python. User configuration,
the SQLite database, logs, downloads, and library roots are preserved.

Options:
  --version VERSION       Install a published version (for example 0.1.0)
  --wheel PATH            Install a local wheel instead of downloading one
  --repository OWNER/REPO GitHub repository for release downloads
  --python VERSION        uv-managed Python version (default 3.11)
  --service               Write the optional systemd user unit
  --enable-service        Write, enable, and start the systemd user unit
  --no-migrate            Do not back up or upgrade the database
  -h, --help              Show this help

Environment:
  SPOTUI_REPOSITORY       Default GitHub repository
  SPOTUI_PYTHON           Default Python version (3.11)
EOF
}

require_value() {
    if [[ $# -lt 2 || -z "$2" ]]; then
        echo "install.sh: $1 requires a value" >&2
        exit 2
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            require_value "$@"
            VERSION="${2#v}"
            shift 2
            ;;
        --wheel)
            require_value "$@"
            WHEEL="$2"
            shift 2
            ;;
        --repository)
            require_value "$@"
            REPOSITORY="$2"
            shift 2
            ;;
        --python)
            require_value "$@"
            PYTHON_VERSION="$2"
            shift 2
            ;;
        --service)
            INSTALL_SERVICE=true
            shift
            ;;
        --enable-service)
            INSTALL_SERVICE=true
            ENABLE_SERVICE=true
            shift
            ;;
        --no-migrate)
            RUN_MIGRATIONS=false
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "install.sh: unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ -z "${HOME:-}" ]]; then
    echo "install.sh: HOME is not set" >&2
    exit 1
fi
if [[ "$(id -u)" -eq 0 ]]; then
    echo "install.sh: install SpotUI as your normal user, not root" >&2
    exit 1
fi
if [[ -n "$WHEEL" && -n "$VERSION" ]]; then
    echo "install.sh: use either --wheel or --version, not both" >&2
    exit 2
fi
if ! command -v uv >/dev/null 2>&1; then
    echo "install.sh: uv is required (https://docs.astral.sh/uv/)" >&2
    exit 1
fi

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
DATA_DIR="$DATA_HOME/spotui"
ENV_DIR="$DATA_DIR/envs/spotui"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
LAUNCHER="$BIN_DIR/spotui"

TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/spotui-install.XXXXXX")"
cleanup() {
    rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

download_release_wheel() {
    if [[ -z "$VERSION" ]]; then
        local api="https://api.github.com/repos/$REPOSITORY/releases/latest"
        local tag
        tag="$(curl -fsSL --retry 3 --proto '=https' --tlsv1.2 "$api" \
            | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
            | head -n 1)"
        if [[ -z "$tag" ]]; then
            echo "install.sh: could not determine the latest release of $REPOSITORY" >&2
            echo "install.sh: pass --version or --wheel" >&2
            exit 1
        fi
        VERSION="${tag#v}"
    fi
    local wheel_name="spotui-${VERSION}-py3-none-any.whl"
    local base="https://github.com/$REPOSITORY/releases/download/v${VERSION}"
    local sums="$TEMP_DIR/SHA256SUMS"
    WHEEL="$TEMP_DIR/$wheel_name"

    echo "Downloading SpotUI $VERSION from $REPOSITORY…"
    curl -fL --retry 3 --proto '=https' --tlsv1.2 \
        -o "$WHEEL" "$base/$wheel_name"
    curl -fL --retry 3 --proto '=https' --tlsv1.2 \
        -o "$sums" "$base/SHA256SUMS"
    if ! grep -F "  ${wheel_name}" "$sums" > "$TEMP_DIR/expected"; then
        echo "install.sh: SHA256SUMS does not list $wheel_name" >&2
        exit 1
    fi
    if ! (
        cd "$TEMP_DIR"
        sha256sum --check --strict expected
    ); then
        echo "install.sh: wheel checksum verification failed" >&2
        exit 1
    fi
}

ensure_server_stopped() {
    if [[ ! -x "$ENV_DIR/bin/spotui" ]]; then
        return
    fi
    local status
    status="$("$ENV_DIR/bin/spotui" status 2>/dev/null || true)"
    if grep -q '^Server: running' <<< "$status"; then
        echo "install.sh: SpotUI is running; stop it before installing an update" >&2
        echo "install.sh: systemctl --user stop spotui.service" >&2
        exit 1
    fi
}

if [[ -n "$WHEEL" ]]; then
    if [[ ! -f "$WHEEL" ]]; then
        echo "install.sh: wheel not found: $WHEEL" >&2
        exit 1
    fi
    WHEEL="$(cd "$(dirname "$WHEEL")" && pwd)/$(basename "$WHEEL")"
    echo "Using local wheel: $WHEEL"
else
    if ! command -v curl >/dev/null 2>&1; then
        echo "install.sh: curl is required for release downloads" >&2
        exit 1
    fi
    download_release_wheel
fi

WHEEL_NAME="$(basename "$WHEEL")"
if [[ "$WHEEL_NAME" != spotui-*.whl ]]; then
    echo "install.sh: invalid wheel filename: $WHEEL_NAME" >&2
    echo "install.sh: use the built artifact named spotui-<version>-py3-none-any.whl" >&2
    exit 1
fi

ensure_server_stopped

echo "Preparing the managed SpotUI environment at $ENV_DIR"
mkdir -p "$DATA_DIR/envs"
if ! uv venv --allow-existing --python "$PYTHON_VERSION" "$ENV_DIR"; then
    echo "install.sh: could not create the managed Python environment" >&2
    exit 1
fi
if ! uv pip install --python "$ENV_DIR/bin/python" --reinstall "$WHEEL"; then
    echo "install.sh: could not install SpotUI into the managed environment" >&2
    exit 1
fi

if [[ ! -x "$ENV_DIR/bin/spotui" ]]; then
    echo "install.sh: installation did not create $ENV_DIR/bin/spotui" >&2
    exit 1
fi
INSTALLED_VERSION="$("$ENV_DIR/bin/spotui" --version 2>/dev/null || true)"
if [[ -z "$INSTALLED_VERSION" ]]; then
    echo "install.sh: the installed SpotUI executable did not report a version" >&2
    exit 1
fi
if [[ -n "$VERSION" && "$INSTALLED_VERSION" != "spotui $VERSION" ]]; then
    echo "install.sh: expected spotui $VERSION, installed $INSTALLED_VERSION" >&2
    exit 1
fi
echo "Installed: $INSTALLED_VERSION"

ensure_server_stopped

if [[ "$RUN_MIGRATIONS" == true ]]; then
    echo "Applying database migrations (existing databases are backed up first)…"
    if ! "$ENV_DIR/bin/spotui" db upgrade; then
        echo "install.sh: database migration failed; the previous backup was retained" >&2
        exit 1
    fi
else
    echo "Skipping database migrations (--no-migrate)."
fi

mkdir -p "$BIN_DIR"
if [[ -L "$LAUNCHER" ]]; then
    current_target="$(readlink "$LAUNCHER" || true)"
    if [[ "$current_target" != "$ENV_DIR/bin/spotui" ]]; then
        backup="$LAUNCHER.legacy-$(date -u +%Y%m%dT%H%M%SZ)"
        mv "$LAUNCHER" "$backup"
        echo "Preserved existing launcher at $backup"
    fi
elif [[ -e "$LAUNCHER" ]]; then
    backup="$LAUNCHER.legacy-$(date -u +%Y%m%dT%H%M%SZ)"
    mv "$LAUNCHER" "$backup"
    echo "Preserved existing launcher at $backup"
fi
ln -sfn "$ENV_DIR/bin/spotui" "$LAUNCHER"
echo "Launcher: $LAUNCHER"

if [[ "$INSTALL_SERVICE" == true ]]; then
    if ! "$ENV_DIR/bin/spotui" service install --exec "$LAUNCHER"; then
        echo "install.sh: could not install the systemd user unit" >&2
        exit 1
    fi
    if [[ "$ENABLE_SERVICE" == true ]]; then
        if ! "$ENV_DIR/bin/spotui" service enable; then
            echo "install.sh: could not enable the systemd user unit" >&2
            exit 1
        fi
    fi
fi

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo "install.sh: add $BIN_DIR to PATH to use the 'spotui' command" >&2
fi

echo
echo "SpotUI is installed ($INSTALLED_VERSION)."
echo "Install the downloader/browser dependencies explicitly with:"
echo "  spotui deps install"
echo "Then start it in the foreground with:"
echo "  spotui serve"
echo "Optional systemd helpers:"
echo "  spotui service install --exec $LAUNCHER"
echo "  spotui service enable"
echo "Legacy queue import (dry run first):"
echo "  spotui migrate-legacy --dry-run"
echo "Database backups:"
echo "  spotui db backup"
