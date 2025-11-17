from __future__ import annotations

import logging
import os
import sys
from typing import Optional

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
COLORS = {
    "DEBUG": "\x1b[38;5;244m",
    "INFO": "\x1b[38;5;39m",
    "WARNING": "\x1b[38;5;214m",
    "ERROR": "\x1b[38;5;196m",
    "CRITICAL": "\x1b[48;5;196m\x1b[97m",
}


class _ColorFormatter(logging.Formatter):
    def __init__(self, fmt: str, datefmt: Optional[str], use_color: bool) -> None:
        super().__init__(fmt, datefmt=datefmt)
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        if self.use_color:
            lvl = record.levelname
            color = COLORS.get(lvl, "")
            record.levelname = f"{BOLD}{color}{lvl}{RESET}"
        try:
            return super().format(record)
        finally:
            if self.use_color:
                # remove the styling we injected
                record.levelname = record.levelname.replace(BOLD, "").replace(RESET, "")
                for c in COLORS.values():
                    record.levelname = record.levelname.replace(c, "")


def _want_color(force: Optional[bool]) -> bool:
    if force is not None:
        return force
    if not sys.stdout.isatty():
        return False
    if os.environ.get("NO_COLOR"):
        return False
    return os.environ.get("CLICOLOR", "1") != "0"


def get_logger(
        name: Optional[str] = None,
        level: int | str = "INFO",
        *,
        to_file: Optional[str] = None,
        color: Optional[bool] = None,
) -> logging.Logger:
    """
    Pretty, colored logger that includes PID and full date.

    Parameters
    ----------
    name:
        Logger name. Defaults to "app".
    level:
        Logging level, e.g. "DEBUG", "INFO".
    to_file:
        Path to the log file. If None, defaults to "run.log".
        Pass an empty string ("") explicitly if you do *not* want a file handler.
    color:
        Force enabling/disabling color. If None, auto-detect TTY support.
    """
    logger_name = name or "app"
    logger = logging.getLogger(logger_name)

    # Default logfile if not given
    if to_file is None:
        to_file = "run.log"

    if not getattr(logger, "_pretty_configured", False):
        logger.setLevel(logging.DEBUG)

        ch = logging.StreamHandler(stream=sys.stdout)
        ch_level = logging._nameToLevel[str(level).upper()] if isinstance(level, str) else level
        ch.setLevel(ch_level)

        # Include *date and time*: YYYY-MM-DD HH:MM:SS
        fmt = "%(asctime)s │ pid=%(process)d │ %(levelname)s │ %(name)s:%(lineno)d │ %(message)s"
        datefmt = "%Y-%m-%d %H:%M:%S"

        use_color = _want_color(color)
        ch.setFormatter(_ColorFormatter(fmt, datefmt, use_color))
        logger.addHandler(ch)

        # File handler (no colors) – only if to_file != ""
        if to_file:
            fh = logging.FileHandler(to_file, encoding="utf-8")
            fh.setLevel(ch_level)
            fh.setFormatter(logging.Formatter(fmt, datefmt=datefmt))
            logger.addHandler(fh)

        logger.propagate = False
        logger._pretty_configured = True  # type: ignore[attr-defined]
    else:
        # If logger already configured, just update handler levels
        lvl = logging._nameToLevel[str(level).upper()] if isinstance(level, str) else level
        for h in logger.handlers:
            h.setLevel(lvl)

    return logger
