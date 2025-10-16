import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]  # repo root (sph2img/)
_SRC = _ROOT / "src"

if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
# ---------------------------------------------------------------------------

from sph2img.utils.pvlog import get_logger
from sph2img.config import get_config
from sph2img.utils.pvhelpers import run_main_if_testing

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
    logger.info("Resetting ParaView session…")
    pxm = servermanager.ProxyManager()
    pxm.UnRegisterProxies()
    del pxm
    Disconnect()
    Connect()
    logger.info("Session reset complete.")


def prepare_paths_from_sim_path(path_to_simulation: str, snapshot_index: int):
    path_to_vtk_snapshots = Path(path_to_simulation) / 'output'

    solid_name = f'out_phase_1_SOLID_rank_0_{snapshot_index}.vtk'
    liquid_name = f'out_phase_2_LIQUID_rank_0_{snapshot_index}.vtk'
    gas_name = f'out_phase_3_GAS_rank_0_{snapshot_index}.vtk'
    wall_name = f'out_phase_4_WALL_rank_0_{snapshot_index}.vtk'

    solid_path = path_to_vtk_snapshots / solid_name
    liquid_path = path_to_vtk_snapshots / liquid_name
    gas_path = path_to_vtk_snapshots / gas_name
    wall_path = path_to_vtk_snapshots / wall_name

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
    # 1) Prepare the ParaView environment by deleting everything from it
    clean_reset_paraview()

    # 2) Create SPH (but hide)
    sph = prepare_sph_interpolator(iteration_number,
                                   path_to_simulation,
                                   path_to_solid_phase,
                                   path_to_liquid_phase,
                                   path_to_gas_phase,
                                   path_to_wall_phase
                                   )

    # 3) Create Slices at the correct positions (and show)
    create_and_colour_slices()
    Render()
    move_slices_origin([x_position, 0.0, 0.0])

    # 4) Take the screenshots and save them
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
        testing_folder=cap.empty_out
    )

    # 5) Delete the .vtk files (if flag activated)
    if delete_vtk:
        # Delete the files
        logger.info(f"Deleting VTK SOLID phase from snapshot {snapshot_index} located at {path_to_solid_phase}")
        Path(path_to_solid_phase).unlink(missing_ok=True)
        logger.info("* * *   D E L E T E D   * * *")

        logger.info(f"Deleting VTK LIQUID phase from snapshot {snapshot_index} located at {path_to_liquid_phase}")
        Path(path_to_liquid_phase).unlink(missing_ok=True)
        logger.info("* * *   D E L E T E D   * * *")

        logger.info(f"Deleting VTK GAS phase from snapshot {snapshot_index} located at {path_to_gas_phase}")
        Path(path_to_gas_phase).unlink(missing_ok=True)
        logger.info("* * *   D E L E T E D   * * *")

        logger.info(f"Deleting VTK WALL phase from snapshot {snapshot_index} located at {path_to_wall_phase}")
        Path(path_to_wall_phase).unlink(missing_ok=True)
        logger.info("* * *   D E L E T E D   * * *")
    else:
        logger.info(
            f"This is a MOCK deletion of the SOLID phase from snapshot {snapshot_index} located at {path_to_solid_phase}")
        logger.info("* * *   M O C K   D E L E T E   * * *")

        logger.info(
            f"This is a MOCK deletion of the LIQUID phase from snapshot {snapshot_index} located at {path_to_liquid_phase}")
        logger.info("* * *   M O C K   D E L E T E   * * *")

        logger.info(
            f"This is a MOCK deletion of the GAS phase from snapshot {snapshot_index} located at {path_to_gas_phase}")
        logger.info("* * *   M O C K   D E L E T E   * * *")

        logger.info(
            f"This is a MOCK deletion of the WALL phase from snapshot {snapshot_index} located at {path_to_wall_phase}")
        logger.info("* * *   M O C K   D E L E T E   * * *")

    return

def main():
    run_name = 'testing-instant-module'
    iteration_number = 0
    snapshot_index = 413
    path_to_simulation = '/Users/ioandanielcraciun/Python-Projects/sph2img/simulations/mhpc3d_200W_Ti64_Ar-3Y'
    paths = prepare_paths_from_sim_path(path_to_simulation, snapshot_index)
    path_to_solid_phase = paths[0]
    path_to_liquid_phase = paths[1]
    path_to_gas_phase = paths[2]
    path_to_wall_phase = paths[3]
    path_to_output_dir = '/Users/ioandanielcraciun/Python-Projects/sph2img/outputs/screenshots/testing_single_approach'
    x_position = 2e-3
    delete_vtk = False

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

if run_main_if_testing:
    main()




