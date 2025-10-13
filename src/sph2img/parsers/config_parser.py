# src/sph2img/parsers/config_parser.py
from __future__ import annotations

# --- path bootstrap: make `sph2img` importable even when run as a script -----
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]   # repo root (sph2img/)
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
# ---------------------------------------------------------------------------

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

from sph2img.config import get_config
from sph2img.utils.pvlog import get_logger

logger = get_logger(__name__)

__all__ = [
    "get_json_path",
    "extract_json_data",
    "ExtractedConfig",
]


@dataclass(frozen=True)
class ExtractedConfig:
    """Strongly-typed view of the minimal config we need.

    The legacy API returned a positional tuple. To avoid breaking callers,
    :func:`extract_json_data` still *returns this dataclass*; if you need the
    old behavior, use ``tuple(cfg)`` which maps the fields in the documented
    order below.

    Field order for backward-compat tuple-compatibility:
        0. laser_power_expression (str)
        1. laser_velocity (Sequence[float] | float)
        2. material (str)
        3. density (float)
        4. domain_rendering_minmax (list[min, max])
        5. smoothing_length (float)
        6. rendering_resolution (list[int])
        7. domain_min (list[float])
        8. domain_max (list[float])
    """

    laser_power_expression: str
    laser_velocity: Sequence[float] | float
    material: str
    density: float
    domain_rendering_minmax: List[Any]
    smoothing_length: float
    rendering_resolution: List[int]
    domain_min: List[float]
    domain_max: List[float]

    # Back-compat: allow tuple(cfg)
    def __iter__(self):  # type: ignore[override]
        yield self.laser_power_expression
        yield self.laser_velocity
        yield self.material
        yield self.density
        yield self.domain_rendering_minmax
        yield self.smoothing_length
        yield self.rendering_resolution
        yield self.domain_min
        yield self.domain_max


# ------------------------------- helpers ------------------------------------

def _must(d: Dict[str, Any], key: str, ctx: str) -> Any:
    if key not in d:
        logger.error("Missing key '%s' under %s", key, ctx)
        raise KeyError(f"Missing key '{key}' under {ctx}")
    return d[key]


def _must_chain(d: Dict[str, Any], path: Sequence[str]) -> Any:
    cur: Any = d
    ctx = "root"
    for k in path:
        cur = _must(cur, k, ctx)
        ctx = f"{ctx}.{k}"
    return cur


# --------------------------------- API --------------------------------------

def get_json_path(path_to_simulation: str) -> str:
    """
    Find the single JSON file inside ``path_to_simulation``.

    Raises:
        FileNotFoundError: if no .json file exists.
        RuntimeError: if more than one .json file exists.
    """
    sim_dir = Path(path_to_simulation).expanduser().resolve()
    logger.info("Config Parser running (scan: %s)", sim_dir)

    if not sim_dir.exists():
        logger.error("Simulation directory not found: %s", sim_dir)
        raise FileNotFoundError(f"Simulation directory not found: {sim_dir}")
    if not sim_dir.is_dir():
        logger.error("Not a directory: %s", sim_dir)
        raise NotADirectoryError(f"Not a directory: {sim_dir}")

    json_files = [p.name for p in sim_dir.iterdir() if p.is_file() and p.suffix.lower() == ".json"]

    if len(json_files) == 0:
        logger.error("No json file in folder %s", sim_dir)
        raise FileNotFoundError(f"No json file in folder {sim_dir}")
    if len(json_files) > 1:
        logger.error("More than one json file in folder %s: %s", sim_dir, json_files)
        raise RuntimeError(f"More than one json file in folder {sim_dir}")

    path_to_json = str(sim_dir / json_files[0])
    logger.info("Configuration detected at %s", path_to_json)
    return path_to_json


def extract_json_data(path_to_simulation: str) -> ExtractedConfig:
    """
    Extract required fields from the simulation's single JSON file.

    Returns:
        ExtractedConfig

    (Back-compat: ``tuple(extract_json_data(...))`` preserves the original
    positional order.)
    """
    path_to_json = get_json_path(path_to_simulation)

    with open(path_to_json, "r", encoding="utf-8") as f:
        try:
            data: Dict[str, Any] = json.load(f)
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in %s: %s", path_to_json, e)
            raise

    # --- Phases: melt/substrate/gas must exist and melt/substrate must match ---
    phases = _must(data, "phases", "root")
    if not isinstance(phases, dict):
        logger.error("'phases' must be an object, got %r", type(phases))
        raise TypeError("'phases' must be an object")

    required = ("melt", "substrate", "gas")
    for r in required:
        _ = _must(phases, r, "phases")

    melt = phases["melt"]
    substrate = phases["substrate"]

    melt_info = {
        "material": _must(melt, "material", "phases.melt"),
        "density": _must(_must(melt, "initial_conditions", "phases.melt"), "density", "phases.melt.initial_conditions"),
    }
    substrate_info = {
        "material": _must(substrate, "material", "phases.substrate"),
        "density": _must(_must(substrate, "initial_conditions", "phases.substrate"), "density", "phases.substrate.initial_conditions"),
    }

    if melt_info != substrate_info:
        logger.error("Mismatch between melt and substrate: %s vs %s", melt_info, substrate_info)
        raise ValueError(f"Melt and substrate mismatch: {melt_info} vs {substrate_info}")

    # --- Laser ---
    laser_physics = _must_chain(data, ["lasers", "single_gaussian_laser", "physics"])  # dict

    power_expr = _must(laser_physics, "power_magnitude_expression", "lasers.single_gaussian_laser.physics")
    velocity = _must(_must(laser_physics, "motion", "lasers.single_gaussian_laser.physics"), "velocity", "lasers.single_gaussian_laser.physics.motion")

    logger.info(
        "Extracted laser/material: power=%s | speed=%s | material=%s | density=%s",
        power_expr, velocity, melt_info["material"], melt_info["density"],
    )

    # --- Rendering/window + SPH ---
    rendering = _must(data, "rendering", "root")
    domain = [
        _must(_must(rendering, "domain", "rendering"), "min", "rendering.domain"),
        _must(_must(rendering, "domain", "rendering"), "max", "rendering.domain"),
    ]

    sph = _must(data, "sph", "root")
    smoothing_length = _must(sph, "particle_spacing", "sph")

    resolution = _must(rendering, "resolution", "rendering")

    # --- Full domain bounds ---
    domain_min = _must(_must(data, "domain", "root"), "domain_min", "domain")
    domain_max = _must(_must(data, "domain", "root"), "domain_max", "domain")

    return ExtractedConfig(
        laser_power_expression=power_expr,
        laser_velocity=velocity,
        material=melt_info["material"],
        density=melt_info["density"],
        domain_rendering_minmax=domain,
        smoothing_length=smoothing_length,
        rendering_resolution=resolution,
        domain_min=domain_min,
        domain_max=domain_max,
    )


if __name__ == "__main__":
    # Keep same behavior as your original script, but use config for the default path.
    cfg = get_config()
    default_sim = str(cfg.paths.sim_path)

    cfg_out = extract_json_data(default_sim)
    # Nudge: print a compact one-liner preview without dumping the whole JSON
    logger.info(
        "OK: power=%s | vx=%s | mat=%s | rho=%s | res=%s",
        cfg_out.laser_power_expression,
        cfg_out.laser_velocity,
        cfg_out.material,
        cfg_out.density,
        cfg_out.rendering_resolution,
    )
