
# sph2img

**sph2img** is a small toolkit that turns AERSPH simulation outputs into
consistent screenshots and GIFs. It prepares an SPH volume interpolator in
ParaView, creates per‑phase slice planes, then captures images at specific
“milestones” (laser position, largest melt delta, or a solidification linspace)
and stitches them into view‑wise animations.

---

## TL;DR – Common Workflow (`bin/run_pipeline.py`)

`run_pipeline.py` is the orchestrator. It performs these steps:

1. **Detect run name** – reads power & vx from the simulation JSON and builds
   a run label like `run_POWER-1300p0_VELX-0p8`.
2. **Prepare SPH interpolator** – builds a unified SPH volume interpolator
   from the four phases (solid/liquid/gas/wall).
3. **Create & color slices** – generates front/side/top slices for each phase
   and colors them with simple “is_*” tags.
4. **Capture screenshots at milestones** – chooses positions/timesteps using one
   of the modes:
   - `laser`   – x-position is the laser head position at each VTK time.
   - `largest` – x-position is the mid‑x of the pair with largest ΔY among
                 neighbors sharing (X,Z).
   - `solid`   – x-position marches along a linspace between start/end.
5. **Make GIFs** – composes one GIF per view from the saved PNGs.

**Outputs** land in `outputs/screenshots/<timestamped-folder>` with files named
`<RUN_NAME>_<index>_<front|side|top>.png` and `animation_<RUN_NAME>_<view>.gif`.

Run it with ParaView’s Python:

```bash
pvpython bin/run_pipeline.py
# …or…
pvbatch  bin/run_pipeline.py
```

> **Heads‑up:** If you run with the system `python`, ParaView modules won’t be
> available. Always use `pvpython`/`pvbatch` for the pipeline.

---

## Repository Layout

```
sph2img/
├── bin/
│   ├── pv_config_check.py      # repo/config preflight (policy + optional fixes)
│   └── run_pipeline.py         # high‑level driver (workflow above)
├── config.json                  # single source of truth for paths/render/capture
├── logs/                        # runtime logs (created if missing)
├── outputs/
│   └── screenshots/            # timestamped result folders
├── simulations/                # your simulation runs (default location)
└── src/sph2img/
    ├── config.py               # config loader + dataclasses
    ├── milestones/             # “what to capture” logic
    │   ├── milestones_common.py
    │   ├── milestones_melt_largest_delta.py
    │   ├── milestones_melt_laser_positions.py
    │   ├── milestones_solidified.py
    │   └── milestones_suite.py
    ├── parsers/                # readers for json/dat/iter files
    │   ├── config_parser.py
    │   ├── data_files_parser.py
    │   ├── master_parser.py
    │   ├── parser_utils.py
    │   └── vtk_iterations_parser.py
    ├── stages/                 # ParaView pipeline stages
    │   ├── sph_creator.py
    │   ├── slice_creator.py
    │   ├── slice_hide_and_show.py
    │   ├── slice_mover.py
    │   ├── screencapture_slice_composite.py
    │   └── screencapture_through_milestones.py
    └── utils/                  # logging, helpers
        ├── pvlog.py
        ├── pvhelpers.py
        ├── crawl_iterations.py
        ├── json_extractor.py
        └── list_installed_modules.py
```

All top‑level scripts and most modules perform **path bootstrap** so they can be
run directly (not only as packages).

---

## Requirements

- **ParaView** ≥ 5.10 (tested with recent 5.x). Use its `pvpython`/`pvbatch`.
- Python 3.10+ (the repo uses `from __future__ import annotations`).
- Python packages (installed into the ParaView site‑packages or available to
  `pvpython`):
  - `numpy`, `scipy` (for KD‑trees in “largest ΔY” milestone),
  - `Pillow` (for GIF creation),
  - (optional) `imageio` if you prefer a different GIF writer.

Check module availability quickly:

```bash
pvpython -m sph2img.utils.list_installed_modules
```

---

## Configuration (`config.json`)

`sph2img/src/sph2img/config.py` enforces a **path policy** and turns the JSON
into typed dataclasses.

- `paths.project_root` (required, **absolute**): authoritative repo root.
- `paths.sim_path` (ABS **or** REL under project_root): input simulation folder.
- `paths.out_dir`  (ABS **or** REL under project_root): where screenshots go.
- `paths.logs_dir` (**relative only** under project_root).
- `paths.cache_dir` (**relative only** under project_root).

Render & capture knobs live under `render` and `capture`.

Example:

```json
{
  "paths": {
    "project_root": "/absolute/path/to/sph2img",
    "sim_path": "simulations/mhpc3d_200W_Ti64_Ar-3",
    "out_dir":  "outputs/screenshots",
    "logs_dir": "logs",
    "cache_dir": ".cache"
  },
  "render": {
    "offscreen": true,
    "image_w": 256,
    "image_h": 256
  },
  "capture": {
    "mode": "largest",           // laser | largest | solid
    "eps": 1e-3,                 // neighbor tolerance for “largest”
    "x_start": null,             // for solid mode; null -> auto
    "x_end": null,
    "solid_cuts": 30,
    "front_w": 256, "front_h": 256,
    "side_w": 256,  "side_h": 256,
    "top_w": 256,   "top_h": 256,
    "x_side_offset": 7e-5,
    "empty_out": true
  }
}
```

### Validate your setup

Run the preflight checker:

```bash
python bin/pv_config_check.py --strict
# or let it create writable dirs for you:
python bin/pv_config_check.py --fix
```

It verifies policy (absolute/relative rules), existence/writability, and whether
`paraview.simple` is importable (unless `--no-paraview`).

---

## Usage

### 1) Full pipeline (recommended)

```bash
pvpython bin/run_pipeline.py
```

This reads `config.json`, prepares the ParaView pipeline, captures screenshots
per the selected `capture.mode`, then writes GIFs alongside the PNGs.

### 2) Stage‑by‑stage (advanced)

If you want to drive stages yourself (e.g., in the ParaView Python shell):

```python
from sph2img.config import get_config
from sph2img.stages.sph_creator import prepare_sph_interpolator
from sph2img.stages.slice_creator import create_and_colour_slices
from sph2img.stages.slice_mover import move_slices_origin
from sph2img.stages.screencapture_through_milestones import run_milestone_capture
from sph2img.stages.gif_maker import gif_creator

cfg = get_config()
prepare_sph_interpolator(str(cfg.paths.sim_path))
create_and_colour_slices()
out_dir = run_milestone_capture(
    sim_path=str(cfg.paths.sim_path),
    mode=cfg.capture.mode,
    epsilon=cfg.capture.eps,
    x_start=cfg.capture.x_start,
    x_end=cfg.capture.x_end,
    linspace_cuts=cfg.capture.solid_cuts,
    run_name="manual_run",
    out_dir=str(cfg.paths.out_dir),
    front_W=cfg.capture.front[0], front_H=cfg.capture.front[1],
    side_W=cfg.capture.side[0],  side_H=cfg.capture.side[1],
    top_W=cfg.capture.top[0],    top_H=cfg.capture.top[1],
    x_side_offset=cfg.capture.x_side_offset,
    testing_folder=cfg.capture.empty_out,
)
gif_creator(out_dir)
```

---

## Outputs

- **PNG screenshots**: `outputs/screenshots/<timestamp>/run_POWER-..._VELX-..._<index>_<view>.png`
- **GIFs**: `outputs/screenshots/<timestamp>/animation_<run>_<view>.gif`
- **Logs**: `logs/<prog>_<timestamp>_<pid>.log` (colorized on console).

---

## Troubleshooting

- **ParaView modules not found**: Ensure you’re using `pvpython` / `pvbatch`,
  not system `python`.
- **Bounded Volume source failure**: The SPH volume bounds come from simulation
  `domain_min`/`domain_max`. If these are missing or inverted, the bounded volume
  may fail in `REQUEST_INFORMATION`. Verify your simulation JSON and that
  `sph_creator.prepare_sph_interpolator` is called *before* slices/screenshots.
- **Duplicate logs**: Loggers in this project disable propagation. If you see
  duplicates, check for external logging setup in your environment and avoid
  re‑configuring `logging.basicConfig` elsewhere.
- **No slices shown**: Run `create_and_colour_slices()` again, or call
  `slice_hide_and_show.show_one_or_all("all")` to make all planes visible.

---

## Development Notes

- All scripts perform minimal **path bootstrap** so they can be called directly.
- The config loader (`src/sph2img/config.py`) is intentionally strict about the
  **absolute/relative path policy** to keep deployments predictable on clusters.
- ParaView shell cannot handle `from __future__ import annotations` unless it’s
  literally the first line—our modules place it correctly; avoid inserting code
  above it.

---

## License

MIT. See [LICENSE](./LICENSE).
