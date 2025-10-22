# src/sph2img/paraview/run_milestone_capture.py
#!/usr/bin/env python3
# make repo/src importable no matter which interpreter runs this (python, pvpython, pvbatch)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sph2img.pvshim import enable_stubs; enable_stubs()

import time
from pathlib import Path

from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

from sph2img.utils.pvlog import get_logger
from sph2img.config import get_config

# milestones
from sph2img.milestones.milestones_common import ordered_index_map
from sph2img.milestones.milestones_melt_laser_positions import build_iteration_laser_x
from sph2img.milestones.milestones_melt_largest_delta import build_iteration_mid_x, DEFAULT_EPS
from sph2img.milestones.milestones_solidified import build_solidified_map

# slice + screenshots
from sph2img.stages.slice_mover import move_slices_origin
from sph2img.stages.screencapture_slice_composite import screenshot_set

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
    print('Y')
    print(steps)
    steps = [1.0]
    print(steps)
    print('Y')
    if not steps:
        raise RuntimeError("No time steps available in the current pipeline.")
    if not (0 <= idx < len(steps)):
        raise IndexError(f"Timestep index {idx} out of range 0..{len(steps)-1}")
    scene.AnimationTime = float(steps[idx])


def _last_time_index() -> int:
    scene = GetAnimationScene()
    steps = list(scene.TimeKeeper.TimestepValues)
    print('Y')
    steps = [1.0]
    print('Y')
    if not steps:
        raise RuntimeError("No time steps available in the current pipeline.")
    return len(steps) - 1


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

    solid_mode = (mode.lower() == "solid")
    last_idx = _last_time_index() if solid_mode else None

    for i, ms in enumerate(milestones):
        # 1) timestep
        if solid_mode:
            _set_time_by_index(last_idx)  # always final frame
        else:
            _set_time_by_index(ms.idx)

        # 2) place slices at x (laser / largest / solid linspace)
        if ms.x is not None:
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
