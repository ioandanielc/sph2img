# src/sph2img/paraview/slice_hide_and_show.py
#!/usr/bin/env python3


from typing import List
from sph2img.utils.pvlog import get_logger
from sph2img.utils.pvhelpers import pv_view_name

# ParaView
from paraview.simple import (  # type: ignore
    GetActiveViewOrCreate, HideScalarBarIfNotNeeded, GetColorTransferFunction,
    FindSource, Show, Hide, UpdatePipeline, Render
)

log = get_logger(__name__)

# All expected slice source names (created by slice_creator.py)
SLICE_SOURCES: List[str] = [
    "Top_Slice_wall",   "Top_Slice_liquid",  "Top_Slice_solid",  "Top_Slice_gas",
    "Front_Slice_wall", "Front_Slice_liquid","Front_Slice_solid","Front_Slice_gas",
    "Side_Slice_wall",  "Side_Slice_liquid", "Side_Slice_solid", "Side_Slice_gas",
]


def show_one_or_all(plane_to_keep: str) -> None:
    """
    Show all slices or only those whose name contains `plane_to_keep` (case-insensitive).
      plane_to_keep: "all" | "front" | "side" | "top"
    """
    view = GetActiveViewOrCreate(pv_view_name())  # use config default view
    # tidy any stray bars (optional)
    try:
        HideScalarBarIfNotNeeded(GetColorTransferFunction("temperature"), view)
    except Exception:
        pass

    key = (plane_to_keep or "").strip().lower()
    known_keys = {"all", "front", "side", "top"}

    if key not in known_keys:
        log.warning(
            "show_one_or_all received an unknown argument: %r (expected one of %s)",
            plane_to_keep, sorted(known_keys)
        )
        return

    if key == "all":
        log.info("Preparing 'all' view")
        for name in SLICE_SOURCES:
            src = FindSource(name)
            if src:
                log.info("  Showing %s", name)
                Show(src)
            else:
                log.debug("  Missing source (skipped): %s", name)
    else:
        log.info("Preparing '%s-only' view", key)
        to_show = [s for s in SLICE_SOURCES if key in s.lower()]
        to_hide = [s for s in SLICE_SOURCES if key not in s.lower()]

        for name in to_hide:
            src = FindSource(name)
            if src:
                log.info("  Hiding %s", name)
                Hide(src)
            else:
                log.debug("  Missing source (skipped hide): %s", name)

        for name in to_show:
            src = FindSource(name)
            if src:
                log.info("  Showing %s", name)
                Show(src)
            else:
                log.debug("  Missing source (skipped show): %s", name)

    UpdatePipeline()
    Render()
    log.info("Update & render complete.")


# ----------------------------
# ParaView shell-friendly `main()` (no CLI args)
# ----------------------------

def main() -> None:
    # Default to showing 'front'; tweak as desired.
    show_one_or_all("all")
    Render()
    log.info("slice_hide_and_show.main() finished.")


# Auto-run in PV shell/batch if paraview.testing=True (or env override)
# run_main_if_testing(main)
