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
import sys
from pathlib import Path

from sph2img.utils.pvlog import get_logger
from sph2img.config import get_config
from sph2img.utils.pvhelpers import run_main_if_testing

# pieces wired from your modules
from sph2img.utils.json_extractor import extract_power_and_vx
from sph2img.stages.sph_creator import prepare_sph_interpolator
from sph2img.stages.slice_creator import create_and_colour_slices
from sph2img.stages.screencapture_through_milestones import run_milestone_capture
from sph2img.stages.gif_maker import gif_creator

log = get_logger(__name__)


def main() -> None:
    cfg = get_config()
    cap = cfg.capture

    sim_path = str(cfg.paths.sim_path)
    out_dir = str(cfg.paths.out_dir)

    # Detect run params and name
    power_s, vx_s = extract_power_and_vx(sim_path)
    run_name = f"run_POWER-{power_s}_VELX-{vx_s}"
    log.info("Detected params → POWER=%s, VEL_X=%s, RUN_NAME=%s", power_s, vx_s, run_name)

    # 1) SPH interpolator
    log.info("Preparing SPH interpolator…")
    prepare_sph_interpolator(sim_path)

    # 2) Slice creation & colouring
    log.info("Creating and colouring slices…")
    create_and_colour_slices()

    # 3) Screencapture (config-driven)
    log.info("Starting screencapture | mode=%s", cap.mode)
    shot_folder = run_milestone_capture(
        sim_path=sim_path,
        mode=cap.mode,  # 'laser' | 'largest' | 'solid'
        epsilon=cap.eps,
        x_start=cap.x_start,
        x_end=cap.x_end,
        linspace_cuts=cap.solid_cuts if cap.solid_cuts is not None else None,
        run_name=run_name,
        out_dir=out_dir,
        front_W=cap.front[0], front_H=cap.front[1],
        side_W=cap.side[0], side_H=cap.side[1],
        top_W=cap.top[0], top_H=cap.top[1],
        x_side_offset=cap.x_side_offset,
        testing_folder=cap.empty_out,  # if True, clears folder on first write
    )
    log.info("Screencapture done: %s", shot_folder)

    # 4) Make GIFs beside the screenshots
    gif_creator(shot_folder)
    log.info("GIFs generated for: %s", shot_folder)


# Auto-run in PV shell/batch if paraview.testing=true in config.json
run_main_if_testing(main)
