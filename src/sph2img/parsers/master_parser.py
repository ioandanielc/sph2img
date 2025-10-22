from __future__ import annotations

# --- path bootstrap: make `sph2img` importable even when run as a script -----
import sys

from sph2img.utils.pvlog import get_logger
from sph2img.config import get_config
from sph2img.parsers import parser_utils, config_parser, data_files_parser, vtk_iterations_parser

logger = get_logger(__name__)

__all__ = ["run"]


def run(path_to_simulation: str):
    logger.info("Master parser started…")

    (
        laser_power,
        laser_velocity,
        melt_material,
        melt_density,
        domain,
        smoothing_length,
        resolution,
        domain_min,
        domain_max,
    ) = config_parser.extract_json_data(path_to_simulation)

    (
        dt_list,
        iter_list,
        pos_bounds_list,
        time_list,
    ) = data_files_parser.get_data_files(path_to_simulation)

    vtk_iterations = vtk_iterations_parser.get_vtk_iterations(path_to_simulation)

    # Casts (keep existing semantics)
    laser_power = float(laser_power)
    laser_velocity = parser_utils.list_of_str_to(laser_velocity, float)
    melt_density = float(melt_density)

    dt_list = parser_utils.list_of_str_to(dt_list, float)
    iter_list = parser_utils.list_of_str_to(iter_list, int)
    pos_bounds_list = parser_utils.list_of_lists_of_str_to(pos_bounds_list, float)
    time_list = parser_utils.list_of_str_to(time_list, float)
    vtk_iterations = parser_utils.list_of_str_to(vtk_iterations, int)

    # Laser positions at each VTK iteration: t * v (component-wise)
    laser_positions_at_vtk_iterations = [
        [time_list[vi] * laser_velocity[0],
         time_list[vi] * laser_velocity[1],
         time_list[vi] * laser_velocity[2]]
        for vi in vtk_iterations
    ]

    return (
        laser_power, laser_velocity,
        melt_material, melt_density,
        dt_list, iter_list, pos_bounds_list, time_list,
        vtk_iterations,
        laser_positions_at_vtk_iterations,
        domain, smoothing_length, resolution,
        domain_min, domain_max,
    )


if __name__ == "__main__":
    # No basicConfig here; pvlog sets handlers to avoid duplicate logs.
    # Optional CLI override: `python master_parser.py /path/to/sim`
    if len(sys.argv) > 1:
        sim_path = sys.argv[1]
    else:
        cfg = get_config()
        sim_path = str(cfg.paths.sim_path)

    (
        laser_power, laser_velocity,
        melt_material, melt_density,
        dt_list, iter_list, pos_bounds_list, time_list,
        vtk_iterations,
        laser_positions_at_vtk_iterations,
        domain, smoothing_length, resolution,
        domain_min, domain_max,
    ) = run(sim_path)

    # Save small artifacts for quick inspection under ../../../testing
    out_parent = cfg.paths.out_dir / "master_parser_testing"
    parser_utils.save_variable_json(laser_power, out_parent, "laser_power")
    parser_utils.save_variable_json(laser_velocity, out_parent, "laser_velocity")
    parser_utils.save_variable_json(melt_material, out_parent, "melt_material")
    parser_utils.save_variable_json(melt_density, out_parent, "melt_density")
    parser_utils.save_variable_json(domain, out_parent, "domain")
    parser_utils.save_variable_json(smoothing_length, out_parent, "smoothing_length")
    parser_utils.save_variable_json(resolution, out_parent, "resolution")
    parser_utils.save_variable_json(dt_list, out_parent, "dt_list")
    parser_utils.save_variable_json(iter_list, out_parent, "iter_list")
    parser_utils.save_variable_json(pos_bounds_list, out_parent, "pos_bounds_list")
    parser_utils.save_variable_json(time_list, out_parent, "time_list")
    parser_utils.save_variable_json(vtk_iterations, out_parent, "vtk_iterations")
    parser_utils.save_variable_json(laser_positions_at_vtk_iterations, out_parent, "laser_positions_at_vtk_iterations")
    parser_utils.save_variable_json(domain_min, out_parent, "domain_min")
    parser_utils.save_variable_json(domain_max, out_parent, "domain_max")

    logger.info("Master parser finished. Artifacts written to %s", out_parent)
