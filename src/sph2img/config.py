# src/sph2img/config.py
from __future__ import annotations
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
import json, os
from typing import Optional

# ---------------- Data models ----------------
@dataclass(frozen=True)
class Paths:
    project_root: Path   # ABS only, authoritative
    sim_path: Path       # ABS ok or REL→resolved under project_root
    out_dir: Path        # ABS ok or REL→resolved under project_root
    logs_dir: Path       # RELATIVE ONLY → resolved under project_root
    cache_dir: Path      # RELATIVE ONLY → resolved under project_root

    # Back-compat for code using paths.ss_dir + '/screenshots'
    @property
    def ss_dir(self) -> str:
        # Return string so existing string concatenations keep working
        return str(self.out_dir)

@dataclass(frozen=True)
class Render:
    offscreen: bool
    image_w: int
    image_h: int

@dataclass(frozen=True)
class ParaView:
    testing: bool = True
    default_view: str = "RenderView"

@dataclass(frozen=True)
class Capture:
    mode: str
    eps: float
    x_start: Optional[float]
    x_end: Optional[float]
    solid_cuts: int

    # keep individual names EXACTLY (no renames)
    front_w: int
    front_h: int
    side_w: int
    side_h: int
    top_w: int
    top_h: int

    x_side_offset: float
    empty_out: bool

    # convenience (non-breaking): tuple views
    @property
    def front(self) -> tuple[int, int]:
        return (self.front_w, self.front_h)

    @property
    def side(self) -> tuple[int, int]:
        return (self.side_w, self.side_h)

    @property
    def top(self) -> tuple[int, int]:
        return (self.top_w, self.top_h)

@dataclass(frozen=True)
class Name:
    run_name: str

@dataclass(frozen=True)
class FilesRemoval:
    post_delete: bool

@dataclass(frozen=True)
class Config:
    name: Name
    paths: Paths
    render: Render
    capture: Capture
    files_removal: FilesRemoval
    paraview: ParaView = field(default_factory=ParaView)

# ---------------- Helpers ----------------
def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}

def _expand(s: str | None) -> str | None:
    return os.path.expandvars(s) if isinstance(s, str) else s

def _resolve_rel(base: Path, value: str | None, default_rel: str) -> Path:
    """Resolve a relative string under 'base'. Absolute values are forbidden here."""
    v = _expand(value)
    if not v:
        return (base / default_rel).resolve()
    p = Path(v).expanduser()
    if p.is_absolute():
        raise ValueError(f"Absolute paths are not allowed for this key: {p}")
    return (base / p).resolve()

def _resolve_rel_or_abs(base: Path, value: str | None, default_rel: str) -> Path:
    """For sim_path/out_dir: accept ABS or REL (REL resolves under base)."""
    v = _expand(value)
    if not v:
        return (base / default_rel).resolve()
    p = Path(v).expanduser()
    return p.resolve() if p.is_absolute() else (base / p).resolve()

# ---------------- Public API ----------------
@lru_cache(maxsize=1)
def get_config() -> Config:
    # Locate config.json relative to this file (repo root two levels up),
    # but paths.project_root in the file remains authoritative.
    code_root = Path(__file__).resolve().parents[2]
    cfg = _read_json(code_root / "config.json")

    name_cfg  = cfg.get("name", {}) or {}
    paths_cfg = cfg.get("paths", {}) or {}
    render_cfg= cfg.get("render", {}) or {}
    cap_cfg   = cfg.get("capture", {}) or {}
    fr_cfg    = cfg.get("files_removal", {}) or {}
    pv_cfg    = cfg.get("paraview", {}) or {}

    # name
    name = Name(run_name=str(name_cfg.get("run_name", "run")))

    # paths
    pr = _expand(paths_cfg.get("project_root"))
    if not pr:
        raise ValueError("config.json: paths.project_root is required and must be an absolute path.")
    project_root = Path(pr).expanduser().resolve()
    if not project_root.is_absolute():
        raise ValueError(f"config.json: paths.project_root must be absolute, got: {pr}")

    sim_path = _resolve_rel_or_abs(project_root, paths_cfg.get("sim_path"), "simulations/mhpc3d_200W_Ti64_Ar-3")
    out_dir  = _resolve_rel_or_abs(project_root, paths_cfg.get("out_dir"),  "outputs/")
    logs_dir = _resolve_rel(project_root,       paths_cfg.get("logs_dir"),  "logs")
    cache_dir= _resolve_rel(project_root,       paths_cfg.get("cache_dir"), ".cache")

    # ensure writable dirs exist
    for d in (out_dir, logs_dir, cache_dir):
        d.mkdir(parents=True, exist_ok=True)

    paths = Paths(
        project_root=project_root,
        sim_path=sim_path,
        out_dir=out_dir,
        logs_dir=logs_dir,
        cache_dir=cache_dir
    )

    # render (keep names as in JSON)
    render = Render(
        offscreen=bool(render_cfg.get("offscreen", True)),
        image_w=int(render_cfg.get("image_w", 256)),
        image_h=int(render_cfg.get("image_h", 256)),
    )

    # capture (keep EXACT field names)
    capture = Capture(
        mode=str(cap_cfg.get("mode", "largest")),
        eps=float(cap_cfg.get("eps", 1e-3)),
        x_start=(float(cap_cfg["x_start"]) if cap_cfg.get("x_start") is not None else None),
        x_end=(float(cap_cfg["x_end"]) if cap_cfg.get("x_end") is not None else None),
        solid_cuts=int(cap_cfg.get("solid_cuts", 30)),
        front_w=int(cap_cfg.get("front_w", 256)),
        front_h=int(cap_cfg.get("front_h", 256)),
        side_w=int(cap_cfg.get("side_w", 256)),
        side_h=int(cap_cfg.get("side_h", 256)),
        top_w=int(cap_cfg.get("top_w", 256)),
        top_h=int(cap_cfg.get("top_h", 256)),
        x_side_offset=float(cap_cfg.get("x_side_offset", 7e-5)),
        empty_out=bool(cap_cfg.get("empty_out", True)),
    )

    files_removal = FilesRemoval(
        post_delete=bool(fr_cfg.get("post_delete", False))
    )

    paraview = ParaView(
        testing=bool(pv_cfg.get("testing", True)),
        default_view=str(pv_cfg.get("default_view", "RenderView")),
    )

    return Config(
        name=name,
        paths=paths,
        render=render,
        capture=capture,
        files_removal=files_removal,
        paraview=paraview
    )

def reload_config_cache() -> None:
    get_config.cache_clear()
