# src/sph2img/paraview/run_all_pipeline.py
#!/usr/bin/env python3
"""
High-level driver for SPH -> slice coloring -> milestone screencapture -> GIFs.

Steps:
  1) Extract POWER and VEL_X from SIM_PATH to build RUN_NAME
  2) Prepare SPH interpolator
  3) Create & color slice planes
  4) Run milestone-based screencapture in one of: 'laser' | 'largest' | 'solid'
  5) Build per-view GIFs from the screenshots
"""

# --- path bootstrap: make `sph2img` importable even when run as a script -----
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]  # repo root (sph2img/)
_SRC = _ROOT / "src"

if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
# ---------------------------------------------------------------------------

from sph2img.utils.pvlog import get_logger
from sph2img.config import get_config
from sph2img.utils.pvhelpers import run_main_if_testing

# pieces wired from your modules
from sph2img.utils.json_extractor import extract_power_and_vx
from sph2img.stages.sph_creator import prepare_sph_interpolator
from sph2img.stages.slice_creator import create_and_colour_slices
from sph2img.stages.screencapture_through_milestones import run_milestone_capture
from sph2img.stages.gif_maker import gif_creator

log = get_logger(__name__)


def deploy():
    # 1) Gather data

    # 1.1) Global data

    # 1.2) Crawl


    # 2) Prepare folder structure for storing the graphic data


    # 3) Start iterating

        # 3.A) Solidified
        # 3.A.1) Choose x_min, x_max, number-of-steps

        # 3.A.2) Perform procedure

        # 3.A.3) ONLY AT THE END: Delete all teh .vtk files (if required)

        # 3.B) Melt
        # 3.B.1) Choose between 'largest' or 'laser'

        # 3.B.2) Compute the x position accordingly

        # 3.B.3) Perform procedure (Delete .vtk file if required)


    # 4) Create .gif


    # 5) Write report and finish process

    return

# Auto-run in PV shell/batch if paraview.testing=true in config.json
run_main_if_testing(main)