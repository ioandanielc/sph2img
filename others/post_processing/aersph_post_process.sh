et -euo pipefail
set -o errtrace
trap 'status=$?; echo "[ERR] Command failed: ${BASH_COMMAND} (exit=$status)"; exit $status' ERR

# ------------------------------------------------------------
# run_pipeline_and_sort.sh
#
# 1) Run sph2img (prints screenshots folder on STDOUT)
# 2) (optional) relocate screenshots_* under --screenshots_parent
# 3) Run stat_tester.py lists → stable/unstable VTK iters
# 4) Create layout inside SCREENSHOTS_DIR:
#       all/    (PNG source of truth)
#       tagged/ (copies only: stable/ unstable/ undefined/)
#       gifs/   (moved GIFs; sibling of all/)
# 5) Move ALL PNGs -> all/
# 6) Move GIFs -> gifs/   <-- NEW REQUIREMENT
# 7) Copy PNGs from all/ -> tagged/{stable,unstable,undefined}/
# 8) (optional) delete SIM
# ------------------------------------------------------------

# Defaults
TOL="${TOL:-0.045}"
WIN="${WIN:-500}"
PY_SPH2IMG="${PY_SPH2IMG:-python3}"
PY_STAT="${PY_STAT:-python3}"
STAT_OUT_PARENT="${STAT_OUT_PARENT:-}"
SCREENSHOTS_PARENT="${SCREENSHOTS_PARENT:-}"
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

# Sanity
if [[ -z "$SIM" || -z "$SPH2IMG_SCRIPT" || -z "$STAT_SCRIPT" ]]; then
  echo "ERROR: --sim, --sph2img, and --stat are required." >&2; exit 1;
fi
[[ -d "$SIM" ]] || { echo "ERROR: simulation path not found: $SIM" >&2; exit 1; }
[[ -f "$SPH2IMG_SCRIPT" ]] || { echo "ERROR: sph2img script not found: $SPH2IMG_SCRIPT" >&2; exit 1; }
[[ -f "$STAT_SCRIPT" ]] || { echo "ERROR: stat script not found: $STAT_SCRIPT" >&2; exit 1; }
if [[ -n "$SCREENSHOTS_PARENT" ]]; then
  mkdir -p "$SCREENSHOTS_PARENT"
  [[ -d "$SCREENSHOTS_PARENT" ]] || { echo "ERROR: screenshots parent not a dir: $SCREENSHOTS_PARENT" >&2; exit 1; }
fi

echo "[INFO] Using:"
echo "  SIM                 = $SIM"
echo "  SPH2IMG             = $SPH2IMG_SCRIPT   (python: $PY_SPH2IMG)"
echo "  STAT                = $STAT_SCRIPT      (python: $PY_STAT)"
echo "  RSD tol / win       = $TOL / $WIN"
[[ -n "$STAT_OUT_PARENT" ]] && echo "  STAT_OUT_PARENT     = $STAT_OUT_PARENT"
[[ -n "$SCREENSHOTS_PARENT" ]] && echo "  SCREENSHOTS_PARENT  = $SCREENSHOTS_PARENT"
echo "  DELETE WHEN FINAL   = $DELETE_WHEN_FINAL"

# 1) Run sph2img
echo "[STEP] Running sph2img pipeline…"
S2_LOG="$(mktemp -t sph2img_log.XXXXXX)"
PYTHONUNBUFFERED=1 "$PY_SPH2IMG" "$SPH2IMG_SCRIPT" 2>&1 | tee "$S2_LOG"
CLEAN_LOG="$(sed -E $'s/\x1B\\[[0-9;]*[A-Za-z]//g' "$S2_LOG")"
SCREENSHOTS_DIR="$(printf '%s\n' "$CLEAN_LOG" \
  | grep -Eo '/[^[:space:]]*/screenshots/screenshots_[^[:space:]]+' \
  | tail -n1 || true)"
if [[ -z "$SCREENSHOTS_DIR" ]]; then
  CANDIDATE_LAST="$(printf '%s\n' "$CLEAN_LOG" | awk 'NF{last=$0} END{print last}' | tr -d '\r')"
  [[ "$CANDIDATE_LAST" = /* ]] && SCREENSHOTS_DIR="$CANDIDATE_LAST"
fi
[[ -n "${SCREENSHOTS_DIR:-}" && -d "$SCREENSHOTS_DIR" ]] || {
  echo "ERROR: could not determine screenshots dir from sph2img output." >&2
  tail -n 60 "$S2_LOG" >&2; exit 1;
}
echo "[OK] Screenshots at: $SCREENSHOTS_DIR"

# 1b) Optional relocate screenshots_*
if [[ -n "$SCREENSHOTS_PARENT" ]]; then
  SHOTS_BASENAME="$(basename "$SCREENSHOTS_DIR")"
  TARGET_DIR="$SCREENSHOTS_PARENT/$SHOTS_BASENAME"
  if [[ "$SCREENSHOTS_DIR" != "$TARGET_DIR" ]]; then
    echo "[STEP] Relocating raw screenshots folder to: $TARGET_DIR"
    if mv -n -- "$SCREENSHOTS_DIR" "$TARGET_DIR" 2>/dev/null; then :; else mv -f -- "$SCREENSHOTS_DIR" "$TARGET_DIR"; fi
    SCREENSHOTS_DIR="$TARGET_DIR"
  fi
  echo "[OK] Raw screenshots root: $SCREENSHOTS_DIR"
fi

# 2) Run stat_tester lists
echo "[STEP] Running stat_tester lists…"
STAT_ARGS=( "lists" "--sim" "$SIM" "--tol" "$TOL" "--win" "$WIN" )
[[ -n "$STAT_OUT_PARENT" ]] && STAT_ARGS+=( "--out" "$STAT_OUT_PARENT" )
ST_LOG="$(mktemp -t stat_tester_log.XXXXXX)"
PYTHONUNBUFFERED=1 "$PY_STAT" "$STAT_SCRIPT" "${STAT_ARGS[@]}" 2>&1 | tee "$ST_LOG" >/dev/null
CLEAN_ST_LOG="$(sed -E $'s/\x1B\\[[0-9;]*[A-Za-z]//g' "$ST_LOG")"
STAT_JSON="$(printf '%s\n' "$CLEAN_ST_LOG" | awk '/^\{/{json=$0} END{print json}')"
[[ -n "$STAT_JSON" ]] || { echo "ERROR: JSON not found in stat_tester output." >&2; tail -n 60 "$ST_LOG" >&2; exit 1; }
printf '%s\n' "$STAT_JSON" | grep -q '"stable_longest"' || { echo "ERROR: JSON missing 'stable_longest'." >&2; exit 1; }

# 3) Parse JSON (jq or awk fallback)
STABLE_ITERS="" UNSTABLE_ITERS="" STAT_OUT_DIR=""
if command -v jq >/dev/null 2>&1; then
  STABLE_ITERS="$(printf '%s' "$STAT_JSON" | jq -r '.stable_longest[]?')"
  UNSTABLE_ITERS="$(printf '%s' "$STAT_JSON" | jq -r '.unstable_outside_longest[]?')"
  STAT_OUT_DIR="$(printf '%s' "$STAT_JSON" | jq -r '.out_dir // empty')"
else
  extract_array_nums() {
    local key="$1"
    awk -v key="$key" 'BEGIN{RS="";}{
      pattern="\"" key "\"[[:space:]]*:[[:space:]]*\\[([^\\]]*)\\]"
      if (match($0, pattern, a)) { s=a[1]; gsub(/[\n\r \t]/,"",s); n=split(s, arr, /,/); for(i=1;i<=n;i++) if(arr[i]!="") print arr[i] }
    }'
  }
  extract_string() {
    local key="$1"
    awk -v key="$key" 'BEGIN{RS="";}{ pattern="\"" key "\"[[:space:]]*:[[:space:]]*\"([^\"]*)\""; if (match($0, pattern, a)) print a[1] }'
  }
  STABLE_ITERS="$(printf '%s' "$STAT_JSON" | extract_array_nums "stable_longest")"
  UNSTABLE_ITERS="$(printf '%s' "$STAT_JSON" | extract_array_nums "unstable_outside_longest")"
  STAT_OUT_DIR="$(printf '%s' "$STAT_JSON" | extract_string "out_dir")"
fi
STABLE_ITERS_ARR=() UNSTABLE_ITERS_ARR=()
IFS=$'\n'; for v in $STABLE_ITERS; do [[ -n "$v" ]] && STABLE_ITERS_ARR+=( "$v" ); done; unset IFS
IFS=$'\n'; for v in $UNSTABLE_ITERS; do [[ -n "$v" ]] && UNSTABLE_ITERS_ARR+=( "$v" ); done; unset IFS
[[ -n "$STAT_OUT_DIR" ]] && echo "[INFO] stat_tester out_dir: $STAT_OUT_DIR"
echo "[INFO] Stable iters   : ${#STABLE_ITERS_ARR[@]}"
echo "[INFO] Unstable iters : ${#UNSTABLE_ITERS_ARR[@]}"

# 4) Layout inside SCREENSHOTS_DIR
ALL_DIR="$SCREENSHOTS_DIR/all"
GIFS_DIR="$SCREENSHOTS_DIR/gifs"          # <-- NEW: sibling of all/
TAGGED_BASE="$SCREENSHOTS_DIR/tagged"
STABLE_DIR="$TAGGED_BASE/stable"
UNSTABLE_DIR="$TAGGED_BASE/unstable"
UNDEFINED_DIR="$TAGGED_BASE/undefined"

mkdir -p "$ALL_DIR" "$GIFS_DIR"
mkdir -p "$STABLE_DIR"/{front,side,top} "$UNSTABLE_DIR"/{front,side,top} "$UNDEFINED_DIR"/{front,side,top}

# 5) Move ALL PNGs into all/
echo "[STEP] Moving all PNGs into: $ALL_DIR"
shopt -s nullglob
set +e
mv -f -- "$SCREENSHOTS_DIR"/ss_*_front.png "$ALL_DIR"/ 2>/dev/null || true
mv -f -- "$SCREENSHOTS_DIR"/ss_*_side.png  "$ALL_DIR"/ 2>/dev/null || true
mv -f -- "$SCREENSHOTS_DIR"/ss_*_top.png   "$ALL_DIR"/ 2>/dev/null || true
set -e
shopt -u nullglob

# 6) Move GIFs into gifs/ (same level as all/)
echo "[STEP] Moving GIFs into: $GIFS_DIR"
shopt -s nullglob
set +e
# common names from your pipeline (animation_ss_front.gif etc.) plus any *.gif
for g in "$SCREENSHOTS_DIR"/animation_ss_*.gif "$SCREENSHOTS_DIR"/*.gif; do
  [[ -f "$g" ]] || continue
  # avoid re-moving if already in gifs/
  [[ "$g" == "$GIFS_DIR/"* ]] && continue
  mv -f -- "$g" "$GIFS_DIR"/ || echo "[WARN] Failed moving GIF: $g"
done
set -e
shopt -u nullglob

# Helper: list all iterations present in ALL_DIR
list_all_iters_from_all() {
  find "$ALL_DIR" -maxdepth 1 -type f -name 'ss_*_*.png' \
    | sed -E 's#.*/ss_([0-9]+)_(front|side|top)\.png#\1#' | sort -u
}

# Compute undefined = ALL - (stable ∪ unstable)
compute_undefined_iters() {
  local tmp_all tmp_tagged
  tmp_all="$(mktemp)"; tmp_tagged="$(mktemp)"
  list_all_iters_from_all > "$tmp_all"
  { printf "%s\n" "${STABLE_ITERS_ARR[@]}" "${UNSTABLE_ITERS_ARR[@]}"; } \
    | awk 'NF' | sort -u > "$tmp_tagged"
  comm -23 "$tmp_all" "$tmp_tagged"
  rm -f "$tmp_all" "$tmp_tagged"
}

# 7) Copy PNGs from all/ into tagged buckets (NO MOVES)
copy_group() {
  local group_name="$1"; shift
  local -a iters=( "$@" )
  local dest_base
  case "$group_name" in
    stable) dest_base="$STABLE_DIR" ;;
    unstable) dest_base="$UNSTABLE_DIR" ;;
    undefined) dest_base="$UNDEFINED_DIR" ;;
    *) echo "[ERR] Unknown group: $group_name"; return 2 ;;
  esac

  local found=0 missing=0 failures=0
  set +e
  for it in "${iters[@]}"; do
    for view in front side top; do
      local src="$ALL_DIR/ss_${it}_${view}.png"
      local dst="$dest_base/$view/"
      if [[ -f "$src" ]]; then
        if cp -f -- "$src" "$dst"; then ((++found)); else ((++failures)); echo "[WARN] cp failed: $src -> $dst"; fi
      else
        ((++missing))
      fi
    done
  done
  set -e
  echo "[INFO] ${group_name}: copied ${found} files; missing ${missing}; cp failures ${failures}"
}

echo "[STEP] Copying PNGs into tagged/{stable,unstable,undefined} …"
if [[ ${#STABLE_ITERS_ARR[@]} -gt 0 ]]; then
  echo "[DBG] Example in ALL_DIR: $ALL_DIR/ss_${STABLE_ITERS_ARR[0]}_{front,side,top}.png"
  copy_group "stable" "${STABLE_ITERS_ARR[@]}"
else
  echo "[WARN] No stable iterations."
fi
if [[ ${#UNSTABLE_ITERS_ARR[@]} -gt 0 ]]; then
  copy_group "unstable" "${UNSTABLE_ITERS_ARR[@]}"
else
  echo "[INFO] No unstable iterations outside the longest segment."
fi
IFS=$'\n' UNDEFINED_ITERS_ARR=( $(compute_undefined_iters) ); unset IFS
if [[ ${#UNDEFINED_ITERS_ARR[@]} -gt 0 ]]; then
  copy_group "undefined" "${UNDEFINED_ITERS_ARR[@]}"
else
  echo "[INFO] No undefined iterations (everything tagged)."
fi

# 8) Optional deletion of SIM
echo "[STEP] Finalize (optional delete)…"
if [[ $DELETE_WHEN_FINAL -eq 1 ]]; then
  ABS_SIM="$(cd "$SIM" && pwd)"
  if [[ -z "$ABS_SIM" || "$ABS_SIM" = "/" ]]; then
    echo "[ABORT] Dangerous SIM path ('$ABS_SIM') — refusing to delete." >&2; exit 1;
  fi
  if [[ "$ABS_SIM" != *"/cfg_"* && "$ABS_SIM" != *"/runs_results/"* ]]; then
    echo "[ABORT] SIM path '$ABS_SIM' looks unsafe (no '/cfg_' or '/runs_results/'). Not deleting." >&2; exit 1;
  fi
  if rm --help 2>/dev/null | grep -q -- '--one-file-system'; then
    echo "[DELETE] Removing simulation directory (one-file-system): $ABS_SIM"
    rm -rf --one-file-system -- "$ABS_SIM"
  else
    echo "[DELETE] Removing simulation directory: $ABS_SIM"
    rm -rf -- "$ABS_SIM"
  fi
  echo "[OK] Deleted: $ABS_SIM"
else
  echo "[INFO] --delete-when-final NOT set → SIM not deleted: $SIM"
fi

# Done
echo "[DONE]"
echo "  Screenshots root     : $SCREENSHOTS_DIR"
echo "  ALL (PNGs)           : $ALL_DIR"
echo "  GIFs                 : $GIFS_DIR"
echo "  Tagged -> stable     : $STABLE_DIR/{front,side,top}"
echo "         -> unstable   : $UNSTABLE_DIR/{front,side,top}"
echo "         -> undefined  : $UNDEFINED_DIR/{front,side,top}"

