from __future__ import annotations

import logging
import stat

from spotui.config import LoggingSettings
from spotui.logging_setup import log_context, redact_text, reset_logging, setup_logging


def test_redacts_credentials_cookies_and_pairing_codes() -> None:
    text = (
        "Authorization: Bearer abc.def.ghi\n"
        "Cookie: cf_clearance=super-secret; other=value\n"
        "url=https://example.test/check?token=query-secret&q=music\n"
        "pairing code 123456\n"
        'body={"password": "hunter2"}'
    )

    redacted = redact_text(text)

    for secret in ("abc.def.ghi", "super-secret", "query-secret", "123456", "hunter2"):
        assert secret not in redacted
    assert "[REDACTED]" in redacted
    assert "q=music" in redacted


def test_setup_logging_writes_context_to_file(env) -> None:
    setup_logging(env.config.logging, env.paths, console=False)

    with log_context(request_id="req-1", job_id="job-1", import_id="imp-1"):
        logging.getLogger("spotui.test").info("hello from the test")
    for handler in logging.getLogger().handlers:
        handler.flush()

    contents = env.paths.log_file.read_text(encoding="utf-8")
    assert "hello from the test" in contents
    assert "request_id=req-1" in contents
    assert "job_id=job-1" in contents
    assert "import_id=imp-1" in contents
    assert "INFO" in contents
    assert stat.S_IMODE(env.paths.log_file.stat().st_mode) == 0o600


def test_log_file_rotates_and_is_bounded(env) -> None:
    settings = LoggingSettings(level="INFO", max_bytes=200, backup_count=2)
    setup_logging(settings, env.paths, console=False)
    logger = logging.getLogger("spotui.rotate")

    for index in range(30):
        logger.info("message %s %s", index, "x" * 80)
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert env.paths.log_file.exists()
    assert (env.paths.log_dir / "spotui.log.1").exists()
    assert not (env.paths.log_dir / "spotui.log.3").exists()


def test_setup_logging_is_idempotent(env) -> None:
    setup_logging(env.config.logging, env.paths, console=True)
    setup_logging(env.config.logging, env.paths, console=True)

    managed = [
        handler
        for handler in logging.getLogger().handlers
        if getattr(handler, "_spotui_managed", False)
    ]
    assert len(managed) == 2  # file + console


def test_reset_logging_removes_handlers(env) -> None:
    setup_logging(env.config.logging, env.paths, console=False)

    reset_logging()

    assert not [
        handler
        for handler in logging.getLogger().handlers
        if getattr(handler, "_spotui_managed", False)
    ]
