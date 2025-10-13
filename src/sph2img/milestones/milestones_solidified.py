# src/sph2img/milestones/milestones_solidified.py
#!/usr/bin/env python3
from __future__ import annotations

# --- path bootstrap: make `sph2img` importable even when run as a script -----
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]   # repo root (sph2img/)
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
# ---------------------------------------------------------------------------

import numpy as np
from typing import Dict

from sph2img.milestones.milestones_common import log, DEFAULT_SIM
from sph2img.utils.crawl_iterations import crawl_iterations
from sph2img.milestones.milestones_melt_largest_delta import (
    build_iteration_mid_x,
    DEFAULT_EPS,
)


def build_solidified_map(
    path_to_simulation: str,
    x_start: float | None = None,
    x_end: float | None = None,
    epsilon: float = DEFAULT_EPS,
    linspace_cuts: int | None = None,
) -> dict[int, tuple[int, float]]:
    """
    Return {0..M -> (max_iteration:int, value:float)} where value is a linspace
    from 0 to (x_end - x_start) inclusive.

    Args:
        path_to_simulation: simulation root (expects `output/` with VTKs)
        x_start, x_end: span endpoints; default to first/last *non-zero* mid_x
        epsilon: tolerance passed to mid_x computation
        linspace_cuts: number of *intervals* in the linspace.
            - If None (default), cuts = (#VTK files - 1), preserving previous behavior.
            - Number of output points = cuts + 1, indexed 0..cuts.

    Notes:
        - max_iteration is always the largest VTK iteration discovered.
        - If no valid mid_x is found, the span defaults to 0 (all zeros).
    """
    _, iterations, _ = crawl_iterations(path_to_simulation)
    if not iterations:
        return {}

    max_iteration = max(iterations)

    # Determine x_start / x_end from widest-mid_x if not provided
    it2mid = build_iteration_mid_x(path_to_simulation, epsilon=epsilon)
    mids_ordered = [it2mid.get(it, 0.0) for it in iterations]
    first_nonzero = next((v for v in mids_ordered if v not in (None, 0.0)), None)
    last_nonzero  = next((v for v in reversed(mids_ordered) if v not in (None, 0.0)), None)

    if x_start is None:
        x_start = float(first_nonzero) if first_nonzero is not None else 0.0
    if x_end is None:
        x_end = float(last_nonzero) if last_nonzero is not None else x_start

    delta = max(0.0, float(x_end) - float(x_start))

    # Decide cardinality: cuts + 1 points
    if linspace_cuts is None:
        cuts = max(0, len(iterations) - 1)  # previous behavior
    else:
        cuts = int(linspace_cuts)
        if cuts < 0:
            cuts = 0

    points = cuts + 1
    vals = np.linspace(0.0, delta, points) if points > 0 else np.array([0.0], dtype=float)

    return {i: (max_iteration, float(vals[i])) for i in range(points)}


if __name__ == "__main__":
    # CLI: python milestones_solidified.py [SIM_PATH] [X_START] [X_END] [EPSILON] [CUTS]
    # Use "none" (case-insensitive) for optional X_START/X_END to keep auto-detection.
    sim = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SIM
    if not sim:
        log.error("No simulation path provided (DEFAULT_SIM missing)")
        sys.exit(2)

    def _opt_float(idx: int):
        if len(sys.argv) <= idx:
            return None
        val = sys.argv[idx].strip()
        if val.lower() in ("", "none", "null"):
            return None
        try:
            return float(val)
        except Exception:
            log.warning("Argument %d ('%s') not a float; treating as None", idx, val)
            return None

    X_START = _opt_float(2)
    X_END   = _opt_float(3)
    EPS     = float(sys.argv[4]) if len(sys.argv) > 4 else DEFAULT_EPS
    CUTS    = int(sys.argv[5]) if len(sys.argv) > 5 else None

    idx2tuple = build_solidified_map(
        sim,
        x_start=X_START,
        x_end=X_END,
        epsilon=EPS,
        linspace_cuts=CUTS,
    )

    # Log a human-friendly listing
    if idx2tuple:
        log.info("Ordered index -> (max_iteration, value):")
        for i in sorted(idx2tuple):
            it, val = idx2tuple[i]
            log.info("%d -> (%d, %.10g)", i, it, val)
    else:
        log.warning("No data produced.")

    # Compact stdout mapping for tooling
    print(idx2tuple)
