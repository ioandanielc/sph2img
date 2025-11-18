#!/usr/bin/env python3
import sys, json, subprocess
from pathlib import Path

def main():
    if len(sys.argv) != 2:
        print(f"Usage: {Path(__file__).name} /path/to/new_config.json", file=sys.stderr)
        sys.exit(2)

    cfg_path = Path(sys.argv[1]).expanduser().resolve()
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    if "sph2img" not in cfg or "out_dir" not in cfg["sph2img"]:
        print("[ERR] config.sph2img.out_dir missing", file=sys.stderr)
        sys.exit(2)

    if "png_sorter" not in cfg:
        print("[ERR] config.png_sorter missing", file=sys.stderr)
        sys.exit(2)
    sc = cfg["png_sorter"]

    # also require 'sim' so we can grab sim/monitor
    required = (
        "sorter_script",
        "result_directory",
        "unaccounted_file",
        "stable_file",
        "unstable_file",
        "sim",
    )
    missing = [k for k in required if k not in sc]
    if missing:
        print(f"[ERR] missing in config.png_sorter: {', '.join(missing)}", file=sys.stderr)
        sys.exit(2)

    sorter_script    = str(Path(sc["sorter_script"]).expanduser().resolve())
    images_path      = str(Path(cfg["sph2img"]["out_dir"]).expanduser().resolve())
    result_directory = str(Path(sc["result_directory"]).expanduser().resolve())
    unaccounted_file = str(Path(sc["unaccounted_file"]).expanduser().resolve())
    stable_file      = str(Path(sc["stable_file"]).expanduser().resolve())
    unstable_file    = str(Path(sc["unstable_file"]).expanduser().resolve())

    # NEW: sim/monitor
    sim_root      = Path(sc["sim"]).expanduser().resolve()
    monitor_path  = str(sim_root / "monitor")

    cmd = [
        sorter_script,
        "--images-path",      images_path,
        "--result-directory", result_directory,
        "--unaccounted-file", unaccounted_file,
        "--stable-file",      stable_file,
        "--unstable-file",    unstable_file,
        "--monitor-path",     monitor_path,
    ]

    print("[CMD]", " ".join(cmd), flush=True)

    try:
        res = subprocess.run(cmd, check=True)
        sys.exit(res.returncode)
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)

if __name__ == "__main__":
    sys.exit(main())
