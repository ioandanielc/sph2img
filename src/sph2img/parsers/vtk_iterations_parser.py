# src/sph2img/parsers/vtk_iterations_parser.py
from __future__ import annotations

# --- path bootstrap: make `sph2img` importable even when run as a script -----
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]   # repo root (sph2img/)
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
# ---------------------------------------------------------------------------

import re
from typing import List

from sph2img.config import get_config
from sph2img.utils.pvlog import get_logger

logger = get_logger(__name__)

__all__ = ["get_vtk_iterations"]


_ITER_RE = re.compile(r"_0_([0-9]+)\.vtk$", re.IGNORECASE)
_PHASE_KEYS = ("SOLID", "LIQUID", "WALL", "GAS")


def _list_dir_files(dir_path: Path) -> List[Path]:
    return [p for p in dir_path.iterdir() if p.is_file()]


def get_vtk_iterations(path_to_simulation: str) -> List[int]:
    """Parse iteration indices from VTK snapshot filenames and verify integrity.

    Requirements:
      - ``<path_to_simulation>/output`` exists and contains only ``*.vtk`` files
      - Four phases (SOLID, LIQUID, WALL, GAS) have identical cardinality
      - All phases are snapshotted at the exact same iteration indices

    Returns:
      Sorted list of iteration integers common to all phases.
    """
    sim_dir = Path(path_to_simulation).expanduser().resolve()
    logger.info(".vtk Files Parser running (scan: %s)", sim_dir)

    out_dir = sim_dir / "output"
    if not out_dir.exists() or not out_dir.is_dir():
        logger.error("Missing 'output' directory under %s", sim_dir)
        raise FileNotFoundError(f"Missing 'output' directory under {sim_dir}")

    files = _list_dir_files(out_dir)
    if not files:
        logger.error("No files found in %s", out_dir)
        raise FileNotFoundError(f"No files found in {out_dir}")

    non_vtk = [p.name for p in files if p.suffix.lower() != ".vtk"]
    if non_vtk:
        logger.error("Not only .vtk inside 'output' folder. Offenders: %s", ", ".join(non_vtk))
        raise RuntimeError("Not only .vtk inside 'output' folder.")

    # Group by phase via substring match
    grouped = {k: [p for p in files if k in p.name] for k in _PHASE_KEYS}

    # Cardinality equality check
    counts = {k: len(v) for k, v in grouped.items()}
    if len(set(counts.values())) != 1:
        logger.error("Phases cardinality should be the same: %s", counts)
        raise RuntimeError("Phases cardinality should be the same")

    # Extract iteration numbers for each phase, verifying regex presence
    iters_by_phase: dict[str, List[int]] = {}
    for k, plist in grouped.items():
        phase_iters: List[int] = []
        for p in plist:
            m = _ITER_RE.search(p.name)
            if not m:
                logger.error("Filename missing iteration token '_0_<N>.vtk': %s", p.name)
                raise ValueError(f"Filename missing iteration token '_0_<N>.vtk': {p.name}")
            phase_iters.append(int(m.group(1)))
        iters_by_phase[k] = sorted(phase_iters)

    # All phases must align exactly
    sequences = list(iters_by_phase.values())
    first = sequences[0]
    if any(seq != first for seq in sequences[1:]):
        logger.error("Phases should be snapshotted at the same iterations: %s", {k: v[:5] for k, v in iters_by_phase.items()})
        raise RuntimeError("Phases should be snapshotted at the same iterations")

    logger.info("Collected iteration numbers (%d): %s", len(first), first)
    return first


if __name__ == "__main__":
    # No basicConfig here to avoid duplicate logs — pvlog provides handlers.
    # Optional CLI override: `python vtk_iterations_parser.py /path/to/sim`
    if len(sys.argv) > 1:
        sim_path = sys.argv[1]
    else:
        cfg = get_config()
        sim_path = str(cfg.paths.sim_path)

    logger.info("[TEST] Using simulation path: %s", sim_path)
    try:
        iters = get_vtk_iterations(sim_path)
        print(f"OK — {len(iters)} iterations parsed. First 10: {iters[:10]}")
    except Exception as e:
        logger.exception("[TEST] Failed: %s", e)
        raise
