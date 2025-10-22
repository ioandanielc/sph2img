# src/sph2img/paraview/screenshoter.py
#!/usr/bin/env python3
# make repo/src importable no matter which interpreter runs this (python, pvpython, pvbatch)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sph2img.pvshim import enable_stubs; enable_stubs()

import os
import shutil
from typing import Dict, Tuple, Optional

from sph2img.utils.pvlog import get_logger
from sph2img.utils.pvhelpers import run_main_if_testing, pv_view_name
from sph2img.config import get_config

# ParaView
from paraview.simple import (  # type: ignore
    GetActiveView, CreateRenderView, GetActiveViewOrCreate,
    GetColorTransferFunction, GetScalarBar, FindSource, SaveScreenshot
)
from sph2img.stages.slice_hide_and_show import show_one_or_all  # type: ignore

log = get_logger(__name__)

# ---- arrays that might have scalar bars in your pipeline ----
_SCALAR_BAR_ARRAYS = [
    "is_liquid", "is_solid", "is_gas", "is_wall",
    "temperature", "phase_change_counter",
]


def _empty_dir(path: str) -> None:
    """Delete ALL contents of `path` (files and subdirs), keeping the folder itself."""
    if not os.path.isdir(path):
        return
    for name in os.listdir(path):
        p = os.path.join(path, name)
        try:
            if os.path.isfile(p) or os.path.islink(p):
                os.remove(p)
            elif os.path.isdir(p):
                shutil.rmtree(p)
        except Exception as e:
            log.warning("Failed to remove %s: %s", p, e)


def ensure_out_dir(out_dir: Optional[str]) -> str:
    """Create output folder if it doesn't exist, return absolute path."""
    out_dir = os.path.abspath(os.path.expanduser(out_dir or "."))
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def _hide_all_scalar_bars(view) -> None:
    """Force-hide scalar bars for all known arrays in the given view."""
    for name in _SCALAR_BAR_ARRAYS:
        try:
            lut = GetColorTransferFunction(name)
            sb = GetScalarBar(lut, view)
            if sb:
                sb.Visibility = 0
        except Exception:
            # LUT or scalar bar may not exist — that's fine.
            pass


def _bounds_dict_for_view(name: str) -> Dict[str, float]:
    """Return the bounding-box bounds of the pipeline element named `name`."""
    px = FindSource(name)
    if px is None:
        raise RuntimeError(f"Source '{name}' not found.")
    try:
        px.UpdatePipeline()
    except Exception:
        pass
    x0, x1, y0, y1, z0, z1 = px.GetDataInformation().GetBounds()
    return {"xmin": x0, "xmax": x1, "ymin": y0, "ymax": y1, "zmin": z0, "zmax": z1}


def _get_slice_origin(slice_proxy) -> Tuple[float, float, float]:
    """Return (ox, oy, oz) for a Slice filter, regardless of plane/cylinder/sphere."""
    st = getattr(slice_proxy, "SliceType", None)
    if st is None:
        raise TypeError("Proxy has no SliceType — not a Slice filter?")
    if hasattr(st, "Origin"):
        o = tuple(st.Origin)
    elif hasattr(st, "Center"):
        o = tuple(st.Center)
    else:
        # best-effort fallback
        o = None
        for attr in ("Origin", "Center"):
            if hasattr(st, attr):
                o = tuple(getattr(st, attr))
                break
        if o is None:
            raise AttributeError("SliceType has no Origin/Center property.")
    if len(o) != 3:
        raise ValueError(f"Unexpected origin length {len(o)} in slice.")
    return float(o[0]), float(o[1]), float(o[2])


def _format_filename(run_name: Optional[str], entry_no: Optional[int], view_key: str) -> str:
    """
    Build filename: <run_name>_<entry_no>_<front|side|top>.png
    """
    rn = (run_name or "run_x").strip().replace(" ", "_")
    en = int(entry_no if entry_no is not None else 99)
    return f"{rn}_{en}_{view_key}.png"


def _center_and_save(
    view_key: str,
    out_dir: str,
    width: int,
    height: int,
    run_name: Optional[str],
    entry_no: Optional[int],
    x_side_offset: float = 0.0,
) -> None:
    """
    Center orthographic camera for a given view ('Top'|'Front'|'Side') and save PNG.
    - width/height are the per-view resolution
    - x_side_offset shifts the *side* view a bit left (decreasing X)
    """
    vk = (view_key or "").strip().lower()
    if vk not in {"top", "front", "side"}:
        raise ValueError("view_key must be one of: Top, Front, Side")

    # Ensure correct slices are visible
    show_one_or_all(view_key)

    # Per-view slice names (query bounds from *_wall as canonical extents)
    slices = {
        "top":   ["Top_Slice_wall",   "Top_Slice_liquid",   "Top_Slice_solid",   "Top_Slice_gas"],
        "front": ["Front_Slice_wall", "Front_Slice_liquid", "Front_Slice_solid", "Front_Slice_gas"],
        "side":  ["Side_Slice_wall",  "Side_Slice_liquid",  "Side_Slice_solid",  "Side_Slice_gas"],
    }

    view_bounds = {view: _bounds_dict_for_view(names[0]) for view, names in slices.items()}

    # View setup
    view = GetActiveView() or CreateRenderView()
    view.CameraParallelProjection = 1
    view.OrientationAxesVisibility = 0

    # Hide **all** scalar bars before capture
    _hide_all_scalar_bars(view)

    # Use the *_wall slice to read the slice-plane's current origin X (for centering)
    wall_name = slices[vk][0]
    wall_src = FindSource(wall_name)
    if wall_src is None:
        raise RuntimeError(f"Slice source '{wall_name}' not found.")
    ox, oy, oz = _get_slice_origin(wall_src)

    # Bounds for current view
    b = view_bounds[vk]
    xmin, xmax = b["xmin"], b["xmax"]
    ymin, ymax = b["ymin"], b["ymax"]
    zmin, zmax = b["zmin"], b["zmax"]

    # Center of bounds; override cx with slice origin X as in your logic
    cx, cy, cz = 0.5 * (xmin + xmax), 0.5 * (ymin + ymax), 0.5 * (zmin + zmax)
    cx = ox

    # Camera setup per view
    delta_d = 1e-6
    if vk == "top":
        view.CameraFocalPoint = [cx, cy, cz]
        view.CameraPosition   = [cx, cy, cz + delta_d]
        view.CameraViewUp     = [0, 1, 0]
        vspan = ymax - ymin
    elif vk == "front":
        view.CameraFocalPoint = [cx, cy, cz]
        view.CameraPosition   = [cx - delta_d, cy, cz]
        view.CameraViewUp     = [0, 0, 1]
        vspan = zmax - zmin
    else:
        # side: shift a bit to the *left* along X if requested
        cx -= float(x_side_offset or 0.0)
        view.CameraFocalPoint = [cx, cy, cz]
        view.CameraPosition   = [cx, cy - delta_d, cz]
        view.CameraViewUp     = [0, 0, 1]
        vspan = zmax - zmin

    view.CameraParallelScale = 0.5 * vspan

    # Build filename and save
    filename = _format_filename(run_name, entry_no, vk)
    out_path = os.path.join(out_dir, filename)
    SaveScreenshot(out_path, view, ImageResolution=[int(width), int(height)], TransparentBackground=0)
    log.info("Saved %s (%dx%d)", out_path, int(width), int(height))


def screenshot_set(
    run_name: Optional[str] = None,
    entry_no: Optional[int] = None,
    out_dir: Optional[str] = None,
    # per-view resolutions (defaults to 256)
    front_W: int = 256, front_H: int = 256,
    side_W: int = 256,  side_H: int = 256,
    top_W: int = 256,   top_H: int = 256,
    # side-view nudge (move left along X)
    x_side_offset: float = 0.0,
    # testing flag: wipe output folder before saving
    testing_folder: bool = True,
) -> None:
    """
    Take Top/Front/Side screenshots and save them into `out_dir`.
    Filenames: <run_name>_<entry_no>_<front|side|top>.png

    If `testing_folder` is True (default), deletes **all contents** of `out_dir`
    before writing new screenshots.
    """
    out_dir = ensure_out_dir(out_dir)

    if testing_folder:
        log.info("Testing mode: clearing output folder %s", out_dir)
        _empty_dir(out_dir)

    _center_and_save("Front", out_dir, front_W, front_H, run_name, entry_no, x_side_offset=x_side_offset)
    _center_and_save("Side",  out_dir, side_W,  side_H,  run_name, entry_no, x_side_offset=x_side_offset)
    _center_and_save("Top",   out_dir, top_W,   top_H,   run_name, entry_no, x_side_offset=x_side_offset)

    # Optional: restore visibility (show everything again)
    show_one_or_all("all")


# ----------------------------
# ParaView shell-friendly `main()` (no CLI args)
# ----------------------------

def main() -> None:
    """
    Read output paths and per-view sizes from config and capture one set.
    Assumes slices already exist (use slice_creator first).
    """
    cfg = get_config()
    cap = cfg.capture

    out_dir = str(cfg.paths.out_dir)
    run_name = "run_x"         # keep simple; derive from sim if you like
    entry_no = 99

    screenshot_set(
        run_name=run_name,
        entry_no=entry_no,
        out_dir=out_dir,
        front_W=cap.front[0], front_H=cap.front[1],
        side_W=cap.side[0],   side_H=cap.side[1],
        top_W=cap.top[0],     top_H=cap.top[1],
        x_side_offset=cap.x_side_offset,
        testing_folder=cap.empty_out,  # reuse your config flag
    )
    log.info("screenshoter.main() finished (view=%s, out=%s)", pv_view_name(), out_dir)


# Auto-run in PV shell/batch if paraview.testing=True (or env override)
# run_main_if_testing(main)
