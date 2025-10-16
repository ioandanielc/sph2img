# src/sph2img/paraview/slice_creator.py
#!/usr/bin/env python3

# --- path bootstrap: make `sph2img` importable even when run as a script -----
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]   # repo root (sph2img/)
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
# ---------------------------------------------------------------------------

from typing import Set, List, Dict

from sph2img.utils.pvlog import get_logger
from sph2img.utils.pvhelpers import run_main_if_testing, pv_view_name  # <<< NEW

# ParaView
from paraview.simple import (  # type: ignore
    _DisableFirstRenderCameraReset,
    FindSource, Slice, HideInteractiveWidgets, GetActiveViewOrCreate,
    Show, ColorBy, GetColorTransferFunction, GetOpacityTransferFunction,
    GetTransferFunction2D, HideScalarBarIfNotNeeded, UpdatePipeline, Render, Hide
)

log = get_logger(__name__)

# Prevent the auto camera jump on first Show
_DisableFirstRenderCameraReset()

# Track created slice names (useful if you want to hide/remove later)
slice_sources: Set[str] = set()

# ---------- helpers ----------

_SLICE_NORMALS: Dict[str, List[float]] = {
    "front": [1.0, 0.0, 0.0],
    "side":  [0.0, 1.0, 0.0],
    "top":   [0.0, 0.0, 1.0],
}
_DEFAULT_ORIGIN: List[float] = [0.0009343591206128476, 0.0, 0.0]


def _slice_title(slice_type: str) -> str:
    if slice_type == "front":
        return "Front"
    if slice_type == "side":
        return "Side"
    if slice_type == "top":
        return "Top"
    return "Cut"  # fallback label


# ---------- main API ----------

def create_section_view(
    sph_source: str = "SPHVolumeInterpolator_phase_change_counter",
    slice_type: str = "front",
    phase: str = "liquid",
    phase_tag: str = None,
    origin: List[float] = None,
    render_view_name: str = "RenderView",
):
    """
    Create a slice of the SPH volume and color it by a phase tag (is_liquid/is_solid/...).
    Returns the created Slice proxy.
    """
    origin = origin or _DEFAULT_ORIGIN
    phase_tag = phase_tag or f"is_{phase}"
    normal = _SLICE_NORMALS.get(slice_type, [1.0, 1.0, 0.0])
    slice_name = f"{_slice_title(slice_type)}_Slice_{phase}"

    src = FindSource(sph_source)
    if not src:
        raise RuntimeError("Cannot find source '%s' in the pipeline." % sph_source)
    log.info("Creating slice '%s' (type=%s, phase=%s, tag=%s)", slice_name, slice_type, phase, phase_tag)

    # Hide the SPH Interpolator
    sph_proxy = FindSource(sph_source)
    Hide(sph_proxy)
    HideInteractiveWidgets(proxy=sph_proxy)

    # Create slice
    sl = Slice(registrationName=slice_name, Input=src)
    HideInteractiveWidgets(proxy=sl)
    sl.SliceType.Origin = origin
    sl.SliceType.Normal = normal

    # Show in view
    view = GetActiveViewOrCreate(render_view_name)
    disp = Show(sl, view, "GeometryRepresentation")
    disp.Representation = "Surface"

    # Color by tag and rescale
    ColorBy(disp, ("POINTS", phase_tag))
    disp.RescaleTransferFunctionToDataRange(True, False)
    disp.SetScalarBarVisibility(view, True)

    # Ensure transfer functions exist (they’re tuned by colour_tag)
    _ = GetColorTransferFunction(phase_tag)
    _ = GetOpacityTransferFunction(phase_tag)
    _ = GetTransferFunction2D(phase_tag)

    slice_sources.add(slice_name)
    return sl


def colour_tag(colour: List[float] = None, threshold: float = 0.5, tag_name: str = "is_liquid"):
    """
    Configure a binary-ish coloring/opacity for the given tag_name.
    Default colors if not provided:
      is_liquid -> red, is_solid -> green, is_gas -> blue, is_wall -> black, else white.
    """
    if colour is None:
        colour = (
            [1.0, 0.0, 0.0] if tag_name == "is_liquid" else
            [0.0, 1.0, 0.0] if tag_name == "is_solid" else
            [0.0, 0.0, 1.0] if tag_name == "is_gas"   else
            [0.0, 0.0, 0.0] if tag_name == "is_wall"  else
            [1.0, 1.0, 1.0]
        )

    lut = GetColorTransferFunction(tag_name)
    lut.Set(
        RGBPoints=[
            # scalar, R, G, B
            0.0, 0.0, 0.0, 0.0,   # 0 -> black
            0.5, 0.0, 0.0, 0.0,   # keep black up to threshold
            1.0, colour[0], colour[1], colour[2],  # 1 -> chosen colour
        ],
        ScalarRangeInitialized=1.0,
    )
    lut.NumberOfTableValues = 2
    lut.EnableOpacityMapping = 1

    pwf = GetOpacityTransferFunction(tag_name)
    pwf.Set(
        Points=[
            0.0,       0.0, 0.5, 0.0,  # fully transparent at 0
            threshold, 0.0, 0.5, 0.0,  # still transparent up to threshold
            threshold, 1.0, 0.5, 0.0,  # jump to opaque at threshold
            1.0,       1.0, 0.5, 0.0,  # stay opaque
        ],
        ScalarRangeInitialized=1,
    )

    _ = GetTransferFunction2D(tag_name)
    log.info("Configured colour/opacity for tag '%s' (threshold=%.3g, colour=%s)", tag_name, threshold, colour)


def create_and_colour_slices():
    """
    Build front/side/top slices for each phase (liquid/solid/gas/wall),
    color them by their respective is_* tags, and tidy scalar bars.
    """
    view = GetActiveViewOrCreate(pv_view_name())  # <<< use config default view

    phases = ["liquid", "solid", "gas", "wall"]
    phase_tags = [f"is_{p}" for p in phases]
    slice_types = ["front", "side", "top"]

    for phase, tag in zip(phases, phase_tags):
        for s_type in slice_types:
            create_section_view(slice_type=s_type, phase=phase, phase_tag=tag, render_view_name=pv_view_name())
            colour_tag(tag_name=tag, colour=None)
            HideScalarBarIfNotNeeded(GetColorTransferFunction(tag), view)

    UpdatePipeline()
    Render()

    log.info("Created and coloured %d slices.", len(slice_sources))


# ----------------------------
# ParaView shell-friendly `main()` (no CLI args)
# ----------------------------

def main() -> None:
    """
    Assumes the SPH interpolator is already present in the pipeline as
    'SPHVolumeInterpolator_phase_change_counter'. Creates slices and renders.
    """
    create_and_colour_slices()
    Render()
    log.info("slice_creator.main() finished.")


# Auto-run in PV shell/batch if paraview.testing=True (or env override)
run_main_if_testing(main)
