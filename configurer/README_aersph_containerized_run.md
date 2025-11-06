# AERSPH Containerized Run — Complete Pack (no "direct" mode)

Contents:
- `scripts/aersph_containerized_run_runner.sh` — header-less runner.
- `scripts/submit_aersph_containerized_run.sh` — Slurm wrapper (no defaults).
- `scripts/aersph_run_from_config.sh` — unified JSON launcher (**batch** / **interactive** only).
- `aersph_run_config.json` — single JSON config consumed by the unified launcher.

## Operation

1. **Runner**: builds a per-run workspace, converts XML→JSON (`configurer.py`), runs `./AERSPH` in an Enroot container, moves results, writes a summary.
2. **Wrapper**: `sbatch`/`srun` frontend; forwards runner args.
3. **Unified launcher**: reads one JSON, chooses **batch** or **interactive**, and expands all flags.

## Invariants

- All paths are explicit. No hidden defaults.
- `RUN_ID = j-<SLURM_JOB_ID>_p-<SLURM_PROCID>`.
- No hashing or timestamps in names.
- Container mandatory; solver fixed: `./AERSPH` inside the mounted run directory.

---

## Required resources and environment (explicit)

These scripts assume the following resources exist and are accessible from the node where they run. Replace placeholder paths with your real ones in `aersph_run_config.json`.

### 1) Files & directories

| Resource | Description | Expected Path (example) | Must exist |
|---|---|---|---|
| **Clean AERSPH tree** | A clean copy of the solver tree containing the `AERSPH` binary and its runtime assets. This tree is copied into each run workspace. | `/proj/clean_files/aersph` | **Yes (dir)** |
| **Enroot image (.sqsh)** | Container image with all runtime dependencies needed by AERSPH. | `/proj/clean_files/aersph-enroot-image.sqsh` | **Yes (file)** |
| **Configurer script** | Python tool that converts the XML template and applies edits to produce the JSON config expected by AERSPH. | `/proj/scripts/helper_scripts/configurer.py` | **Yes (file)** |
| **XML template** | Base solver configuration (XML) to be converted to JSON and edited. | `/proj/clean_files/aersph_containerized_run_configuration.xml` | **Yes (file)** |
| **Running root** | Parent directory where per-run workspaces will be created. The runner creates `<running_root>/j-<job>_p-<proc>/aersph/`. | `/proj/currently_running` | **Yes (dir, writable)** |
| **Results root** | Parent directory where final results are moved to. | `/proj/runs_results` | **Yes (dir, writable)** |
| **Log paths (optional)** | If using `--output/--error` in Slurm, their parent dirs must exist. | `/proj/logs/` | Optional but recommended |

### 2) Software & system

| Requirement | Why | How to check |
|---|---|---|
| **Slurm** | Batch/interactive scheduling. | `sinfo`, `srun --version`, `sbatch --version` |
| **GPU allocation** | AERSPH requires GPU; allocate with `--gres=gpu:1` (or more). | `nvidia-smi` shows a device in the allocation |
| **Enroot** | Container runtime used by the runner. | `enroot --version` |
| **Python 3** | Runs `configurer.py`. | `python3 --version` |
| **jq** | JSON parsing in the unified launcher and helpers. | `jq --version` |
| **Writable FS** | Space for workspaces and results. | `df -h <running_root> <results_root>` |
| **Permissions** | You must be able to read source files and write to roots. | `touch` in roots; `ls -l` on inputs |

### 3) Enroot execution semantics

- Runner creates a named container `aersph_j-<job>_p-<proc>` from the provided `.sqsh` and starts it with:
  - `--mount "<run_dir>:/mnt/aersph"`
  - Entry command: `bash -lc 'cd /mnt/aersph && ./AERSPH cfg_j-<job>_p-<proc>.json'`
- The container must have a working runtime for `./AERSPH` (libraries, drivers where needed).
- The host allocation must expose the GPU to Enroot (cluster default should cover this).

### 4) Slurm assumptions

- **Batch mode**: You must pass all required Slurm flags (`--job-name`, `--partition`, `--gres`, `--cpus-per-task`, `--mem`, `--time`). The wrapper does not embed defaults.
- **Interactive mode**: Use `salloc` or equivalent first; the unified launcher then runs with `srun --exclusive`. `SLURM_JOB_ID` must be present.

---

## JSON schema (`aersph_run_config.json`)

```jsonc
{
  "mode": "batch | interactive",
  "paths": {
    "wrapper": "/abs/path/submit_aersph_containerized_run.sh",
    "runner": "/abs/path/aersph_containerized_run_runner.sh",
    "clean_aersph": "/abs/path/clean_files/aersph",
    "enroot_image": "/abs/path/aersph-enroot-image.sqsh",
    "configurer_py": "/abs/path/configurer.py",
    "template_xml": "/abs/path/template.xml",
    "running_root": "/abs/path/currently_running",
    "results_root": "/abs/path/runs_results"
  },
  "slurm": {
    "job_name": "aersph_containerized_run",
    "partition": "lrz-hgx-h100-94x4",
    "gres": "gpu:1",
    "cpus_per_task": 4,
    "mem": "32G",
    "time": "48:00:00",
    "qos": "",
    "output": "/path/logs/slurm-%x-%j.out",
    "error": "/path/logs/slurm-%x-%j.err",
    "array": "",
    "constraint": "",
    "account": "",
    "mail_type": "",
    "mail_user": ""
  },
  "runner_flags": {
    "keep_run_dir": false,
    "dry_run": false
  },
  "edits": [
    ["/reference_values/velocity", 6.5],
    ["/rendering/resolution", [640, 320, 320]]
  ]
}
```

- `edits` are forwarded as repeated `--set PATH VALUE` for `configurer.py`. `VALUE` can be a number or a JSON array.

---

## Usage

```bash
# Batch (submit to queue)
scripts/aersph_run_from_config.sh ./aersph_run_config.json

# Interactive (within existing allocation)
# 1) salloc --partition=lrz-hgx-h100-94x4 --gres=gpu:1 --cpus-per-task=4 --mem=32G --time=02:00:00
# 2) scripts/aersph_run_from_config.sh ./aersph_run_config.json   # with "mode": "interactive"
```

## Inputs → Outputs (workflow)

1. **Inputs** (from config): clean solver tree, enroot image, XML template, edits.
2. **Runner**:
   - Copies clean tree → `<running_root>/j-<job>_p-<proc>/aersph/`
   - Generates JSON: `cfg_j-<job>_p-<proc>.json` into that directory.
   - Runs containerized `./AERSPH <json>`; solver writes `<json_basename>/...` next to the JSON.
3. **Outputs**:
   - Moved to `<results_root>/j-<job>_p-<proc>/cfg_j-<job>_p-<proc>/...`
   - Summary: `<results_root>/j-<job>_p-<proc>/experiment_summary.txt`

## Validation checklist (pre-flight)

- [ ] `enroot --version` works on the compute node.
- [ ] `jq --version` works on the submit and/or compute node.
- [ ] `python3` available; `python3 <configurer_py> --help` prints usage.
- [ ] `AERSPH` exists and is executable in the clean solver tree.
- [ ] Sufficient disk space on `running_root` and `results_root`.
- [ ] Slurm partition and QoS are correct for GPUs in your site.
- [ ] Log directories exist if you set `slurm.output` / `slurm.error`.

## Troubleshooting

- **Runner aborts: `SLURM_JOB_ID is required`**  
  Ensure you’re running via the wrapper/launcher in batch or in a proper interactive allocation.

- **`enroot not in PATH`**  
  Load the site module or add Enroot to PATH; re-run the job/allocation so the compute node has it.

- **JSON not produced**  
  Check `configurer.py` errors; validate your `edits` paths and types against the XML.

- **No output directory from solver**  
  The runner keeps the workspace for inspection; review logs and the mounted run directory.

- **Containers fail to start**  
  Verify the `.sqsh` image exists and the GPU is visible in the allocation (`nvidia-smi`).

---

## Security and isolation

- Workspaces are per-run under `<running_root>/j-<job>_p-<proc>/`.  
- Results are copied out and the workspace is removed unless `keep_run_dir` is set.

---

## Versioning tips

- Keep the Enroot image name/version in sync with the solver build used to populate the clean tree.  
- Prefer immutable paths (e.g., versioned directories) and track changes in Git for `configurer.py` and templates.

