from __future__ import annotations

import numpy as np

def build_solidified_map_online(
    iteration: int,
    x_start: float | None = None,
    x_end: float | None = None,
    linspace_cuts: int | None = None,
) :
    """
    ONLINE single-iteration: produce absolute X positions as a linspace in [x_start, x_end] (inclusive).
    If x_start is None -> 0.0; if x_end is None -> x_start (zero-length linspace).
    If linspace_cuts is None -> 0; negative cuts -> 0.
    """
    xs = 0.0 if x_start is None else float(x_start)
    xe = xs  if x_end   is None else float(x_end)

    cuts = 0 if linspace_cuts is None else max(0, int(linspace_cuts))
    points = cuts + 1

    vals = np.linspace(xs, xe, points) if points > 0 else np.array([xs], dtype=float)
    return vals, {i: (int(iteration), float(vals[i])) for i in range(points)}
