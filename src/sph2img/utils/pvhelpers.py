# src/sph2img/utils/pvhelpers.py
# Small helpers to centralize ParaView script behavior.

import os
from typing import Callable

from sph2img.config import get_config

_TRUE = {"1", "true", "yes", "on"}

def _get_paraview_section():
    """
    Returns (testing: bool, default_view: str), with sane fallbacks.
    Works whether get_config() returns dataclasses or dicts.
    """
    cfg = get_config()

    # defaults
    testing = True
    default_view = "RenderView"

    # dataclass-style (your current setup)
    try:
        pv = cfg.paraview
        if pv is not None:
            testing = bool(getattr(pv, "testing", testing))
            default_view = str(getattr(pv, "default_view", default_view))
    except Exception:
        # dict-style fallback
        try:
            pv = cfg.get("paraview", {}) or {}
            testing = bool(pv.get("testing", testing))
            default_view = str(pv.get("default_view", default_view))
        except Exception:
            pass

    # env override: SPH2IMG_PV_TESTING=0/1,true/false,yes/no,on/off
    env = os.environ.get("SPH2IMG_PV_TESTING")
    if env is not None:
        testing = env.strip().lower() in _TRUE

    return testing, default_view

def pv_testing() -> bool:
    testing, _ = _get_paraview_section()
    return testing

def pv_view_name() -> str:
    _, view = _get_paraview_section()
    return view

def run_main_if_testing(main_callable: Callable[[], None]) -> None:
    """Call `main_callable()` iff paraview.testing is true (with env override)."""
    if pv_testing():
        main_callable()
