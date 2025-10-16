from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import os
import re

from sph2img.config import get_config

# ---------- formatting ----------
_FMT = "%(asctime)s [%(levelname)s] pid=%(process)d %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

# ANSI support + colorizer
_ESC_RE = re.compile(r"\x1b\[[0-9;]*m")

def _supports_color(stream) -> bool:
    try:
        return hasattr(stream, "isatty") and stream.isatty() and os.environ.get("TERM") not in (None, "dumb")
    except Exception:
        return False

class _ColorFormatter(logging.Formatter):
    COLORS = {
        "DEBUG":    "\x1b[36m",  # cyan
        "INFO":     "\x1b[32m",  # green
        "WARNING":  "\x1b[33m",  # yellow
        "ERROR":    "\x1b[31m",  # red
        "CRITICAL": "\x1b[41m",  # red bg
    }
    RESET = "\x1b[0m"

    def __init__(self, fmt: str, datefmt: str | None, enable_colors: bool):
        super().__init__(fmt=fmt, datefmt=datefmt)
        self.enable_colors = enable_colors

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        if not self.enable_colors:
            return _ESC_RE.sub("", msg)
        color = self.COLORS.get(record.levelname, "")
        return f"{color}{msg}{self.RESET}" if color else msg

# ---------- internals ----------

_cfg = None  # cached config

def _ensure_cfg():
    global _cfg
    if _cfg is None:
        _cfg = get_config()
    return _cfg

def _safe_file_handler(path: Path) -> logging.Handler | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        h = RotatingFileHandler(str(path), maxBytes=5_000_000, backupCount=2, encoding="utf-8")
        h.setFormatter(logging.Formatter(fmt=_FMT, datefmt=_DATEFMT))  # file logs are plain (no ANSI)
        return h
    except Exception:
        return None

class _LevelFilter(logging.Filter):
    """Pass records whose level is between [min_level, max_level] inclusive."""
    def __init__(self, min_level: int, max_level: int):
        super().__init__()
        self.min_level = min_level
        self.max_level = max_level
    def filter(self, record: logging.LogRecord) -> bool:
        return self.min_level <= record.levelno <= self.max_level

# ---------- public ----------

def get_logger(name: str, run_name: str | None = None) -> logging.Logger:
    """
    Return a module logger that logs to:
      - stdout (DEBUG/INFO, colored if terminal supports it)
      - stderr (WARNING/ERROR/CRITICAL, colored)
      - rotating file logs/<run_name>_<pid>.log (plain)

    Default level: INFO.
    """
    cfg = _ensure_cfg()
    logger = logging.getLogger(name)

    if getattr(logger, "_sph2img_configured", False):
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False  # avoid duplicate emission via root

    # Console handlers
    use_color_out = _supports_color(sys.stdout)
    use_color_err = _supports_color(sys.stderr)

    # stdout: DEBUG..INFO
    ch_out = logging.StreamHandler(stream=sys.stdout)
    ch_out.addFilter(_LevelFilter(logging.DEBUG, logging.INFO))
    ch_out.setFormatter(_ColorFormatter(fmt=_FMT, datefmt=_DATEFMT, enable_colors=use_color_out))
    logger.addHandler(ch_out)

    # stderr: WARNING..CRITICAL
    ch_err = logging.StreamHandler(stream=sys.stderr)
    ch_err.addFilter(_LevelFilter(logging.WARNING, logging.CRITICAL))
    ch_err.setFormatter(_ColorFormatter(fmt=_FMT, datefmt=_DATEFMT, enable_colors=use_color_err))
    logger.addHandler(ch_err)

    # File handler (PID in filename)
    pid = os.getpid()
    base = run_name or "sph2img"
    fname = f"{base}_{pid}.log"
    fh = _safe_file_handler(Path(cfg.paths.logs_dir) / fname)
    if fh:
        logger.addHandler(fh)

    logger._sph2img_configured = True  # type: ignore[attr-defined]
    return logger
