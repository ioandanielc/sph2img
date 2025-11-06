# Runner‑Centric Pipeline Plan (v4) — Sequential, Env‑First, Hard‑Constrained Preflight

This version keeps the **big predicted config** (central `RUN.json`), enforces a **strict sequential order** (`simulation → statistics → images → (optional) delete`), and adds a **hard‑constrained preflight reservation** so the run directory is fixed and guaranteed unique **before** any Slurm allocation.

---

## Global Config — `RUN.json` (kept as in v3)

> The following block is the canonical, *predicted* config schema and example used by the runner and all tools. It remains unchanged here and is the single source of truth for paths, resources, and per‑tool defaults. Comments use JSONC style for readability.

```jsonc
{
  "meta": { "name": "lp-200_vx-0p4_caseA", "timezone": "Europe/Berlin" },

  "resources": {
    "partition": "lrz-hgx-h100-94x4",
    "gpus_sim": 1, "cpus_sim": 4, "mem_sim_gb": 32,
    "gpus_stats": 0, "cpus_stats": 4, "mem_stats_gb": 16,
    "gpus_images": 0, "cpus_images": 4, "mem_images_gb": 16,
    "time_limit_h": 6
  },

  "paths": {
    "enroot_image": "/abs/aersph.sqsh",
    "clean_aersph": "/abs/clean/AERSPH",
    "xml_template": "/abs/aersph_containerized_run_configuration.xml",
    "configurer_py": "/abs/configurer.py",
    "work_root": "/abs/work",
    "results_root": "/abs/results",

    "stat_tester_py": "/abs/aersph_stat_checker/src/aersph_stat_checker/stat_tester.py",
    "sph2img_bin": "/abs/sph2img/bin/run_pipeline_single_mode.py",
    "pvbatch_bin": "/abs/ParaView/pvbatch"
  },

  "sim": {
    "edits": { "laser.power": 200.0, "vel.x": 0.4 },
    "extra_mounts": ["/data:/data:rw"],
    "env": { "OMP_NUM_THREADS": "4" },
    "output_map": { "vtk_dir": "sim_outputs/vtk", "monitor_dir": "sim_outputs/monitor" },
    "fail_policy": "abort"
  },

  "stats": {
    "enabled": true,
    "tol": 0.045,
    "win": 500,
    "out_suffix": "stability_bidirectional_rsd",
    "lists_only": false,
    "extra_args": [],
    "fail_policy": "abort",

    // === tool-config mapping (stat_tester config.json) ===
    "tool_config": {
      "version": 1,
      "runtime": { "timezone": "Europe/Berlin" },
      "paths": {
        "project_root": "/abs/aersph_stat_checker",
        "results_parent": "/abs/aersph_stat_checker/stat_results",
        "logs_dir": "/abs/aersph_stat_checker/logs",
        "simulations_root": "/abs/sph2img/simulations"
      },
      "defaults": {
        "single_run": {
          "sim": "AUTO",      // replaced by manifests.sim.path at runtime
          "tol": 0.045,
          "win": 500,
          "out_suffix": "stability_bidirectional_rsd"
        },
        "batch": { "out_dir_base": "/abs/aersph_stat_checker/stat_results" }
      }
    }
  },

  "images": {
    "enabled": true,
    "mode": "largest",                        // normalized to tool’s lowercase
    "screenshots_parent": "post_proc_screenshots",
    "move_gifs_to": "post_proc_screenshots/gifs",
    "copy_tagged_to": "post_proc_screenshots/tagged",
    "gif": { "fps": 12, "loop": 0 },
    "extra_args": [],
    "fail_policy": "abort",

    // === tool-config mapping (sph2img) ===
    "sph2img": {
      "host_paths": {
        "abs_root": "/Users/ioandanielcraciun",
        "sim_path": "AUTO",     // replaced by manifests.sim.path
        "out_dir":  "outputs/",
        "logs_dir": "logs",
        "cache_dir": ".cache"
      },
      "capturer": {
        "name": { "run_name": "ss" },
        "paths": {
          "abs_root": "~",
          "sim_path": "AUTO",   // replaced by manifests.sim.path
          "out_dir":  "outputs/",
          "logs_dir": "logs",
          "cache_dir": ".cache"
        },
        "render": { "offscreen": true, "image_w": 256, "image_h": 256 },
        "capture": {
          "mode": "largest",
          "eps": 0.001,
          "x_start": null, "x_end": null, "solid_cuts": 30,
          "front_w": 256, "front_h": 256,
          "side_w":  512, "side_h":  256,
          "top_w":   256, "top_h":   256,
          "x_side_offset": 0.00007,
          "empty_out": true
        },
        "files_removal": { "post_delete": false },
        "paraview": { "testing": false, "default_view": "RenderView" }
      }
    }
  },

  "delete": {
    "enabled": false, "dry_run": true,
    "keep_patterns": ["manifests/**","logs/**","stats/**","post_proc_screenshots/**","cfg/**","README*","*.md"],
    "remove_patterns": ["sim_outputs/vtk/**","sim_outputs/monitor/**","tmp/**"],
    "fail_policy": "abort"
  }
}
```

---

## Sequential Orchestration (unchanged)

- All components are executed **in order** by `aersph_containerized_run_runner.sh` **within one allocation**.  
- `srun` steps: **Sim → Stats → Images → (Delete)**.  
- Contracts between steps are expressed via **manifests** and **materialized tool configs** under `RESULTS_RUN_DIR/cfg/`.

---

## Hard‑Constrained Preflight (new, strict)

**Goal:** guarantee a unique per‑run directory **before** Slurm allocation to avoid queueing for hours only to fail due to a name collision.

**Policy:** **fail‑fast** if the planned path already exists. No suffixing, no auto‑rename.

**Where:** run on the **login node** prior to `sbatch`/`salloc`.

### Deterministic naming & reservation

```
RESULTS_ROOT    ← from RUN.json: .paths.results_root
RUN_BASE        ← j-<TIMESTAMP_HOST_PID>_p-0         # submit-time identifier
RESULTS_RUN_DIR ← ${RESULTS_ROOT}/${RUN_BASE}
SIM_PATH        ← ${RESULTS_RUN_DIR}/sim_outputs     # canonical contract for downstream
```

**Preflight snippet**

```bash
set -euo pipefail
RUN_JSON="/abs/RUN.json"

RESULTS_ROOT="$(jq -r '.paths.results_root' "$RUN_JSON")"
mkdir -p "${RESULTS_ROOT}"
RUN_BASE="$(date +%F_%H-%M-%S-%3N)_${HOSTNAME}_$$"
RESULTS_RUN_DIR="${RESULTS_ROOT}/j-${RUN_BASE}_p-0"

# Hard constraint: abort if exists
if ! mkdir -m 750 "${RESULTS_RUN_DIR}"; then
  echo "[preflight] run directory already exists: ${RESULTS_RUN_DIR}" >&2
  exit 2
fi

# Optional marker
date -Is > "${RESULTS_RUN_DIR}/.reserved_at"

# Batch submit with reserved dir exported
sbatch --export=ALL,RESULTS_RUN_DIR="${RESULTS_RUN_DIR}" submit_aersph_containerized_run.sh --cfg "$RUN_JSON"

# Interactive:
# export RESULTS_RUN_DIR; salloc ...; aersph_run_from_config.sh --cfg "$RUN_JSON"
```

**Inside allocation (runner requires it):**
```bash
: "${RESULTS_RUN_DIR:?preflight must export RESULTS_RUN_DIR}"
umask 0027
mkdir -p "${RESULTS_RUN_DIR}"/{cfg,logs,manifests,stats,post_proc_screenshots,sim_outputs/{monitor,vtk}}
SIM_PATH="${RESULTS_RUN_DIR}/sim_outputs"
```

---

## Manifests (authoritative hand‑off)

### `manifests/preflight_manifest.json` *(new)*
```json
{
  "reserved_at": "2025-11-05T12:09:22+01:00",
  "results_root": "/abs/results",
  "results_run_dir": "/abs/results/j-2025-11-05_12-09-22-413_login-04_12345_p-0",
  "sim_path": "/abs/results/j-2025-11-05_12-09-22-413_login-04_12345_p-0/sim_outputs",
  "policy": "hard-constrained",
  "status": "reserved"
}
```

### `manifests/sim_manifest.json`
```json
{
  "sim": {
    "path": "/abs/.../sim_outputs",
    "monitor_dir": "/abs/.../sim_outputs/monitor",
    "vtk_dir": "/abs/.../sim_outputs/vtk"
  },
  "cfg_json": "/abs/.../cfg/cfg_sim.json",
  "started_at": "2025-11-05T12:20:00+01:00",
  "finished_at": "2025-11-05T12:50:12+01:00",
  "status": "ok"
}
```

### `manifests/stats_manifest.json`
```json
{
  "stats": {
    "out_dir": "/abs/.../stats/statistics_05-11-2025_12-53-01-311",
    "stable_longest_vtk": [11002,11004,11006],
    "unstable_vtk": [12002,12004],
    "triptych_png": "/abs/.../rolling_rsd_triptych.png"
  },
  "tool_config": "cfg/stat_tester.config.json",
  "status": "ok"
}
```

### `manifests/images_manifest.json`
```json
{
  "images": {
    "screenshots_parent": "/abs/.../post_proc_screenshots/screenshots_2025-11-05_12-59-10-402-mode-LARGEST-power-200-vx-0p4",
    "gifs_dir": "/abs/.../post_proc_screenshots/gifs",
    "tagged_dir": "/abs/.../post_proc_screenshots/tagged"
  },
  "tool_configs": {
    "sph2img_host": "cfg/sph2img.host_paths.json",
    "sph2img_capturer": "cfg/sph2img.capturer.json"
  },
  "status": "ok"
}
```

### `manifests/delete_manifest.json`
```json
{
  "delete": {
    "dry_run": true,
    "removed": [],
    "kept": ["manifests/**","logs/**","stats/**","post_proc_screenshots/**","cfg/**","README*","*.md"]
  },
  "status": "ok"
}
```

---

## Items in Config Affected by the Hard Constraint

**Affected (runtime‑filled or overridden):**
- `.paths.results_root` — **base only**. The per‑run directory name is **not** in config; it is reserved by preflight and exported as `RESULTS_RUN_DIR`.
- `.sim.output_map` — must resolve under `${RESULTS_RUN_DIR}/sim_outputs/{monitor,vtk}` so the sim writes into the canonical contract.
- `.stats.tool_config.defaults.single_run.sim` — filled at runtime with `SIM_PATH`.
- `.images.sph2img.host_paths.sim_path` and `.images.sph2img.capturer.paths.sim_path` — both filled at runtime with `SIM_PATH`.
- `.stats.tool_config.paths.results_parent` — coerced to `${RESULTS_RUN_DIR}/stats` to keep all artifacts under the reserved run directory.

**Unaffected:**
- `.resources.*` (Slurm sizing), `.delete.*` (kept—but now scoped under `RESULTS_RUN_DIR`), `render/capture` defaults, tolerances, etc.

---

## Biggest Hurdle to Overcome (and how this solves it)

**Hurdle:** If the per‑run results directory is not fixed before allocation, later stages can dereference wrong or stale paths—often discovered only after long queue and compute times.

**Solution:** The **hard‑constrained preflight** makes the run directory decision up front, atomically reserves it, and **aborts immediately** on a name collision (no Slurm allocation). The runner then enforces a single canonical **`SIM_PATH`** for all downstream tools, materializing tool configs only **after** simulation finishes. Path drift disappears; failures become fast and deterministic.

---

## Command Skeletons (for reference)

**Batch submit (after preflight reservation)**
```bash
sbatch --export=ALL,RESULTS_RUN_DIR="${RESULTS_RUN_DIR}" submit_aersph_containerized_run.sh --cfg /abs/RUN.json
```

**Interactive**
```bash
export RESULTS_RUN_DIR; salloc -p lrz-hgx-h100-94x4 --gres=gpu:1 --cpus-per-task=4 --mem=32G --time=06:00:00
aersph_run_from_config.sh --cfg /abs/RUN.json
```

**Runner (inside allocation): Sim → Stats → Images → (Delete) using SIM_PATH**
```bash
SIM_PATH="${RESULTS_RUN_DIR}/sim_outputs"
# Sim writes to SIM_PATH
# Stats:  python .../stat_tester.py run --sim "$SIM_PATH" --out "${RESULTS_RUN_DIR}/stats" --tol ... --win ...
# Images: pvbatch .../run_pipeline_single_mode.py --host-config cfg/... --capturer-config cfg/...  (both use SIM_PATH)
# Delete: confined to ${RESULTS_RUN_DIR}
```
