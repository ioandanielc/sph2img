# sph2img — build an image dataset from SPH (ParaView)

Create a clean, reproducible **image dataset** from SPH simulation output using **ParaView**  
(SPH interpolator → slices → milestone-based screencapture → GIFs).

- Deterministic config via a single `config.json` (no env vars required)
- Headless-friendly (`pvbatch`)
- Clear separation: entrypoints in `src/bin/`, library code in `src/sph2img/`
- Outputs kept out of code folders (`outputs/`)

---

## Directory layout

```text
traces/                          # GIT ROOT
├─ README.md
├─ .gitignore
├─ config.json                   # single source of truth (see below)
│
├─ simulations/                  # INPUT data (read-only)
│  └─ mhpc3d_200W_Ti64_Ar-3/...
│
├─ outputs/                      # OUTPUTS (no code here)
│  ├─ screenshots/
│  └─ gifs/
│
├─ logs/                         # runtime logs (pvlog)
├─ .cache/                       # scratch/temp
│
└─ src/
   ├─ bin/                       # ENTRYPOINTS you run
   │  ├─ sph2img.py              # pvbatch driver (SPH→slices→capture→GIF)
   │  └─ pv_config_check.py      # preflight sanity check
   │
   └─ sph2img/                   # IMPORTABLE LIB (your code)
      ├─ __init__.py
      ├─ config.py               # get_config(): JSON→immutable settings
      ├─ stages/
      │  ├─ sph_creator.py
      │  ├─ slice_creator.py
      │  └─ capture.py
      ├─ parsers/
      │  ├─ __init__.py
      │  ├─ json_extractor.py
      │  ├─ master_parser.py
      │  ├─ data_files_parser.py
      │  └─ vtk_iterations_parser.py
      ├─ milestones/
      │  ├─ __init__.py
      │  ├─ milestones_common.py
      │  ├─ milestones_melt_largest_delta.py
      │  ├─ milestones_melt_laser_positions.py
      │  └─ milestones_solidified.py
      └─ utils/
         ├─ __init__.py
         ├─ pvlog.py
         ├─ add_once.py
         ├─ gif_maker.py
         ├─ crawl_iterations.py
         ├─ histogram.py
         ├─ histogram_and_rfd_graphs.py
         └─ remover.py
```

---

## Requirements

- **ParaView** with `pvbatch`/`pvpython` (EGL/OSMesa build recommended for headless)
- **Python** inside ParaView runtime
- Optional: **Pillow** (for GIF creation) – if your `gif_maker.py` uses PIL

Tip: verify paths:
```bash
which pvbatch
which pvpython
pvpython --version
```

---

## Configuration

One file: **`config.json`** at repo root (`traces/`). No environment overrides needed.

```json
{
  "paths": {
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
    "mode": "largest",
    "eps": 0.001,
    "x_start": null,
    "x_end": null,
    "solid_cuts": 30,
    "front_w": 256, "front_h": 256,
    "side_w":  256, "side_h":  256,
    "top_w":   256, "top_h":   256,
    "x_side_offset": 0.00007,
    "empty_out": true
  }
}
```

- All paths are **relative to repo root**.
- If `sim_path` points to a different run, just edit it here.
- `empty_out: true` clears `outputs/screenshots` before each run.

---

## Quick start

### Preflight
```bash
python src/bin/pv_config_check.py
```

### Run the pipeline (headless)
```bash
pvbatch src/bin/sph2img.py
```

**Output:**
- Screenshots → `outputs/screenshots/<run_name>/...`
- GIFs → `outputs/gifs/` (or adjacent, depending on `gif_maker.py`)
- Logs → `logs/`

---

## What it does (end-to-end)

1. **SPH interpolator**: builds SPH volume interpolator from `simulations/...`
2. **Slices & coloring**: sets up front/side/top slices and color maps
3. **Milestone screencapture**: iterates by mode (`laser`/`largest`/`solid`), saves frames at each milestone
4. **GIF**: composes frames into an animated GIF (same folder or `outputs/gifs/`)

---

## Running on HPC (Slurm example)

If `pvbatch` is available on compute nodes:

```bash
#!/usr/bin/env bash
#SBATCH -p gpu
#SBATCH -t 02:00:00
#SBATCH -J sph2img
#SBATCH -o logs/%x_%j.out
set -euo pipefail

# No env overrides needed; config.json is authoritative
python  src/bin/pv_config_check.py
pvbatch src/bin/sph2img.py
```

---

## Logging

- All scripts use `sph2img.utils.pvlog`.
- Log files are written to `logs/` (as configured).
- The headless driver prints a concise run summary (sim path, out path, run name).

---

## Development notes

- **Entry vs library**: keep runnable scripts in `src/bin/`; put all logic in `src/sph2img/`.
- **Immutability**: config objects are frozen dataclasses (safer, reproducible).
- **Imports**: `src/` is added to `PYTHONPATH` programmatically by entry scripts for clean `from sph2img...` imports.
- **Tests (optional)**: add `tests/` and import from `sph2img.*`.

---

## Troubleshooting

- **Black screenshots / X errors**: your ParaView build may not support offscreen on that node. Try an OSMesa/EGL build or run with a display.
- **“module not found”**: ensure you run from repo root (`traces/`) so `src/` path bootstrap works.
- **GIF not created**: check Pillow availability and where `gif_maker.py` writes (screenshots folder vs `outputs/gifs/`).

---

## FAQ

**Why no environment variables?**  
Simplicity. One `config.json` controls everything. Change it, commit it, done.

**Can I keep multiple configs (dev/prod)?**  
Yes—use `config.prod.json` and teach `sph2img/config.py` to prefer it, or just swap `config.json` as needed.

**Can I change per-view resolutions?**  
Yes—set `front_w/front_h`, `side_w/side_h`, `top_w/top_h` in `config.json`.

---

## License

Add your preferred license here.
