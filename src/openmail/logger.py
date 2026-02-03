from __future__ import annotations

import logging

LOGGER_NAME = "email_manager"

def get_logger(name: str = LOGGER_NAME) -> logging.Logger:
    return logging.getLogger(name)

def configure_logging(level: int = logging.INFO) -> None:
    logger = get_logger()
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(level)
