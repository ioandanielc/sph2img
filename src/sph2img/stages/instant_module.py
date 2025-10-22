# sph2img/src/sph2img/stages/instant_module.py
# make repo/src importable no matter which interpreter runs this (python, pvpython, pvbatch)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sph2img.pvshim import enable_stubs; enable_stubs()

import time
from pathlib import Path

from sph2img.utils.pvlog import get_logger
from sph2img.config import get_config

# pieces wired from your modules
from sph2img.stages.sph_creator_single import prepare_sph_interpolator
from sph2img.stages.slice_creator import create_and_colour_slices
from sph2img.stages.slice_mover import move_slices_origin
from sph2img.stages.screencapture_slice_composite import screenshot_set

from paraview.simple import (Delete, ResetSession, RemoveViewsAndLayouts, GetActiveView, GetSources, GetAnimationScene,
                             CreateRenderView, SetActiveView, Render, Disconnect, Connect)
from paraview import servermanager

logger = get_logger(__name__)

def clean_reset_paraview() -> None:
    """Terminate the current ParaView session and start a new one."""
    logger.info("[pv] Resetting ParaView session…")
    t0 = time.time()
    pxm = servermanager.ProxyManager()
    pxm.UnRegisterProxies()
    del pxm
    Disconnect()
    Connect()
    logger.info("[pv] Session reset complete (Δt=%.3fs).", time.time() - t0)


def prepare_paths_from_sim_path(path_to_simulation: str, snapshot_index: int):
    logger.info("[paths] Preparing phase paths from sim=%s, snapshot=%s", path_to_simulation, snapshot_index)
    t0 = time.time()
    path_to_vtk_snapshots = Path(path_to_simulation) / 'output'

    solid_name = f'out_phase_1_SOLID_rank_0_{snapshot_index}.vtk'
    liquid_name = f'out_phase_2_LIQUID_rank_0_{snapshot_index}.vtk'
    gas_name = f'out_phase_3_GAS_rank_0_{snapshot_index}.vtk'
    wall_name = f'out_phase_4_WALL_rank_0_{snapshot_index}.vtk'

    solid_path = path_to_vtk_snapshots / solid_name
    liquid_path = path_to_vtk_snapshots / liquid_name
    gas_path = path_to_vtk_snapshots / gas_name
    wall_path = path_to_vtk_snapshots / wall_name

    logger.info("[paths] solid=%s", solid_path)
    logger.info("[paths] liquid=%s", liquid_path)
    logger.info("[paths] gas=%s", gas_path)
    logger.info("[paths] wall=%s", wall_path)
    logger.info("[paths] Phase paths prepared (Δt=%.3fs).", time.time() - t0)

    return solid_path, liquid_path, gas_path, wall_path


def deploy_and_die(
        run_name: str,
        iteration_number: int,
        snapshot_index: int,
        path_to_simulation: str,
        path_to_solid_phase: str,
        path_to_liquid_phase: str,
        path_to_gas_phase: str,
        path_to_wall_phase: str,
        path_to_output_dir: str,
        x_position: int,
        delete_vtk: bool = False,
):
    logger.info("[deploy] START run_name=%s iter=%s snap=%s x=%.6g delete_vtk=%s",
                run_name, iteration_number, snapshot_index, x_position, delete_vtk)
    logger.info("[deploy.paths] sim=%s", path_to_simulation)
    logger.info("[deploy.paths] out_dir=%s", path_to_output_dir)
    logger.info("[deploy.paths] solid=%s", path_to_solid_phase)
    logger.info("[deploy.paths] liquid=%s", path_to_liquid_phase)
    logger.info("[deploy.paths] gas=%s", path_to_gas_phase)
    logger.info("[deploy.paths] wall=%s", path_to_wall_phase)

    t_all = time.time()

    # 1) Prepare the ParaView environment by deleting everything from it
    t_reset = time.time()
    clean_reset_paraview()
    logger.info("[deploy] ParaView environment ready (Δt=%.3fs).", time.time() - t_reset)

    # 2) Create SPH (but hide)
    logger.info("[deploy] Creating SPH interpolator…")
    t_sph = time.time()
    sph = prepare_sph_interpolator(iteration_number,
                                   path_to_simulation,
                                   path_to_solid_phase,
                                   path_to_liquid_phase,
                                   path_to_gas_phase,
                                   path_to_wall_phase
                                   )
    logger.info("[deploy] SPH interpolator created (Δt=%.3fs).", time.time() - t_sph)

    # 3) Create Slices at the correct positions (and show)
    logger.info("[deploy] Creating & coloring slices…")
    t_slices = time.time()
    create_and_colour_slices()
    Render()
    logger.info("[deploy] Slices created and rendered (Δt=%.3fs).", time.time() - t_slices)

    logger.info("[deploy] Moving slices to x=%.6g", x_position)
    t_move = time.time()
    move_slices_origin([x_position, 0.0, 0.0])
    Render()
    logger.info("[deploy] Slices moved & rendered (Δt=%.3fs).", time.time() - t_move)

    # 4) Take the screenshots and save them
    logger.info("[deploy] Capturing screenshots…")
    t_shot = time.time()
    cfg = get_config()
    cap = cfg.capture

    screenshot_set(
        run_name=run_name,
        entry_no=iteration_number,
        out_dir=path_to_output_dir,
        front_W=cap.front[0], front_H=cap.front[1],
        side_W=cap.side[0],   side_H=cap.side[1],
        top_W=cap.top[0],     top_H=cap.top[1],
        x_side_offset=cap.x_side_offset,
        testing_folder=False
    )
    logger.info("[deploy] Screenshots saved (Δt=%.3fs).", time.time() - t_shot)

    # 5) Delete the .vtk files (if flag activated)
    if delete_vtk:
        logger.info("[deploy] Deleting VTK files for snapshot %s …", snapshot_index)
        t_del = time.time()
        Path(path_to_solid_phase).unlink(missing_ok=True)
        logger.info("[deploy] Deleted SOLID: %s", path_to_solid_phase)

        Path(path_to_liquid_phase).unlink(missing_ok=True)
        logger.info("[deploy] Deleted LIQUID: %s", path_to_liquid_phase)

        Path(path_to_gas_phase).unlink(missing_ok=True)
        logger.info("[deploy] Deleted GAS: %s", path_to_gas_phase)

        Path(path_to_wall_phase).unlink(missing_ok=True)
        logger.info("[deploy] Deleted WALL: %s", path_to_wall_phase)
        logger.info("[deploy] VTK deletions complete (Δt=%.3fs).", time.time() - t_del)
    else:
        logger.info("[deploy] MOCK delete: SOLID %s", path_to_solid_phase)
        logger.info("[deploy] MOCK delete: LIQUID %s", path_to_liquid_phase)
        logger.info("[deploy] MOCK delete: GAS %s", path_to_gas_phase)
        logger.info("[deploy] MOCK delete: WALL %s", path_to_wall_phase)

    logger.info("[deploy] FINISHED (total Δt=%.3fs).", time.time() - t_all)
    return

def main():
    logger.info("[main] instant_module main() START")
    run_name = 'testing-instant-module'
    iteration_number = 0
    snapshot_index = 413
    path_to_simulation = '/Users/ioandanielcraciun/Python-Projects/sph2img/simulations/mhpc3d_200W_Ti64_Ar-3Y'
    logger.info("[main] run_name=%s iter=%s snap=%s sim=%s",
                run_name, iteration_number, snapshot_index, path_to_simulation)

    paths = prepare_paths_from_sim_path(path_to_simulation, snapshot_index)
    path_to_solid_phase = paths[0]
    path_to_liquid_phase = paths[1]
    path_to_gas_phase = paths[2]
    path_to_wall_phase = paths[3]
    path_to_output_dir = '/Users/ioandanielcraciun/Python-Projects/sph2img/outputs/screenshots/testing_single_approach'
    x_position = 2e-3
    delete_vtk = False

    logger.info("[main.paths] solid=%s", path_to_solid_phase)
    logger.info("[main.paths] liquid=%s", path_to_liquid_phase)
    logger.info("[main.paths] gas=%s", path_to_gas_phase)
    logger.info("[main.paths] wall=%s", path_to_wall_phase)
    logger.info("[main] out_dir=%s x=%.6g delete_vtk=%s", path_to_output_dir, x_position, delete_vtk)

    deploy_and_die(
            run_name=run_name,
            iteration_number=iteration_number,
            snapshot_index=snapshot_index,
            path_to_simulation=path_to_simulation,
            path_to_solid_phase=path_to_solid_phase,
            path_to_liquid_phase=path_to_liquid_phase,
            path_to_gas_phase=path_to_gas_phase,
            path_to_wall_phase=path_to_wall_phase,
            path_to_output_dir=path_to_output_dir,
            x_position=x_position,
            delete_vtk=delete_vtk,
    )
    logger.info("[main] instant_module main() END")
