#!/usr/bin/env python3
import sys
import json
import argparse
from pathlib import Path

# make package importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from sph2img.utils.pvlog import get_logger
from sph2img.stages.gif_maker import gif_creator  # one-arg signature: gif_creator(out_dir)

log = get_logger(__name__)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create GIFs using the 'gif' section in config.")
    parser.add_argument("config_path", help="Path to JSON config containing a 'gif' section")
    return parser.parse_args()

def main():
    args = parse_args()
    cfg_path = Path(args.config_path)

    with cfg_path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)

    if "gif" not in cfg or not isinstance(cfg["gif"], dict):
        print("[ERR] config must contain a 'gif' object with 'input_dir' and 'output_dir'", file=sys.stderr)
        sys.exit(2)

    gif_cfg = cfg["gif"]
    input_dir = Path(gif_cfg["input_dir"]).expanduser().resolve()
    output_dir = Path(gif_cfg["output_dir"]).expanduser().resolve()

    if not input_dir.is_dir():
        print(f"[ERR] gif.input_dir does not exist or is not a directory: {input_dir}", file=sys.stderr)
        sys.exit(3)

    if output_dir != input_dir:
        log.info(f"[gif] Note: gif_creator writes into its argument directory. "
                 f"Ignoring separate output_dir={output_dir} and writing into input_dir={input_dir}.")

    log.info(f"[gif] input={input_dir}")
    gif_creator(input_dir)
    log.info("[gif] done")

if __name__ == "__main__":
    sys.exit(main())
