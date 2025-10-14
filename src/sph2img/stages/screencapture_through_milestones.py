#screencapture_through_milestones.py
#!/usr/bin/env python3

# --- path bootstrap: make `sph2img` importable even when run as a script -----
import sys, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]   # repo root (sph2img/)
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
# ---------------------------------------------------------------------------

from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

from sph2img.utils.pvlog import get_logger
from sph2img.utils.pvhelpers import run_main_if_testing
from sph2img.config import get_config

# milestones
from sph2img.milestones.milestones_common import ordered_index_map
from sph2img.milestones.milestones_melt_laser_positions import build_iteration_laser_x
from sph2img.milestones.milestones_melt_largest_delta import build_iteration_mid_x, DEFAULT_EPS
from sph2img.milestones.milestones_solidified import build_solidified_map

# slice + screenshots
from sph2img.stages.slice_mover import move_slices_origin
from sph2img.stages.screencapture_slice_composite import screenshot_set

# dynamic slab: getters published by sph_creator.prepare_sph_interpolator()
from sph2img.stages.sph_creator import get_sph, get_upstream, get_domain_bounds

# PV time
from paraview.simple import GetAnimationScene  # type: ignore

log = get_logger(__name__)


def create_timestamped_folder(base_dir: str = ".") -> Path:
    """
    Create screenshots_YYYY-MM-DD_HH-MM-SS-MMM under base_dir.
    Uses the system's local time (no zoneinfo dependency).
    """
    now = datetime.fromtimestamp(time.time())  # local time
    millis = f"{int((now.microsecond) / 1000):03d}"
    folder_name = f"screenshots_{now.strftime('%Y-%m-%d_%H-%M-%S')}-{millis}"
    path = Path(base_dir) / folder_name
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass(frozen=True)
class Milestone:
    idx: int
    iteration: int          # for 'solid': this is the max iteration
    x: Optional[float]      # x to place slices; in 'solid' this is the linspace value


def _set_time_by_index(idx: int) -> None:
    scene = GetAnimationScene()
    steps = list(scene.TimeKeeper.TimestepValues)
    if not steps:
        raise RuntimeError("No time steps available in the current pipeline.")
    if not (0 <= idx < len(steps)):
        raise IndexError(f"Timestep index {idx} out of range 0..{len(steps)-1}")
    scene.AnimationTime = float(steps[idx])


def _last_time_index() -> int:
    scene = GetAnimationScene()
    steps = list(scene.TimeKeeper.TimestepValues)
    if not steps:
        raise RuntimeError("No time steps available in the current pipeline.")
    return len(steps) - 1


# ----------------------------
# Dynamic slab helpers
# ----------------------------

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))

def _set_sph_slab_from_pc_height(
    sph,
    upstream,
    center_x: float,
    domain_min: List[float],
    domain_max: List[float],
    slab_half_x_frac: float,
    pad_mult_x: float,
    pad_mult_yz: float,   # kept for signature compatibility (unused)
    center_y: float = 0.0,
    center_z: float = 0.0,
) -> None:
    """
    Compute point-cloud height H_pc from the upstream proxy's current timestep.
    Slab sizing:
      - X: half-width = slab_half_x_frac * H_pc; then pad by pad_mult_x * H_pc on both sides
      - Y: center_y ± 1.1 * (slab half-width in X)
      - Z: center_z ± 1.1 * (slab half-width in X)
    """
    # Try live upstream bounds for current timestep
    try:
        xmin, xmax, ymin, ymax, zmin, zmax = map(float, upstream.GetDataInformation().GetBounds())
        H_pc = max(0.0, zmax - zmin)
        if not (H_pc > 0.0):
            raise ValueError("Non-positive H_pc from upstream bounds")
    except Exception:
        # Fallback to full domain height if upstream isn't ready yet
        zmin, zmax = float(domain_min[2]), float(domain_max[2])
        H_pc = max(0.0, zmax - zmin)

    # Slab parameters
    half_x = float(slab_half_x_frac) * H_pc
    pad_x  = float(pad_mult_x) * H_pc
    band_yz = 1.1 * half_x  # <-- requested: use 1.1 * slab half-width for Y and Z

    minx, miny, minz = map(float, domain_min)
    maxx, maxy, maxz = map(float, domain_max)

    # X: narrow + padding (clamped)
    x_lo = _clamp(center_x - half_x - pad_x, minx, maxx)
    x_hi = _clamp(center_x + half_x + pad_x, minx, maxx)

    # Y/Z: ±(1.1 * half_x) around center, clamped to domain
    y_lo = _clamp(center_y - band_yz, miny, maxy)
    y_hi = _clamp(center_y + band_yz, miny, maxy)
    z_lo = _clamp(center_z - band_yz, minz, maxz)
    z_hi = _clamp(center_z + band_yz, minz, maxz)

    sph.Source.Origin = [x_lo, y_lo, z_lo]
    sph.Source.Scale  = [max(1e-30, x_hi - x_lo),
                         max(1e-30, y_hi - y_lo),
                         max(1e-30, z_hi - z_lo)]
    sph.UpdatePipeline()


# ----------------------------
# Milestones
# ----------------------------

def gather_milestones(
    mode: str,
    sim_path: str,
    epsilon: float = DEFAULT_EPS,
    x_start: Optional[float] = None,
    x_end: Optional[float] = None,
    linspace_cuts: Optional[int] = None,
) -> List[Milestone]:
    m = mode.lower()
    if m == "laser":
        it2x = build_iteration_laser_x(sim_path)
        idx2 = ordered_index_map(it2x)
        return [Milestone(i, it, float(x)) for i, (it, x) in sorted(idx2.items())]

    if m == "largest":
        it2mid = build_iteration_mid_x(sim_path, epsilon=epsilon)
        idx2 = ordered_index_map(it2mid)
        return [Milestone(i, it, float(x)) for i, (it, x) in sorted(idx2.items())]

    if m == "solid":
        idx2 = build_solidified_map(
            sim_path, x_start=x_start, x_end=x_end,
            epsilon=epsilon, linspace_cuts=linspace_cuts,
        )  # {i -> (max_iter, value)}
        return [Milestone(i, it, float(val)) for i, (it, val) in sorted(idx2.items())]

    raise ValueError("mode must be one of: 'laser', 'largest', 'solid'")


# ----------------------------
# Entry point
# ----------------------------

def run_milestone_capture(
    sim_path: str,
    mode: str = "laser",
    epsilon: float = DEFAULT_EPS,
    x_start: Optional[float] = None,
    x_end: Optional[float] = None,
    linspace_cuts: Optional[int] = None,
    run_name: str = "run_x",
    out_dir: str = ".",
    front_W: int = 256, front_H: int = 256,
    side_W: int = 256,  side_H: int = 256,
    top_W: int = 256,   top_H: int = 256,
    x_side_offset: float = 0.0,
    testing_folder: bool = True,
) -> str:
    log.info("Milestone capture | mode=%s | sim=%s", mode, sim_path)

    out_dir_path = create_timestamped_folder(out_dir)

    milestones = gather_milestones(
        mode=mode, sim_path=sim_path, epsilon=epsilon,
        x_start=x_start, x_end=x_end, linspace_cuts=linspace_cuts,
    )
    if not milestones:
        log.warning("No milestones produced for mode=%s", mode)
        return ''

    # dynamic slab params (config-driven, with safe defaults matching your rule)
    cap_cfg = get_config().capture
    slab_half_x_frac = getattr(cap_cfg, "slab_half_x_frac", 0.08)  # 8% of H_pc
    pad_mult_x       = getattr(cap_cfg, "pad_mult_x", 1.0)        # X pad = 1.0 * H_pc
    pad_mult_yz      = getattr(cap_cfg, "pad_mult_yz", 0.5)       # Y/Z pad = 0.5 * H_pc

    # SPH + upstream + domain bounds must have been prepared by sph_creator.prepare_sph_interpolator()
    sph = get_sph()
    upstream = get_upstream()
    dmin, dmax = get_domain_bounds()
    if sph is None or upstream is None or dmin is None or dmax is None:
        raise RuntimeError("SPH pipeline not initialized. Call prepare_sph_interpolator() before run_milestone_capture().")

    solid_mode = (mode.lower() == "solid")
    last_idx = _last_time_index() if solid_mode else None

    for i, ms in enumerate(milestones):
        # 1) timestep
        if solid_mode:
            _set_time_by_index(last_idx)  # always final frame
        else:
            _set_time_by_index(ms.idx)

        # 2) set SPH bounded-volume slab based on current point-cloud height
        if ms.x is not None:
            _set_sph_slab_from_pc_height(
                sph=sph,
                upstream=upstream,
                center_x=ms.x,
                domain_min=dmin,
                domain_max=dmax,
                slab_half_x_frac=slab_half_x_frac,
                pad_mult_x=pad_mult_x,
                pad_mult_yz=pad_mult_yz,
                center_y=0.0,
                center_z=0.0,
            )
            # place slices at x (laser / largest / solid linspace)
            move_slices_origin([ms.x, 0.0, 0.0])

        # 3) save screenshots; clear folder only once if testing_folder=True
        screenshot_set(
            run_name=run_name,
            entry_no=ms.idx,  # keep filenames tied to the milestone index
            out_dir=str(out_dir_path),
            front_W=front_W, front_H=front_H,
            side_W=side_W,   side_H=side_H,
            top_W=top_W,     top_H=top_H,
            x_side_offset=x_side_offset,
            testing_folder=(testing_folder and i == 0),
        )

    log.info("Milestone capture finished. %d milestones processed.", len(milestones))
    return str(out_dir_path)


# ----------------------------
# ParaView shell-friendly `main()` (no CLI args)
# ----------------------------

def main() -> None:
    """
    Uses config.json for defaults:
      - paths.sim_path / paths.out_dir
      - capture.mode, capture.eps, capture.x_start/x_end, capture.solid_cuts
      - capture.front/side/top sizes, capture.x_side_offset, capture.empty_out
      - (optional) capture.slab_half_x_frac, capture.pad_mult_x, capture.pad_mult_yz
    """
    cfg = get_config()
    cap = cfg.capture

    out_dir = str(cfg.paths.out_dir)
    sim_path = str(cfg.paths.sim_path)

    # Run with config-driven settings
    run_milestone_capture(
        sim_path=sim_path,
        mode=cap.mode,                # 'laser' | 'largest' | 'solid'
        epsilon=cap.eps,
        x_start=cap.x_start,
        x_end=cap.x_end,
        linspace_cuts=cap.solid_cuts if cap.solid_cuts is not None else None,
        run_name="run_x",             # simple label; adjust if you want dynamic names
        out_dir=out_dir,
        front_W=cap.front[0], front_H=cap.front[1],
        side_W=cap.side[0],   side_H=cap.side[1],
        top_W=cap.top[0],     top_H=cap.top[1],
        x_side_offset=cap.x_side_offset,
        testing_folder=cap.empty_out,
    )
    log.info("run_milestone_capture.main() finished (out_dir=%s)", out_dir)


# Auto-run in PV shell/batch if paraview.testing=True (or env override)
# run_main_if_testing(main)
