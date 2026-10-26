"""Configuration loading and validation.

Precedence, lowest to highest:

1. Built-in defaults.
2. ``config.toml`` under the resolved XDG config directory.
3. ``SPOTUI_*`` environment variables intended for deployment.
4. CLI flags.

The merged result is validated once at startup so that invalid ports, subnets,
and log settings fail with an actionable message before any listener is bound.
"""

from __future__ import annotations

import copy
import ipaddress
import logging
import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from spotui.paths import Paths


class ConfigError(RuntimeError):
    """A configuration file or override is invalid or unreadable."""


class ServerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    port: int = Field(default=8765, ge=1, le=65535)
    trusted_subnet: str | None = None
    shutdown_grace_seconds: float = Field(default=5.0, ge=0.0, le=300.0)

    @field_validator("trusted_subnet", mode="before")
    @classmethod
    def _validate_trusted_subnet(cls, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        try:
            network = ipaddress.ip_network(str(value), strict=False)
        except ValueError as exc:
            raise ValueError(
                "must be a valid IPv4 CIDR (for example 192.168.1.0/24): "
                f"{exc}"
            ) from exc
        if network.version != 4:
            raise ValueError("must be an IPv4 CIDR; IPv6 LAN binding is not supported")
        return str(network)


class LoggingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    level: str = "INFO"
    max_bytes: int = Field(default=5 * 1024 * 1024, ge=1)
    backup_count: int = Field(default=5, ge=1)

    @field_validator("level", mode="before")
    @classmethod
    def _validate_level(cls, value: object) -> str:
        level = str(value).strip().upper()
        if level not in logging.getLevelNamesMapping() or not isinstance(
            logging.getLevelNamesMapping()[level], int
        ):
            raise ValueError(f"unknown log level {value!r}")
        return level


class QueueSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cancel_grace_seconds: float = Field(default=5.0, ge=0.0, le=60.0)
    shutdown_grace_seconds: float = Field(default=5.0, ge=0.0, le=60.0)
    job_timeout_seconds: float = Field(default=900.0, ge=10.0, le=7200.0)


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    server: ServerSettings = Field(default_factory=ServerSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    queue: QueueSettings = Field(default_factory=QueueSettings)


_ENV_SETTINGS: dict[str, tuple[str, str, type[Any]]] = {
    "SPOTUI_PORT": ("server", "port", int),
    "SPOTUI_TRUSTED_SUBNET": ("server", "trusted_subnet", str),
    "SPOTUI_SHUTDOWN_GRACE_SECONDS": ("server", "shutdown_grace_seconds", float),
    "SPOTUI_LOG_LEVEL": ("logging", "level", str),
    "SPOTUI_LOG_MAX_BYTES": ("logging", "max_bytes", int),
    "SPOTUI_LOG_BACKUP_COUNT": ("logging", "backup_count", int),
    "SPOTUI_CANCEL_GRACE_SECONDS": ("queue", "cancel_grace_seconds", float),
    "SPOTUI_QUEUE_SHUTDOWN_GRACE_SECONDS": ("queue", "shutdown_grace_seconds", float),
    "SPOTUI_JOB_TIMEOUT_SECONDS": ("queue", "job_timeout_seconds", float),
}


def _merge(base: dict[str, Any], incoming: Mapping[str, Any]) -> None:
    for key, value in incoming.items():
        if isinstance(value, Mapping) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ConfigError(f"cannot read configuration file {path}: {exc}") from exc
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"configuration file {path} must contain a TOML table")
    return data


def _env_overrides(environ: Mapping[str, str]) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for variable, (section, key, converter) in _ENV_SETTINGS.items():
        if variable not in environ:
            continue
        raw = environ[variable].strip()
        try:
            value: Any = converter(raw)
        except ValueError as exc:
            raise ConfigError(f"{variable} has invalid value {raw!r}: {exc}") from exc
        overrides.setdefault(section, {})[key] = value
    return overrides


def _format_validation_error(path: Path, exc: ValidationError) -> ConfigError:
    details = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "configuration"
        details.append(f"  {location}: {error['msg']}")
    joined = "\n".join(details)
    return ConfigError(f"invalid configuration in {path}:\n{joined}")


def load_config(
    paths: Paths,
    *,
    environ: Mapping[str, str] | None = None,
    cli_overrides: Mapping[str, Any] | None = None,
    require_file: bool = False,
) -> AppConfig:
    """Load, merge, and validate configuration.

    ``require_file`` should be true when the user explicitly selected a config
    path; a missing explicit file is more likely a mistake than a fresh install.
    """
    env = os.environ if environ is None else environ
    if require_file and not paths.config_file.is_file():
        raise ConfigError(f"configuration file not found: {paths.config_file}")

    merged = _read_toml(paths.config_file)
    _merge(merged, _env_overrides(env))
    if cli_overrides:
        _merge(merged, cli_overrides)

    try:
        return AppConfig.model_validate(merged)
    except ValidationError as exc:
        raise _format_validation_error(paths.config_file, exc) from exc


def is_explicit_config_path(*, cli_path: str | Path | None, environ: Mapping[str, str]) -> bool:
    """Whether a config file was explicitly requested by flag or environment."""
    return cli_path is not None or bool(environ.get("SPOTUI_CONFIG", "").strip())
