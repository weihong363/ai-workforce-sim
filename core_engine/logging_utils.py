"""Minimal structured logging helpers."""

import json
import logging
from typing import Any


LOGGER_NAME = "sim_engine"


def setup_logging() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
    return logger


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    logger.info(json.dumps(payload, ensure_ascii=True))
