# AERSPH Containerized Run — End‑to‑End Pipeline

Concise documentation of the launcher → Slurm wrapper → runner → configurator chain used to execute AERSPH inside an Enroot container. Focus on who calls whom, inputs/outputs at each hop, and minimal commands for batch and interactive usage.

---

## Overview

**Single entrypoint** for both modes: `aersph_run_from_config.sh <RUN_CONFIG.json>`  
- Decides between **batch** (via `sbatch`) and **interactive** (direct execution inside an allocation).  
- For batch, the Slurm wrapper schedules the **runner**, which performs configuration and launches the containerized solver.

---

## Call Graph

```
aersph_run_from_config.sh                      # unified launcher
 ├─(batch)──> submit_aersph_containerized_run.sh   # sbatch wrapper
 │             └─sbatch──> Slurm scheduler
 │                    └─runs──> aersph_containerized_run_runner.sh    # main runner
 │                                   ├──> configurer.py                # XML → final JSON config
 │                                   └──> Enroot container → ./AERSPH <cfg.json>
 └─(interactive)──> aersph_containerized_run_runner.sh  # run directly inside allocation
                     ├──> configurer.py
                     └──> Enroot container → ./AERSPH <cfg.json>
```

Artifacts involved:
- XML template: `aersph_containerized_run_configuration.xml`
- Slurm wrapper: `submit_aersph_containerized_run.sh`
- Unified launcher: `aersph_run_from_config.sh`
- Runner: `aersph_containerized_run_runner.sh`
- Configurator: `configurer.py`

---

## End‑to‑End Flows

### A) Batch (queued via Slurm)

1. **Launcher** `aersph_run_from_config.sh` parses `<RUN_CONFIG.json>` and constructs the command line for the wrapper.
2. **Wrapper** `submit_aersph_containerized_run.sh` passes Slurm options and the runner invocation to `sbatch`.
3. **Slurm** allocates resources and executes `aersph_containerized_run_runner.sh` on the compute node.
4. **Runner** prepares workspace, calls `configurer.py` to materialize `cfg_<job>_<proc>.json` from the XML template and edits, then launches the **Enroot** container to run `./AERSPH <cfg.json>`. On completion, it relocates outputs and writes a summary.

### B) Interactive (inside an allocation)

1. Obtain an allocation (e.g., `salloc …` or using an existing interactive job).
2. **Launcher** `aersph_run_from_config.sh` detects interactive mode and **directly** runs `aersph_containerized_run_runner.sh` with the same arguments as the batch path.
3. **Runner** performs the same steps as in batch: configure, run containerized solver, collect outputs, summarize.

---

## Inputs & Outputs per Component

### `aersph_run_from_config.sh` (Launcher)
**Input**
- Run configuration JSON: paths to wrapper, runner, Enroot image, clean AERSPH tree, `configurer.py`, XML template, results root, temporary workspace root, and either Slurm or interactive flags.
- Optional per‑run edits/overrides for configuration.

**Output**
- Either: `sbatch submit_aersph_containerized_run.sh …` (batch)  
- Or: direct invocation of `aersph_containerized_run_runner.sh …` (interactive)

---

### `submit_aersph_containerized_run.sh` (Slurm wrapper; batch only)
**Input**
- Slurm parameters (partition, gres, cpus, mem, time, qos, output/error paths, arrays, etc.).
- Path to `aersph_containerized_run_runner.sh` and its arguments.

**Output**
- Scheduled Slurm job; on start, the job executes the **runner** with the provided arguments.

---

### `aersph_containerized_run_runner.sh` (Runner)
**Input**
- Paths: clean AERSPH tree, Enroot image (`.sqsh`), `configurer.py`, XML template, work/results roots.
- Metadata: job/proc identifiers, run mode, environment setup flags.
- Config edits: numeric/text replacements to apply on top of the XML template.

**Actions**
- Creates a timestamped working directory.
- Calls `configurer.py` to render the final JSON config from the XML template plus edits.
- Starts the Enroot container; executes `./AERSPH <cfg.json>` inside.
- Upon exit: gathers logs and outputs; moves/renames into structured results; writes a run summary.

**Output**
- Final JSON config used by the solver.
- Solver logs and artifacts under the chosen results root, typically under `j-<JOBID>_p-<PROCID>/…` hierarchy.
- Summary file (paths, timings, return codes).

---

### `configurer.py` (Configurator)
**Input**
- XML template: `aersph_containerized_run_configuration.xml`
- Edit instructions received from the runner (CLI flags or environment), possibly sourced from the launcher’s JSON.

**Output**
- Validated `cfg_*.json` consumed by the solver inside the container.
- Optional sanity checks or echo of applied overrides.

---

## Minimal Commands

### Batch execution
```bash
# Single entrypoint (reads RUN_CONFIG.json and submits a Slurm job)
./aersph_run_from_config.sh /path/to/RUN_CONFIG.json
```

### Interactive execution
```bash
# Obtain an allocation first (example only; adjust for LRZ)
salloc -p <partition> --gres=gpu:1 --cpus-per-task=4 --mem=32G --time=02:00:00

# Run the same entrypoint in interactive mode (as configured in RUN_CONFIG.json)
./aersph_run_from_config.sh /path/to/RUN_CONFIG.json
```

---

## Configuration Notes

- The XML template remains the single source; `configurer.py` applies edits and emits JSON for the solver.
- The runner is the only component that touches the container runtime and the solver binary.
- The wrapper carries no domain logic; it only declares Slurm directives and forwards arguments.
- The launcher owns the policy of **which** path (batch vs interactive) is taken and assembles arguments consistently.

---

## Directory & Artifact Conventions

- **Workspace**: one timestamped folder per run under a designated work root (created by the runner).
- **Results**: collected under a stable results root; per‑job subfolders include identifiers to allow later correlation.
- **Configs**: final JSON is versioned alongside outputs; the original XML and applied edits can be archived for reproducibility.

---

## Troubleshooting (quick)

- **Job submitted but runner not found**: verify the wrapper receives an absolute path to `aersph_containerized_run_runner.sh` and that it is executable on compute nodes.
- **Config mismatches**: ensure the XML template path and edit set are consistent; confirm the generated JSON path is the file passed to the solver.
- **Container launch issues**: confirm the Enroot image path and required mounts; test with a minimal `enroot start … /bin/true` to isolate environment problems.
- **Path ownership/permissions**: results and work roots must be writable on compute nodes; set explicit `--output/--error` paths in Slurm to capture early failures.

---

## Files (this repo snapshot)

- `aersph_run_from_config.sh` — unified launcher (batch/interactive)
- `submit_aersph_containerized_run.sh` — Slurm wrapper
- `aersph_containerized_run_runner.sh` — main runner that configures and launches the containerized solver
- `configurer.py` — XML→JSON configurator
- `aersph_containerized_run_configuration.xml` — base template for solver configuration
- `README_aersph_containerized_run.md` — additional usage notes
