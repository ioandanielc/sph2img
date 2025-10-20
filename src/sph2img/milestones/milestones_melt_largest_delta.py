# src/sph2img/milestones/milestones_melt_largest_delta.py
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

import os
from pathlib import Path
import numpy as np

# shared utils
from sph2img.milestones.milestones_common import log, ordered_index_map, emit_ordered, DEFAULT_SIM
from sph2img.utils.crawl_iterations import crawl_iterations

# heavy deps (runtime environment must provide ParaView + SciPy)
from paraview.simple import LegacyVTKReader  # type: ignore
from paraview import servermanager  # type: ignore
from paraview.vtk.util import numpy_support as ns  # type: ignore
from scipy.spatial import cKDTree  # type: ignore

DEFAULT_EPS = 1e-3


def build_iteration_largest_online(path_to_simulation: str,
                                 path_to_liquid_phase: str,
                                 iteration: int,
                                 epsilon: float = DEFAULT_EPS) -> float:
    """
    ONLINE variant for a single iteration.
    Args kept for historical reasons: `path_to_simulation`, `iteration` (redundant).
    `path_to_liquid_phase` is a DIRECT path to the LIQUID VTK file.
    Returns mid_x (float). On any failure / empty / no-pair -> 0.0.
    """
    try:
        reader = LegacyVTKReader(FileNames=[str(path_to_liquid_phase)])
        reader.UpdatePipeline()
        data = servermanager.Fetch(reader)

        pts = ns.vtk_to_numpy(data.GetPoints().GetData())
        if pts.size == 0:
            log.info("it=%d has no points, mid_x=0.0 (%s)", iteration, path_to_liquid_phase)
            return 0.0

        xz = pts[:, (0, 2)]
        tree = cKDTree(xz)

        max_dy, best_pair = -1.0, None
        for i in range(len(pts)):
            idxs = tree.query_ball_point(xz[i], r=epsilon)
            if len(idxs) <= 1:
                continue
            dy = np.abs(pts[i, 1] - pts[idxs, 1])
            j_rel = int(np.argmax(dy))
            if dy[j_rel] > max_dy:
                max_dy = float(dy[j_rel])
                best_pair = (i, idxs[j_rel])

        if best_pair is None:
            log.info("it=%d no pair within ε=%.3g, mid_x=0.0 (%s)", iteration, epsilon, path_to_liquid_phase)
            return 0.0

        p1x = float(pts[best_pair[0], 0])
        p2x = float(pts[best_pair[1], 0])
        return 0.5 * (p1x + p2x)

    except Exception as e:
        log.warning("it=%d (%s) failed: %s -> mid_x=0.0", iteration, path_to_liquid_phase, e)
        return 0.0


