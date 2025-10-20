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


from typing import Dict

def build_iteration_laser_x_online(path_to_simulation: str,
                                   path_to_liquid_phase: str,  # unused (historical)
                                   iteration: int) -> float:
    """
    ONLINE variant: return the laser X position for a SINGLE `iteration`.

    Args kept for historical reasons: `path_to_liquid_phase`.
    Falls back to 0.0 if the iteration isn't present or parsing fails.
    """
    try:
        log.info("Parsing simulation at: %s (it=%d)", path_to_simulation, iteration)
        (
            _lp, _lv, _mat, _dens,
            _dt, _iters, _pos_bounds, _time,
            vtk_iterations,
            laser_positions_at_vtk_iterations,
            _domain, _smooth, _res,
            _dmin, _dmax,
        ) = master_parser.run(path_to_simulation)

        if not vtk_iterations or not laser_positions_at_vtk_iterations:
            log.warning("No vtk_iterations or laser positions found -> x=0.0")
            return 0.0

        # Map iteration -> x
        x_positions, _, _ = zip(*laser_positions_at_vtk_iterations)
        it2x: Dict[int, float] = dict(zip(vtk_iterations, x_positions))

        if iteration not in it2x:
            log.warning("Requested it=%d not in parsed iterations -> x=0.0", iteration)
            return 0.0

        return float(it2x[iteration])

    except Exception as e:
        log.warning("build_iteration_laser_x_online failed for it=%d: %s -> x=0.0", iteration, e)
        return 0.0

