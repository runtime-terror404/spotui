"""The ``spotui`` management and launch CLI."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from spotui import __version__
from spotui.app import create_app
from spotui.config import (
    AppConfig,
    ConfigError,
    is_explicit_config_path,
    load_config,
)
from spotui.deps import (
    SUPPORTED_LUCIDADL_VERSION,
    DependencyError,
    check_downloader,
    check_spotui_browser,
    install_downloader,
    install_spotui_browser,
    report_lines,
)
from spotui.lifecycle import (
    AlreadyRunningError,
    ProcessLock,
    ProcessLockError,
    inspect_lock,
)
from spotui.logging_setup import setup_logging
from spotui.paths import PathError, Paths
from spotui.persistence.backup import BackupError, backup_database
from spotui.persistence.database import Database, database_url_for_path
from spotui.persistence.migrate import (
    SchemaNotCurrentError,
    check_database_current,
    current_revision,
    head_revision,
    upgrade_database,
)
from spotui.persistence.repositories.legacy import LegacyQueueRepository
from spotui.runtime import ApplicationRuntime
from spotui.server import (
    Listener,
    PortUnavailableError,
    bind_listeners,
    close_listeners,
    listener_specs,
    run_server,
)
from spotui.service import (
    ServiceError,
    disable_service,
    enable_service,
    install_service,
    service_status,
    uninstall_service,
)
from spotui.services.factory import build_application_services
from spotui.services.legacy_migration import (
    LegacyMigrationError,
    LegacyMigrationService,
    render_report,
)

logger = logging.getLogger("spotui.cli")


def _add_config_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        type=Path,
        metavar="PATH",
        help="configuration file (overrides SPOTUI_CONFIG and the XDG default)",
    )


def _add_server_overrides(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--port", type=int, help="HTTP port (default 8765)")
    parser.add_argument(
        "--trusted-subnet",
        metavar="CIDR",
        help="trusted IPv4 home subnet for LAN listening (empty disables LAN)",
    )
    parser.add_argument("--log-level", help="log level (for example INFO or DEBUG)")


def _cli_overrides(args: argparse.Namespace) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    server: dict[str, Any] = {}
    port = getattr(args, "port", None)
    if port is not None:
        server["port"] = port
    subnet = getattr(args, "trusted_subnet", None)
    if subnet is not None:
        server["trusted_subnet"] = subnet
    if server:
        overrides["server"] = server
    log_level = getattr(args, "log_level", None)
    if log_level is not None:
        overrides["logging"] = {"level": log_level}
    return overrides


def _load_configuration(args: argparse.Namespace, paths: Paths) -> AppConfig:
    return load_config(
        paths,
        cli_overrides=_cli_overrides(args),
        require_file=is_explicit_config_path(cli_path=args.config, environ=os.environ),
    )


def _running_message(error: AlreadyRunningError) -> str:
    existing = error.existing or {}
    urls = existing.get("urls") or []
    details = []
    if urls:
        details.append("at " + ", ".join(str(url) for url in urls))
    if existing.get("pid"):
        details.append(f"pid {existing['pid']}")
    suffix = f" ({', '.join(details)})" if details else ""
    return (
        f"SpotUI is already running{suffix}. Use 'spotui status' or stop the "
        "existing server before starting another."
    )


def _warn_if_lan_unavailable(config: AppConfig, listeners: tuple[Listener, ...]) -> None:
    if config.server.trusted_subnet and not any(
        listener.kind == "lan" for listener in listeners
    ):
        logger.warning(
            "trusted subnet %s is configured but no matching active IPv4 interface "
            "was found; serving loopback only",
            config.server.trusted_subnet,
        )


def _cmd_serve(args: argparse.Namespace) -> int:
    paths = Paths.resolve(config_file=args.config)
    config = _load_configuration(args, paths)
    paths.ensure_runtime_directories()
    setup_logging(config.logging, paths)

    listeners = listener_specs(config)
    _warn_if_lan_unavailable(config, listeners)

    lock = ProcessLock(paths.lock_file)
    try:
        lock.acquire(
            {
                "version": __version__,
                "config": str(paths.config_file),
                "urls": [listener.url for listener in listeners],
            }
        )
    except AlreadyRunningError as exc:
        print(f"spotui: {_running_message(exc)}", file=sys.stderr)
        return 1

    try:
        try:
            check_database_current(database_url_for_path(paths.database_file))
        except SchemaNotCurrentError as exc:
            print(f"spotui: {exc}", file=sys.stderr)
            return 1

        try:
            sockets = bind_listeners(listeners)
        except PortUnavailableError as exc:
            print(f"spotui: {exc}", file=sys.stderr)
            return 1

        try:
            lock.update_metadata({"urls": [listener.url for listener in listeners]})
            for listener in listeners:
                logger.info("listening on %s (%s)", listener.url, listener.kind)
            runtime = ApplicationRuntime(
                config=config,
                paths=paths,
                listeners=listeners,
                services_factory=build_application_services,
            )
            app = create_app(runtime)
            server = run_server(app, sockets, config)
            if not server.started:
                logger.error("server failed to start")
                return 1
            return 0
        finally:
            close_listeners(sockets)
    finally:
        lock.release()


def _probe_health(base_url: str) -> str:
    try:
        with urllib.request.urlopen(f"{base_url}/api/v1/health", timeout=1.0) as response:
            payload = json.loads(response.read(4096))
    except (OSError, ValueError) as exc:
        return f"unreachable ({exc.__class__.__name__})"
    if isinstance(payload, dict) and payload.get("ok") is True:
        version = payload.get("version", "unknown")
        return f"reachable (version {version})"
    return "unexpected response"


def _cmd_status(args: argparse.Namespace) -> int:
    paths = Paths.resolve(config_file=args.config)
    config = _load_configuration(args, paths)
    listeners = listener_specs(config)
    local_listener = next(listener for listener in listeners if listener.kind == "local")

    print(f"SpotUI {__version__}")
    config_state = "" if paths.config_file.exists() else " (missing; using defaults)"
    print(f"Config: {paths.config_file}{config_state}")
    print(f"Root: {paths.data_dir}")
    print(f"Database: {paths.database_file}")
    print(f"Backups: {paths.backup_dir}")
    print(f"Logs: {paths.log_file}")
    print(f"Cache: {paths.cache_dir}")
    print(f"Lock: {paths.lock_file}")
    launcher_missing = "" if paths.launcher_file.exists() else " (not installed)"
    unit_missing = "" if paths.systemd_unit_file.exists() else " (not installed)"
    print(f"Launcher: {paths.launcher_file}{launcher_missing}")
    print(f"Systemd unit: {paths.systemd_unit_file}{unit_missing}")
    if config.server.trusted_subnet:
        lan_listener = next(
            (listener for listener in listeners if listener.kind == "lan"), None
        )
        if lan_listener is not None:
            print(f"Local: {local_listener.url}")
            print(
                f"LAN: {lan_listener.url} (trusted subnet "
                f"{config.server.trusted_subnet})"
            )
        else:
            print(f"Local: {local_listener.url}")
            print(
                f"LAN: unavailable (trusted subnet {config.server.trusted_subnet}; "
                "no matching active IPv4 interface)"
            )
    else:
        print(f"Local: {local_listener.url}")
        print("LAN: disabled (server.trusted_subnet is not configured)")

    lock_info = inspect_lock(paths.lock_file)
    if lock_info.locked:
        metadata = lock_info.metadata or {}
        urls = metadata.get("urls") or []
        pid = metadata.get("pid", "unknown")
        where = ", ".join(str(url) for url in urls) if urls else "URL unknown"
        print(f"Server: running (pid {pid}; {where})")
    else:
        print("Server: not running")
    print(f"Health: {_probe_health(local_listener.url)}")
    return 0


def _server_is_running(paths: Paths) -> bool:
    return inspect_lock(paths.lock_file).locked


def _refuse_if_server_running(paths: Paths, action: str) -> bool:
    if not _server_is_running(paths):
        return False
    print(
        f"spotui: stop the running SpotUI server before {action}",
        file=sys.stderr,
    )
    return True


def _cmd_db_backup(args: argparse.Namespace) -> int:
    paths = Paths.resolve(config_file=args.config)
    _load_configuration(args, paths)
    target = args.output.expanduser() if args.output is not None else None
    backup = backup_database(
        paths.database_file,
        paths.backup_dir,
        target=target,
        keep=args.keep,
    )
    print(f"Backup: {backup}")
    return 0


def _cmd_db_upgrade(args: argparse.Namespace) -> int:
    paths = Paths.resolve(config_file=args.config)
    config = _load_configuration(args, paths)
    paths.ensure_runtime_directories()
    setup_logging(config.logging, paths)
    if _refuse_if_server_running(paths, "applying database migrations"):
        return 1
    database_url = database_url_for_path(paths.database_file)
    print(f"Database: {paths.database_file}")
    if paths.database_file.is_file():
        current = current_revision(database_url)
        if current != head_revision():
            backup = backup_database(paths.database_file, paths.backup_dir)
            print(f"Backup before migration: {backup}")
    upgrade_database(database_url)
    check_database_current(database_url)
    print(f"Database is current at revision {current_revision(database_url)}")
    return 0


def _cmd_db_current(args: argparse.Namespace) -> int:
    paths = Paths.resolve(config_file=args.config)
    _load_configuration(args, paths)
    head = head_revision()
    if not paths.database_file.exists():
        print(f"Database: {paths.database_file}")
        print(f"Revision: not initialized (head {head})")
        return 0
    current = current_revision(database_url_for_path(paths.database_file))
    print(f"Database: {paths.database_file}")
    if current is None:
        print(f"Revision: not initialized (head {head})")
    elif current == head:
        print(f"Revision: {current} (head)")
    else:
        print(f"Revision: {current} (head {head}; run 'spotui db upgrade')")
    return 0


def _cmd_migrate_legacy(args: argparse.Namespace) -> int:
    paths = Paths.resolve(config_file=args.config)
    _load_configuration(args, paths)
    if _refuse_if_server_running(paths, "importing the legacy queue"):
        return 1
    database_url = database_url_for_path(paths.database_file)
    check_database_current(database_url)
    source = args.source or paths.legacy_queue_file
    database = Database.from_url(database_url)
    try:
        service = LegacyMigrationService(
            LegacyQueueRepository(database.session_factory)
        )
        if args.dry_run:
            report = service.migrate(source, dry_run=True)
            print(render_report(report))
            _print_legacy_configuration_note()
            return 0
        if not args.yes:
            if not sys.stdin.isatty():
                print(
                    "spotui: refusing to write without --yes in a non-interactive session",
                    file=sys.stderr,
                )
                return 1
            preview = service.migrate(source, dry_run=True)
            print(render_report(preview))
            _print_legacy_configuration_note()
            print()
            answer = input("Type 'import' to write these records: ").strip()
            if answer != "import":
                print("spotui: migration cancelled; no data was written")
                return 1
        report = service.migrate(source, dry_run=False)
        print(render_report(report))
        _print_legacy_configuration_note()
    finally:
        database.dispose()
    return 1 if report.failed else 0


def _print_legacy_configuration_note() -> None:
    print(
        "Legacy configuration: the v0 release had no settings file, so no "
        "settings were imported. Re-enter server, library root, and downloader "
        "settings in config.toml (see README)."
    )


def _cmd_service(args: argparse.Namespace) -> int:
    paths = Paths.resolve(config_file=args.config)
    if args.service_command == "install":
        unit = install_service(
            paths,
            executable=args.executable,
            daemon_reload=not args.no_daemon_reload,
        )
        print(f"Installed systemd user unit: {unit}")
        print("Enable and start it with: spotui service enable")
        return 0
    if args.service_command == "enable":
        enable_service()
        print("Enabled and started spotui.service")
        return 0
    if args.service_command == "disable":
        disable_service()
        print("Disabled and stopped spotui.service")
        return 0
    if args.service_command == "uninstall":
        existed = uninstall_service(paths)
        if existed:
            print(f"Removed systemd user unit: {paths.systemd_unit_file}")
        else:
            print(f"No systemd user unit at {paths.systemd_unit_file}")
        return 0
    print(f"spotui.service: {service_status()}")
    return 0


def _cmd_deps_check(args: argparse.Namespace) -> int:
    paths = Paths.resolve(config_file=args.config)
    downloader = check_downloader(paths)
    browser = check_spotui_browser()
    print("Managed downloader environment:")
    print(f"  Environment: {paths.lucidadl_env_dir}")
    print(f"  Pinned lucidadl: {SUPPORTED_LUCIDADL_VERSION}")
    for line in report_lines(downloader):
        print(f"  {line}")
    print()
    print("SpotUI browser runtime:")
    for line in report_lines(browser):
        print(f"  {line}")
    return 0 if downloader.ok and browser.ok else 1


def _install_deps(args: argparse.Namespace, *, upgrading: bool) -> int:
    paths = Paths.resolve(config_file=args.config)
    action = "Upgrading" if upgrading else "Installing"
    print(f"{action} managed lucidadl {SUPPORTED_LUCIDADL_VERSION} in {paths.lucidadl_env_dir}")
    try:
        install_downloader(paths)
        print("Installing SpotUI's Playwright Chromium browser…")
        install_spotui_browser()
    except DependencyError as exc:
        print(f"spotui: {exc}", file=sys.stderr)
        return 1
    print(
        "Dependency commands completed. If Cloudflare clearance is missing, run "
        f"'{paths.lucidadl_executable} setup' in a desktop session."
    )
    return _cmd_deps_check(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spotui",
        description="SpotUI local music search and download application",
    )
    parser.add_argument("--version", action="version", version=f"spotui {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="run the server in the foreground")
    _add_config_option(serve)
    _add_server_overrides(serve)
    serve.set_defaults(func=_cmd_serve)

    status = subparsers.add_parser(
        "status", help="show effective paths, URLs, lock, and health state"
    )
    _add_config_option(status)
    _add_server_overrides(status)
    status.set_defaults(func=_cmd_status)

    database = subparsers.add_parser("db", help="database migration commands")
    database_subparsers = database.add_subparsers(dest="db_command", required=True)
    upgrade = database_subparsers.add_parser("upgrade", help="apply Alembic migrations")
    _add_config_option(upgrade)
    upgrade.set_defaults(func=_cmd_db_upgrade)
    current = database_subparsers.add_parser("current", help="show the applied revision")
    _add_config_option(current)
    current.set_defaults(func=_cmd_db_current)
    backup = database_subparsers.add_parser(
        "backup",
        help="create and verify a SQLite backup before maintenance",
    )
    _add_config_option(backup)
    backup.add_argument(
        "--output",
        type=Path,
        metavar="PATH",
        help="explicit new backup file (must not already exist)",
    )
    backup.add_argument(
        "--keep",
        type=int,
        default=5,
        metavar="N",
        help="managed backups to retain in the backup directory (default 5)",
    )
    backup.set_defaults(func=_cmd_db_backup)

    legacy = subparsers.add_parser(
        "migrate-legacy",
        help="report or import the read-only legacy JSON queue",
    )
    _add_config_option(legacy)
    legacy.add_argument(
        "--source",
        type=Path,
        metavar="PATH",
        help="legacy queue.json (default: the XDG SpotUI data directory)",
    )
    legacy.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and report without writing any migration records",
    )
    legacy.add_argument(
        "--yes",
        action="store_true",
        help="write the migration without an interactive confirmation",
    )
    legacy.set_defaults(func=_cmd_migrate_legacy)

    service = subparsers.add_parser(
        "service",
        help="optional systemd user-service helpers",
    )
    service_subparsers = service.add_subparsers(
        dest="service_command",
        required=True,
    )
    service_install = service_subparsers.add_parser(
        "install",
        help="write the systemd user unit (does not enable it)",
    )
    _add_config_option(service_install)
    service_install.add_argument(
        "--exec",
        dest="executable",
        type=Path,
        metavar="PATH",
        help="installed spotui launcher (default: the managed SpotUI environment)",
    )
    service_install.add_argument(
        "--no-daemon-reload",
        action="store_true",
        help="skip systemctl --user daemon-reload (for offline unit generation)",
    )
    service_install.set_defaults(func=_cmd_service)
    for command, help_text in (
        ("enable", "enable and start the systemd user service"),
        ("disable", "disable and stop the systemd user service"),
        ("uninstall", "stop/disable and remove the systemd user unit only"),
        ("status", "show the systemd user-service state"),
    ):
        command_parser = service_subparsers.add_parser(command, help=help_text)
        _add_config_option(command_parser)
        command_parser.set_defaults(func=_cmd_service)

    deps = subparsers.add_parser("deps", help="managed downloader dependency commands")
    deps_subparsers = deps.add_subparsers(dest="deps_command", required=True)
    deps_check = deps_subparsers.add_parser("check", help="verify the managed environment")
    _add_config_option(deps_check)
    deps_check.set_defaults(func=_cmd_deps_check)
    deps_install = deps_subparsers.add_parser(
        "install", help="install the pinned downloader environment"
    )
    _add_config_option(deps_install)
    deps_install.set_defaults(func=lambda args: _install_deps(args, upgrading=False))
    deps_upgrade = deps_subparsers.add_parser(
        "upgrade", help="reconcile the managed environment to the pinned release"
    )
    _add_config_option(deps_upgrade)
    deps_upgrade.set_defaults(func=lambda args: _install_deps(args, upgrading=True))

    return parser


_KNOWN_ERRORS = (
    ConfigError,
    PathError,
    BackupError,
    LegacyMigrationError,
    ServiceError,
    ProcessLockError,
    PortUnavailableError,
    SchemaNotCurrentError,
    DependencyError,
    SQLAlchemyError,
    OSError,
)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("spotui: interrupted", file=sys.stderr)
        return 130
    except _KNOWN_ERRORS as exc:
        print(f"spotui: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
