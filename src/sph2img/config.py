# src/sph2img/config.py
from __future__ import annotations
import os, json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, MutableMapping

from .selectors import auto_host_config

# ---------------- dataclasses (match your schema) ----------------
@dataclass
class Name:
    run_name: str

@dataclass
class Paths:
    abs_root: Path
    project_root: Path
    sim_path: Path
    out_dir: Path
    logs_dir: Path
    cache_dir: Path

@dataclass
class Render:
    offscreen: bool
    image_w: int
    image_h: int

@dataclass
class Capture:
    mode: str
    eps: float
    x_start: float | None
    x_end: float | None
    solid_cuts: int
    front_w: int; front_h: int
    side_w: int;  side_h: int
    top_w: int;   top_h: int
    x_side_offset: float
    empty_out: bool

@dataclass
class FilesRemoval:
    post_delete: bool

@dataclass
class ParaView:
    testing: bool
    default_view: str

@dataclass
class Config:
    name: Name
    paths: Paths
    render: Render
    capture: Capture
    files_removal: FilesRemoval
    paraview: ParaView

# ---------------- helpers ----------------
def _read_json(p: Path | None) -> dict:
    return json.loads(p.read_text()) if p and p.exists() else {}

def _deep_update(dst: MutableMapping[str, Any], src: Mapping[str, Any] | None) -> MutableMapping[str, Any]:
    if not src:
        return dst
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_update(dst[k], v)
        else:
            dst[k] = v
    return dst

def _ensure_and_normalize(cfg: dict, repo_root: Path) -> None:
    """
    Guarantees:
      - paths.abs_root (ABS; from ABS_ROOT env, or 'abs_root', or derived from legacy project_root, or HOME)
      - paths.project_root := abs_root / 'sph2img'   (enforced)
      - logs_dir, cache_dir treated as REL in input; stored back as ABS
      - sim_path, out_dir may be REL or ABS in input; stored back as ABS
    """
    cfg.setdefault("paths", {})
    p = cfg["paths"]

    # expand ~ and $VARS on all strings under 'paths'
    for k, v in list(p.items()):
        if isinstance(v, str):
            p[k] = os.path.expanduser(os.path.expandvars(v))

    # 1) abs_root: priority ENV > config.abs_root > legacy(project_root parent) > HOME
    abs_root_str = os.getenv("ABS_ROOT", p.get("abs_root", "")).strip()
    if abs_root_str:
        abs_root = Path(abs_root_str).expanduser().resolve()
    else:
        pr_legacy = p.get("project_root", "").strip()
        abs_root = (Path(pr_legacy).expanduser().resolve().parent
                    if pr_legacy else Path("~").expanduser().resolve())

    if not abs_root.is_absolute():
        raise ValueError("paths.abs_root must resolve to an absolute path. Set ABS_ROOT or add 'abs_root'.")

    # 2) Enforce project_root rule
    project_root = (abs_root / "sph2img").resolve()

    # 3) required REL keys (provide defaults if missing)
    logs_rel  = p.get("logs_dir", "logs")
    cache_rel = p.get("cache_dir", ".cache")
    if Path(logs_rel).is_absolute():
        raise ValueError("paths.logs_dir must be relative to project_root.")
    if Path(cache_rel).is_absolute():
        raise ValueError("paths.cache_dir must be relative to project_root.")

    # 4) sim_path & out_dir may be REL or ABS (default out_dir if missing)
    sim_raw = p.get("sim_path", "")
    out_raw = p.get("out_dir", "outputs/")

    sim_path = Path(sim_raw)
    out_dir  = Path(out_raw)
    sim_path = (sim_path if sim_path.is_absolute() else (project_root / sim_path)).resolve()
    out_dir  = (out_dir  if out_dir.is_absolute()  else (project_root / out_dir)).resolve()

    # 5) materialize absolute strings
    p["abs_root"]     = str(abs_root)
    p["project_root"] = str(project_root)
    p["sim_path"]     = str(sim_path)
    p["out_dir"]      = str(out_dir)
    p["logs_dir"]     = str((project_root / logs_rel).resolve())
    p["cache_dir"]    = str((project_root / cache_rel).resolve())

def _to_dc(cfg: dict) -> Config:
    # ensure top-level sections exist (defensive)
    cfg.setdefault("name", {"run_name": "ss"})
    cfg.setdefault("paths", {})
    cfg.setdefault("render", {"offscreen": True, "image_w": 256, "image_h": 256})
    cfg.setdefault("capture", {
        "mode": "largest", "eps": 0.001, "x_start": None, "x_end": None, "solid_cuts": 30,
        "front_w": 256, "front_h": 256, "side_w": 512, "side_h": 256, "top_w": 256, "top_h": 256,
        "x_side_offset": 0.00007, "empty_out": True
    })
    cfg.setdefault("files_removal", {"post_delete": False})
    cfg.setdefault("paraview", {"testing": False, "default_view": "RenderView"})

    n = cfg["name"]; p = cfg["paths"]; r = cfg["render"]; c = cfg["capture"]
    fr = cfg["files_removal"]; pv = cfg["paraview"]

    # final guard: compute project_root if missing (shouldn’t happen after normalize)
    if "project_root" not in p:
        abs_root = Path(p.get("abs_root", Path("~").expanduser()))
        p["project_root"] = str((abs_root / "sph2img").resolve())

    return Config(
        name=Name(**n),
        paths=Paths(
            abs_root=Path(p["abs_root"]),
            project_root=Path(p["project_root"]),
            sim_path=Path(p["sim_path"]),
            out_dir=Path(p["out_dir"]),
            logs_dir=Path(p["logs_dir"]),
            cache_dir=Path(p["cache_dir"]),
        ),
        render=Render(**r),
        capture=Capture(
            mode=c["mode"], eps=c["eps"],
            x_start=c.get("x_start"), x_end=c.get("x_end"),
            solid_cuts=c["solid_cuts"],
            front_w=c["front_w"], front_h=c["front_h"],
            side_w=c["side_w"],  side_h=c["side_h"],
            top_w=c["top_w"],    top_h=c["top_h"],
            x_side_offset=c["x_side_offset"], empty_out=c["empty_out"],
        ),
        files_removal=FilesRemoval(**fr),
        paraview=ParaView(**pv),
    )

# ---------------- main API ----------------
def get_config(config_path: str | None = None) -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    cfg_dir   = repo_root / "config"

    merged: dict = {}

    # BASE: prefer config/defaults.json, else legacy root config.json
    if (cfg_dir / "defaults.json").exists():
        merged = _deep_update(merged, _read_json(cfg_dir / "defaults.json"))
    elif (repo_root / "config.json").exists():
        merged = _deep_update(merged, _read_json(repo_root / "config.json"))
    else:
        raise RuntimeError("No base config found. Add config/defaults.json or keep root config.json.")

    # host override (JSON), if any
    host_file = auto_host_config(cfg_dir)
    if host_file:
        merged = _deep_update(merged, _read_json(host_file))

    # ENV override (JSON)
    env_p = os.getenv("S2I_CONFIG")
    if env_p:
        merged = _deep_update(merged, _read_json(Path(env_p)))

    # CLI override (JSON)
    if config_path:
        merged = _deep_update(merged, _read_json(Path(config_path)))

    # normalize & return dataclasses
    _ensure_and_normalize(merged, repo_root)
    return _to_dc(merged)
