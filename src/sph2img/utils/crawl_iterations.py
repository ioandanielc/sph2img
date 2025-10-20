# src/sph2img/utils/iterations_utils.py

# --- path bootstrap: make `sph2img` importable even when run as a script -----
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]  # repo root (sph2img/)
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
# ---------------------------------------------------------------------------

import os
import re
from typing import List, Tuple, Dict

from sph2img.utils.pvlog import get_logger
from sph2img.config import get_config

log = get_logger(__name__)

# --- constants ---
_ITER_RE = re.compile(r"^out_phase_2_LIQUID_rank_0_(\d+)\.vtk$")

# Prefer milestones_common.DEFAULT_SIM when available, else config fallback
try:
    from sph2img.parsers.milestones_extractor.milestones_common import DEFAULT_SIM as _DEFAULT_SIM  # type: ignore
    DEFAULT_SIM = _DEFAULT_SIM
except Exception:
    try:
        from milestones_common import DEFAULT_SIM as _DEFAULT_SIM  # type: ignore
        DEFAULT_SIM = _DEFAULT_SIM
    except Exception:
        try:
            DEFAULT_SIM = str(get_config().paths.sim_path)
        except Exception:
            DEFAULT_SIM = ""


def crawl_iterations(
    path_to_simulation: str,
    output_subdir: str = "output",
) -> Tuple[List[int], List[int], Dict[int, int], List[Path], Dict[int, Path]]:
    """
    Scan <path_to_simulation>/<output_subdir> for VTKs named:
        out_phase_2_LIQUID_rank_0_<ITER>.vtk

    Returns:
      - indices:        [0, 1, ..., card-1]
      - iterations:     [it0, it1, ...]                   (ascending)
      - order_to_iter:  {0: it0, 1: it1, ...}
      - paths:          [Path(it0), Path(it1), ...]       (same order as iterations)
      - iter_to_path:   {it0: Path(it0), it1: Path(it1), ...}
    """
    out_dir = Path(path_to_simulation) / output_subdir
    if not out_dir.is_dir():
        raise NotADirectoryError(f"Missing output dir: {out_dir}")

    log.info("Crawling VTK iterations in: %s", out_dir)

    pairs: List[tuple[int, Path]] = []
    for f in out_dir.glob("out_phase_2_LIQUID_rank_0_*.vtk"):
        m = _ITER_RE.match(f.name)
        if m:
            it = int(m.group(1))
            pairs.append((it, f))

    pairs.sort(key=lambda x: x[0])
    iters: List[int] = [it for it, _ in pairs]
    paths: List[Path] = [p for _, p in pairs]

    indices = list(range(len(iters)))
    order_to_iter: Dict[int, int] = {i: it for i, it in enumerate(iters)}
    iter_to_path: Dict[int, Path] = {it: p for it, p in pairs}

    if iters:
        log.info("Found %d iterations. Range: %d -> %d", len(iters), iters[0], iters[-1])
        log.debug("order_to_iter = %s", order_to_iter)
    else:
        log.warning("No matching VTK files found in %s", out_dir)

    return indices, iters, order_to_iter, paths, iter_to_path


def main() -> int:
    # Args: SIM_PATH [SUBDIR]; fallbacks: env SIM_PATH, DEFAULT_SIM; SUBDIR→"output"
    sim = (
        sys.argv[1]
        if len(sys.argv) > 1
        else (os.environ.get("SIM_PATH") or DEFAULT_SIM)
    )
    sub = sys.argv[2] if len(sys.argv) > 2 else "output"

    if not sim:
        log.error("No simulation path provided (arg/SIM_PATH/DEFAULT_SIM all missing).")
        print("USAGE: python iterations_utils.py <SIM_PATH> [SUBDIR]", file=sys.stderr)
        return 2

    try:
        idx, its, o2i, paths, i2p = crawl_iterations(sim, sub)
        # Compact stdout for tooling/grepping; logging already has richer info.
        print("indices:", idx[:10], f"(total {len(idx)})")
        print("iterations:", its[:10], f"(total {len(its)})")
        # Show first few paths for quick sanity check
        print("paths:", [str(p) for p in paths[:3]], ("..." if len(paths) > 3 else ""))
        return 0
    except Exception as e:
        log.exception("crawl failed: %s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
