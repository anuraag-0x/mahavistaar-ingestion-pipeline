"""
Application logging.

One format for everything the API and the worker emit, so a line in
logs/backend.log or logs/worker.log always answers three questions: when, from
where, and what failed. Uvicorn's own loggers are re-pointed at the same
handler so access lines and application lines interleave in one stream.
"""

import logging
import os
import sys
import uuid

LOG_FORMAT = "%(levelname)-8s %(name)s: %(message)s"


def setup_logging() -> None:
    """Install the shared handler. Safe to call more than once."""
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Uvicorn installs its own handlers; drop them so nothing prints twice.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        target = logging.getLogger(name)
        target.handlers = []
        target.propagate = True

    # These libraries are chatty at DEBUG and drown out our own lines.
    for name in ("httpx", "httpcore", "urllib3", "botocore"):
        logging.getLogger(name).setLevel(max(level, logging.WARNING))


def new_error_id() -> str:
    """Short id printed in the log and returned to the caller, so a user can
    quote it and we can find the exact traceback."""
    return uuid.uuid4().hex[:8]


def describe(exc: BaseException) -> str:
    """`ValueError: file is empty` — the type is what usually identifies the
    fault, and bare str(exc) drops it."""
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
