#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sph2img - configuration & repo preflight checker.

Goals
- Works even during repo setup: shows False for missing/misplaced bits without crashing.
- Enforces your path policy:
  * paths.project_root: ABSOLUTE (authoritative)
  * paths.sim_path: ABS or REL (resolved under project_root)
  * paths.out_dir:  ABS or REL (resolved under project_root)
  * paths.logs_dir: RELATIVE ONLY (resolved under project_root)
  * paths.cache_dir: RELATIVE ONLY (resolved under project_root)
- Validates config schema & value types.
- Optional actions:
  --allow-missing   : Don’t fail on missing dirs/files (still report False).
  --fix             : Create missing dirs (logs/cache/out_dir) and re-check writability.
  --strict          : Fail on any missing OR policy error (default).
  --no-paraview     : Skip ParaView import check.

Exit codes
  0 = OK (or OK under --allow-missing)
  1 = Non-fatal issues fixed under --fix (policy OK after fix)
  2 = Errors (policy violations, unreadable config, or missing when not allowed)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple
import argparse
import json
import os
import sys

# -----------------------------------------------------------------------------
# Path bootstrap so `from sph2img...` works regardless of CWD
# Repo layout:  <repo>/bin/pv_config_check.py   &   <repo>/src/sph2img/...
# -----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]  # repo root
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Import only the dataclasses/types; ParaView is optional here.
try:
    from sph2img.config import get_config  # noqa: F401  (not required but ensures package import works)
    CONFIG_IMPORTABLE = True
except Exception:
    CONFIG_IMPORTABLE = False


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Preflight check for sph2img repo/config.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument(
        "--allow-missing",
        action="store_true",
        help="Don’t fail if paths are missing; still report False but exit 0 unless policy error.",
    )
    p.add_argument(
        "--fix",
        action="store_true",
        help="Create missing dirs (logs/cache/out_dir) and re-check writability.",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Fail on any missing OR policy error (default behavior if this flag is present).",
    )
    p.add_argument(
        "--no-paraview",
        action="store_true",
        help="Skip ParaView import test.",
    )
    return p.parse_args()


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------
@dataclass
class PathCheck:
    declared: Optional[str]         # raw config value (str or None)
    resolved: Optional[Path]        # resolved absolute path (or None on failure)
    policy_ok: bool                 # path policy satisfied (abs/rel rule)
    exists: bool                    # path exists on filesystem
    writable: Optional[bool]        # None if not applicable; else True/False


def _read_json(path: Path) -> Tuple[Optional[dict], Optional[str]]:
    if not path.exists():
        return None, f"Missing file: {path}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as e:
        return None, f"Failed to parse JSON ({path}): {e}"


def _expand_env(s: Optional[str]) -> Optional[str]:
    return os.path.expandvars(s) if isinstance(s, str) else s


def _is_writable_dir(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        test = p / ".writetest"
        test.write_text("ok", encoding="utf-8")
        test.unlink()
        return True
    except Exception:
        return False


def _resolve_rel(base: Path, value: Optional[str], default_rel: str) -> PathCheck:
    v = _expand_env(value)
    if not v:
        p = (base / default_rel).resolve()
        return PathCheck(value, p, policy_ok=True, exists=p.exists(), writable=None)
    cand = Path(v).expanduser()
    if cand.is_absolute():
        # RELATIVE ONLY policy violation
        return PathCheck(value, cand, policy_ok=False, exists=cand.exists(), writable=None)
    p = (base / cand).resolve()
    return PathCheck(value, p, policy_ok=True, exists=p.exists(), writable=None)


def _resolve_rel_or_abs(base: Path, value: Optional[str], default_rel: str) -> PathCheck:
    v = _expand_env(value)
    if not v:
        p = (base / default_rel).resolve()
        return PathCheck(value, p, policy_ok=True, exists=p.exists(), writable=None)
    cand = Path(v).expanduser()
    p = cand.resolve() if cand.is_absolute() else (base / cand).resolve()
    return PathCheck(value, p, policy_ok=True, exists=p.exists(), writable=None)


def _fmt_bool(b: Optional[bool]) -> str:
    return "—" if b is None else ("True" if b else "False")


# -----------------------------------------------------------------------------
# Main check
# -----------------------------------------------------------------------------
def main() -> int:
    args = parse_args()

    print("== sph2img preflight ==")
    print(f"Repo root (by script location): {ROOT}")
    print(f"Package importable: {CONFIG_IMPORTABLE}")
    print()

    # 1) config.json
    cfg_path = ROOT / "config.json"
    cfg, cfg_err = _read_json(cfg_path)
    if cfg_err:
        print(f"[CONFIG] {cfg_err}")
        if args.allow_missing:
            print("\nConfig keys expected under `paths`, `render`, `capture`.")
            return 0
        return 2

    # Basic schema expectations (soft)
    paths_cfg = cfg.get("paths", {}) or {}
    render_cfg = cfg.get("render", {}) or {}
    cap_cfg = cfg.get("capture", {}) or {}

    if not isinstance(paths_cfg, dict):
        print("[ERROR] `paths` must be an object.")
        return 2
    if not isinstance(render_cfg, dict):
        print("[ERROR] `render` must be an object.")
        return 2
    if not isinstance(cap_cfg, dict):
        print("[ERROR] `capture` must be an object.")
        return 2

    # 2) project_root (required, absolute)
    pr_raw = _expand_env(paths_cfg.get("project_root"))
    if not pr_raw:
        print("[ERROR] paths.project_root is required and must be an absolute path.")
        return 2
    project_root = Path(pr_raw).expanduser().resolve()
    pr_abs_ok = project_root.is_absolute()
    pr_exists = project_root.exists()
    print(f"project_root  : {project_root}  | absolute={pr_abs_ok}  exists={pr_exists}")

    policy_error = not pr_abs_ok

    # 3) Resolve other paths with policy
    sim_ck   = _resolve_rel_or_abs(project_root, paths_cfg.get("sim_path"),  "simulations/mhpc3d_200W_Ti64_Ar-3")
    out_ck   = _resolve_rel_or_abs(project_root, paths_cfg.get("out_dir"),   "outputs/screenshots")
    logs_ck  = _resolve_rel(project_root,       paths_cfg.get("logs_dir"),   "logs")
    cache_ck = _resolve_rel(project_root,       paths_cfg.get("cache_dir"),  ".cache")

    # apply writability checks (only for dirs we expect to be writable)
    for ck in (out_ck, logs_ck, cache_ck):
        ck.writable = _is_writable_dir(ck.resolved) if (ck.policy_ok and ck.resolved) else None

    # 4) Render/Capture (soft extract)
    def _as_int(x, default):
        try:
            return int(x)
        except Exception:
            return default

    def _as_float(x, default):
        try:
            return float(x)
        except Exception:
            return default

    render_offscreen = bool(render_cfg.get("offscreen", True))
    render_w = _as_int(render_cfg.get("image_w", 256), 256)
    render_h = _as_int(render_cfg.get("image_h", 256), 256)

    cap_mode = str(cap_cfg.get("mode", "largest"))
    cap_eps  = _as_float(cap_cfg.get("eps", 1e-3), 1e-3)
    cap_cuts = _as_int(cap_cfg.get("solid_cuts", 30), 30)

    # 5) ParaView availability (optional)
    pv_ok = None
    if not args.no_paraview:
        try:
            import importlib
            importlib.import_module("paraview.simple")
            pv_ok = True
        except Exception:
            pv_ok = False

    # 6) Report
    print("\n-- Paths (policy/existence/writable) --")
    print(f"sim_path      : {sim_ck.resolved}  | policy_ok={sim_ck.policy_ok}  exists={sim_ck.exists}  writable={_fmt_bool(sim_ck.writable)}")
    print(f"out_dir       : {out_ck.resolved}   | policy_ok={out_ck.policy_ok}  exists={out_ck.exists}  writable={_fmt_bool(out_ck.writable)}")
    print(f"logs_dir      : {logs_ck.resolved}  | policy_ok={logs_ck.policy_ok} exists={logs_ck.exists} writable={_fmt_bool(logs_ck.writable)}  (RELATIVE ONLY)")
    print(f"cache_dir     : {cache_ck.resolved} | policy_ok={cache_ck.policy_ok} exists={cache_ck.exists} writable={_fmt_bool(cache_ck.writable)}  (RELATIVE ONLY)")

    print("\n-- Render/Capture --")
    print(f"offscreen={render_offscreen}  image_size=({render_w}x{render_h})")
    print(f"mode={cap_mode}  eps={cap_eps}  solid_cuts={cap_cuts}")

    if pv_ok is not None:
        print(f"\n-- ParaView import --\nparaview.simple importable: {pv_ok}")

    # 7) Exit logic
    policy_error |= not pr_exists
    for ck in (logs_ck, cache_ck):
        if not ck.policy_ok:
            policy_error = True

    any_missing = (not sim_ck.exists) or (not out_ck.exists) or (not logs_ck.exists) or (not cache_ck.exists)

    if args.fix:
        # Create only the dirs we own (logs/cache/out); not sim_path (input)
        created = []
        for label, ck in (("out_dir", out_ck), ("logs_dir", logs_ck), ("cache_dir", cache_ck)):
            if ck.policy_ok and ck.resolved and not ck.exists:
                try:
                    ck.resolved.mkdir(parents=True, exist_ok=True)
                    ck.exists = True
                    ck.writable = _is_writable_dir(ck.resolved)
                    created.append(label)
                except Exception:
                    pass
        if created:
            print(f"\n[fix] created: {', '.join(created)}")
        # recompute missing flag
        any_missing = (not sim_ck.exists) or (not out_ck.exists) or (not logs_ck.exists) or (not cache_ck.exists)

    if policy_error:
        print("\n[RESULT] POLICY ERROR(S) — please fix the items above marked policy_ok=False or project_root invalid.")
        return 2

    if any_missing:
        if args.allow_missing and not args.strict:
            print("\n[RESULT] OK (allow-missing): some paths are missing while repo is being set up.")
            return 0
        elif args.fix:
            print("\n[RESULT] Some paths were created, but others still missing (e.g., sim_path).")
            return 1
        else:
            print("\n[RESULT] MISSING paths — run with --allow-missing during setup or --fix to create owned dirs.")
            return 2

    print("\n[RESULT] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
