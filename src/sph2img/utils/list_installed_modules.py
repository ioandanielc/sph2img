# src/sph2img/utils/env_probe.py
from __future__ import annotations

# --- path bootstrap: make `sph2img` importable even when run as a script -----
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]   # repo root (sph2img/)
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
# ---------------------------------------------------------------------------

import importlib
from typing import Iterable, List, Tuple

from sph2img.utils.pvlog import get_logger

logger = get_logger(__name__)

CANDIDATES: List[str] = [
    "paraview", "paraview.simple", "vtk",
    "numpy", "scipy", "PIL", "matplotlib",
    "pandas", "imageio",
]


def mod_version(name: str) -> str:
    """Return a human-readable version string for a module.

    If the module is missing, returns a compact marker with the exception name.
    """
    try:
        m = importlib.import_module(name)
        v = getattr(m, "__version__", None)
        if v is None and hasattr(m, "version"):
            v = getattr(m, "version")
        return str(v) if v is not None else "(no __version__)"
    except Exception as e:  # ImportError, etc.
        return f"(missing: {e.__class__.__name__})"


def _probe(names: Iterable[str]) -> List[Tuple[str, str]]:
    return [(n, mod_version(n)) for n in names]


def main() -> int:
    rows = _probe(CANDIDATES)

    # Pretty, aligned log output
    width = max((len(n) for n, _ in rows), default=8)
    logger.info("=== Installed modules ===")
    for n, v in rows:
        logger.info(f"{n:<{width}} : {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
