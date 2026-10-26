"""Centralised logging configuration for CVAuto.

Call :func:`setup_logging` once at application start-up.
"""

from __future__ import annotations

import logging
import sys


class _StdoutHandler(logging.StreamHandler):
    """Logs INFO and below to stdout."""

    def __init__(self) -> None:
        super().__init__(sys.stdout)
        self.setLevel(logging.DEBUG)
        self.addFilter(lambda record: record.levelno <= logging.INFO)


class _StderrHandler(logging.StreamHandler):
    """Logs WARNING and above to stderr."""

    def __init__(self) -> None:
        super().__init__(sys.stderr)
        self.setLevel(logging.WARNING)


def setup_logging(*, level: int = logging.INFO, log_file: str | None = None) -> None:
    """Configure root loggers for cvauto.

    Parameters
    ----------
    level:
        Console logging level (default ``INFO``).
    log_file:
        Optional path to a file handler that receives *all* messages.
    """
    fmt = "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"
    datefmt = "%H:%M:%S"
    formatter = logging.Formatter(fmt, datefmt)

    root = logging.getLogger("cvauto")
    root.setLevel(logging.DEBUG)
    root.handlers = []

    # stdout (info and below)
    out_handler = _StdoutHandler()
    out_handler.setFormatter(formatter)
    out_handler.setLevel(level)
    root.addHandler(out_handler)

    # stderr (warning and above)
    err_handler = _StderrHandler()
    err_handler.setFormatter(formatter)
    root.addHandler(err_handler)

    if log_file is not None:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        root.addHandler(file_handler)
