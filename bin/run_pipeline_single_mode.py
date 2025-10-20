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
from sph2img.milestones.milestones_melt_largest_delta import build_iteration_largest_online, DEFAULT_EPS

from sph2img.stages.sph_creator_single import prepare_sph_interpolator
from sph2img.stages.slice_creator import create_and_colour_slices
from sph2img.stages.slice_mover import move_slices_origin
from sph2img.stages.instant_module import prepare_paths_from_sim_path, clean_reset_paraview, deploy_and_die
from sph2img.stages.screencapture_slice_composite import screenshot_set
from sph2img.stages.gif_maker import gif_creator

from paraview.simple import (  # type: ignore
    Render
)

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
    log.info(f"[create_timestamped_folder] Created output folder: {path}")
    return path


def deploy():
    t0 = time.time()
    log.info("=== run_all_pipeline.deploy → START ===")

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
    ss_dir = Path.joinpath(out_path, 'screenshots')

    log.info(f"[config] run_name={run_name}")
    log.info(f"[config] sim_path={sim_path}")
    log.info(f"[config] out_path={out_path}")
    log.info(f"[config] ss_dir={ss_dir}")
    log.info(f"[config] post_delete={post_delete}")

    power, vx = extract_power_and_vx(sim_path)
    log.info(f"[json] Extracted POWER={power}, VEL_X={vx} from {sim_path}")

    mode = cap.mode
    eps = cap.eps
    x_start = cap.x_start  # gets overwritten
    x_end = cap.x_end      # gets overwritten
    solid_cuts = cap.solid_cuts

    front_w = cap.front_w
    front_h = cap.front_h
    side_w = cap.side_w
    side_h = cap.side_h
    top_w = cap.top_w
    top_h = cap.top_h

    x_side_offset = cap.x_side_offset
    empty_out = cap.empty_out

    log.info(f"[capture] mode={mode}, eps={eps}, solid_cuts={solid_cuts}, x_side_offset={x_side_offset}, empty_out={empty_out}")
    log.info(f"[capture] front=({front_w}x{front_h}), side=({side_w}x{side_h}), top=({top_w}x{top_h})")

    # 1.2) Crawl
    log.info("[crawl] Crawling liquid-phase iterations…")
    liquid_phase_indices, liquid_phase_iters, liquid_phase_order_to_iter, liquid_phase_paths, liquid_phase_iter_to_path = crawl_iterations(sim_path)
    log.info(f"[crawl] Found {len(liquid_phase_indices)} liquid-phase indices.")
    if liquid_phase_indices:
        log.info(f"[crawl] First iter={liquid_phase_iters[0]} @ {liquid_phase_paths[0]}")
        log.info(f"[crawl] Last  iter={liquid_phase_iters[-1]} @ {liquid_phase_paths[-1]}")

    # 2) Prepare folder structure for storing the graphic data
    output_folder = create_timestamped_folder(power, vx, ss_dir)
    log.info(f"[paths] Output folder for screenshots: {output_folder}")

    # 3) Start iterating
    if mode == 'solid':
        log.info("[solidified] Starting SOLIDIFIED pipeline…")
        # 3.A) Solidified
        # 3.A.1) Get indices
        # If the config values are 0, take the first and last mid
        i_start = 0
        i_end = liquid_phase_indices[-1]
        log.info(f"[solidified] Using i_start={i_start}, i_end={i_end} (from crawled indices)")

        x_start = build_iteration_largest_online(sim_path, liquid_phase_paths[i_start], liquid_phase_iters[i_start])
        x_end = build_iteration_largest_online(sim_path, liquid_phase_paths[i_end], liquid_phase_iters[i_end])
        log.info(f"[solidified] Computed x_start={x_start:.6g}, x_end={x_end:.6g} from 'largest' metric")

        cuts_pos, lin_dict = build_solidified_map_online(
            liquid_phase_iters[-1],
            x_start,
            x_end,
            solid_cuts
        )
        log.info(f"[solidified] Built solidified map with {len(cuts_pos)} cuts. Example (first 3): {cuts_pos[:3]}")

        # 3.A.2) Perform procedure
        solid_path, liquid_path, gas_path, wall_path = prepare_paths_from_sim_path(sim_path, liquid_phase_iters[-1])
        log.info(f"[solidified] Paths → solid={solid_path}, liquid={liquid_path}, gas={gas_path}, wall={wall_path}")
        log.info("[solidified] Cleaning and resetting ParaView session…")
        clean_reset_paraview()
        log.info("[solidified] ParaView session reset OK.")

        log.info("[solidified] Creating SPH interpolator (hidden)…")
        sph = prepare_sph_interpolator(
            liquid_phase_iters[-1],
            sim_path,
            solid_path,
            liquid_path,
            gas_path,
            wall_path
        )
        log.info("[solidified] SPH interpolator ready.")

        log.info("[solidified] Creating and coloring slices…")
        create_and_colour_slices()
        Render()
        log.info("[solidified] Slices created and shown (initial render complete).")
        for i, cut in enumerate(cuts_pos):
            log.info(f"[solidified] Moving slices to x={cut:.6g} (entry {i+1}/{len(cuts_pos)})…")
            t_move = time.time()
            move_slices_origin([cut, 0.0, 0.0])
            Render()
            log.info(f"[solidified] Rendered at x={cut:.6g} (Δt={time.time()-t_move:.3f}s). Capturing screenshots…")

            screenshot_set(
                run_name=run_name,
                entry_no=i,
                out_dir=output_folder,
                front_W=cap.front[0], front_H=cap.front[1],
                side_W=cap.side[0], side_H=cap.side[1],
                top_W=cap.top[0], top_H=cap.top[1],
                x_side_offset=cap.x_side_offset,
                testing_folder=False,  # reuse your config flag
            )
            log.info(f"[solidified] Screenshots captured for entry {i} at x={cut:.6g}.")

    elif mode == 'laser' or mode == 'largest':
        for i, iteration in enumerate(liquid_phase_iters):
            # 3.B) Melt
            # 3.B.1) Compute the x position accordingly
            if mode == 'largest':
                x_s = build_iteration_largest_online(sim_path,
                                                     liquid_phase_paths[i],
                                                     iteration,
                                                     DEFAULT_EPS)
                pass
            elif mode == 'laser':
                x_s = build_iteration_largest_online(sim_path,
                                                     iteration)
                pass
            else:
                x_s = 0.0
            solid_path, liquid_path, gas_path, wall_path = prepare_paths_from_sim_path(sim_path, iteration)

            # 3.B.2) Perform procedure
            deploy_and_die(
                run_name=run_name,
                iteration_number=iteration,
                snapshot_index=i,
                path_to_simulation=sim_path,
                path_to_solid_phase=solid_path,
                path_to_liquid_phase=liquid_path,
                path_to_gas_phase=gas_path,
                path_to_wall_phase=wall_path,
                path_to_output_dir=output_folder,
                x_position=x_s,
                delete_vtk=False,
            )
    else:
        log.info(f"[mode] Unknown mode '{mode}'. No pipeline executed (config issue?).")


    # 4) Create .gif
    log.info("[gif] Creating GIFs from screenshots…")
    t_gif = time.time()
    gif_creator(output_folder)
    log.info(f"[gif] GIF creation finished (Δt={time.time()-t_gif:.3f}s). Output folder: {output_folder}")

    if mode in ['solid', 'laser', 'largest'] and post_delete:
        log.info(f"[cleanup] post_delete=True → deleting simulation directory: {out_path}")
        shutil.rmtree(out_path)
        log.info("[cleanup] Simulation directory deleted.")


    # 5) Write report and finish process
    log.info(f"=== run_all_pipeline.deploy → FINISHED in {time.time()-t0:.3f}s ===")
    return


if __name__ == '__main__':
    deploy()