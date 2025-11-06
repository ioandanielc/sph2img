# AERSPH Stat Checker — Component 2: Bidirectional RSD

Bidirectional rolling–relative-standard-deviation (RSD) checker for AERSPH monitor data.  
Operates on a single simulation folder, or a batch described by a JSON/TOML config.  
Produces shaded series plots, an RSD triptych, and machine-readable summaries.

---

## Purpose

Identify the longest interval where the melt-pool extents (`dx, dy, dz`) are statistically stable when tested **both** forward and backward with a rolling window. Results are indexed on monitor sample indices and annotated with **real VTK iteration** vertical lines.

---

## Inputs

### Required simulation directory structure
A path `SIM_ROOT` containing:

```
SIM_ROOT/
└─ monitor/
   ├─ position-bounds_melt.dat          # 6 columns: x_min x_max y_min y_max z_min z_max
   ├─ average-temperature_melt.dat      # 1 value per line
   ├─ transferred-laser-power_melt.dat  # 1 value per line
   └─ total-energy_melt.dat             # 1 value per line
```

The component also reads iteration numbers (e.g., from VTK outputs) via the project’s `crawl_iterations()` utility.  
Only the **iteration values** are needed; vertical lines are drawn for `iters[2:-2]`.

### Key preprocessing rules
- Trims all monitor series to `[2:-2]` to avoid boundary artifacts.
- Sanitizes bounds: replaces NaN/Inf/|value|>1e20 and swapped min/max with linearly interpolated values.
- Defines extents as:
  - `dx = x_max - x_min`, `dy = y_max - y_min`, `dz = z_max - z_min`.

---

## Outputs

All artifacts are written into a **timestamped child** directory created inside the provided output **parent**:

```
OUT_PARENT/                             # --out (parent)
└─ statistics_DD-MM-YYYY_HH-MM-SS-mmm/  # created by the tool
   ├─ dx_series_shaded_abs.png
   ├─ dy_series_shaded_abs.png
   ├─ dz_series_shaded_abs.png
   ├─ rolling_rsd_triptych.png
   ├─ consecutive_stable_segments.txt          # human-readable segment report
   ├─ longest_stable_segment_indices.txt       # absolute window centers (TXT)
   ├─ longest_stable_segment_indices.csv       # absolute window centers (CSV)
   ├─ longest_stable_segment_vtk_iters.txt     # VTK iters inside longest segment (TXT)
   ├─ longest_stable_segment_vtk_iters.csv     # VTK iters inside longest segment (CSV)
   ├─ equilibrium_bidirectional_rsd_dxdyz_abs.txt   # text summary
   └─ equilibrium_bidirectional_rsd_dxdyz_abs.json  # machine-readable summary
```

### JSON summary (high-value fields)
`equilibrium_bidirectional_rsd_dxdyz_abs.json` includes:
- `out_dir`: absolute path to the timestamped output directory.
- `path`: simulation path.
- `count_trimmed`: number of samples after `[2:-2]`.
- `rolling_window`, `rsd_tolerance`.
- `trim.first_iter`, `trim.last_iter`: real iteration values used for vertical lines (after trim band definition).
- `index_domain_relative`: valid centers `[lo, hi]` for the rolling windows.
- `domain_relative`: `{exists, L, R, length}` for the **longest** stable overlap (forward ∩ backward).
- `absolute.domain`: `{L, R}` absolute indices (base = `iters[2]`).
- `absolute.stabilized_at_index`: absolute index where stability first holds (start of longest segment).
- `plots`: file paths for produced figures.
- `stable_segments`: all stable segments, report paths, and detailed info for the longest segment.
- `vtk_iters.stable_longest` and `vtk_iters.unstable_outside_longest`.

---

## Method (concise)

1. **Data assembly**  
   Load and sanitize bounds (6-cols) → compute `dx, dy, dz`; trim `[2:-2]`.  
   Gather scalar series (`temperature`, `laser power`, `energy`) for completeness (not used in masks).

2. **RSD masks (forward & backward)**  
   For each of `dx, dy, dz`, compute rolling RSD with window `win`.  
   A sample is **forward-ok** if `RSD ≤ tol` at the window **end**; **backward-ok** if `RSD ≤ tol` at the window **start**.  
   The **overlap** is `forward_ok_end ∩ backward_ok_start` over valid centers `[win−1, n−win]`.

3. **Segments**  
   Find all consecutive `True` segments on the overlap; select the **longest**.  
   Map relative indices to **absolute** monitor indices with base `first_iter = iters[2]`.

4. **Plots & summaries**  
   - `dx/dy/dz` series with shaded longest domain and decimated iteration vlines (≤300).  
   - Triptych of rolling RSD (`dx`, `dy`, `dz`).  
   - Text and CSV/TXT lists with indices and VTK iterations in/out the longest domain.  
   - JSON + TXT summaries for downstream automation.

---

## CLI

### Single run (plots + summaries)
```bash
python stat_tester.py run   --sim /path/to/SIM_ROOT   --out /path/to/OUT_PARENT   --tol 0.045   --win 500
```

- `--sim`: simulation root containing `monitor/`.
- `--out`: **parent** directory; a timestamped child is created inside.
- `--tol`: RSD tolerance (float).
- `--win`: rolling window length (int).

If `--tol`/`--win` are omitted, host config defaults are used.

### Lists mode (machine-readable selection only)
```bash
python stat_tester.py lists   --sim /path/to/SIM_ROOT   --out /path/to/OUT_PARENT   --tol 0.05   --win 500
```
Prints a JSON object to STDOUT:
```json
{
  "stable_longest": [ /* VTK iters inside longest stable domain */ ],
  "unstable_outside_longest": [ /* VTK iters outside */ ],
  "out_dir": "/abs/path/to/statistics_..."
}
```

### Batch mode (config-driven)
```bash
python stat_tester.py run   --config /path/to/batch_config.json   --workers 8
```

#### JSON schema (informal)
```json
{
  "defaults": {
    "out_dir_base": "/path/to/OUT_PARENT_BASE",
    "rolling_window": 500,
    "rsd_tolerance": 0.05
  },
  "jobs": [
    { "sim": "/path/to/SIM_A" },
    { "sim_glob": "/data/sims/run_*/" },           // expands and sorts
    {
      "sim": "/path/to/SIM_B",
      "out_dir": "/custom/parent/for/B",
      "rolling_window": 700,
      "rsd_tolerance": 0.03
    }
  ]
}
```

#### TOML example
```toml
[defaults]
out_dir_base   = "/path/to/OUT_PARENT_BASE"
rolling_window = 500
rsd_tolerance  = 0.05

[[jobs]]
sim = "/path/to/SIM_A"

[[jobs]]
sim_glob = "/data/sims/run_*/"

[[jobs]]
sim = "/path/to/SIM_B"
out_dir = "/custom/parent/for/B"
rolling_window = 700
rsd_tolerance  = 0.03
```

The `out_dir` used per job is a **parent**; each execution creates exactly one `statistics_*` child.

---

## Logging & Console Output

- Logs via `aersph_stat_checker.utils.pvlog.get_logger`.  
- Progress uses `tqdm` when available; otherwise a minimal logger.  
- Single run prints:
  - `[max_consecutive_stable] <N> (see <report_file>)`
  - `[out_dir] <timestamped_child_path>`

---

## Performance & Limits

- Rolling RSD is computed with cumulative sums (O(n) per axis).  
- Vertical lines are decimated to ≤300 for plot readability.  
- XY downsampling targets ~5k points per plot.  
- `--workers` controls process pool size in batch mode; “auto” uses CPU count.

---

## Error Handling

- Missing/empty monitor files → `FileNotFoundError`.
- Inconsistent lengths after trim → `ValueError`.
- `rolling_window` invalid for series length → `ValueError`.
- Batch jobs report `{ok: false, error: "<Type>: <message>"} and continue.

---

## Exit Codes

- `0` on success.  
- Non-zero on unhandled exceptions (e.g., invalid inputs).

---

## Dependencies

- Python ≥ 3.10
- `numpy`, `matplotlib`
- `tqdm` (optional, for progress bars)
- `tomllib` (Py3.11+) or `tomli` (for TOML configs)
- Project modules:
  - `aersph_stat_checker.config.get_config`
  - `aersph_stat_checker.utils.pvlog.get_logger`
  - `aersph_stat_checker.utils.crawl_iterations.crawl_iterations`

---

## Assumptions & Conventions

- Monitor index base for absolute X-axis is `iters[2]` (third iteration).  
- Trim band is fixed at `[2:-2]`.  
- Stability requires **all three** axes (`dx`, `dy`, `dz`) to satisfy `RSD ≤ tol` **both** forward and backward.  
- Output directory creation is atomic: one `statistics_*` per invocation.

---

## Minimal Examples

**Typical single run**
```bash
python stat_tester.py run   --sim /data/sim_001   --out /results/stability_bidirectional_rsd   --tol 0.04   --win 600
```

**Only lists for downstream scripts**
```bash
python stat_tester.py lists   --sim /data/sim_001   --out /results/stability_bidirectional_rsd   --tol 0.05   --win 500 | jq .
```

---

## File Glossary

- `*_series_shaded_abs.png` — raw `dx/dy/dz` vs absolute monitor indices; longest stable domain shaded; real VTK vlines (decimated).  
- `rolling_rsd_triptych.png` — forward RSD time series for `dx`, `dy`, `dz`.  
- `consecutive_stable_segments.txt` — all stable segments (relative and absolute), total True count, and max consecutive length.  
- `longest_stable_segment_indices.{txt,csv}` — absolute window centers `[L..R]` of the longest stable domain.  
- `longest_stable_segment_vtk_iters.{txt,csv}` — real VTK iterations inside the longest domain.  
- `equilibrium_bidirectional_rsd_dxdyz_abs.{json,txt}` — full machine-readable and human-readable summaries.
