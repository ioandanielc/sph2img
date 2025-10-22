# src/sph2img/utils/power_vx_from_json.py
from __future__ import annotations

import sys
from pathlib import Path

import json
from pathlib import Path
from typing import Tuple
import os

from sph2img.config import get_config
from sph2img.utils.pvlog import get_logger

log = get_logger(__name__)


def last_folder(path: str) -> str:
    """
    Return the final directory name from a path string.
    - Trims surrounding quotes/whitespace
    - Works with or without trailing slashes
    """
    cleaned = path.strip().strip('"').strip("'")
    return Path(cleaned).name


def dot_to_p_float(s: str) -> str:
    """Replace '.' with 'p' in a float string; if no ., return unchanged."""
    return s.replace('.', 'p') if '.' in s else s


def extract_power_and_vx(simulation_path: str | Path) -> Tuple[str, str]:
    """
    Read an AERSPH-style JSON file and return (laser_power, vx) as strings.

    Expects:
      lasers:
        <any_name>:
          physics:
            power_magnitude_expression: "<power>"
            motion:
              velocity: ["<vx>", "<vy>", "<vz>"]  # strings or numbers

    Args:
        json_path: filesystem path to the JSON file.

    Returns:
        (power_str, vx_str): both values as strings.

    Raises:
        FileNotFoundError, json.JSONDecodeError, KeyError, ValueError
    """
    json_name = last_folder(str(simulation_path)) + '.json'
    p = os.path.join(str(simulation_path), json_name)
    p = Path(p)

    if not p.is_file():
        raise FileNotFoundError(f"No such file: {p}")

    data = json.loads(p.read_text())

    lasers = data.get("lasers")
    if not isinstance(lasers, dict) or not lasers:
        raise KeyError("Missing or empty 'lasers' object in JSON.")

    # take the first laser definition
    first_laser = next(iter(lasers.values()))
    physics = first_laser.get("physics") or {}
    motion = physics.get("motion") or {}

    power = physics.get("power_magnitude_expression")
    vel = motion.get("velocity")

    if power is None:
        raise KeyError("Missing 'physics.power_magnitude_expression'.")
    if not (isinstance(vel, (list, tuple)) and len(vel) >= 1):
        raise KeyError("Missing or invalid 'physics.motion.velocity' (expected list with x component).")

    vx = vel[0]

    # Ensure both are strings
    power_str = power if isinstance(power, str) else str(power)
    vx_str = vx if isinstance(vx, str) else str(vx)

    # Basic sanity check: non-empty strings
    if power_str.strip() == "" or vx_str.strip() == "":
        raise ValueError("Extracted power or vx is empty.")

    return dot_to_p_float(power_str), dot_to_p_float(vx_str)


if __name__ == "__main__":
    # Default to config's sim path; optional CLI override
    if len(sys.argv) > 1:
        sim_path = sys.argv[1]
    else:
        sim_path = str(get_config().paths.sim_path)

    try:
        power_s, vx_s = extract_power_and_vx(sim_path)
        log.info("Extracted (from %s): power=%s | vx=%s", sim_path, power_s, vx_s)
        print(power_s, vx_s)
    except Exception as e:
        log.exception("Failed to extract power/vx from %s: %s", sim_path, e)
        raise
