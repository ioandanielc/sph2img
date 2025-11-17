#!/usr/bin/env python3
from __future__ import annotations

import sys
import argparse
import time
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sph2img.pvshim import enable_stubs; enable_stubs()

from sph2img.utils.pvlog import get_logger
from sph2img.utils.crawl_iterations import crawl_iterations
from sph2img.milestones.milestones_solidified import build_solidified_map_online
from sph2img.milestones.milestones_melt_laser_positions import build_iteration_laser_x_online
from sph2img.milestones.milestones_melt_largest_delta import build_iteration_largest_online, DEFAULT_EPS
from sph2img.stages.sph_creator_single import prepare_sph_interpolator
from sph2img.stages.slice_creator import create_and_colour_slices
from sph2img.stages.slice_mover import move_slices_origin
from sph2img.stages.instant_module import prepare_paths_from_sim_path, clean_reset_paraview, deploy_and_die
from sph2img.stages.screencapture_slice_composite import screenshot_set
from paraview.simple import Render  # type: ignore
import importlib.util


def load_get_logger(logger_path: str):
    path = Path(logger_path).expanduser().resolve()
    spec = importlib.util.spec_from_file_location("external_pvlog", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.get_logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SPH2IMG single-mode (CLI-only).", allow_abbrev=False)
    parser.add_argument("--python-bin", required=True)
    parser.add_argument("--sim-path",  type=Path, required=True)
    parser.add_argument("--out-dir",   type=Path, required=True)
    parser.add_argument("--mode",      choices=["solid", "laser", "largest"], required=True)
    parser.add_argument("--run-name",  type=str, required=True)
    parser.add_argument("--logger-path",   type=Path, required=True)

    parser.add_argument("--eps", type=float, default=float(DEFAULT_EPS))
    parser.add_argument("--x-start", type=float, default=None)
    parser.add_argument("--x-end",   type=float, default=None)
    parser.add_argument("--solid-cuts", type=int, default=30)
    parser.add_argument("--front-w", type=int, default=256)
    parser.add_argument("--front-h", type=int, default=256)
    parser.add_argument("--side-w",  type=int, default=256)
    parser.add_argument("--side-h",  type=int, default=256)
    parser.add_argument("--top-w",   type=int, default=256)
    parser.add_argument("--top-h",   type=int, default=256)
    parser.add_argument("--x-side-offset", type=float, default=0.0)
    parser.add_argument("--empty-out", action="store_true")
    parser.add_argument("--post-delete", action="store_true")
    parser.add_argument("--single-iter", type=int, default=-1,
                        help="If != -1, process only this iteration. Default -1 = all.")
    parser.add_argument("-c", "--config", help=argparse.SUPPRESS)
    return parser.parse_args()


def restrict_to_single_iter(liq_idx, liq_iters, liq_paths, wanted: int):
    if wanted == -1:
        return liq_idx, liq_iters, liq_paths
    try:
        pos = liq_iters.index(wanted)
    except ValueError:
        raise SystemExit(f"[ERROR] iteration {wanted} not found.")
    return [liq_idx[pos]], [liq_iters[pos]], [liq_paths[pos]]


def deploy(args: argparse.Namespace) -> Path:
    log = get_logger("SPH2IMG", level="INFO")

    t0 = time.time()
    log.info("=== run_pipeline_full_mode.deploy START ===")
    log.info(f"[python] intended={args.python_bin} running={sys.executable}")

    sim_path_str = str(args.sim_path)
    out_folder = Path(args.out_dir).resolve()
    out_folder.mkdir(parents=True, exist_ok=True)

    mode = args.mode
    run_name = args.run_name

    if mode == "solid" and args.solid_cuts <= 0:
        raise SystemExit("--solid-cuts must be > 0")
    for k in ("front_w", "front_h", "side_w", "side_h", "top_w", "top_h"):
        if getattr(args, k) <= 0:
            flag = k.replace("_", "-")
            raise SystemExit(f"--{flag} must be > 0")

    liq_idx, liq_iters, _o2i, liq_paths, _i2p = crawl_iterations(sim_path_str)
    log.info(f"[crawl] found {len(liq_idx)}")
    if not liq_idx and not args.empty_out:
        log.warning("[crawl] none found; set --empty-out to suppress downstream issues")

    liq_idx, liq_iters, liq_paths = restrict_to_single_iter(liq_idx, liq_iters, liq_paths, args.single_iter)

    if mode == "solid":
        if liq_idx:
            i_start, i_end = 0, len(liq_idx) - 1
            if args.x_start is None or args.x_end is None:
                x_start = build_iteration_largest_online(sim_path_str, liq_paths[i_start], liq_iters[i_start])
                x_end   = build_iteration_largest_online(sim_path_str, liq_paths[i_end],   liq_iters[i_end])
            else:
                x_start, x_end = args.x_start, args.x_end

            cuts_pos, _lin = build_solidified_map_online(liq_iters[-1], x_start, x_end, args.solid_cuts)

            solid_path, liquid_path, gas_path, wall_path = prepare_paths_from_sim_path(sim_path_str, liq_iters[-1])
            clean_reset_paraview()
            _sph = prepare_sph_interpolator(liq_iters[-1], sim_path_str, solid_path, liquid_path, gas_path, wall_path)
            create_and_colour_slices(); Render()

            for entry_no, cut in enumerate(cuts_pos):
                move_slices_origin([cut, 0.0, 0.0]); Render()
                screenshot_set(
                    run_name=run_name, entry_no=entry_no, out_dir=out_folder,
                    front_W=args.front_w, front_H=args.front_h,
                    side_W=args.side_w,   side_H=args.side_h,
                    top_W=args.top_w,     top_H=args.top_h,
                    x_side_offset=args.x_side_offset, testing_folder=False,
                )

    elif mode in ("laser", "largest"):
        for snapshot_index, iteration in enumerate(liq_iters):
            if mode == "largest":
                x_pos = build_iteration_largest_online(sim_path_str, liq_paths[snapshot_index], iteration, args.eps)
            else:
                x_pos = build_iteration_laser_x_online(sim_path_str, iteration)

            solid_path, liquid_path, gas_path, wall_path = prepare_paths_from_sim_path(sim_path_str, iteration)
            deploy_and_die(
                run_name=run_name,
                iteration_number=iteration,
                snapshot_index=snapshot_index,
                path_to_simulation=sim_path_str,
                path_to_solid_phase=solid_path,
                path_to_liquid_phase=liq_paths[snapshot_index],
                path_to_gas_phase=gas_path,
                path_to_wall_phase=wall_path,
                path_to_output_dir=out_folder,
                x_position=x_pos,
                delete_vtk=False,
            )

    if args.post_delete:
        shutil.rmtree(out_folder)
        log.info(f"[cleanup] deleted {out_folder}")

    log.info(f"=== FINISHED in {time.time()-t0:.3f}s ===")
    return out_folder


def main():
    args = parse_args()
    out_dir = deploy(args)


if __name__ == "__main__":
    sys.exit(main())
