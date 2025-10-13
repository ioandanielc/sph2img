# src/sph2img/milestones/milestones_suite.py
#!/usr/bin/env python3

# --- path bootstrap: make `sph2img` importable even when run as a script -----
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]   # repo root (sph2img/)
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
# ---------------------------------------------------------------------------

from typing import Dict, Tuple, Optional

from sph2img.milestones.milestones_common import log, ordered_index_map, emit_ordered, DEFAULT_SIM
from sph2img.milestones.milestones_melt_largest_delta import build_iteration_mid_x, DEFAULT_EPS
from sph2img.milestones.milestones_melt_laser_positions import build_iteration_laser_x
from sph2img.milestones.milestones_solidified import build_solidified_map


def run_mid(sim_path: str = DEFAULT_SIM, epsilon: float = DEFAULT_EPS) -> Dict[int, float]:
    it2mid = build_iteration_mid_x(sim_path, epsilon=epsilon)
    emit_ordered("mid_x", ordered_index_map(it2mid))
    return it2mid


def run_laser(sim_path: str = DEFAULT_SIM) -> Dict[int, float]:
    it2x = build_iteration_laser_x(sim_path)
    emit_ordered("x_position", ordered_index_map(it2x))
    return it2x


def run_solid(
    sim_path: str = DEFAULT_SIM,
    x_start: Optional[float] = None,
    x_end: Optional[float] = None,
    epsilon: float = DEFAULT_EPS,
    linspace_cuts: Optional[int] = None,  # NEW: number of intervals; points = cuts + 1
) -> Dict[int, Tuple[int, float]]:
    idx2tuple = build_solidified_map(
        sim_path,
        x_start=x_start,
        x_end=x_end,
        epsilon=epsilon,
        linspace_cuts=linspace_cuts,
    )
    if idx2tuple:
        log.info("Ordered index -> (max_iteration, value):")
        for i in sorted(idx2tuple):
            it, val = idx2tuple[i]
            log.info("%d -> (%d, %.10g)", i, it, val)
    return idx2tuple


def run_all(
    sim_path: str = DEFAULT_SIM,
    epsilon: float = DEFAULT_EPS,
    x_start: Optional[float] = None,
    x_end: Optional[float] = None,
    linspace_cuts: Optional[int] = None,   # NEW
):
    return (
        run_mid(sim_path=sim_path, epsilon=epsilon),
        run_laser(sim_path=sim_path),
        run_solid(sim_path=sim_path, x_start=x_start, x_end=x_end,
                  epsilon=epsilon, linspace_cuts=linspace_cuts),
    )


# pretty summary …
def _section_header(title: str) -> str:
    bar = "─" * max(8, len(title) + 2)
    return f"{bar}\n {title}\n{bar}"


def _fmt_rows_indexed_timestep_value(idx2pair: Dict[int, Tuple[int, float]]) -> str:
    if not idx2pair:
        return "(no entries)"
    i_w = len(str(max(idx2pair))) if idx2pair else 1
    t_w = len(str(max(it for it, _ in idx2pair.values()))) if idx2pair else 1
    lines = [
        f"{'i':>{i_w}} | {'timestep':>{t_w}} | value",
        f"{'-'*i_w}-+-{'-'*t_w}-+-------",
    ]
    for i in sorted(idx2pair):
        it, val = idx2pair[i]
        lines.append(f"{i:>{i_w}} | {it:>{t_w}} | {val:.10g}")
    return "\n".join(lines)


def _fmt_rows_indexed_maxiter_value(idx2pair: Dict[int, Tuple[int, float]]) -> str:
    if not idx2pair:
        return "(no entries)"
    i_w = len(str(max(idx2pair)))
    t_w = len(str(max(it for it, _ in idx2pair.values())))
    lines = [
        f"{'i':>{i_w}} | {'max_iter':>{t_w}} | value",
        f"{'-'*i_w}-+-{'-'*t_w}-+-------",
    ]
    for i in sorted(idx2pair):
        it, val = idx2pair[i]
        lines.append(f"{i:>{i_w}} | {it:>{t_w}} | {val:.10g}")
    return "\n".join(lines)

def main():
    # CLI: python milestones_suite.py [SIM_PATH] [EPSILON] [X_START] [X_END] [CUTS]
    sim = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SIM
    EPS = float(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_EPS

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

    X_START = _opt_float(3)
    X_END   = _opt_float(4)
    CUTS    = int(sys.argv[5]) if len(sys.argv) > 5 else None

    mid, laser, solid = run_all(
        sim_path=sim,
        epsilon=EPS,
        x_start=X_START,
        x_end=X_END,
        linspace_cuts=CUTS,
    )

    mid_idx   = ordered_index_map(mid)
    laser_idx = ordered_index_map(laser)
    solid_idx = solid

    summary_lines = []
    summary_lines.append(_section_header("Milestones Summary — 3 Conventions"))
    summary_lines.append("")
    summary_lines.append("[A] Melt Largest ΔY → mid_x  (i → (timestep, mid_x))")
    summary_lines.append(_fmt_rows_indexed_timestep_value(mid_idx))
    summary_lines.append("")
    summary_lines.append("[B] Laser Positions → x_position  (i → (timestep, x_position))")
    summary_lines.append(_fmt_rows_indexed_timestep_value(laser_idx))
    summary_lines.append("")
    summary_lines.append("[C] Solidified Progress (linspace)  (i → (max_iter, value))")
    summary_lines.append(_fmt_rows_indexed_maxiter_value(solid_idx))

    for line in "\n".join(summary_lines).splitlines():
        log.info(line)

    # also print compact mappings for tooling
    print({i: (it, mid[it]) for i, it in enumerate(sorted(mid))})
    print({i: (it, laser[it]) for i, it in enumerate(sorted(laser))})
    print(solid_idx)

main()