from __future__ import annotations

import os

import pytest

from spotui.config import ConfigError, load_config
from tests.helpers import write_config


def test_defaults(env) -> None:
    config = env.config

    assert config.server.port == 8765
    assert config.server.trusted_subnet is None
    assert config.server.shutdown_grace_seconds == 5.0
    assert config.logging.level == "INFO"
    assert config.logging.max_bytes == 5 * 1024 * 1024
    assert config.logging.backup_count == 5
    assert config.queue.cancel_grace_seconds == 5.0
    assert config.queue.shutdown_grace_seconds == 5.0
    assert config.queue.job_timeout_seconds == 900.0
    assert config.library.roots == ()
    assert config.library.refresh_seconds == 3600
    assert config.library.scan_on_startup is True


def test_file_values_override_defaults(env) -> None:
    write_config(
        env.paths,
        """
[server]
port = 9000
trusted_subnet = "192.168.1.0/24"
shutdown_grace_seconds = 2.5

[logging]
level = "debug"
max_bytes = 1024
backup_count = 2

[queue]
cancel_grace_seconds = 2.0
shutdown_grace_seconds = 3.0
job_timeout_seconds = 600.0

[library]
roots = ["/music/one", "/music/two"]
refresh_seconds = 600
scan_on_startup = false
""",
    )

    config = load_config(env.paths, environ={})

    assert config.server.port == 9000
    assert config.server.trusted_subnet == "192.168.1.0/24"
    assert config.server.shutdown_grace_seconds == 2.5
    assert config.logging.level == "DEBUG"
    assert config.logging.max_bytes == 1024
    assert config.logging.backup_count == 2
    assert config.queue.cancel_grace_seconds == 2.0
    assert config.queue.shutdown_grace_seconds == 3.0
    assert config.queue.job_timeout_seconds == 600.0
    assert config.library.roots == ("/music/one", "/music/two")
    assert config.library.refresh_seconds == 600
    assert config.library.scan_on_startup is False


def test_environment_overrides_file_and_cli_overrides_environment(env) -> None:
    write_config(env.paths, "[server]\nport = 9000\n")

    from_env = load_config(env.paths, environ={"SPOTUI_PORT": "9100"})
    from_cli = load_config(
        env.paths,
        environ={"SPOTUI_PORT": "9100"},
        cli_overrides={"server": {"port": 9200}},
    )

    assert from_env.server.port == 9100
    assert from_cli.server.port == 9200


def test_environment_subnet_override(env) -> None:
    config = load_config(env.paths, environ={"SPOTUI_TRUSTED_SUBNET": "10.0.0.0/24"})

    assert config.server.trusted_subnet == "10.0.0.0/24"


def test_queue_environment_overrides(env) -> None:
    config = load_config(
        env.paths,
        environ={
            "SPOTUI_CANCEL_GRACE_SECONDS": "1.5",
            "SPOTUI_QUEUE_SHUTDOWN_GRACE_SECONDS": "2.5",
            "SPOTUI_JOB_TIMEOUT_SECONDS": "600",
        },
    )

    assert config.queue.cancel_grace_seconds == 1.5
    assert config.queue.shutdown_grace_seconds == 2.5
    assert config.queue.job_timeout_seconds == 600.0


def test_library_environment_overrides(env) -> None:
    first = env.root / "library-one"
    second = env.root / "library-two"
    first.mkdir()
    second.mkdir()

    config = load_config(
        env.paths,
        environ={
            "SPOTUI_LIBRARY_ROOTS": os.pathsep.join((str(first), str(second))),
            "SPOTUI_LIBRARY_REFRESH_SECONDS": "120",
            "SPOTUI_LIBRARY_SCAN_ON_STARTUP": "false",
        },
    )

    assert config.library.roots == (str(first.resolve()), str(second.resolve()))
    assert config.library.refresh_seconds == 120
    assert config.library.scan_on_startup is False


def test_library_roots_must_be_absolute(env) -> None:
    with pytest.raises(ConfigError, match="absolute"):
        load_config(env.paths, environ={"SPOTUI_LIBRARY_ROOTS": "relative/music"})


def test_duplicate_library_roots_are_rejected(env) -> None:
    root = env.root / "music"
    root.mkdir()

    with pytest.raises(ConfigError, match="duplicate library root"):
        load_config(
            env.paths,
            environ={"SPOTUI_LIBRARY_ROOTS": os.pathsep.join((str(root), str(root)))},
        )


def test_library_root_that_is_a_file_is_rejected(env) -> None:
    file_path = env.root / "music.flac"
    file_path.write_bytes(b"audio")

    with pytest.raises(ConfigError, match="not a directory"):
        load_config(env.paths, environ={"SPOTUI_LIBRARY_ROOTS": str(file_path)})


@pytest.mark.parametrize(
    "value",
    ["-1", "86401", "not-a-number"],
)
def test_invalid_library_refresh_interval_is_rejected(env, value: str) -> None:
    with pytest.raises(ConfigError, match="refresh_seconds|SPOTUI_LIBRARY_REFRESH_SECONDS"):
        load_config(env.paths, environ={"SPOTUI_LIBRARY_REFRESH_SECONDS": value})


def test_invalid_library_scan_boolean_is_rejected(env) -> None:
    with pytest.raises(ConfigError, match="SPOTUI_LIBRARY_SCAN_ON_STARTUP"):
        load_config(env.paths, environ={"SPOTUI_LIBRARY_SCAN_ON_STARTUP": "sometimes"})


def test_empty_trusted_subnet_means_localhost_only(env) -> None:
    write_config(env.paths, '[server]\ntrusted_subnet = ""\n')

    config = load_config(env.paths, environ={})

    assert config.server.trusted_subnet is None


@pytest.mark.parametrize("port", ["0", "65536", "not-a-port"])
def test_invalid_ports_are_rejected(env, port: str) -> None:
    with pytest.raises(ConfigError, match="port"):
        load_config(env.paths, environ={"SPOTUI_PORT": port})


def test_invalid_subnet_is_rejected(env) -> None:
    with pytest.raises(ConfigError, match="trusted_subnet"):
        load_config(env.paths, environ={"SPOTUI_TRUSTED_SUBNET": "192.168.1.0/33"})


def test_ipv6_subnet_is_rejected(env) -> None:
    with pytest.raises(ConfigError, match="IPv4"):
        load_config(env.paths, environ={"SPOTUI_TRUSTED_SUBNET": "fd00::/64"})


def test_unknown_config_keys_are_rejected(env) -> None:
    write_config(env.paths, "[server]\nprot = 8765\n")

    with pytest.raises(ConfigError, match="prot"):
        load_config(env.paths, environ={})


def test_unknown_log_level_is_rejected(env) -> None:
    with pytest.raises(ConfigError, match="log level"):
        load_config(env.paths, environ={"SPOTUI_LOG_LEVEL": "LOUD"})


def test_malformed_toml_is_reported(env) -> None:
    write_config(env.paths, "[server\nport = 8765\n")

    with pytest.raises(ConfigError, match="invalid TOML"):
        load_config(env.paths, environ={})


def test_missing_explicit_config_file_is_an_error(env) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(env.paths, environ={}, require_file=True)


def test_invalid_environment_number_is_reported(env) -> None:
    with pytest.raises(ConfigError, match="SPOTUI_LOG_MAX_BYTES"):
        load_config(env.paths, environ={"SPOTUI_LOG_MAX_BYTES": "many"})


@pytest.mark.parametrize("value", ["-1", "61", "not-a-number"])
def test_invalid_queue_grace_is_rejected(env, value: str) -> None:
    with pytest.raises(ConfigError, match="cancel_grace_seconds|SPOTUI_CANCEL_GRACE_SECONDS"):
        load_config(env.paths, environ={"SPOTUI_CANCEL_GRACE_SECONDS": value})
