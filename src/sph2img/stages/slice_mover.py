# src/sph2img/paraview/slice_mover.py
#!/usr/bin/env python3

# --- path bootstrap: make `sph2img` importable even when run as a script -----
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]   # repo root (sph2img/)
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
# ---------------------------------------------------------------------------

from typing import Iterable, List

from sph2img.utils.pvlog import get_logger
from sph2img.utils.pvhelpers import run_main_if_testing, pv_view_name  # NEW

# ParaView
from paraview.simple import (  # type: ignore
    GetActiveViewOrCreate, HideScalarBarIfNotNeeded, GetColorTransferFunction,
    FindSource, UpdatePipeline, Render
)

log = get_logger(__name__)

# Slice names created by slice_creator.py
SLICE_SOURCES: List[str] = [
    "Top_Slice_wall", "Top_Slice_liquid", "Top_Slice_solid", "Top_Slice_gas",
    "Front_Slice_wall", "Front_Slice_liquid", "Front_Slice_solid", "Front_Slice_gas",
    "Side_Slice_wall", "Side_Slice_liquid", "Side_Slice_solid", "Side_Slice_gas",
]


def move_slices_origin(new_origin: Iterable[float]) -> None:
    """
    Set the same origin for all known slice planes.

    Args:
        new_origin: iterable of three floats [x, y, z]
    """
    try:
        origin = [float(v) for v in new_origin]
    except Exception as e:
        raise ValueError("new_origin must be 3 floats; got %r" % (new_origin,)) from e
    if len(origin) != 3:
        raise ValueError("new_origin must have length 3; got %d" % len(origin))

    view = GetActiveViewOrCreate(pv_view_name())  # use config default view
    try:
        HideScalarBarIfNotNeeded(GetColorTransferFunction("temperature"), view)
    except Exception:
        pass

    log.info("Changing slice planes' origin to %s", origin)

    moved, missing = 0, 0
    for name in SLICE_SOURCES:
        src = FindSource(name)
        if src and hasattr(src, "SliceType"):
            try:
                src.SliceType.Origin = origin
                moved += 1
                log.info("  Moved %s", name)
            except Exception as e:
                log.warning("  Failed to move %s: %s", name, e)
        else:
            missing += 1
            log.debug("  Missing or non-slice source (skipped): %s", name)

    UpdatePipeline()
    Render()
    log.info("Move complete. Updated: %d, missing/skipped: %d", moved, missing)


# ----------------------------
# ParaView shell-friendly `main()` (no CLI args)
# ----------------------------

def main() -> None:
    # Default target position; adjust as needed for your runs.
    move_here = [0.000925, 0.0, 0.0]
    move_slices_origin(move_here)
    Render()
    log.info("slice_mover.main() finished.")


# Auto-run in PV shell/batch if paraview.testing=True (or env override)
# run_main_if_testing(main)
