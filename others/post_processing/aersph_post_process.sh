#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------
# run_pipeline_and_sort.sh
#
# 1) Runs sph2img pipeline (prints screenshots folder on STDOUT)
# 2) (Optional) relocates that screenshots folder under --screenshots_parent
# 3) Runs stat_tester.py `lists` to get stable/unstable VTK iters
# 4) Moves PNGs: ss_<ITER>_{front,side,top}.png into stable/ / unstable/
# 5) Optionally deletes the simulation directory at the very end
#
# Usage:
#   ./run_pipeline_and_sort.sh \
#     --sim "/abs/path/to/cfg_..._vx-..." \
#     --sph2img "/abs/path/to/sph2img/bin/run_pipeline_single_mode.py" \
#     --stat "/abs/path/to/aersph_stat_checker/stat_tester.py" \
#     [--tol 0.045] [--win 500] \
#     [--python_sph2img /path/to/python] \
#     [--python_stat /path/to/python] \
#     [--stat_out_parent /abs/path/for/stat/outputs] \
#     [--screenshots_parent /abs/path/for/screenshots] \
#     [--delete-when-final]
#
# Notes:
# - Works on Bash 3.x+ (no readarray/mapfile used).
# - If `jq` is missing, falls back to small Python snippets to parse JSON.
# - stat_tester.py --out is a **parent** dir; it creates a timestamped child.
# ------------------------------------------------------------

# Defaults (overridable via env or flags)
TOL="${TOL:-0.045}"
WIN="${WIN:-500}"
PY_SPH2IMG="${PY_SPH2IMG:-python3}"     # interpreter for sph2img script
PY_STAT="${PY_STAT:-python3}"           # interpreter for stat_tester script
STAT_OUT_PARENT="${STAT_OUT_PARENT:-}"  # parent dir for stat_tester outputs
SCREENSHOTS_PARENT="${SCREENSHOTS_PARENT:-}"  # optional relocation parent for screenshots
DELETE_WHEN_FINAL=0

# Args
SIM=""
SPH2IMG_SCRIPT=""
STAT_SCRIPT=""

print_help() { awk 'NR==1, NR==200 {print}' "$0"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sim) SIM="$2"; shift 2;;
    --sph2img) SPH2IMG_SCRIPT="$2"; shift 2;;
    --stat) STAT_SCRIPT="$2"; shift 2;;
    --tol) TOL="$2"; shift 2;;
    --win) WIN="$2"; shift 2;;
    --python_sph2img) PY_SPH2IMG="$2"; shift 2;;
    --python_stat) PY_STAT="$2"; shift 2;;
    --stat_out_parent) STAT_OUT_PARENT="$2"; shift 2;;
    --screenshots_parent) SCREENSHOTS_PARENT="$2"; shift 2;;
    --delete-when-final) DELETE_WHEN_FINAL=1; shift 1;;
    -h|--help) print_help; exit 0;;
    *) echo "Unknown arg: $1" >&2; exit 1;;
  esac
done

# Sanity checks
if [[ -z "$SIM" || -z "$SPH2IMG_SCRIPT" || -z "$STAT_SCRIPT" ]]; then
  echo "ERROR: --sim, --sph2img, and --stat are required." >&2
  exit 1
fi
[[ -d "$SIM" ]] || { echo "ERROR: simulation path not found: $SIM" >&2; exit 1; }
[[ -f "$SPH2IMG_SCRIPT" ]] || { echo "ERROR: sph2img script not found: $SPH2IMG_SCRIPT" >&2; exit 1; }
[[ -f "$STAT_SCRIPT" ]] || { echo "ERROR: stat script not found: $STAT_SCRIPT" >&2; exit 1; }
if [[ -n "$SCREENSHOTS_PARENT" ]]; then
  mkdir -p "$SCREENSHOTS_PARENT"
  [[ -d "$SCREENSHOTS_PARENT" ]] || { echo "ERROR: screenshots parent not a directory: $SCREENSHOTS_PARENT" >&2; exit 1; }
fi

echo "[INFO] Using:"
echo "  SIM                 = $SIM"
echo "  SPH2IMG             = $SPH2IMG_SCRIPT   (python: $PY_SPH2IMG)"
echo "  STAT                = $STAT_SCRIPT      (python: $PY_STAT)"
echo "  RSD tol / win       = $TOL / $WIN"
[[ -n "$STAT_OUT_PARENT" ]] && echo "  STAT_OUT_PARENT     = $STAT_OUT_PARENT (parent; timestamped child is created inside)"
[[ -n "$SCREENSHOTS_PARENT" ]] && echo "  SCREENSHOTS_PARENT  = $SCREENSHOTS_PARENT (will relocate the created screenshots_* folder)"
echo "  DELETE WHEN FINAL   = $DELETE_WHEN_FINAL"

# -----------------------------
# 1) Run sph2img pipeline (stream logs + robustly extract screenshots dir)
# -----------------------------
echo "[STEP] Running sph2img pipeline…"
S2_LOG="$(mktemp -t sph2img_log.XXXXXX)"

# Stream logs live, save to file
PYTHONUNBUFFERED=1 "$PY_SPH2IMG" "$SPH2IMG_SCRIPT" 2>&1 | tee "$S2_LOG"

# Strip ANSI color codes before parsing
CLEAN_LOG="$(sed -E $'s/\x1B\\[[0-9;]*[A-Za-z]//g' "$S2_LOG")"

# Strategy A: last absolute path containing '/screenshots/screenshots_...'
SCREENSHOTS_DIR="$(printf '%s\n' "$CLEAN_LOG" \
  | grep -Eo '/[^[:space:]]*/screenshots/screenshots_[^[:space:]]+' \
  | tail -n1 || true)"

# Strategy B: the very last non-empty line if it's an absolute path
if [[ -z "$SCREENSHOTS_DIR" ]]; then
  CANDIDATE_LAST="$(printf '%s\n' "$CLEAN_LOG" | awk 'NF{last=$0} END{print last}' | tr -d '\r')"
  if [[ "$CANDIDATE_LAST" = /* ]]; then
    SCREENSHOTS_DIR="$CANDIDATE_LAST"
  fi
fi

# Validate; only accept existing directories; do NOT rebase relative paths
if [[ -z "${SCREENSHOTS_DIR:-}" || ! -d "$SCREENSHOTS_DIR" ]]; then
  echo "ERROR: could not determine screenshots dir from sph2img output." >&2
  echo "Hint: ensure run_pipeline_single_mode.py prints the absolute path as its final line." >&2
  echo "Tail of log:" >&2
  tail -n 60 "$S2_LOG" >&2
  exit 1
fi
echo "[OK] Screenshots at: $SCREENSHOTS_DIR"

# -----------------------------
# 1b) Optional relocation of screenshots folder under --screenshots_parent
# -----------------------------
if [[ -n "$SCREENSHOTS_PARENT" ]]; then
  SHOTS_BASENAME="$(basename "$SCREENSHOTS_DIR")"
  TARGET_DIR="$SCREENSHOTS_PARENT/$SHOTS_BASENAME"

  if [[ "$SCREENSHOTS_DIR" != "$TARGET_DIR" ]]; then
    echo "[STEP] Relocating screenshots folder to: $TARGET_DIR"
    if mv -n -- "$SCREENSHOTS_DIR" "$TARGET_DIR" 2>/dev/null; then
      :
    else
      mv -f -- "$SCREENSHOTS_DIR" "$TARGET_DIR"
    fi
    SCREENSHOTS_DIR="$TARGET_DIR"
    echo "[OK] Relocated. New screenshots root: $SCREENSHOTS_DIR"
  else
    echo "[INFO] Screenshots already under desired parent."
  fi
fi

# -----------------------------
# 2) Run stat tester (lists)
# -----------------------------
echo "[STEP] Running stat_tester lists…"
STAT_ARGS=( "lists" "--sim" "$SIM" "--tol" "$TOL" "--win" "$WIN" )
if [[ -n "$STAT_OUT_PARENT" ]]; then
  STAT_ARGS+=( "--out" "$STAT_OUT_PARENT" )
fi

ST_LOG="$(mktemp -t stat_tester_log.XXXXXX)"
PYTHONUNBUFFERED=1 "$PY_STAT" "$STAT_SCRIPT" "${STAT_ARGS[@]}" 2>&1 | tee "$ST_LOG" >/dev/null

# Clean log and extract the final JSON line (skip warnings/info lines)
CLEAN_ST_LOG="$(sed -E $'s/\x1B\\[[0-9;]*[A-Za-z]//g' "$ST_LOG")"
STAT_JSON="$(printf '%s\n' "$CLEAN_ST_LOG" | awk '/^\{/{json=$0} END{print json}')"

if [[ -z "$STAT_JSON" ]]; then
  echo "ERROR: Could not find JSON line in stat_tester output." >&2
  echo "Tail of log:" >&2
  tail -n 60 "$ST_LOG" >&2
  exit 1
fi

# Optional sanity
printf '%s\n' "$STAT_JSON" | grep -q '"stable_longest"' || {
  echo "ERROR: JSON does not contain 'stable_longest'." >&2
  echo "JSON was:" >&2
  printf '%s\n' "$STAT_JSON" >&2
  exit 1
}

# -----------------------------
# 3) Parse JSON (Bash 3–safe; no readarray/mapfile)
# -----------------------------
STABLE_ITERS=""
UNSTABLE_ITERS=""
STAT_OUT_DIR=""

if command -v jq >/dev/null 2>&1; then
  STABLE_ITERS="$(printf '%s' "$STAT_JSON" | jq -r '.stable_longest[]?')"
  UNSTABLE_ITERS="$(printf '%s' "$STAT_JSON" | jq -r '.unstable_outside_longest[]?')"
  STAT_OUT_DIR="$(printf '%s' "$STAT_JSON" | jq -r '.out_dir // empty')"
else
  STABLE_ITERS="$("$PY_STAT" - <<'PY'
import sys,json
data=json.load(sys.stdin)
for v in data.get("stable_longest", []): print(v)
PY
<<<"$STAT_JSON")"
  UNSTABLE_ITERS="$("$PY_STAT" - <<'PY'
import sys,json
data=json.load(sys.stdin)
for v in data.get("unstable_outside_longest", []): print(v)
PY
<<<"$STAT_JSON")"
  STAT_OUT_DIR="$("$PY_STAT" - <<'PY'
import sys,json
data=json.load(sys.stdin); print(data.get("out_dir",""))
PY
<<<"$STAT_JSON")"
fi

# Convert to arrays without readarray/mapfile
STABLE_ITERS_ARR=()
UNSTABLE_ITERS_ARR=()
IFS=$'\n'
for v in $STABLE_ITERS; do
  [[ -n "$v" ]] && STABLE_ITERS_ARR+=( "$v" )
done
for v in $UNSTABLE_ITERS; do
  [[ -n "$v" ]] && UNSTABLE_ITERS_ARR+=( "$v" )
done
unset IFS

[[ -n "$STAT_OUT_DIR" ]] && echo "[INFO] stat_tester out_dir (timestamped child): $STAT_OUT_DIR"
echo "[INFO] Stable iters   : ${#STABLE_ITERS_ARR[@]}"
echo "[INFO] Unstable iters : ${#UNSTABLE_ITERS_ARR[@]}"

# -----------------------------
# 4) Create stable/unstable folders
# -----------------------------
STABLE_DIR="$SCREENSHOTS_DIR/stable"
UNSTABLE_DIR="$SCREENSHOTS_DIR/unstable"
mkdir -p "$STABLE_DIR/front" "$STABLE_DIR/side" "$STABLE_DIR/top"
mkdir -p "$UNSTABLE_DIR/front" "$UNSTABLE_DIR/side" "$UNSTABLE_DIR/top"

# -----------------------------
# 5) Move PNGs per list (ss_<ITER>_{front,side,top}.png)
# -----------------------------
move_group() {
  local group_name="$1"; shift
  # shellcheck disable=SC2124
  local iters=( "$@" )
  local dest_base
  if [[ "$group_name" == "stable" ]]; then
    dest_base="$STABLE_DIR"
  else
    dest_base="$UNSTABLE_DIR"
  fi

  local found=0 missing=0
  for it in "${iters[@]}"; do
    for view in front side top; do
      local src="$SCREENSHOTS_DIR/ss_${it}_${view}.png"
      if [[ -f "$src" ]]; then
        mv -f -- "$src" "$dest_base/$view/"
        ((found++))
      else
        ((missing++))
      fi
    done
  done
  echo "[INFO] ${group_name}: moved ${found} files; missing (non-fatal) ${missing}"
}

echo "[STEP] Moving PNGs into stable/ and unstable/…"
if [[ ${#STABLE_ITERS_ARR[@]} -gt 0 ]]; then
  move_group "stable" "${STABLE_ITERS_ARR[@]}"
else
  echo "[WARN] No stable iterations."
fi

if [[ ${#UNSTABLE_ITERS_ARR[@]} -gt 0 ]]; then
  move_group "unstable" "${UNSTABLE_ITERS_ARR[@]}"
else
  echo "[INFO] No unstable iterations outside the longest segment."
fi

# -----------------------------
# 6) Optional deletion of SIM (with guardrails)
# -----------------------------
echo "[STEP] Finalize (optional delete)…"
if [[ $DELETE_WHEN_FINAL -eq 1 ]]; then
  ABS_SIM="$(cd "$SIM" && pwd)"
  if [[ -z "$ABS_SIM" || "$ABS_SIM" = "/" ]]; then
    echo "[ABORT] Dangerous SIM path ('$ABS_SIM') — refusing to delete." >&2
    exit 1
  fi
  # Heuristic guard to avoid accidents
  if [[ "$ABS_SIM" != *"/cfg_"* && "$ABS_SIM" != *"/runs_results/"* ]]; then
    echo "[ABORT] SIM path '$ABS_SIM' does not match expected run patterns (no '/cfg_' or '/runs_results/'). Not deleting." >&2
    exit 1
  fi

  # Use --one-file-system if available
  if rm --help 2>/dev/null | grep -q -- '--one-file-system'; then
    echo "[DELETE] Removing simulation directory (one-file-system): $ABS_SIM"
    rm -rf --one-file-system -- "$ABS_SIM"
  else
    echo "[DELETE] Removing simulation directory: $ABS_SIM"
    rm -rf -- "$ABS_SIM"
  fi
  echo "[OK] Deleted: $ABS_SIM"
else
  echo "[INFO] --delete-when-final NOT set → simulation directory was NOT deleted: $SIM"
fi

# -----------------------------
# 7) Done
# -----------------------------
echo "[DONE]"
echo "  Screenshots root : $SCREENSHOTS_DIR"
echo "  Stable PNGs   ->  $STABLE_DIR/{front,side,top}"
echo "  Unstable PNGs ->  $UNSTABLE_DIR/{front,side,top}"
[[ $DELETE_WHEN_FINAL -eq 1 ]] || echo "  SIM not deleted  ->  $SIM"
