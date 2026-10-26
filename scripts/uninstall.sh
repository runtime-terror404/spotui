#!/usr/bin/env bash
# Remove SpotUI's installed code and optional user service.
# User data is retained unless --purge-data is explicitly supplied.
set -euo pipefail
umask 077

PURGE_DATA=false
CONFIRMED=false

usage() {
    cat <<'EOF'
Usage: uninstall.sh [options]

Removes the managed SpotUI environment, launcher, and optional systemd user
unit. The complete SpotUI root, including configuration, database, logs,
cache, and the lucidadl environment, remains in place unless --purge-data is
used. Music outside the root is never touched.

Options:
  --purge-data   Also remove the complete SpotUI root and old scattered dirs
  --yes          Skip the destructive purge confirmation prompt
  -h, --help     Show this help

Environment:
  SPOTUI_HOME    Absolute root used by the installation
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --purge-data)
            PURGE_DATA=true
            shift
            ;;
        --yes)
            CONFIRMED=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "uninstall.sh: unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ -z "${HOME:-}" ]]; then
    echo "uninstall.sh: HOME is not set" >&2
    exit 1
fi
if [[ "$(id -u)" -eq 0 ]]; then
    echo "uninstall.sh: run as your normal user, not root" >&2
    exit 1
fi

if [[ -n "${SPOTUI_HOME:-}" ]]; then
    DATA_DIR="$SPOTUI_HOME"
else
    DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
    DATA_DIR="$DATA_HOME/spotui"
fi
STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
LEGACY_STATE_DIR="$STATE_HOME/spotui"
LEGACY_CACHE_DIR="$CACHE_HOME/spotui"
LEGACY_CONFIG_DIR="$CONFIG_HOME/spotui"
ENV_DIR="$DATA_DIR/envs/spotui"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
LAUNCHER="$BIN_DIR/spotui"
UNIT_FILE="$CONFIG_HOME/systemd/user/spotui.service"

if [[ "$DATA_DIR" != /* || "$DATA_DIR" == "/" || "$DATA_DIR" == "$HOME" ]]; then
    echo "uninstall.sh: refusing unsafe SpotUI root: $DATA_DIR" >&2
    exit 1
fi

if [[ -x "$ENV_DIR/bin/spotui" ]]; then
    "$ENV_DIR/bin/spotui" service uninstall || {
        echo "uninstall.sh: could not remove the systemd unit automatically" >&2
    }
elif [[ -f "$UNIT_FILE" ]]; then
    systemctl --user disable --now spotui.service >/dev/null 2>&1 || true
    rm -f "$UNIT_FILE"
    systemctl --user daemon-reload >/dev/null 2>&1 || true
fi

if [[ -x "$ENV_DIR/bin/spotui" ]]; then
    server_status="$("$ENV_DIR/bin/spotui" status 2>/dev/null || true)"
    if grep -q '^Server: running' <<< "$server_status"; then
        echo "uninstall.sh: SpotUI is still running" >&2
        echo "uninstall.sh: stop the foreground server, then rerun this script" >&2
        exit 1
    fi
fi

if [[ -L "$LAUNCHER" ]]; then
    target="$(readlink "$LAUNCHER" || true)"
    if [[ "$target" == "$ENV_DIR/bin/spotui" ]]; then
        rm -f "$LAUNCHER"
        echo "Removed launcher: $LAUNCHER"
    else
        echo "uninstall.sh: leaving unrelated launcher at $LAUNCHER" >&2
    fi
elif [[ -e "$LAUNCHER" ]]; then
    echo "uninstall.sh: leaving non-managed launcher at $LAUNCHER" >&2
fi

if [[ -d "$ENV_DIR" ]]; then
    rm -rf "$ENV_DIR"
    echo "Removed managed environment: $ENV_DIR"
fi
rmdir "$DATA_DIR/envs" 2>/dev/null || true

if [[ "$PURGE_DATA" == true ]]; then
    if [[ "$CONFIRMED" != true ]]; then
        if [[ ! -t 0 ]]; then
            echo "uninstall.sh: --purge-data in a non-interactive session requires --yes" >&2
            exit 1
        fi
        echo "This permanently deletes the complete SpotUI root at:"
        echo "  $DATA_DIR"
        echo "It includes configuration, database, logs, cache, and the managed"
        echo "lucidadl environment. Music outside the root is never touched."
        read -r -p "Type 'delete' to continue: " answer
        if [[ "$answer" != "delete" ]]; then
            echo "uninstall.sh: purge cancelled; installed code has been removed"
            exit 1
        fi
    fi
    rm -rf "$DATA_DIR"
    echo "Removed: $DATA_DIR"
    for path in "$LEGACY_CONFIG_DIR" "$LEGACY_STATE_DIR" "$LEGACY_CACHE_DIR"; do
        if [[ -d "$path" ]]; then
            rm -rf "$path"
            echo "Removed legacy scattered directory: $path"
        fi
    done
else
    echo
    echo "User data was preserved under:"
    echo "  $DATA_DIR"
    echo "  Configuration: $DATA_DIR/config.toml"
    echo "  Database:      $DATA_DIR/spotui.sqlite3"
    echo "  Logs:          $DATA_DIR/logs"
    echo "To remove it explicitly, rerun with --purge-data."
fi
