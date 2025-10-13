from __future__ import annotations
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys
import os
import re

from sph2img.config import get_config

_cfg = None  # cached config

# ---------- formatting ----------
_FMT = "%(asctime)s [%(levelname)s] pid=%(process)d %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

# ANSI support + colorizer (same trick as the snippet you showed)
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
            # strip any ANSI that might have slipped in
            return _ESC_RE.sub("", msg)
        color = self.COLORS.get(record.levelname, "")
        return f"{color}{msg}{self.RESET}" if color else msg

# ---------- internals ----------

def _ensure_cfg():
    global _cfg
    if _cfg is None:
        _cfg = get_config()
    return _cfg

def _safe_file_handler(path: Path) -> logging.Handler | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        h = RotatingFileHandler(str(path), maxBytes=5_000_000, backupCount=2, encoding="utf-8")
        # file logs are NOT colored
        h.setFormatter(logging.Formatter(fmt=_FMT, datefmt=_DATEFMT))
        return h
    except Exception:
        return None

# ---------- public ----------

def get_logger(name: str, run_name: str | None = None) -> logging.Logger:
    """
    Return a module logger that logs to stderr (colored) and to logs/<run>_<pid>.log (plain).

    - `run_name` (optional) names the file; defaults to 'sph2img'.
    - Log level defaults to INFO.
    - Messages include PID on both console and file.
    - Console colors: INFO=green, WARNING=yellow, ERROR/CRITICAL=red (CRITICAL has red bg), DEBUG=cyan.
    """
    cfg = _ensure_cfg()
    logger = logging.getLogger(name)
    if getattr(logger, "_sph2img_configured", False):
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False  # avoid duplicate emission via root

    # Console (colorized)
    use_color = _supports_color(sys.stderr)
    ch = logging.StreamHandler(stream=sys.stderr)
    ch.setFormatter(_ColorFormatter(fmt=_FMT, datefmt=_DATEFMT, enable_colors=use_color))
    logger.addHandler(ch)

    # File (PID in filename)
    pid = os.getpid()
    base = run_name or "sph2img"
    fname = f"{base}_{pid}.log"
    fh = _safe_file_handler(cfg.paths.logs_dir / fname)
    if fh:
        logger.addHandler(fh)

    logger._sph2img_configured = True  # type: ignore[attr-defined]
    return logger
