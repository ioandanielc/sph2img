# src/sph2img/parsers/data_files_parser_v2.py
from __future__ import annotations

# --- path bootstrap: make `sph2img` importable even when run as a script -----
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]   # repo root (sph2img/)
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
# ---------------------------------------------------------------------------

import logging
from typing import List, Tuple

from sph2img.config import get_config
from sph2img.utils.pvlog import get_logger
from sph2img.parsers import parser_utils  # keep API but import cleanly

logger = get_logger(__name__)

__all__ = [
    "get_data_files_paths",
    "get_data_files",
]

# Required files inside the simulation's `monitor/` directory
REQUIRED_MONITOR_FILES = ("dt.dat", "iter.dat", "position-bounds_melt.dat", "time.dat")


def get_data_files_paths(path_to_simulation: str) -> List[str]:
    """Locate required monitor files under the simulation's ``monitor/`` folder.

    Expected layout::

        <path_to_simulation>/
            monitor/
                dt.dat
                iter.dat
                position-bounds_melt.dat
                time.dat

    Raises:
        FileNotFoundError: if ``monitor`` is missing or any required ``*.dat`` is missing.
        RuntimeError: if more than one ``monitor`` directory is found.
    """
    sim_dir = Path(path_to_simulation).expanduser().resolve()
    logger.info("Data Files Parser running (scan: %s)", sim_dir)

    if not sim_dir.exists():
        logger.error("Simulation directory not found: %s", sim_dir)
        raise FileNotFoundError(f"Simulation directory not found: {sim_dir}")
    if not sim_dir.is_dir():
        logger.error("Not a directory: %s", sim_dir)
        raise NotADirectoryError(f"Not a directory: {sim_dir}")

    monitor_dirs = [p for p in sim_dir.iterdir() if p.is_dir() and p.name == "monitor"]

    if len(monitor_dirs) == 0:
        logger.error("No 'monitor' directory in folder %s", sim_dir)
        raise FileNotFoundError(f"No 'monitor' directory in folder {sim_dir}")
    if len(monitor_dirs) > 1:
        logger.error("More than one 'monitor' directory in folder %s", sim_dir)
        raise RuntimeError(f"More than one 'monitor' directory in folder {sim_dir}")

    monitor_dir = monitor_dirs[0]

    # Ensure all required files exist exactly once
    paths: List[str] = []
    missing: List[str] = []

    for fname in REQUIRED_MONITOR_FILES:
        fpath = monitor_dir / fname
        if not fpath.exists() or not fpath.is_file():
            missing.append(fname)
        else:
            paths.append(str(fpath))

    if missing:
        logger.error("Missing required files under %s: %s", monitor_dir, ", ".join(missing))
        raise FileNotFoundError(f"Missing required files under {monitor_dir}: {', '.join(missing)}")

    logger.info("Data files detected:\n\t%s", "\n\t".join(paths))
    return paths


def get_data_files(path_to_simulation: str) -> Tuple[List[str], List[str], List[List[float]], List[str]]:
    """Read and return the monitor data.

    Returns:
        (dt_list, iter_list, pos_bounds_list, time_list)

    Note:
        Values are returned as strings (except `pos_bounds_list` which is parsed as floats)
        to match existing behavior. Convert at callsite if needed.
    """
    paths = get_data_files_paths(path_to_simulation)

    # The order in REQUIRED_MONITOR_FILES is the semantic order we return
    dt_path, iter_path, pos_bounds_path, time_path = paths

    dt_list = parser_utils.load_file(dt_path)
    iter_list = parser_utils.load_file(iter_path)
    pos_bounds_list = parser_utils.csv_to_lists(pos_bounds_path)
    time_list = parser_utils.load_file(time_path)

    logger.info(
        "Loaded monitor data: dt=%d | iter=%d | pos_bounds=%d | time=%d",
        len(dt_list), len(iter_list), len(pos_bounds_list), len(time_list)
    )
    return dt_list, iter_list, pos_bounds_list, time_list


if __name__ == "__main__":
    # Optional CLI override: `python data_files_parser_v2.py /path/to/sim`
    if len(sys.argv) > 1:
        sim_path = sys.argv[1]
    else:
        cfg = get_config()
        sim_path = str(cfg.paths.sim_path)

    logger.info("[TEST] Using simulation path: %s", sim_path)

    try:
        dt, iters, posb, times = get_data_files(sim_path)
        # Preview heads for sanity
        head = lambda xs, n=3: xs[:n]
        logger.info(
            "[TEST] Samples => dt:%s | iter:%s | pos_bounds(first row):%s | time:%s",
            head(dt), head(iters), (posb[0] if posb else []), head(times)
        )
        print("OK — monitor files parsed successfully.")
    except Exception as e:
        logger.exception("[TEST] Failed to parse monitor files: %s", e)
        raise
