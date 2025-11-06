#!/usr/bin/env bash
# =============================================================================
# aersph_containerized_run_runner.sh
#
# Role
#   Prepare a per-run workspace, generate JSON from an XML template using
#   configurer.py, execute ./AERSPH inside an Enroot container, collect results,
#   and write a summary.
#
# Invariants
#   - All paths via CLI (no hardcoded defaults).
#   - RUN_ID = j-<SLURM_JOB_ID>_p-<SLURM_PROCID> (Slurm required).
#   - No hashing/timestamps in names.
#   - Container mandatory; solver is fixed to ./AERSPH.
# =============================================================================
set -euo pipefail

newline() { echo; echo; }
banner()  { newline; echo "=============================="; echo "[SECTION $1] $2"; echo "=============================="; }
trap 'ec=$?; echo "ERROR: Runner failed (exit $ec) at line $LINENO"; exit $ec' ERR

# ------------------ Arguments ------------------
CLEAN_AERSPH=""
ENROOT_IMAGE=""
CONFIGURER_PY=""
TEMPLATE_XML=""
RUNNING_ROOT=""
RESULTS_ROOT=""
KEEP_RUN_DIR=false
DRY_RUN=false

print_help() {
  cat <<'HLP'
Required:
  --clean-aersph DIR           Clean AERSPH tree (contains ./AERSPH)
  --enroot-image FILE          Enroot .sqsh image
  --configurer-py FILE         configurer.py (XML→JSON)
  --template-xml FILE          XML template
  --running-root DIR           Root for workspaces
  --results-root DIR           Root for results

Optional:
  --keep-run-dir               Keep workspace after transfer
  --dry-run                    Generate JSON; skip solver exec
  -h|--help                    Show help

Configurer args (forwarded after --):
  Repeated --set PATH VALUE pairs. VALUE may be JSON.
HLP
}

SET_ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --clean-aersph)  CLEAN_AERSPH="${2:?}"; shift 2 ;;
    --enroot-image)  ENROOT_IMAGE="${2:?}"; shift 2 ;;
    --configurer-py) CONFIGURER_PY="${2:?}"; shift 2 ;;
    --template-xml)  TEMPLATE_XML="${2:?}"; shift 2 ;;
    --running-root)  RUNNING_ROOT="${2:?}"; shift 2 ;;
    --results-root)  RESULTS_ROOT="${2:?}"; shift 2 ;;
    --keep-run-dir)  KEEP_RUN_DIR=true; shift ;;
    --dry-run)       DRY_RUN=true; shift ;;
    -h|--help)       print_help; exit 0 ;;
    --)              shift; SET_ARGS=( "$@" ); break ;;
    *) echo "Unknown option: $1" >&2; print_help; exit 1 ;;
  esac
done

# ------------------ Validation ------------------
[[ -n "$CLEAN_AERSPH"  && -d "$CLEAN_AERSPH"  ]] || { echo "Missing/invalid --clean-aersph"; exit 1; }
[[ -n "$ENROOT_IMAGE"  && -f "$ENROOT_IMAGE"  ]] || { echo "Missing/invalid --enroot-image"; exit 1; }
[[ -n "$CONFIGURER_PY" && -f "$CONFIGURER_PY" ]] || { echo "Missing/invalid --configurer-py"; exit 1; }
[[ -n "$TEMPLATE_XML"  && -f "$TEMPLATE_XML"  ]] || { echo "Missing/invalid --template-xml"; exit 1; }
[[ -n "$RUNNING_ROOT"                          ]] || { echo "Missing --running-root"; exit 1; }
[[ -n "$RESULTS_ROOT"                          ]] || { echo "Missing --results-root"; exit 1; }
[[ -n "${SLURM_JOB_ID:-}" ]] || { echo "SLURM_JOB_ID is required"; exit 1; }
[[ -n "${SLURM_PROCID:-}" ]] || { echo "SLURM_PROCID is required"; exit 1; }
command -v enroot >/dev/null 2>&1 || { echo "enroot not in PATH"; exit 1; }

# ------------------ IDs & Paths ------------------
RUN_ID="j-${SLURM_JOB_ID}_p-${SLURM_PROCID}"
CONTAINER_NAME="aersph_${RUN_ID}"
RUN_DIR="${RUNNING_ROOT}/${RUN_ID}/aersph"
RESULTS_DIR="${RESULTS_ROOT}/${RUN_ID}"
JSON_BASENAME="cfg_${RUN_ID}"
OUT_JSON="${RUN_DIR}/${JSON_BASENAME}.json"

banner 1 "Workspace"
mkdir -p "$RUN_DIR"

# Copy clean tree but exclude VCS/irrelevant bits that can cause permission errors
# Prefer rsync; fall back to tar if rsync is unavailable.
echo "[copy] from: $CLEAN_AERSPH"
echo "[copy] to  : $RUN_DIR"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete \
    --exclude='.git' --exclude='.git/**' \
    --exclude='.github' --exclude='.gitmodules' \
    --exclude='.svn' --exclude='.hg' \
    "${CLEAN_AERSPH}/" "${RUN_DIR}/"
else
  ( cd "$CLEAN_AERSPH"
    tar --exclude='.git' --exclude='.github' --exclude='.svn' --exclude='.hg' -cf - . \
    | tar -C "$RUN_DIR" -xf -
  )
fi
echo "RUN_ID=$RUN_ID"
echo "RUN_DIR=$RUN_DIR"

banner 2 "Config generation (XML→JSON)"
CONF_CMD=( python3 "$CONFIGURER_PY" --in-xml "$TEMPLATE_XML" --out-json "$OUT_JSON" )
if [[ ${#SET_ARGS[@]} -gt 0 ]]; then CONF_CMD+=( "${SET_ARGS[@]}" ); fi
echo "[configurer] ${CONF_CMD[*]}"
"${CONF_CMD[@]}"
[[ -f "$OUT_JSON" ]] || { echo "ERROR: JSON not produced at $OUT_JSON"; exit 1; }

banner 3 "Execute solver in Enroot"
if $DRY_RUN; then
  echo "[dry-run] Skipping solver execution."
else
  enroot list | grep -qx "$CONTAINER_NAME" && enroot remove -f "$CONTAINER_NAME" || true
  enroot create -n "$CONTAINER_NAME" "$ENROOT_IMAGE"
  ( set -x
    enroot start --rw --mount "${RUN_DIR}:/mnt/aersph" "$CONTAINER_NAME" \
      bash -lc "set -euo pipefail; cd /mnt/aersph; ./AERSPH '${JSON_BASENAME}.json'"
  )
  enroot remove -f "$CONTAINER_NAME" || echo "WARN: could not remove container"
fi

banner 4 "Collect results"
EXP_SOURCE="${RUN_DIR}/${JSON_BASENAME}"
mkdir -p "$RESULTS_DIR"
if [[ -d "$EXP_SOURCE" ]]; then
  mv "$EXP_SOURCE" "$RESULTS_DIR/"
else
  echo "WARN: Expected solver output directory not found: $EXP_SOURCE"
fi

banner 5 "Finalize"
if [[ -d "$RESULTS_DIR/${JSON_BASENAME}" ]]; then
  $KEEP_RUN_DIR || rm -rf "${RUNNING_ROOT}/${RUN_ID}"
else
  echo "Note: keeping workspace for inspection: ${RUNNING_ROOT}/${RUN_ID}"
fi

banner 6 "Summary"
START_TS_HUMAN="${START_TS_HUMAN:-$(date +"%Y-%m-%d %H:%M:%S")}"
END_TS_HUMAN="$(date +"%Y-%m-%d %H:%M:%S")"
cat > "${RESULTS_DIR}/experiment_summary.txt" <<EOF
==============================================
 AERSPH Containerized Run — Summary
   Run ID       : ${RUN_ID}
   Job ID       : ${SLURM_JOB_ID}
   Proc ID      : ${SLURM_PROCID}
   Config File  : ${JSON_BASENAME}.json
   Results Path : ${RESULTS_DIR}
   Started at   : ${START_TS_HUMAN}
   Finished at  : ${END_TS_HUMAN}
==============================================
EOF
echo "[END] Runner completed."

