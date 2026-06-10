"""Structured logging via loguru — routes stdlib logging through the same JSON sink."""

import logging
import sys

from loguru import logger


class _InterceptHandler(logging.Handler):
    """Forward every stdlib log record to loguru so FastAPI/uvicorn logs are structured."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging() -> None:
    """Configure loguru as the single structured JSON sink (stdout)."""
    logger.remove()
    logger.add(sys.stdout, serialize=True, level="INFO")
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
