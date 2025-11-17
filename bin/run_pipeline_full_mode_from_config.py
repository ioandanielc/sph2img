#!/usr/bin/env python3
import sys, json, argparse, subprocess
from pathlib import Path
import subprocess

REQ = [
    "python_bin","script_path","sim_path","out_dir","mode","run_name",
    "eps","x_start","x_end","solid_cuts",
    "front_w","front_h","side_w","side_h","top_w","top_h",
    "x_side_offset","empty_out","post_delete"
]

def parse_args():
    ap = argparse.ArgumentParser(description="Config wrapper for SPH2IMG runner (supports --single-iter).")
    ap.add_argument("config_path", help="Path to new_config.json")
    ap.add_argument("--single-iter", type=int, default=-1,
                    help="If != -1, process only this iteration; otherwise all.")
    return ap.parse_args()

def main():
    args = parse_args()
    cfg_path = Path(args.config_path).expanduser().resolve()
    try:
        big = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[ERR] cannot read {cfg_path}: {e}", file=sys.stderr); sys.exit(1)

    if "sph2img" not in big or not isinstance(big["sph2img"], dict):
        print("[ERR] Missing 'sph2img' section.", file=sys.stderr); sys.exit(1)
    cfg = big["sph2img"]

    missing = [k for k in REQ if k not in cfg]
    if missing:
        print(f"[ERR] Missing in sph2img: {', '.join(missing)}", file=sys.stderr); sys.exit(1)

    cmd = [
        str(cfg["python_bin"]),
        str(cfg["script_path"]),
        "--python-bin", str(cfg["python_bin"]),
        "--sim-path",   str(cfg["sim_path"]),
        "--out-dir",    str(cfg["out_dir"]),
        "--mode",       str(cfg["mode"]),
        "--run-name",   str(cfg["run_name"]),
        "--eps",           str(cfg["eps"]),
        "--x-start",       str(cfg["x_start"]),
        "--x-end",         str(cfg["x_end"]),
        "--solid-cuts",    str(int(cfg["solid_cuts"])),
        "--front-w",       str(int(cfg["front_w"])),
        "--front-h",       str(int(cfg["front_h"])),
        "--side-w",        str(int(cfg["side_w"])),
        "--side-h",        str(int(cfg["side_h"])),
        "--top-w",         str(int(cfg["top_w"])),
        "--top-h",         str(int(cfg["top_h"])),
        "--x-side-offset", str(cfg["x_side_offset"]),
        "--logger-path", str(big["logger_path"]),
    ]
    if bool(cfg["empty_out"]):
        cmd.append("--empty-out")
    if bool(cfg["post_delete"]):
        cmd.append("--post-delete")
    if args.single_iter != -1:
        cmd += ["--single-iter", str(args.single_iter)]

    print("[CMD]", " ".join(cmd), flush=True)
    try:
        res = subprocess.run(cmd, check=True)
        sys.exit(res.returncode)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)

if __name__ == "__main__":
    sys.exit(main())
