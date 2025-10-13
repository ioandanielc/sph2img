from __future__ import annotations
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
import json, os

# ---------------- Data models ----------------
@dataclass(frozen=True)
class Paths:
    project_root: Path   # authoritative repo root from config.json
    sim_path: Path       # ABS ok (LRZ) or REL→resolved under project_root
    out_dir: Path        # ABS ok (LRZ) or REL→resolved under project_root
    logs_dir: Path       # RELATIVE ONLY → resolved under project_root
    cache_dir: Path      # RELATIVE ONLY → resolved under project_root

@dataclass(frozen=True)
class Render:
    offscreen: bool
    image_size: tuple[int, int]

@dataclass(frozen=True)
class ParaView:
    testing: bool = True
    default_view: str = "RenderView"

@dataclass(frozen=True)
class Capture:
    mode: str
    eps: float
    x_start: float | None
    x_end: float | None
    solid_cuts: int
    front: tuple[int, int]
    side: tuple[int, int]
    top: tuple[int, int]
    x_side_offset: float
    empty_out: bool

@dataclass(frozen=True)
class Config:
    paths: Paths
    render: Render
    capture: Capture
    paraview: ParaView = field(default_factory=ParaView)

# ---------------- Helpers ----------------
def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}

def _expand(s: str | None) -> str | None:
    return os.path.expandvars(s) if isinstance(s, str) else s  # supports $USER, etc.

def _resolve_rel(base: Path, value: str | None, default_rel: str) -> Path:
    """
    Resolve a relative string under 'base'. If empty, use 'default_rel' under base.
    Absolute values are NOT allowed here (we enforce relative-only for some keys).
    """
    v = _expand(value)
    if not v:
        return (base / default_rel).resolve()
    p = Path(v).expanduser()
    if p.is_absolute():
        raise ValueError(f"Absolute paths are not allowed for this key: {p}")
    return (base / p).resolve()

def _resolve_rel_or_abs(base: Path, value: str | None, default_rel: str) -> Path:
    """
    For sim_path/out_dir: accept ABS or REL (REL resolves under base).
    """
    v = _expand(value)
    if not v:
        return (base / default_rel).resolve()
    p = Path(v).expanduser()
    return p.resolve() if p.is_absolute() else (base / p).resolve()

def _pair(v, dw, dh) -> tuple[int, int]:
    if isinstance(v, (list, tuple)) and len(v) >= 2:
        return int(v[0]), int(v[1])
    return int(dw), int(dh)

# ---------------- Public API ----------------
@lru_cache(maxsize=1)
def get_config() -> Config:
    # Find config.json relative to this file (3 levels up = repo root by code position),
    # BUT project_root in the file is authoritative.
    code_root = Path(__file__).resolve().parents[2]
    cfg = _read_json(code_root / "config.json")
    paths_cfg = cfg.get("paths", {}) or {}
    render_cfg = cfg.get("render", {}) or {}
    cap_cfg = cfg.get("capture", {}) or {}
    pv_cfg  = cfg.get("paraview", {}) or {}


    # 1) project_root is REQUIRED and must be ABS
    pr = _expand(paths_cfg.get("project_root"))
    if not pr:
        raise ValueError("config.json: paths.project_root is required and must be an absolute path.")
    project_root = Path(pr).expanduser().resolve()
    if not project_root.is_absolute():
        raise ValueError(f"config.json: paths.project_root must be absolute, got: {pr}")

    # 2) Resolve paths with the policy you asked for
    sim_path = _resolve_rel_or_abs(project_root, paths_cfg.get("sim_path"), "simulations/mhpc3d_200W_Ti64_Ar-3")
    out_dir  = _resolve_rel_or_abs(project_root, paths_cfg.get("out_dir"),  "outputs/screenshots")
    logs_dir = _resolve_rel(project_root,       paths_cfg.get("logs_dir"),  "logs")     # REL only
    cache_dir= _resolve_rel(project_root,       paths_cfg.get("cache_dir"), ".cache")   # REL only

    # 3) Make sure write targets exist
    for d in (out_dir, logs_dir, cache_dir):
        d.mkdir(parents=True, exist_ok=True)

    # 4) Render + Capture
    W = int(render_cfg.get("image_w", 256))
    H = int(render_cfg.get("image_h", 256))
    render = Render(offscreen=bool(render_cfg.get("offscreen", True)),
                    image_size=(W, H))

    capture = Capture(
        mode=cap_cfg.get("mode", "largest"),
        eps=float(cap_cfg.get("eps", 1e-3)),
        x_start=(float(cap_cfg["x_start"]) if cap_cfg.get("x_start") is not None else None),
        x_end=(float(cap_cfg["x_end"]) if cap_cfg.get("x_end") is not None else None),
        solid_cuts=int(cap_cfg.get("solid_cuts", 30)),
        front=_pair((cap_cfg.get("front_w"), cap_cfg.get("front_h")), 256, 256),
        side=_pair((cap_cfg.get("side_w"),  cap_cfg.get("side_h")),  256, 256),
        top=_pair((cap_cfg.get("top_w"),   cap_cfg.get("top_h")),   256, 256),
        x_side_offset=float(cap_cfg.get("x_side_offset", 7e-5)),
        empty_out=bool(cap_cfg.get("empty_out", True)),
    )

    paraview = ParaView(
        testing=bool(pv_cfg.get("testing", True)),
        default_view=str(pv_cfg.get("default_view", "RenderView")),
    )


    return Config(
        paths=Paths(
            project_root=project_root,
            sim_path=sim_path,
            out_dir=out_dir,
            logs_dir=logs_dir,
            cache_dir=cache_dir
        ),
        render=render,
        capture=capture,
        paraview=paraview
    )

def reload_config_cache() -> None:
    get_config.cache_clear()
