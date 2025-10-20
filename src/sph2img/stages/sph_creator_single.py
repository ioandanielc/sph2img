# sph2img/src/sph2img/stages/sph_creator_single.py
# import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]  # repo root (sph2img/)
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
print(_SRC)
# ---------------------------------------------------------------------------

import re
import time  # for lightweight timings
from pathlib import Path
from typing import Dict, List

from sph2img.utils.pvlog import get_logger
from sph2img.config import get_config
from sph2img.parsers import master_parser
from sph2img.utils.pvhelpers import run_main_if_testing, pv_view_name
from sph2img.utils.pvhelpers import run_main_if_testing  # re-import safe; clarify intent

# ParaView heavy deps (runtime environment must provide them)
from paraview import servermanager  # type: ignore
from paraview.simple import (  # type: ignore
    LegacyVTKReader,
    GetActiveViewOrCreate,
    SPHVolumeInterpolator,
    AppendDatasets,
    Calculator,
    Show,
    HideScalarBarIfNotNeeded,
    GetColorTransferFunction,
    GetOpacityTransferFunction,
    GetTransferFunction2D,
    ColorBy,
    Disconnect,
    Connect,
    GetAnimationScene,
)

logger = get_logger(__name__)


# ----------------------------
# session helpers
# ----------------------------

def reset_session() -> None:
    """Terminate the current ParaView session and start a new one."""
    logger.info("[session] Resetting ParaView session…")
    t0 = time.time()
    pxm = servermanager.ProxyManager()
    pxm.UnRegisterProxies()
    del pxm
    Disconnect()
    Connect()
    logger.info("[session] Session reset complete (Δt=%.3fs).", time.time() - t0)


# ----------------------------
# data discovery
# ----------------------------

def create_reader(phase_path, phase_key, phase_iteration):
    """Create a LegacyVTKReader for each phase key and register them in the pipeline."""
    logger.info("[reader] Creating reader: phase=%s iter=%s path=%s", phase_key, phase_iteration, phase_path)
    t0 = time.time()
    l = [str(phase_path)]
    reader = LegacyVTKReader(
        registrationName=f"out_phase_{phase_key}_{phase_iteration}.vtk",
        FileNames=l,
    )
    logger.info("[reader] Reader created for phase %s @ iter %s (Δt=%.3fs)", phase_key, phase_iteration, time.time() - t0)
    return reader


# ----------------------------
# pipeline
# ----------------------------

def prepare_sph_interpolator(iteration_number: int,
                             path_to_simulation: str,
                             path_to_solid_phase: str,
                             path_to_liquid_phase: str,
                             path_to_gas_phase: str,
                             path_to_wall_phase: str, ):
    """
    Build a phase-agnostic SPH interpolator combining SOLID/LIQUID/GAS/WALL, and
    return the created SPHVolumeInterpolator proxy. Also prepares the view.

    Returns:
        SPHVolumeInterpolator proxy
    """
    logger.info("[sph] prepare_sph_interpolator START (iter=%s)", iteration_number)
    t_all = time.time()

    render_view = GetActiveViewOrCreate(pv_view_name())  # <-- use config default view
    render_view.OrientationAxesVisibility = 0
    logger.info("[sph] Render view ready (axes hidden).")

    logger.info("[sph] Parsing simulation config: %s", path_to_simulation)
    t_parse = time.time()
    (
        _laser_power,
        _laser_velocity,
        _melt_material,
        _melt_density,
        _dt_list,
        _iter_list,
        _pos_bounds_list,
        _time_list,
        _vtk_iterations,
        _laser_positions_at_vtk_iterations,
        _domain,
        smoothing_length,
        _resolution,
        domain_min,
        domain_max,
    ) = master_parser.run(path_to_simulation)
    logger.info("[sph] Parsed config (Δt=%.3fs). smoothing_length=%s, domain_min=%s, domain_max=%s",
                time.time() - t_parse, smoothing_length, domain_min, domain_max)

    logger.info("[sph] Creating readers for phases…")
    t_readers = time.time()
    try:
        solid_phase_single = create_reader(Path(path_to_solid_phase), 'SOLID', iteration_number)
        liquid_phase_single = create_reader(path_to_liquid_phase, 'LIQUID', iteration_number)
        gas_phase_single = create_reader(path_to_gas_phase, 'GAS', iteration_number)
        wall_phase_single = create_reader(path_to_wall_phase, 'WALL', iteration_number)
    except KeyError as e:
        logger.info("[sph] Reader creation failed due to missing phase.")
        raise RuntimeError(f"Missing expected phase in outputs: {e}.") from e
    logger.info("[sph] All readers created (Δt=%.3fs).", time.time() - t_readers)

    # --- SOLID branch calculators ---
    logger.info("[calc] Building SOLID calculators…")
    t_calc_solid = time.time()
    calc_solid_is_solid = Calculator(registrationName="Calculator_solid_is_solid", Input=solid_phase_single)
    calc_solid_is_solid.ResultArrayName = "is_solid";  calc_solid_is_solid.Function = "1"

    calc_solid_is_liquid = Calculator(registrationName="Calculator_solid_is_liquid", Input=calc_solid_is_solid)
    calc_solid_is_liquid.ResultArrayName = "is_liquid";  calc_solid_is_liquid.Function = "0"

    calc_solid_is_gas = Calculator(registrationName="Calculator_solid_is_gas", Input=calc_solid_is_liquid)
    calc_solid_is_gas.ResultArrayName = "is_gas";  calc_solid_is_gas.Function = "0"

    calc_solid_is_wall = Calculator(registrationName="Calculator_solid_is_wall", Input=calc_solid_is_gas)
    calc_solid_is_wall.ResultArrayName = "is_wall";  calc_solid_is_wall.Function = "0"

    calc_solid_aggregate = Calculator(registrationName="Calculator_solid_aggregate_state", Input=calc_solid_is_wall)
    calc_solid_aggregate.ResultArrayName = "aggregate_state";  calc_solid_aggregate.Function = "0"

    calc_solid_pcc = Calculator(registrationName="Calculator_solid_phase_change_counter", Input=calc_solid_aggregate)
    calc_solid_pcc.ResultArrayName = "phase_change_counter";  calc_solid_pcc.Function = "Tags_3_0"
    logger.info("[calc] SOLID calculators ready (Δt=%.3fs).", time.time() - t_calc_solid)

    # --- LIQUID branch calculators ---
    logger.info("[calc] Building LIQUID calculators…")
    t_calc_liq = time.time()
    calc_liquid_is_solid = Calculator(registrationName="Calculator_liquid_is_solid", Input=liquid_phase_single)
    calc_liquid_is_solid.ResultArrayName = "is_solid";  calc_liquid_is_solid.Function = "0"

    calc_liquid_is_liquid = Calculator(registrationName="Calculator_liquid_is_liquid", Input=calc_liquid_is_solid)
    calc_liquid_is_liquid.ResultArrayName = "is_liquid";  calc_liquid_is_liquid.Function = "1"

    calc_liquid_is_gas = Calculator(registrationName="Calculator_liquid_is_gas", Input=calc_liquid_is_liquid)
    calc_liquid_is_gas.ResultArrayName = "is_gas";  calc_liquid_is_gas.Function = "0"

    calc_liquid_is_wall = Calculator(registrationName="Calculator_liquid_is_wall", Input=calc_liquid_is_gas)
    calc_liquid_is_wall.ResultArrayName = "is_wall";  calc_liquid_is_wall.Function = "0"

    calc_liquid_aggregate = Calculator(registrationName="Calculator_liquid_aggregate_state", Input=calc_liquid_is_wall)
    calc_liquid_aggregate.ResultArrayName = "aggregate_state";  calc_liquid_aggregate.Function = "1"

    calc_liquid_pcc = Calculator(registrationName="Calculator_liquid_phase_change_counter", Input=calc_liquid_aggregate)
    calc_liquid_pcc.ResultArrayName = "phase_change_counter";  calc_liquid_pcc.Function = "Tags_1_0"
    logger.info("[calc] LIQUID calculators ready (Δt=%.3fs).", time.time() - t_calc_liq)

    # --- GAS branch calculators ---
    logger.info("[calc] Building GAS calculators…")
    t_calc_gas = time.time()
    calc_gas_is_solid = Calculator(registrationName="Calculator_gas_is_solid", Input=gas_phase_single)
    calc_gas_is_solid.ResultArrayName = "is_solid";  calc_gas_is_solid.Function = "0"

    calc_gas_is_liquid = Calculator(registrationName="Calculator_gas_is_liquid", Input=calc_gas_is_solid)
    calc_gas_is_liquid.ResultArrayName = "is_liquid";  calc_gas_is_liquid.Function = "0"

    calc_gas_is_gas = Calculator(registrationName="Calculator_gas_is_gas", Input=calc_gas_is_liquid)
    calc_gas_is_gas.ResultArrayName = "is_gas";  calc_gas_is_gas.Function = "1"

    calc_gas_is_wall = Calculator(registrationName="Calculator_gas_is_wall", Input=calc_gas_is_gas)
    calc_gas_is_wall.ResultArrayName = "is_wall";  calc_gas_is_wall.Function = "0"

    calc_gas_aggregate = Calculator(registrationName="Calculator_gas_aggregate_state", Input=calc_gas_is_wall)
    calc_gas_aggregate.ResultArrayName = "aggregate_state";  calc_gas_aggregate.Function = "2"

    calc_gas_pcc = Calculator(registrationName="Calculator_gas_phase_change_counter", Input=calc_gas_aggregate)
    calc_gas_pcc.ResultArrayName = "phase_change_counter";  calc_gas_pcc.Function = "0"
    logger.info("[calc] GAS calculators ready (Δt=%.3fs).", time.time() - t_calc_gas)

    # --- WALL branch calculators ---
    logger.info("[calc] Building WALL calculators…")
    t_calc_wall = time.time()
    calc_wall_is_wall_a = Calculator(registrationName="Calculator_wall_is_wall", Input=wall_phase_single)
    calc_wall_is_wall_a.ResultArrayName = "is_solid";  calc_wall_is_wall_a.Function = "0"

    calc_wall_is_liquid = Calculator(registrationName="Calculator_wall_is_liquid", Input=calc_wall_is_wall_a)
    calc_wall_is_liquid.ResultArrayName = "is_liquid";  calc_wall_is_liquid.Function = "0"

    calc_wall_is_gas = Calculator(registrationName="Calculator_wall_is_gas", Input=calc_wall_is_liquid)
    calc_wall_is_gas.ResultArrayName = "is_gas";  calc_wall_is_gas.Function = "0"

    calc_wall_is_wall_b = Calculator(registrationName="Calculator_wall_is_wall", Input=calc_wall_is_gas)
    calc_wall_is_wall_b.ResultArrayName = "is_wall";  calc_wall_is_wall_b.Function = "1"

    calc_wall_aggregate = Calculator(registrationName="Calculator_wall_aggregate_state", Input=calc_wall_is_wall_b)
    calc_wall_aggregate.ResultArrayName = "aggregate_state";  calc_wall_aggregate.Function = "3"

    calc_wall_pcc = Calculator(registrationName="Calculator_wall_phase_change_counter", Input=calc_wall_aggregate)
    calc_wall_pcc.ResultArrayName = "phase_change_counter";  calc_wall_pcc.Function = "0"
    logger.info("[calc] WALL calculators ready (Δt=%.3fs).", time.time() - t_calc_wall)

    # --- append + derived fields ---
    logger.info("[append] Appending phases and computing derived arrays…")
    t_append = time.time()
    append_pcc = AppendDatasets(
        registrationName="AppendDatasets_phase_change_counter",
        Input=[calc_solid_pcc, calc_liquid_pcc, calc_gas_pcc, calc_wall_pcc],
    )

    # density
    calc_density = Calculator(registrationName="Calculator_density", Input=append_pcc)
    calc_density.ResultArrayName = "density"
    calc_density.Function = "Conservatives_0_0"

    # velocity
    calc_velocity = Calculator(registrationName="Calculator_velocity", Input=calc_density)
    calc_velocity.ResultArrayName = "velocity"
    calc_velocity.Function = (
        "Conservatives_1_0*iHat + Conservatives_2_0*jHat + Conservatives_3_0*kHat"
    )

    # temperature
    calc_temperature = Calculator(registrationName="Calculator_temperature", Input=calc_velocity)
    calc_temperature.ResultArrayName = "temperature"
    calc_temperature.Function = "Primitives_1_0"
    logger.info("[append] Derived arrays density/velocity/temperature set (Δt=%.3fs).", time.time() - t_append)

    # --- SPH volume interpolator ---
    logger.info("[sph] Creating SPHVolumeInterpolator for combined phases…")
    t_sph = time.time()
    sph = SPHVolumeInterpolator(
        registrationName="SPHVolumeInterpolator_phase_change_counter",
        Input=calc_temperature,
        Source="Bounded Volume",
    )

    # kernel & locator
    sph.Kernel = "SPHQuinticKernel"
    sph.Locator = "Static Point Locator"

    # origin/scale from domain bounds
    sph.Source.Origin = list(map(float, domain_min))
    sph.Source.Scale = [float(domain_max[i]) - float(domain_min[i]) for i in range(len(domain_min))]

    # discretization
    sph.Source.RefinementMode = "Use cell-size"
    sph.Source.CellSize = float(smoothing_length)
    sph.Kernel.SpatialStep = float(smoothing_length)

    # arrays
    sph.DensityArray = "phase_change_counter"
    sph.MassArray = "None"
    sph.ExcludedArrays = [
        "ColorGradient_0_0", "ColorGradient_10_0", "ColorGradient_11_0", "ColorGradient_1_0", "ColorGradient_2_0",
        "ColorGradient_3_0", "ColorGradient_4_0", "ColorGradient_5_0", "ColorGradient_6_0", "ColorGradient_7_0",
        "ColorGradient_8_0", "ColorGradient_9_0", "Conservatives_0_0", "Conservatives_1_0", "Conservatives_2_0",
        "Conservatives_3_0", "Conservatives_4_0", "MaterialVariables_0_0", "MaterialVariables_1_0",
        "MaterialVariables_2_0", "MaterialVariables_3_0", "MaterialVariables_4_0", "MaterialVariables_5_0",
        "Primitives_0_0", "Primitives_10_0", "Primitives_1_0", "Primitives_2_0", "Primitives_3_0", "Primitives_4_0",
        "Primitives_5_0", "Primitives_6_0", "Primitives_7_0", "Primitives_8_0", "Primitives_9_0",
        "Tags_0_0", "Tags_1_0", "TimeDerivatives_0_0", "attr7", "attr8", "domain",
    ]
    sph.ComputeShepardSum = 1

    logger.info("[sph] SPH settings: Origin=%s Scale=%s CellSize=%.6g SpatialStep=%.6g",
                sph.Source.Origin, sph.Source.Scale, sph.Source.CellSize, sph.Kernel.SpatialStep)
    logger.info("[sph] Using DensityArray=%s MassArray=%s (ExcludedArrays=%d)",
                sph.DensityArray, sph.MassArray, len(sph.ExcludedArrays))
    logger.info("[sph] SPH interpolator ready (Δt=%.3fs).", time.time() - t_sph)

    # # --- show & color map (kept minimal; no scalar bar by default) ---
    # disp = Show(sph, render_view, "UniformGridRepresentation")
    # ColorBy(disp, ("POINTS", "phase_change_counter"))
    # disp.SetRepresentationType("Point Gaussian")
    # disp.GaussianRadius = 4e-06
    # disp.RescaleTransferFunctionToDataRange(True, False)
    # phase_change_counterLUT = GetColorTransferFunction("phase_change_counter")
    # HideScalarBarIfNotNeeded(phase_change_counterLUT, render_view)
    # _ = GetOpacityTransferFunction("phase_change_counter")
    # _ = GetTransferFunction2D("phase_change_counter")

    logger.info("[sph] prepare_sph_interpolator FINISHED (total Δt=%.3fs).", time.time() - t_all)
    return sph


# ----------------------------
# ParaView shell-friendly `main()` (no CLI args)
# ----------------------------

def main() -> None:
    logger.info("[main] START")
    cfg = get_config()
    sim_path = str(cfg.paths.sim_path)
    logger.info("[main] sim_path=%s", sim_path)

    reset_session()
    iteration_number = 111469
    path_to_solid_phase = f'/Users/ioandanielcraciun/Python-Projects/sph2img/simulations/mhpc3d_200W_Ti64_Ar-3Y/output/out_phase_1_SOLID_rank_0_413.vtk'
    path_to_liquid_phase = f'/Users/ioandanielcraciun/Python-Projects/sph2img/simulations/mhpc3d_200W_Ti64_Ar-3Y/output/out_phase_2_LIQUID_rank_0_413.vtk'
    path_to_gas_phase = f'/Users/ioandanielcraciun/Python-Projects/sph2img/simulations/mhpc3d_200W_Ti64_Ar-3Y/output/out_phase_3_GAS_rank_0_413.vtk'
    path_to_wall_phase = f'/Users/ioandanielcraciun/Python-Projects/sph2img/simulations/mhpc3d_200W_Ti64_Ar-3Y/output/out_phase_4_WALL_rank_0_413.vtk'

    logger.info("[main] iteration=%s", iteration_number)
    logger.info("[main.paths] solid=%s", path_to_solid_phase)
    logger.info("[main.paths] liquid=%s", path_to_liquid_phase)
    logger.info("[main.paths] gas=%s", path_to_gas_phase)
    logger.info("[main.paths] wall=%s", path_to_wall_phase)

    _sph = prepare_sph_interpolator(
        iteration_number,
        sim_path,
        path_to_solid_phase,
        path_to_liquid_phase,
        path_to_gas_phase,
        path_to_wall_phase
    )
    logger.info("[main] prepare_phase_interpolator finished for %s", sim_path)
    logger.info("[main] END")


# Auto-run in PV shell/batch if paraview.testing=True (or env override)
#
# run_main_if_testing(main)
