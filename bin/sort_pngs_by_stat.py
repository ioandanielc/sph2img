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
    ap = argparse.ArgumentParser(description="Copy PNGs into result_directory/<cat>/<view>/")
    ap.add_argument("--images-path", required=True, type=Path)
    ap.add_argument("--result-directory", required=True, type=Path)
    ap.add_argument("--unaccounted-file", required=True, type=Path)
    ap.add_argument("--stable-file", required=True, type=Path)
    ap.add_argument("--unstable-file", required=True, type=Path)
    args = ap.parse_args()

    src_root = args.images_path.expanduser().resolve()
    dst_root = args.result_directory.expanduser().resolve()
    dst_root.mkdir(parents=True, exist_ok=True)

    cats  = ("unaccounted", "stable", "unstable")
    views = ("front", "side", "top")
    for c in cats:
        for v in views:
            (dst_root / c / v).mkdir(parents=True, exist_ok=True)

    unaccounted = load_list(args.unaccounted_file.expanduser().resolve())
    stable      = load_list(args.stable_file.expanduser().resolve())
    unstable    = load_list(args.unstable_file.expanduser().resolve())

    copied = 0
    skipped = 0
    for png in src_root.rglob("*.png"):
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

        dst = dst_root / cat / view / name
        try:
            shutil.copy2(str(png), str(dst))  # copy, preserve metadata
            copied += 1
        except Exception as e:
            print(f"[WARN] could not copy {png} -> {dst}: {e}", file=sys.stderr)

    print(f"[DONE] copied={copied} skipped={skipped} into {dst_root}")

if __name__ == "__main__":
    sys.exit(main())
