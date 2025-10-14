# --- path bootstrap: make `sph2img` importable even when run as a script -----
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]   # repo root (sph2img/)
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
# ---------------------------------------------------------------------------

import re
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
    logger.info("Resetting ParaView session…")
    pxm = servermanager.ProxyManager()
    pxm.UnRegisterProxies()
    del pxm
    Disconnect()
    Connect()
    logger.info("Session reset complete.")


# ----------------------------
# data discovery
# ----------------------------

_PHASE_RE = re.compile(r"^out_phase_(\d+)_(\w+)_rank_0_(\d+)\.vtk$")


def collect_phase_files(path_to_simulation: str) -> Dict[str, List[str]]:
    """
    Collect all VTK files under <sim>/output and group them by "<phase_num>_<material>".
    Lists are sorted by timestep ascending.

    Returns:
        dict like {"1_SOLID": [paths...], "2_LIQUID": [...], "3_GAS": [...], "4_WALL": [...]}
    """
    out_dir = Path(path_to_simulation) / "output"
    if not out_dir.is_dir():
        raise NotADirectoryError(f"Missing output dir: {out_dir}")

    phases: Dict[str, List[Path]] = {}
    for f in out_dir.glob("out_phase_*_rank_0_*.vtk"):
        m = _PHASE_RE.match(f.name)
        if not m:
            continue
        phase_num, material, _ts = m.groups()
        key = f"{phase_num}_{material}"
        phases.setdefault(key, []).append(f)

    # sort by numeric timestep
    for key, files in phases.items():
        files.sort(key=lambda p: int(_PHASE_RE.match(p.name).group(3)))
        phases[key] = [str(p) for p in files]

    if not phases:
        logger.warning("No out_phase_* VTK files found in %s", out_dir)
    else:
        logger.info("Collected phase files:")
        for k in sorted(phases):
            logger.info(
                "  %-10s -> %d files (range: %s .. %s)",
                k,
                len(phases[k]),
                Path(phases[k][0]).name if phases[k] else "n/a",
                Path(phases[k][-1]).name if phases[k] else "n/a",
            )
    return phases


def create_readers(phases: Dict[str, List[str]]):
    """Create a LegacyVTKReader for each phase key and register them in the pipeline."""
    readers = {}
    for phase_key, files in phases.items():
        if not files:
            continue
        readers[phase_key] = LegacyVTKReader(
            registrationName=f"out_phase_{phase_key}.vtk",
            FileNames=files,
        )
        logger.info("Reader created for phase %s (%d files)", phase_key, len(files))
    return readers


# ----------------------------
# pipeline
# ----------------------------

def prepare_sph_interpolator(path_to_simulation: str):
    """
    Build a phase-agnostic SPH interpolator combining SOLID/LIQUID/GAS/WALL, and
    return the created SPHVolumeInterpolator proxy. Also prepares the view.

    Returns:
        SPHVolumeInterpolator proxy
    """
    render_view = GetActiveViewOrCreate(pv_view_name())   # <-- use config default view
    render_view.OrientationAxesVisibility = 0

    logger.info("Parsing simulation config: %s", path_to_simulation)
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

    logger.info("Creating readers for phases…")
    phases = collect_phase_files(path_to_simulation)
    try:
        solid_phase = create_readers(phases)["1_SOLID"]
        liquid_phase = create_readers(phases)["2_LIQUID"]
        gas_phase = create_readers(phases)["3_GAS"]
        wall_phase = create_readers(phases)["4_WALL"]
    except KeyError as e:
        raise RuntimeError(
            f"Missing expected phase in outputs: {e}. Have keys: {sorted(phases.keys())}"
        ) from e

    # --- SOLID branch calculators ---
    calc_solid_is_solid = Calculator(registrationName="Calculator_solid_is_solid", Input=solid_phase)
    calc_solid_is_solid.ResultArrayName = "is_solid";   calc_solid_is_solid.Function = "1"

    calc_solid_is_liquid = Calculator(registrationName="Calculator_solid_is_liquid", Input=calc_solid_is_solid)
    calc_solid_is_liquid.ResultArrayName = "is_liquid"; calc_solid_is_liquid.Function = "0"

    calc_solid_is_gas = Calculator(registrationName="Calculator_solid_is_gas", Input=calc_solid_is_liquid)
    calc_solid_is_gas.ResultArrayName = "is_gas";       calc_solid_is_gas.Function = "0"

    calc_solid_is_wall = Calculator(registrationName="Calculator_solid_is_wall", Input=calc_solid_is_gas)
    calc_solid_is_wall.ResultArrayName = "is_wall";     calc_solid_is_wall.Function = "0"

    calc_solid_aggregate = Calculator(registrationName="Calculator_solid_aggregate_state", Input=calc_solid_is_wall)
    calc_solid_aggregate.ResultArrayName = "aggregate_state"; calc_solid_aggregate.Function = "0"

    calc_solid_pcc = Calculator(registrationName="Calculator_solid_phase_change_counter", Input=calc_solid_aggregate)
    calc_solid_pcc.ResultArrayName = "phase_change_counter";  calc_solid_pcc.Function = "Tags_3_0"

    # --- LIQUID branch calculators ---
    calc_liquid_is_solid = Calculator(registrationName="Calculator_liquid_is_solid", Input=liquid_phase)
    calc_liquid_is_solid.ResultArrayName = "is_solid";  calc_liquid_is_solid.Function = "0"

    calc_liquid_is_liquid = Calculator(registrationName="Calculator_liquid_is_liquid", Input=calc_liquid_is_solid)
    calc_liquid_is_liquid.ResultArrayName = "is_liquid"; calc_liquid_is_liquid.Function = "1"

    calc_liquid_is_gas = Calculator(registrationName="Calculator_liquid_is_gas", Input=calc_liquid_is_liquid)
    calc_liquid_is_gas.ResultArrayName = "is_gas";      calc_liquid_is_gas.Function = "0"

    calc_liquid_is_wall = Calculator(registrationName="Calculator_liquid_is_wall", Input=calc_liquid_is_gas)
    calc_liquid_is_wall.ResultArrayName = "is_wall";    calc_liquid_is_wall.Function = "0"

    calc_liquid_aggregate = Calculator(registrationName="Calculator_liquid_aggregate_state", Input=calc_liquid_is_wall)
    calc_liquid_aggregate.ResultArrayName = "aggregate_state"; calc_liquid_aggregate.Function = "1"

    calc_liquid_pcc = Calculator(registrationName="Calculator_liquid_phase_change_counter", Input=calc_liquid_aggregate)
    calc_liquid_pcc.ResultArrayName = "phase_change_counter";  calc_liquid_pcc.Function = "Tags_1_0"

    # --- GAS branch calculators ---
    calc_gas_is_solid = Calculator(registrationName="Calculator_gas_is_solid", Input=gas_phase)
    calc_gas_is_solid.ResultArrayName = "is_solid";     calc_gas_is_solid.Function = "0"

    calc_gas_is_liquid = Calculator(registrationName="Calculator_gas_is_liquid", Input=calc_gas_is_solid)
    calc_gas_is_liquid.ResultArrayName = "is_liquid";   calc_gas_is_liquid.Function = "0"

    calc_gas_is_gas = Calculator(registrationName="Calculator_gas_is_gas", Input=calc_gas_is_liquid)
    calc_gas_is_gas.ResultArrayName = "is_gas";         calc_gas_is_gas.Function = "1"

    calc_gas_is_wall = Calculator(registrationName="Calculator_gas_is_wall", Input=calc_gas_is_gas)
    calc_gas_is_wall.ResultArrayName = "is_wall";       calc_gas_is_wall.Function = "0"

    calc_gas_aggregate = Calculator(registrationName="Calculator_gas_aggregate_state", Input=calc_gas_is_wall)
    calc_gas_aggregate.ResultArrayName = "aggregate_state"; calc_gas_aggregate.Function = "2"

    calc_gas_pcc = Calculator(registrationName="Calculator_gas_phase_change_counter", Input=calc_gas_aggregate)
    calc_gas_pcc.ResultArrayName = "phase_change_counter";    calc_gas_pcc.Function = "0"

    # --- WALL branch calculators ---
    calc_wall_is_wall_a = Calculator(registrationName="Calculator_wall_is_wall", Input=wall_phase)
    calc_wall_is_wall_a.ResultArrayName = "is_solid";   calc_wall_is_wall_a.Function = "0"

    calc_wall_is_liquid = Calculator(registrationName="Calculator_wall_is_liquid", Input=calc_wall_is_wall_a)
    calc_wall_is_liquid.ResultArrayName = "is_liquid";  calc_wall_is_liquid.Function = "0"

    calc_wall_is_gas = Calculator(registrationName="Calculator_wall_is_gas", Input=calc_wall_is_liquid)
    calc_wall_is_gas.ResultArrayName = "is_gas";        calc_wall_is_gas.Function = "0"

    calc_wall_is_wall_b = Calculator(registrationName="Calculator_wall_is_wall", Input=calc_wall_is_gas)
    calc_wall_is_wall_b.ResultArrayName = "is_wall";    calc_wall_is_wall_b.Function = "1"

    calc_wall_aggregate = Calculator(registrationName="Calculator_wall_aggregate_state", Input=calc_wall_is_wall_b)
    calc_wall_aggregate.ResultArrayName = "aggregate_state";  calc_wall_aggregate.Function = "3"

    calc_wall_pcc = Calculator(registrationName="Calculator_wall_phase_change_counter", Input=calc_wall_aggregate)
    calc_wall_pcc.ResultArrayName = "phase_change_counter";    calc_wall_pcc.Function = "0"

    # --- append + derived fields ---
    logger.info("Appending phases and computing derived arrays…")
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

    # --- SPH volume interpolator ---
    logger.info("Creating SPHVolumeInterpolator for combined phases…")
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
        "ColorGradient_0_0","ColorGradient_10_0","ColorGradient_11_0","ColorGradient_1_0","ColorGradient_2_0",
        "ColorGradient_3_0","ColorGradient_4_0","ColorGradient_5_0","ColorGradient_6_0","ColorGradient_7_0",
        "ColorGradient_8_0","ColorGradient_9_0","Conservatives_0_0","Conservatives_1_0","Conservatives_2_0",
        "Conservatives_3_0","Conservatives_4_0","MaterialVariables_0_0","MaterialVariables_1_0",
        "MaterialVariables_2_0","MaterialVariables_3_0","MaterialVariables_4_0","MaterialVariables_5_0",
        "Primitives_0_0","Primitives_10_0","Primitives_1_0","Primitives_2_0","Primitives_3_0","Primitives_4_0",
        "Primitives_5_0","Primitives_6_0","Primitives_7_0","Primitives_8_0","Primitives_9_0",
        "Tags_0_0","Tags_1_0","TimeDerivatives_0_0","attr7","attr8","domain",
    ]
    sph.ComputeShepardSum = 1

    # --- show & color map (kept minimal; no scalar bar by default) ---
    # disp = Show(sph, render_view, "UniformGridRepresentation")
    # logger.info("X1.")
    #
    # ColorBy(disp, ("POINTS", "phase_change_counter"))
    # disp.SetRepresentationType("Point Gaussian")
    # disp.GaussianRadius = 3e-06
    # disp.RescaleTransferFunctionToDataRange(True, False)
    #
    # phase_change_counterLUT = GetColorTransferFunction("phase_change_counter")
    # HideScalarBarIfNotNeeded(phase_change_counterLUT, render_view)
    # _ = GetOpacityTransferFunction("phase_change_counter")
    # _ = GetTransferFunction2D("phase_change_counter")
    #
    # render_view.ResetCamera(False, 0.9)
    #
    # # sync animation (kept as in your original)
    # anim = GetAnimationScene()
    # anim.AnimationTime = 5.0
    # anim.UpdateAnimationUsingDataTimeSteps()

    logger.info("SPH interpolator ready.")
    return sph


# ----------------------------
# ParaView shell-friendly `main()` (no CLI args)
# ----------------------------

def main() -> None:
    cfg = get_config()
    sim_path = str(cfg.paths.sim_path)
    reset_session()
    _sph = prepare_sph_interpolator(sim_path)
    logger.info("prepare_phase_interpolator.main() finished for %s", sim_path)


# Auto-run in PV shell/batch if paraview.testing=True (or env override)
# run_main_if_testing(main)
