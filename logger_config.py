"""
logger_config.py — RestIQ
Structured logging with agent-specific prefixes for every pipeline step.
"""

import logging
import sys
from enum import Enum


class AgentPrefix(str, Enum):
    INTAKE = "[INTAKE]"
    SCHEDULER = "[SCHEDULER]"
    TRACKER = "[TRACKER]"
    ANALYZER = "[ANALYZER]"
    REPORTER = "[REPORTER]"
    PIPELINE = "[PIPELINE]"
    BOT = "[BOT]"


def get_logger(name: str, prefix: AgentPrefix | None = None) -> logging.Logger:
    """
    Returns a named logger pre-configured with a consistent format.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(prefix)-12s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File handler — writes all logs to restiq.log
    fh = logging.FileHandler("restiq.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Inject the prefix into every LogRecord as a default extra
    _prefix_str = prefix.value if prefix else ""
    logger = logging.LoggerAdapter(logger, extra={"prefix": _prefix_str})

    return logger  # type: ignore[return-value]


def get_pipeline_logger() -> logging.Logger:
    return get_logger("pipeline", AgentPrefix.PIPELINE)  # type: ignore[return-value]


def get_bot_logger() -> logging.Logger:
    return get_logger("bot", AgentPrefix.BOT)  # type: ignore[return-value]
