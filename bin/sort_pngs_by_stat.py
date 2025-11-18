#!/usr/bin/env python3
import sys, argparse, shutil, re
from pathlib import Path

VIEW_RE = re.compile(r"(front|side|top)\.png$", re.IGNORECASE)
ITER_RE = re.compile(r"ss_(\d+)_", re.IGNORECASE)

def load_list(path: Path) -> set[int]:
    s = set()
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                s.add(int(line))
            except ValueError:
                pass
    return s

def main():
    ap = argparse.ArgumentParser(
        description=(
            "Copy PNGs into result_directory/<cat>/<view>/, then move original PNGs "
            "to ./png_files and GIFs to ./gif_files under images-path. "
            "Optionally move a monitor/ directory into result_directory/monitor/."
        )
    )
    ap.add_argument("--images-path", required=True, type=Path)
    ap.add_argument("--result-directory", required=True, type=Path)
    ap.add_argument("--unaccounted-file", required=True, type=Path)
    ap.add_argument("--stable-file", required=True, type=Path)
    ap.add_argument("--unstable-file", required=True, type=Path)
    # NEW: optional monitor path (typically sim/monitor)
    ap.add_argument("--monitor-path", required=False, type=Path)
    args = ap.parse_args()

    src_root = args.images_path.expanduser().resolve()
    dst_root = args.result_directory.expanduser().resolve()
    dst_root.mkdir(parents=True, exist_ok=True)

    # Folders where originals will be moved (under images-path)
    png_store = src_root / "png_files"
    gif_store = src_root / "gif_files"
    png_store.mkdir(parents=True, exist_ok=True)
    gif_store.mkdir(parents=True, exist_ok=True)

    # Prepare destination classification dirs
    cats  = ("unaccounted", "stable", "unstable")
    views = ("front", "side", "top")
    for c in cats:
        for v in views:
            (dst_root / 'sorted_png_files' / c / v).mkdir(parents=True, exist_ok=True)

    unaccounted = load_list(args.unaccounted_file.expanduser().resolve())
    stable      = load_list(args.stable_file.expanduser().resolve())
    unstable    = load_list(args.unstable_file.expanduser().resolve())

    copied = 0
    skipped = 0
    moved_png = 0
    moved_gif = 0

    # Take a snapshot list so moving files doesn't interfere with rglob iteration
    png_files = list(src_root.rglob("*.png"))

    # Classify + copy PNGs, then move originals to png_files/
    for png in png_files:
        name = png.name
        m_view = VIEW_RE.search(name)
        m_iter = ITER_RE.search(name)
        if not m_view or not m_iter:
            skipped += 1
            continue

        view = m_view.group(1).lower()
        it = int(m_iter.group(1))

        if it in stable:
            cat = "stable"
        elif it in unstable:
            cat = "unstable"
        elif it in unaccounted:
            cat = "unaccounted"
        else:
            skipped += 1
            continue

        dst = dst_root / 'sorted_png_files' / cat / view
        try:
            # Copy to category/view destination
            shutil.copy2(str(png), str(dst))  # preserve metadata
            copied += 1

            # Move original PNG into png_files/
            final_png_path = png_store / name
            shutil.move(str(png), str(final_png_path))
            moved_png += 1
        except Exception as e:
            print(f"[WARN] could not handle {png} -> {dst}: {e}", file=sys.stderr)

    # Now move all GIFs into gif_files/
    gif_files = list(src_root.rglob("*.gif"))
    for g in gif_files:
        try:
            final_gif_path = gif_store / g.name
            shutil.move(str(g), str(final_gif_path))
            moved_gif += 1
        except Exception as e:
            print(f"[WARN] could not move GIF {g} -> {gif_store}: {e}", file=sys.stderr)

    # OPTIONAL: move sim/monitor → result_directory/monitor
    if args.monitor_path is not None:
        monitor_src = args.monitor_path.expanduser().resolve()
        monitor_dst = dst_root / "monitor"
        monitor_dst.mkdir(parents=True, exist_ok=True)

        if monitor_src.is_dir():
            for item in monitor_src.iterdir():
                target = monitor_dst / item.name
                try:
                    shutil.copy2(str(item), str(target))
                except Exception as e:
                    print(f"[WARN] could not move {item} -> {target}: {e}", file=sys.stderr)
        else:
            print(f"[WARN] monitor-path '{monitor_src}' is not a directory", file=sys.stderr)

    print(
        f"[DONE] copied_png={copied} "
        f"moved_png={moved_png} moved_gif={moved_gif} "
        f"skipped_png={skipped} into {dst_root}"
    )

if __name__ == "__main__":
    sys.exit(main())
