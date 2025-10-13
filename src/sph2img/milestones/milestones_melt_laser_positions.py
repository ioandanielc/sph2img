# src/sph2img/milestones/milestones_melt_laser_positions.py
#!/usr/bin/env python3

# milestones_melt_laser_positions.py
import sys
from pathlib import Path

# --- path bootstrap: make `sph2img` importable even when run as a script -----
_ROOT = Path(__file__).resolve().parents[2]   # repo root (sph2img/)
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
# ---------------------------------------------------------------------------

from typing import Dict

from sph2img.milestones.milestones_common import log, ordered_index_map, emit_ordered, DEFAULT_SIM
from sph2img.parsers import master_parser


def build_iteration_laser_x(path_to_simulation: str) -> Dict[int, float]:
    log.info("Parsing simulation at: %s", path_to_simulation)
    (
        _lp, _lv, _mat, _dens,
        _dt, _iters, _pos_bounds, _time,
        vtk_iterations,
        laser_positions_at_vtk_iterations,
        _domain, _smooth, _res,
        _dmin, _dmax,
    ) = master_parser.run(path_to_simulation)

    if not vtk_iterations or not laser_positions_at_vtk_iterations:
        log.warning("No vtk_iterations or laser positions found.")
        return {}
    x_positions, _, _ = zip(*laser_positions_at_vtk_iterations)
    return dict(zip(vtk_iterations, x_positions))


if __name__ == "__main__":
    # CLI: python milestones_melt_laser_positions.py [SIM_PATH]
    sim = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SIM
    if not sim:
        log.error("No simulation path provided (DEFAULT_SIM missing)")
        sys.exit(2)

    it2x = build_iteration_laser_x(sim)
    emit_ordered("x_position", ordered_index_map(it2x))
    # compact stdout for tooling
    ordered_keys = sorted(it2x)
    print({i: (it, it2x[it]) for i, it in enumerate(ordered_keys)})
