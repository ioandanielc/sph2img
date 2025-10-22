# src/sph2img/utils/milestones_common.py
from __future__ import annotations

# --- path bootstrap: make `sph2img` importable even when run as a script -----
# make repo/src importable no matter which interpreter runs this (python, pvpython, pvbatch)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from typing import Dict, Tuple

from sph2img.config import get_config
from sph2img.utils.pvlog import get_logger

log = get_logger(__name__)

# single source of truth: prefer config path
try:
    DEFAULT_SIM = str(get_config().paths.sim_path)
except Exception:
    DEFAULT_SIM = ""


def ordered_index_map(d: Dict[int, float]) -> Dict[int, Tuple[int, float]]:
    """{iteration -> value} → {0..N-1 -> (iteration, value)} (ascending)."""
    return {i: (it, d[it]) for i, it in enumerate(sorted(d))}


def emit_ordered(name: str, idx2pair: Dict[int, Tuple[int, float]]) -> None:
    if not idx2pair:
        log.info("No entries to list for %s.", name)
        return
    log.info("Ordered index -> (timestep, %s):", name)
    for i in sorted(idx2pair):
        it, val = idx2pair[i]
        log.info("%d -> (%d, %.10g)", i, it, val)


if __name__ == "__main__":
    # Demo the helpers using either CLI-provided pairs or a tiny built-in sample.
    # Usage examples:
    #   python milestones_common.py                 # uses sample data
    #   python milestones_common.py 0:0.0 100:0.1 200:0.25
    #   python milestones_common.py 10=1.5 20=3.2   # '=' also accepted

    # 1) show the configured default simulation path
    if DEFAULT_SIM:
        log.info("DEFAULT_SIM = %s", DEFAULT_SIM)
    else:
        log.warning("DEFAULT_SIM is empty; check your configuration (paths.sim_path)")

    # 2) build the {iteration -> value} dictionary
    data: Dict[int, float] = {}
    if len(sys.argv) > 1:
        for tok in sys.argv[1:]:
            sep = ":" if ":" in tok else "=" if "=" in tok else None
            if not sep:
                log.warning("Skipping token without ':' or '=': %s", tok)
                continue
            k_str, v_str = tok.split(sep, 1)
            try:
                k = int(k_str)
                v = float(v_str)
            except Exception:
                log.warning("Skipping unparsable token: %s", tok)
                continue
            data[k] = v
    else:
        # fallback sample
        data = {0: 0.0, 100: 0.12, 200: 0.27, 350: 0.42}

    # 3) run helpers and emit
    idx2pair = ordered_index_map(data)
    emit_ordered("value", idx2pair)

    # also print a compact summary to stdout for quick tooling
    ordered_keys = sorted(data)
    print({i: (it, data[it]) for i, it in enumerate(ordered_keys)})
