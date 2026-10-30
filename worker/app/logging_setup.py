"""JSON logs to logs/worker.log. Spec: specs/11-coding-standards.md#6-logging-all-three-apps"""

from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import structlog
from structlog.typing import EventDict, WrappedLogger

SERVICE = "worker"
BACKUP_DAYS = 14


def _add_service(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    event_dict["service"] = SERVICE
    return event_dict


def _uppercase_level(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    event_dict["level"] = event_dict["level"].upper()
    return event_dict


def configure_logging(logs_dir: Path) -> None:
    """Sends structlog output, one JSON object per line, to a file rotated daily."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    handler = TimedRotatingFileHandler(
        logs_dir / "worker.log", when="midnight", backupCount=BACKUP_DAYS, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    # httpx logs plain text at INFO, which would break the one-JSON-object-per-line format.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            _uppercase_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="ts"),
            _add_service,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
