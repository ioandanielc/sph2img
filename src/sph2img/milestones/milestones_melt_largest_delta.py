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


def _vtk_path(sim_path: str, iteration: int) -> Path:
    return Path(sim_path) / "output" / f"out_phase_2_LIQUID_rank_0_{iteration}.vtk"


def build_iteration_mid_x(path_to_simulation: str, epsilon: float = DEFAULT_EPS) -> dict[int, float]:
    """
    For each LIQUID VTK, compute mid_x for the pair with largest ΔY among neighbors
    that share (X,Z) within epsilon. If no points/pair, mid_x = 0.0.
    """
    _idx, iterations, _order2iter = crawl_iterations(path_to_simulation)
    it2mid: dict[int, float] = {}

    for it in iterations:
        f = _vtk_path(path_to_simulation, it)
        try:
            reader = LegacyVTKReader(FileNames=[str(f)]); reader.UpdatePipeline()
            data = servermanager.Fetch(reader)
            pts = ns.vtk_to_numpy(data.GetPoints().GetData())
            if pts.size == 0:
                it2mid[it] = 0.0
                log.info("it=%d has no points, setting mid_x=0.0 (%s)", it, f); continue

            xz = pts[:, (0, 2)]
            tree = cKDTree(xz)

            max_dy, best_pair = -1.0, None
            for i in range(len(pts)):
                idxs = tree.query_ball_point(xz[i], r=epsilon)
                if len(idxs) <= 1: continue
                dy = np.abs(pts[i, 1] - pts[idxs, 1])
                j_rel = int(np.argmax(dy))
                if dy[j_rel] > max_dy:
                    max_dy = float(dy[j_rel]); best_pair = (i, idxs[j_rel])

            if best_pair is None:
                it2mid[it] = 0.0
                log.info("it=%d no pair within ε=%.3g, setting mid_x=0.0 (%s)", it, epsilon, f); continue

            p1x = float(pts[best_pair[0], 0]); p2x = float(pts[best_pair[1], 0])
            it2mid[it] = 0.5 * (p1x + p2x)

        except Exception as e:
            it2mid[it] = 0.0
            log.warning("it=%d (%s) failed: %s -> mid_x=0.0", it, f, e)
    return it2mid


if __name__ == "__main__":
    # CLI: python milestones_melt_largest_delta.py [SIM_PATH] [EPSILON]
    sim = sys.argv[1] if len(sys.argv) > 1 else (os.environ.get("SIM_PATH") or DEFAULT_SIM)
    eps = float(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_EPS

    if not sim:
        log.error("No simulation path provided (SIM_PATH/DEFAULT_SIM missing)")
        sys.exit(2)

    it2mid = build_iteration_mid_x(sim, eps)
    emit_ordered("mid_x", ordered_index_map(it2mid))
    # compact stdout for quick tooling: {index: (iter, mid_x)}
    keys = sorted(it2mid)
    ordered = {i: (it, it2mid[it]) for i, it in enumerate(keys)}
    print(ordered)
