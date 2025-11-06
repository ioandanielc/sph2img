#!/usr/bin/env bash
# =============================================================================
# submit_aersph_containerized_run.sh
#
# Role
#   Front-end for launching aersph_containerized_run_runner.sh via Slurm.
#   - Batch (default): submit with sbatch using --wrap (no temp files).
#   - Interactive:     run runner directly inside existing allocation (NO srun).
# =============================================================================
set -euo pipefail

RUNNER=""
INTERACTIVE=false
DRY_RUN=false

# Slurm options (no defaults inside the script)
JOB_NAME=""
PARTITION=""
GRES=""
CPUS_PER_TASK=""
MEM=""
TIME=""
QOS=""
OUTPUT_FILE=""
ERROR_FILE=""
ARRAY_SPEC=""
CONSTRAINT_STR=""
ACCOUNT=""
MAIL_TYPE=""
MAIL_USER=""

print_help() {
  cat <<'USAGE'
submit_aersph_containerized_run.sh --runner PATH [--interactive] [SLURM_OPTS...] -- [RUNNER_ARGS...]

Batch (no internal defaults; all required must be passed):
  --job-name NAME     --partition PART   --gres VAL   --cpus-per-task N
  --mem MEM           --time T

Optional:
  --qos QOS           --output FILE      --error FILE
  --array SPEC        --constraint STR   --account ACCT
  --mail-type TYPE    --mail-user EMAIL  --dry-run

Interactive:
  --interactive       Run the runner directly inside the current allocation.
                      (No srun is used. Requires SLURM_JOB_ID in env.)
USAGE
}

RUNNER_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --runner)           RUNNER="${2:?}"; shift 2 ;;
    --interactive)      INTERACTIVE=true; shift ;;
    --job-name)         JOB_NAME="${2:?}"; shift 2 ;;
    --partition)        PARTITION="${2:?}"; shift 2 ;;
    --gres)             GRES="${2:?}"; shift 2 ;;
    --cpus-per-task)    CPUS_PER_TASK="${2:?}"; shift 2 ;;
    --mem)              MEM="${2:?}"; shift 2 ;;
    --time)             TIME="${2:?}"; shift 2 ;;
    --qos)              QOS="${2:-}"; shift 2 ;;
    --output)           OUTPUT_FILE="${2:-}"; shift 2 ;;
    --error)            ERROR_FILE="${2:-}"; shift 2 ;;
    --array)            ARRAY_SPEC="${2:-}"; shift 2 ;;
    --constraint)       CONSTRAINT_STR="${2:-}"; shift 2 ;;
    --account)          ACCOUNT="${2:-}"; shift 2 ;;
    --mail-type)        MAIL_TYPE="${2:-}"; shift 2 ;;
    --mail-user)        MAIL_USER="${2:-}"; shift 2 ;;
    --dry-run)          DRY_RUN=true; shift ;;
    -h|--help)          print_help; exit 0 ;;
    --)                 shift; RUNNER_ARGS=( "$@" ); break ;;
    *) echo "Unknown option: $1" >&2; print_help; exit 1 ;;
  esac
done

[[ -n "$RUNNER" && -x "$RUNNER" ]] || { echo "ERROR: --runner must be an executable runner script"; exit 1; }

# ---------------------- INTERACTIVE PATH ----------------------
# Run the runner directly inside an existing allocation (no srun).
if $INTERACTIVE; then
  [[ -n "${SLURM_JOB_ID:-}" ]] || { echo "ERROR: --interactive requires SLURM_JOB_ID (start with salloc or srun --pty)"; exit 1; }
  export SLURM_PROCID="${SLURM_PROCID:-0}"
  echo "[interactive] running runner directly inside current allocation (job=${SLURM_JOB_ID}, procid=${SLURM_PROCID})"
  echo "             command: $RUNNER ${RUNNER_ARGS[*]}"
  $DRY_RUN || exec "$RUNNER" "${RUNNER_ARGS[@]}"
  exit 0
fi

# ------------------------ BATCH PATH -------------------------
# Validate required Slurm flags explicitly
for v in JOB_NAME PARTITION GRES CPUS_PER_TASK MEM TIME; do
  [[ -n "${!v}" ]] || { echo "ERROR: Missing required Slurm option --${v//_/-}" >&2; print_help; exit 1; }
done

# Assemble sbatch options safely
SBATCH_OPTS=(
  --job-name "$JOB_NAME"
  --partition "$PARTITION"
  --gres "$GRES"
  --cpus-per-task "$CPUS_PER_TASK"
  --mem "$MEM"
  --time "$TIME"
)
[[ -n "$QOS"            ]] && SBATCH_OPTS+=( --qos "$QOS" )
[[ -n "$OUTPUT_FILE"    ]] && SBATCH_OPTS+=( --output "$OUTPUT_FILE" )
[[ -n "$ERROR_FILE"     ]] && SBATCH_OPTS+=( --error "$ERROR_FILE" )
[[ -n "$ARRAY_SPEC"     ]] && SBATCH_OPTS+=( --array "$ARRAY_SPEC" )
[[ -n "$CONSTRAINT_STR" ]] && SBATCH_OPTS+=( --constraint "$CONSTRAINT_STR" )
[[ -n "$ACCOUNT"        ]] && SBATCH_OPTS+=( --account "$ACCOUNT" )
[[ -n "$MAIL_TYPE"      ]] && SBATCH_OPTS+=( --mail-type "$MAIL_TYPE" )
[[ -n "$MAIL_USER"      ]] && SBATCH_OPTS+=( --mail-user "$MAIL_USER" )

# Build a safely-quoted one-liner for --wrap (no temp files anywhere)
build_cmd() {
  local out
  printf -v out "%q" "$RUNNER"
  for a in "${RUNNER_ARGS[@]}"; do
    printf -v out "%s %q" "$out" "$a"
  done
  printf '%s' "$out"
}
WRAP_CMD="$(build_cmd)"

echo "[submit] sbatch ${SBATCH_OPTS[*]} --wrap '$WRAP_CMD'"
if $DRY_RUN; then
  echo "[dry-run] not submitting."
  echo "Runner would be: $WRAP_CMD"
else
  sbatch "${SBATCH_OPTS[@]}" --wrap "$WRAP_CMD"
fi

