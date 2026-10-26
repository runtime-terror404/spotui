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
unit. Configuration, database, logs, caches, the lucidadl environment, and all
music remain in place unless --purge-data is used.

Options:
  --purge-data   Also remove SpotUI configuration, database, logs, and caches
  --yes          Skip the destructive purge confirmation prompt
  -h, --help     Show this help
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

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
DATA_DIR="$DATA_HOME/spotui"
STATE_DIR="$STATE_HOME/spotui"
CACHE_DIR="$CACHE_HOME/spotui"
CONFIG_DIR="$CONFIG_HOME/spotui"
ENV_DIR="$DATA_DIR/envs/spotui"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
LAUNCHER="$BIN_DIR/spotui"
UNIT_FILE="$CONFIG_HOME/systemd/user/spotui.service"

for path in "$DATA_DIR" "$STATE_DIR" "$CACHE_DIR" "$CONFIG_DIR"; do
    if [[ "$path" != /* ]]; then
        echo "uninstall.sh: refusing non-absolute XDG path: $path" >&2
        exit 1
    fi
done

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
        echo "This permanently deletes SpotUI configuration, the database, logs,"
        echo "caches, and the managed lucidadl environment. Music is never touched."
        read -r -p "Type 'delete' to continue: " answer
        if [[ "$answer" != "delete" ]]; then
            echo "uninstall.sh: purge cancelled; installed code has been removed"
            exit 1
        fi
    fi
    for path in "$CONFIG_DIR" "$DATA_DIR" "$STATE_DIR" "$CACHE_DIR"; do
        case "$path" in
            "$CONFIG_HOME"/*|"$DATA_HOME"/*|"$STATE_HOME"/*|"$CACHE_HOME"/*) ;;
            *)
                echo "uninstall.sh: refusing unexpected purge path: $path" >&2
                exit 1
                ;;
        esac
        rm -rf "$path"
        echo "Removed: $path"
    done
else
    echo
    echo "User data was preserved:"
    echo "  Configuration: $CONFIG_DIR"
    echo "  Database:      $DATA_DIR/spotui.sqlite3"
    echo "  Logs:          $STATE_DIR/logs"
    echo "To remove it explicitly, rerun with --purge-data."
fi
