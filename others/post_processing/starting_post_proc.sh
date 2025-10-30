# --- fill these with your actual paths/values ---
SIM="/dss/dssfs04/lwp-dss-0002/pn36ni/pn36ni-dss-0000/ge57gon2/projects/aersph_enroot_automation/runs_results/2025-10-07_18-06-32p970_lp-200p0_vx-0p4_j-5342389_p-0/cfg_2025-10-07_18-06-32p970_lp-200p0_vx-0p4_j-5342389_p-0"
SPH2IMG_SCRIPT="/dss/dssfs04/lwp-dss-0002/pn36ni/pn36ni-dss-0000/ge57gon2/projects/sph2img/bin/run_pipeline_single_mode.py"
STAT_SCRIPT="/dss/dssfs04/lwp-dss-0002/pn36ni/pn36ni-dss-0000/ge57gon2/projects/aersph_stat_checker/src/aersph_stat_checker/stat_tester.py"

# interpreters (can be the same or different venvs)
PY_SPH2IMG="/dss/dssfs04/lwp-dss-0002/pn36ni/pn36ni-dss-0000/ge57gon2/opt/paraview/ParaView-6.0.0-MPI-Linux-Python3.12-x86_64/bin/pvbatch"
PY_STAT="/dss/dssfs04/lwp-dss-0002/pn36ni/pn36ni-dss-0000/ge57gon2/opt/paraview/ParaView-6.0.0-MPI-Linux-Python3.12-x86_64/bin/pvbatch"

# RSD params
TOL="0.045"
WIN="500"

# parents for outputs
STAT_OUT_PARENT="/dss/dssfs04/lwp-dss-0002/pn36ni/pn36ni-dss-0000/ge57gon2/projects/aersph_stat_checker/stat_results/post_proc_stats"          # stat_tester will create a timestamped child inside here
SCREENSHOTS_PARENT="/dss/dssfs04/lwp-dss-0002/pn36ni/pn36ni-dss-0000/ge57gon2/projects/sph2img/outputs/screenshots/post_proc_screenshots"        # we will move the screenshots_* folder here

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
/dss/dssfs04/lwp-dss-0002/pn36ni/pn36ni-dss-0000/ge57gon2/projects/sph2img/others/post_processing/aersph_post_process.sh \
  --sim "$SIM" \
  --sph2img "$SPH2IMG_SCRIPT" \
  --stat "$STAT_SCRIPT" \
  --tol "$TOL" \
  --win "$WIN" \
  --stat_out_parent "$STAT_OUT_PARENT" \
  --screenshots_parent "$SCREENSHOTS_PARENT" \
  ${DEL_FLAG}
