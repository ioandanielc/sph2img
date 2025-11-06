# Step‑1 Minimal‑Change Rollout — Update Configs + Runner Only

Objective: enable a **sequential, single‑allocation** pipeline (`sim → stats → images → (delete)`) by changing **only**:
1) central JSON configs (`RUN.json` + tool templates), and  
2) the common headless runner (`aersph_containerized_run_runner.sh`).

A fail‑fast *preflight* reservation can be added later; not required for step‑1.

---

## A) Config changes (JSON only, no code)

### 1. `RUN.json` (central “big” config)
Keep the structure you already use (mode, paths, slurm/resources, runner_flags, edits). Ensure these keys are set:

- **Base roots**
  - `.paths.results_root` — **base only** (no per‑run subfolder here).  
  - (Optional) `.paths.running_root` if the runner still needs a working area.

- **Simulation contract**
  - `.sim.output_map` → `"vtk_dir": "sim_outputs/vtk"`, `"monitor_dir": "sim_outputs/monitor"`  
    → enforces the canonical SIM layout under the per‑run directory.

- **Stat tester (late‑bound sim path)**
  - `.stats.tool_config.defaults.single_run.sim` → `"AUTO"` (the runner fills with `SIM_PATH`).

- **sph2img (late‑bound sim path)**
  - `.images.sph2img.host_paths.sim_path` → `"AUTO"`
  - `.images.sph2img.capturer.paths.sim_path` → `"AUTO"`

- **Optional env-first**
  - Add `.env` for TZ/threads/etc., if desired. The runner exports them once per run.

### 2. Stat tester template (tool config)
- Keep your template as‑is but with:  
  `defaults.single_run.sim = "AUTO"`  
- At runtime, the runner writes `cfg/stat_tester.config.json` with `sim = SIM_PATH` and (optionally) coerces `paths.results_parent = "${RESULTS_RUN_DIR}/stats"`.

### 3. sph2img templates
- Keep your templates; ensure **both** have `sim_path = "AUTO"`:  
  - `sph2img.host_paths.json`  
  - `sph2img.capturer.json`  
- At runtime, the runner writes the materialized files under `cfg/` with `sim_path = SIM_PATH`.

---

## B) Runner changes (`aersph_containerized_run_runner.sh`)

Implement sequential orchestration and late binding; do **not** change wrappers or other scripts.

1) **Per‑run directories**
```
RESULTS_RUN_DIR = <results_root>/j-<RUN_ID>_p-<PROCID>
SIM_PATH        = ${RESULTS_RUN_DIR}/sim_outputs
mkdir -p ${RESULTS_RUN_DIR}/{cfg,logs,manifests,stats,post_proc_screenshots,sim_outputs/{monitor,vtk}}
```
- `RUN_ID`: use `$SLURM_JOB_ID` (batch) or timestamp+host+pid (interactive).

2) **Simulation**
- Materialize `cfg/cfg_sim.json` from XML + `.edits` so outputs land under `SIM_PATH/{monitor,vtk}`.
- Run containerized AERSPH.
- Write `manifests/sim_manifest.json` with:  
  `{"sim":{"path":SIM_PATH,"monitor_dir":..., "vtk_dir":...},"cfg_json":"cfg/cfg_sim.json","status":"ok"}`

3) **Statistics**
- Read `SIM_PATH` from `sim_manifest.json`.
- Materialize `cfg/stat_tester.config.json` (inject `sim = SIM_PATH`).
- Call:  
  `python stat_tester.py run --sim "$SIM_PATH" --out "${RESULTS_RUN_DIR}/stats" --tol ... --win ...`

4) **Images**
- Materialize `cfg/sph2img.host_paths.json` and `cfg/sph2img.capturer.json` (inject `sim_path = SIM_PATH`).
- Call pvbatch/sph2img, then post‑ops (move GIFs, copy tagged PNGs).

5) **(Optional) Delete**
- Constrain deletion to `${RESULTS_RUN_DIR}`; respect keep/remove globs from config.

---

## Command skeletons (unchanged UX)

**Batch**
```bash
# submit via your existing wrapper/launcher
scripts/aersph_run_from_config.sh /path/to/aersph_run_config_batch.json
```

**Interactive**
```bash
# inside an allocation
scripts/aersph_run_from_config.sh /path/to/aersph_run_config_interactive.json
```

---

## Why this is sufficient for Step‑1

- Downstream tools (`stat_tester`, `sph2img`) only require **SIM_PATH**.  
- Runner becomes the single place that decides per‑run dirs and fills `"AUTO"` fields.  
- No changes to wrappers or submission flow; only configs + the runner are touched.

---

## Optional (later): fail‑fast preflight

Add a small login‑node wrapper that **creates** `RESULTS_RUN_DIR` **before** `sbatch` and **aborts if it exists**. This avoids allocating resources when a name collision would later fail.
