#!/usr/bin/env bash
# =============================================================================
# aersph_run_from_config.sh  (jq-free; uses Python stdlib json)
#
# Role
#   Single-entry launcher reading one JSON config and either:
#     - submits a batch job (sbatch via wrapper), or
#     - runs inside an existing allocation WITHOUT srun (wrapper --interactive).
#
#   Modes are selected by .mode in the JSON: "batch" | "interactive".
# =============================================================================
set -euo pipefail

CFG="${1:-}"
[[ -n "$CFG" && -f "$CFG" ]] || { echo "Usage: $0 /path/to/aersph_run_config.json" >&2; exit 1; }

# --- Tiny JSON accessor implemented in Python (no jq required) ---
pyget() {
python3 - "$CFG" "$1" <<'PY'
import sys, json
cfg_path, jp = sys.argv[1], sys.argv[2]
with open(cfg_path, 'r', encoding='utf-8') as f:
    d = json.load(f)

def get_path(d, path):
    if path == '.edits':
        return d.get('edits', [])
    cur = d
    parts = [p for p in path.strip().split('.') if p]
    for p in parts:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur

val = get_path(d, jp)
if jp == '.edits':
    for e in (val or []):
        # Emit triplets: --set \n PATH \n VALUE(JSON)
        print('--set')
        print(e[0])
        print(json.dumps(e[1], ensure_ascii=False))
else:
    if val is None:
        print("", end="")
    elif isinstance(val, (dict, list)):
        print(json.dumps(val, ensure_ascii=False))
    else:
        print(str(val))
PY
}

MODE="$(pyget '.mode')"
[[ "$MODE" == "batch" || "$MODE" == "interactive" ]] || { echo "[ERR] .mode must be batch|interactive"; exit 1; }

RUNNER="$(pyget '.paths.runner')"
SUBMIT="$(pyget '.paths.wrapper')"
CLEAN_AERSPH="$(pyget '.paths.clean_aersph')"
ENROOT_IMAGE="$(pyget '.paths.enroot_image')"
CONFIGURER_PY="$(pyget '.paths.configurer_py')"
TEMPLATE_XML="$(pyget '.paths.template_xml')"
RUNNING_ROOT="$(pyget '.paths.running_root')"
RESULTS_ROOT="$(pyget '.paths.results_root')"

KEEP="$(pyget '.runner_flags.keep_run_dir')"
DRY="$(pyget '.runner_flags.dry_run')"
[[ -z "${KEEP}" ]] && KEEP=false
[[ -z "${DRY}"  ]] && DRY=false

# Build EDITS array (triplets emitted by pyget .edits)
mapfile -t EDITS_TRIPLES < <(pyget '.edits')
EDITS=()
i=0
while (( i < ${#EDITS_TRIPLES[@]} )); do
  EDITS+=( "${EDITS_TRIPLES[i]}" "${EDITS_TRIPLES[i+1]}" "${EDITS_TRIPLES[i+2]}" )
  (( i+=3 ))
done

# Common runner args
RUNNER_ARGS=(
  --clean-aersph  "$CLEAN_AERSPH"
  --enroot-image  "$ENROOT_IMAGE"
  --configurer-py "$CONFIGURER_PY"
  --template-xml  "$TEMPLATE_XML"
  --running-root  "$RUNNING_ROOT"
  --results-root  "$RESULTS_ROOT"
)
[[ "$KEEP" == "true" ]] && RUNNER_ARGS+=( --keep-run-dir )
[[ "$DRY"  == "true" ]] && RUNNER_ARGS+=( --dry-run )
RUNNER_ARGS+=( -- )
RUNNER_ARGS+=( "${EDITS[@]}" )

# -------- Interactive path (no srun; wrapper will exec the runner directly) --------
if [[ "$MODE" == "interactive" ]]; then
  [[ -n "${SLURM_JOB_ID:-}" ]] || { echo "[ERR] interactive mode requires SLURM_JOB_ID (use salloc/srun --pty)"; exit 1; }
  echo "[INFO] mode=interactive → delegating to wrapper with --interactive (no srun will be used)"
  exec /bin/bash "$SUBMIT" --runner "$RUNNER" --interactive -- "${RUNNER_ARGS[@]}"
fi

# -------- Batch path (submit via wrapper → sbatch) --------
JOB_NAME="$(pyget '.slurm.job_name')"
PARTITION="$(pyget '.slurm.partition')"
GRES="$(pyget '.slurm.gres')"
CPUS_PER_TASK="$(pyget '.slurm.cpus_per_task')"
MEM="$(pyget '.slurm.mem')"
TIME="$(pyget '.slurm.time')"

QOS="$(pyget '.slurm.qos')"
OUTPUT="$(pyget '.slurm.output')"
ERRORF="$(pyget '.slurm.error')"
ARRAY="$(pyget '.slurm.array')"
CONSTRAINT="$(pyget '.slurm.constraint')"
ACCOUNT="$(pyget '.slurm.account')"
MAIL_TYPE="$(pyget '.slurm.mail_type')"
MAIL_USER="$(pyget '.slurm.mail_user')"

# Build sbatch option array safely
SBATCH_OPTS=(
  --job-name "$JOB_NAME"
  --partition "$PARTITION"
  --gres "$GRES"
  --cpus-per-task "$CPUS_PER_TASK"
  --mem "$MEM"
  --time "$TIME"
)
[[ -n "$QOS"        ]] && SBATCH_OPTS+=( --qos "$QOS" )
[[ -n "$OUTPUT"     ]] && SBATCH_OPTS+=( --output "$OUTPUT" )
[[ -n "$ERRORF"     ]] && SBATCH_OPTS+=( --error "$ERRORF" )
[[ -n "$ARRAY"      ]] && SBATCH_OPTS+=( --array "$ARRAY" )
[[ -n "$CONSTRAINT" ]] && SBATCH_OPTS+=( --constraint "$CONSTRAINT" )
[[ -n "$ACCOUNT"    ]] && SBATCH_OPTS+=( --account "$ACCOUNT" )
[[ -n "$MAIL_TYPE"  ]] && SBATCH_OPTS+=( --mail-type "$MAIL_TYPE" )
[[ -n "$MAIL_USER"  ]] && SBATCH_OPTS+=( --mail-user "$MAIL_USER" )

echo "[INFO] mode=batch → submitting via wrapper/sbatch"
exec /bin/bash "$SUBMIT" \
  --runner "$RUNNER" \
  "${SBATCH_OPTS[@]}" \
  -- \
  "${RUNNER_ARGS[@]}"

