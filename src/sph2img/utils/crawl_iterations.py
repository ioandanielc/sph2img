# src/sph2img/utils/iterations_utils.py

# --- path bootstrap: make `sph2img` importable even when run as a script -----
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]  # repo root (sph2img/)
_SRC = _ROOT / "src"
print(_ROOT)
print(_SRC)
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
# ---------------------------------------------------------------------------

import os
import re
from pathlib import Path
from typing import List, Tuple, Dict

from sph2img.utils.pvlog import get_logger
from sph2img.config import get_config
from sph2img.utils.pvhelpers import run_main_if_testing

log = get_logger(__name__)

# --- constants ---
_ITER_RE = re.compile(r"^out_phase_2_LIQUID_rank_0_(\d+)\.vtk$")

# Prefer milestones_common.DEFAULT_SIM when available, else config fallback
try:
    # Try fully-qualified path first (common project layout)
    from sph2img.parsers.milestones_extractor.milestones_common import DEFAULT_SIM as _DEFAULT_SIM  # type: ignore

    DEFAULT_SIM = _DEFAULT_SIM
except Exception:
    try:
        # Fallback to plain import if PYTHONPATH already set elsewhere
        from milestones_common import DEFAULT_SIM as _DEFAULT_SIM  # type: ignore

        DEFAULT_SIM = _DEFAULT_SIM
    except Exception:
        # Final fallback: config
        try:
            DEFAULT_SIM = str(get_config().paths.sim_path)
        except Exception:
            DEFAULT_SIM = ""


def crawl_iterations(
        path_to_simulation: str,
        output_subdir: str = "output",
) -> Tuple[List[int], List[int], Dict[int, int]]:
    """
    Scan <path_to_simulation>/<output_subdir> for VTKs named:
        out_phase_2_LIQUID_rank_0_<ITER>.vtk

    Returns:
      - indices:      [0, 1, ..., card-1]
      - iterations:   [it0, it1, ...]     (ascending)
      - order_to_iter:{0: it0, 1: it1, ...}
    """
    out_dir = Path(path_to_simulation) / output_subdir
    if not out_dir.is_dir():
        raise NotADirectoryError(f"Missing output dir: {out_dir}")

    log.info("Crawling VTK iterations in: %s", out_dir)

    iters: List[int] = []
    for f in out_dir.glob("out_phase_2_LIQUID_rank_0_*.vtk"):
        m = _ITER_RE.match(f.name)
        if m:
            iters.append(int(m.group(1)))

    iters.sort()
    indices = list(range(len(iters)))
    order_to_iter = {i: it for i, it in enumerate(iters)}

    if iters:
        log.info("Found %d iterations. Range: %d -> %d", len(iters), iters[0], iters[-1])
        log.debug("order_to_iter = %s", order_to_iter)
    else:
        log.warning("No matching VTK files found in %s", out_dir)

    return indices, iters, order_to_iter


def main():
    if len(sys.argv) > 1:
        sim = sys.argv[1]
    else:
        sim = os.environ.get("SIM_PATH") or DEFAULT_SIM

    sub = sys.argv[2] if len(sys.argv) > 2 else "output"

    if not sim:
        log.error("No simulation path provided (SIM_PATH/DEFAULT_SIM missing)")
        sys.exit(2)
    try:
        idx, its, o2i = crawl_iterations(sim, sub)
        log.info("indices=%s", idx[:10])
        log.info("iterations(first 10)=%s", its[:10])
        print(idx, its)  # compact stdout for quick tooling
    except Exception as e:
        log.exception("crawl failed: %s", e)
        raise

# run_main_if_testing(main)
