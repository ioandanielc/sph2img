# src/sph2img/paraview/run_all_pipeline.py
#!/usr/bin/env python3
"""
High-level driver for SPH -> slice coloring -> milestone screencapture -> GIFs.

Steps:
  1) Extract POWER and VEL_X from SIM_PATH to build RUN_NAME
  2) Prepare SPH interpolator
  3) Create & color slice planes
  4) Run milestone-based screencapture in one of: 'laser' | 'largest' | 'solid'
  5) Build per-view GIFs from the screenshots
"""

# --- path bootstrap: make `sph2img` importable even when run as a script -----
import sys
import time
import shutil
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]  # repo root (sph2img/)
_SRC = _ROOT / "src"

if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
# ---------------------------------------------------------------------------

from datetime import datetime

from sph2img.config import get_config
from sph2img.utils.pvlog import get_logger
from sph2img.utils.pvhelpers import run_main_if_testing
from sph2img.utils.crawl_iterations import crawl_iterations
from sph2img.utils.json_extractor import extract_power_and_vx


from sph2img.milestones.milestones_solidified import build_solidified_map_online
from sph2img.milestones.milestones_melt_laser_positions import build_iteration_laser_x_online
from sph2img.milestones.milestones_melt_largest_delta import build_iteration_largest_online

from sph2img.stages.sph_creator_single import prepare_sph_interpolator
from sph2img.stages.slice_creator import create_and_colour_slices
from sph2img.stages.slice_mover import move_slices_origin
from sph2img.stages.instant_module import prepare_paths_from_sim_path, clean_reset_paraview
from sph2img.stages.screencapture_slice_composite import screenshot_set
from sph2img.stages.gif_amker import gif_creator

from paraview.simple import (  # type: ignore
    Render
)
# pieces wired from your modules

log = get_logger(__name__)


def create_timestamped_folder(power, vx, base_dir: str = ".") -> Path:
    """
    Create screenshots_YYYY-MM-DD_HH-MM-SS-MMM under base_dir.
    Uses the system's local time (no zoneinfo dependency).
    """
    now = datetime.fromtimestamp(time.time())  # local time
    millis = f"{int((now.microsecond) / 1000):03d}"
    folder_name = f"screenshots_{now.strftime('%Y-%m-%d_%H-%M-%S')}-{millis}-power-{power}-vx-{vx}"
    path = Path(base_dir) / folder_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def deploy():
    # 1) Gather data
    # 1.1) Global data
    cfg = get_config()
    paths = cfg.paths
    cap = cfg.capture
    fr = cfg.files_removal
    name = cfg.name

    run_name = name.run_name

    post_delete = fr.post_delete

    sim_path = paths.sim_path
    out_path = paths.out_dir
    ss_dir = paths.ss_dir + '/screenshots'

    power, vx = extract_power_and_vx(sim_path)

    mode = cap.mode
    eps = cap.eps
    x_start = cap.x_start  # gets overwritten
    x_end = cap.x_end  # gets overwritten
    solid_cuts = cap.solid_cuts

    front_w = cap.front_w
    front_h = cap.front_h
    side_w = cap.side_w
    side_h = cap.side_h
    top_w = cap.top_w
    top_h = cap.top_h

    x_side_offset = cap.x_side_offset
    empty_out = cap.empty_out

    # 1.2) Crawl
    liquid_phase_indices, liquid_phase_iters, liquid_phase_order_to_iter, liquid_phase_paths, liquid_phase_iter_to_path \
        = crawl_iterations(sim_path)

    # 2) Prepare folder structure for storing the graphic data
    output_folder = create_timestamped_folder(power, vx, ss_dir)

    # 3) Start iterating
    if mode == 'solidified':
        # 3.A) Solidified
        # 3.A.1) Get indices
        # If the config values are 0, take the first and last mid
        i_start = 0
        i_end = liquid_phase_indices[-1]
        x_start = build_iteration_largest_online(sim_path, liquid_phase_paths[i_start], liquid_phase_iters[i_start])
        x_end = build_iteration_largest_online(sim_path, liquid_phase_paths[i_end], liquid_phase_iters[i_end])
        cuts_pos, lin_dict = build_solidified_map_online(sim_path, liquid_phase_paths[-1], liquid_phase_iters[-1],
                                               x_start, x_end, x_side_offset, 0, solid_cuts)

        # 3.A.2) Perform procedure
        solid_path, liquid_path, gas_path, wall_path = prepare_paths_from_sim_path(sim_path, liquid_phase_iters[-1])

        ## 1) Prepare the ParaView environment by deleting everything from it
        clean_reset_paraview()

        ## 2) Create SPH (but hide)
        sph = prepare_sph_interpolator(liquid_phase_iters[-1],
                                       sim_path,
                                       solid_path,
                                       liquid_path,
                                       gas_path,
                                       wall_path
                                       )

        ## 3) Create Slices at the correct positions (and show)
        create_and_colour_slices()
        Render()

        for i, cut in enumerate(cuts_pos):
            move_slices_origin([cut, 0.0, 0.0])
            Render()
            screenshot_set(
                run_name=run_name,
                entry_no=i,
                out_dir=output_folder,
                front_W=cap.front[0], front_H=cap.front[1],
                side_W=cap.side[0], side_H=cap.side[1],
                top_W=cap.top[0], top_H=cap.top[1],
                x_side_offset=cap.x_side_offset,
                testing_folder=cap.empty_out,  # reuse your config flag
            )


        # 3.A.3) ONLY AT THE END: Delete all the .vtk files (if required)
        if post_delete:
            shutil.rmtree(sim_path)

    elif mode == 'laser' or mode == 'largest':
        # 3.B) Melt
        # 3.B.1) Choose between 'largest' or 'laser'

        # 3.B.2) Compute the x position accordingly

        # 3.B.3) Perform procedure (Delete .vtk file if required)
        pass

    # 4) Create .gif
    gif_creator(output_folder)

    # 5) Write report and finish process
    log.info('Finished')

    return


# Auto-run in PV shell/batch if paraview.testing=true in config.json
run_main_if_testing(deploy)
