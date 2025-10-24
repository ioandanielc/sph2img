# --- fill these with your actual paths/values ---
SIM="/Users/ioandanielcraciun/Python-Projects/sph2img/simulations/mhpc3d_200W_Ti64_Ar-3"
SPH2IMG_SCRIPT="/Users/ioandanielcraciun/Python-Projects/sph2img/bin/run_pipeline_single_mode.py"
STAT_SCRIPT="/Users/ioandanielcraciun/Python-Projects/aersph_stat_checker/src/aersph_stat_checker/stat_tester.py"

# interpreters (can be the same or different venvs)
PY_SPH2IMG="/Applications/ParaView-6.0.0.app/Contents/bin/pvbatch"
PY_STAT="/Applications/ParaView-6.0.0.app/Contents/bin/pvbatch"

# RSD params
TOL="0.045"
WIN="500"

# parents for outputs
STAT_OUT_PARENT="/Users/ioandanielcraciun/Python-Projects/aersph_stat_checker/results/post_proc_script_testing"          # stat_tester will create a timestamped child inside here
SCREENSHOTS_PARENT="/Users/ioandanielcraciun/Python-Projects/sph2img/outputs/screenshots/post_proc_script_testing"        # we will move the screenshots_* folder here

# optional: toggle deletion at the very end (0 = keep, 1 = delete)
DELETE_AFTER=0

# --- build optional flag for deletion ---
DEL_FLAG=""
if [[ "${DELETE_AFTER}" -eq 1 ]]; then
  DEL_FLAG="--delete-when-final"
fi

# --- run ---
PY_SPH2IMG="$PY_SPH2IMG" \
PY_STAT="$PY_STAT" \
/Users/ioandanielcraciun/Python-Projects/sph2img/others/post_processing/aersph_post_process.sh \
  --sim "$SIM" \
  --sph2img "$SPH2IMG_SCRIPT" \
  --stat "$STAT_SCRIPT" \
  --tol "$TOL" \
  --win "$WIN" \
  --stat_out_parent "$STAT_OUT_PARENT" \
  --screenshots_parent "$SCREENSHOTS_PARENT" \
  ${DEL_FLAG}
