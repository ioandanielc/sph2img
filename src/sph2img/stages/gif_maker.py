# src/sph2img/utils/make_gifs_by_view.py
#!/usr/bin/env python3

# --- path bootstrap: make `sph2img` importable even when run as a script -----
from pathlib import Path

import os
from collections import defaultdict, OrderedDict
from typing import Dict, List, OrderedDict as TOrderedDict

from PIL import Image  # pip install pillow

from sph2img.utils.pvlog import get_logger
from sph2img.config import get_config

log = get_logger(__name__)

# --- config ---
FRAME_DURATION_MS = 200  # per-frame delay in ms for the GIF
ALLOWED_VIEWS = ("front", "side", "top")


# ---------- helpers ----------

def _parse(folder: Path) -> Dict[str, Dict[str, TOrderedDict[int, Path]]]:
    """
    Crawl <folder> for *.png and group into:
        exps[exp][view][iter] = Path

    Filenames must look like: "<exp>_<iter>_<view>.png"
    where <exp> may contain underscores. We split from the right:
        base.rsplit("_", 2) -> [exp, iter_str, view]
    """
    exps: Dict[str, Dict[str, Dict[int, Path]]] = defaultdict(lambda: defaultdict(dict))
    skipped = 0

    for p in folder.rglob("*.png"):
        base = p.name[:-4]  # strip ".png"
        try:
            exp, it_str, view = base.rsplit("_", 2)
        except ValueError:
            skipped += 1
            continue

        view_l = view.lower()
        if view_l not in ALLOWED_VIEWS:
            skipped += 1
            continue

        if not it_str.isdigit():
            skipped += 1
            continue

        exps[exp][view_l][int(it_str)] = p

    # order iterations
    for exp in exps:
        for view in exps[exp]:
            exps[exp][view] = OrderedDict(sorted(exps[exp][view].items()))

    if skipped:
        log.info("Skipped %d files that didn't match '<exp>_<iter>_<view>.png'.", skipped)
    return exps  # type: ignore[return-value]


def _open_frame(path: Path, ref_size: tuple[int, int] | None = None) -> Image.Image:
    """
    Open an image and return a *flattened RGB* frame (no alpha).
    This avoids any accidental transparency when saving to GIF.
    """
    im = Image.open(path)
    # If the image has alpha (RGBA/LA or P with transparency), composite on opaque background.
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        bg = Image.new("RGBA", im.size, (0, 0, 0, 255))
        bg.paste(im, (0, 0), im if im.mode in ("RGBA", "LA") else None)
        im = bg.convert("RGB")
    else:
        im = im.convert("RGB")

    if ref_size and im.size != ref_size:
        im = im.resize(ref_size, Image.BICUBIC)
    return im


def _save_gif(paths: List[Path], out_path: Path, duration_ms: int = FRAME_DURATION_MS) -> bool:
    """Save a GIF from a list of image paths. Returns True if written, False if empty list."""
    if not paths:
        return False

    first = _open_frame(paths[0])
    ref_size = first.size
    frames = [first] + [_open_frame(p, ref_size) for p in paths[1:]]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    first.save(
        out_path,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=0,
        optimize=False,
    )
    log.info("Wrote: %s", out_path)
    return True


# ---------- main API ----------

def gif_creator(folder_path: str) -> None:
    """
    Build one GIF per (experiment, view) using all iterations in order.
    Output files: animation_<exp>_<view>.gif in the same folder.
    """
    folder = Path(folder_path).expanduser().resolve()
    log.info("Scanning: %s", folder)
    if not folder.is_dir():
        raise SystemExit(f"Folder not found: {folder}")

    exps = _parse(folder)
    if not exps:
        raise SystemExit("No matching files found.")

    made = 0
    for exp, views in exps.items():
        for view in ALLOWED_VIEWS:
            seq = views.get(view)
            if not seq:
                continue
            paths = list(seq.values())
            out_name = f"animation_{exp}_{view}.gif"
            _save_gif(paths, folder / out_name)
            made += 1

    if made == 0:
        raise SystemExit("Found files, but nothing matched the required pattern.")
    log.info("Done. Generated %d GIF(s).", made)


def main() -> None:
    """
    Config-driven default: read screenshots from cfg.paths.out_dir
    and build GIFs per experiment/view.
    """
    cfg = get_config()
    folder = str(cfg.paths.out_dir) + "/screenshots_2025-10-13_19-42-39-834"
    gif_creator(folder)


# 1) Auto-run via config flag (paraview.testing) without CLI
# run_main_if_testing(main)
