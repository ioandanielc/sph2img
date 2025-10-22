#!/usr/bin/env python3
"""
Copy every n-th VTK snapshot per phase to a target directory.

Example:
  python select_every_n_vtk.py \
      /path/to/output \
      /path/to/selection \
      --stride 50

Behavior:
- Groups files by phase using the filename pattern:
    out_phase_<PHASE_NUM>_<PHASE_NAME>_rank_<RANK>_<ITER>.vtk
- Sorts each group by <ITER> (numeric) and takes every n-th item.
- Copies to DEST, preserving per-phase subfolders by default:
    DEST/<PHASE_NUM>_<PHASE_NAME>/<original_file>
- Use --flat to put all copies directly in DEST (no subfolders).
"""

from __future__ import annotations
import argparse
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

# Matches: out_phase_2_LIQUID_rank_0_123859.vtk
VTK_RE = re.compile(
    r"^out_phase_(?P<phase_num>\d+)_(?P<phase_name>[A-Z]+)_rank_(?P<rank>\d+)_(?P<iter>\d+)\.vtk$"
)

@dataclass(frozen=True)
class VtkInfo:
    phase_num: int
    phase_name: str
    rank: int
    iteration: int
    path: Path

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Copy every n-th VTK file per phase into a destination directory."
    )
    p.add_argument("src", type=Path, help="Source directory containing VTK files (e.g., .../output)")
    p.add_argument("dest", type=Path, help="Destination directory for selected files")
    p.add_argument("--stride", "-n", type=int, default=50, help="Take every n-th file per phase (default: 50)")
    p.add_argument("--offset", type=int, default=0, help="Start offset within each phase before striding (default: 0)")
    p.add_argument("--flat", action="store_true", help="Do not create per-phase subfolders in DEST")
    p.add_argument("--dry-run", action="store_true", help="Print what would be copied, but do not copy")
    p.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    return p.parse_args()

def scan_vtks(src: Path) -> List[VtkInfo]:
    if not src.is_dir():
        raise SystemExit(f"Source directory does not exist or is not a directory: {src}")
    infos: List[VtkInfo] = []
    # os.scandir is faster on huge dirs
    with os.scandir(src) as it:
        for entry in it:
            if not entry.is_file():
                continue
            m = VTK_RE.match(entry.name)
            if not m:
                continue
            infos.append(
                VtkInfo(
                    phase_num=int(m["phase_num"]),
                    phase_name=m["phase_name"],
                    rank=int(m["rank"]),
                    iteration=int(m["iter"]),
                    path=Path(entry.path),
                )
            )
    return infos

def group_by_phase(infos: List[VtkInfo]) -> Dict[Tuple[int, str], List[VtkInfo]]:
    groups: Dict[Tuple[int, str], List[VtkInfo]] = {}
    for info in infos:
        key = (info.phase_num, info.phase_name)
        groups.setdefault(key, []).append(info)
    # Sort each group by iteration
    for key in groups:
        groups[key].sort(key=lambda x: x.iteration)
    return groups

def select_stride(items: List[VtkInfo], stride: int, offset: int) -> List[VtkInfo]:
    if stride <= 0:
        raise ValueError("Stride must be a positive integer.")
    if offset < 0:
        raise ValueError("Offset must be >= 0.")
    if not items:
        return []
    start = min(offset, max(len(items) - 1, 0))
    return items[start::stride]

def main() -> None:
    args = parse_args()
    src: Path = args.src.resolve()
    dest: Path = args.dest.resolve()
    stride: int = args.stride
    offset: int = args.offset
    flat: bool = args.flat
    dry: bool = args.dry_run
    verbose: bool = args.verbose

    infos = scan_vtks(src)
    if not infos:
        raise SystemExit(f"No matching VTK files found under: {src}")

    groups = group_by_phase(infos)

    if verbose:
        total = sum(len(v) for v in groups.values())
        print(f"Found {total} matching files across {len(groups)} phases in {src}")
        for (pnum, pname), items in sorted(groups.items()):
            print(f"  Phase {pnum}_{pname}: {len(items)} files")

    # Ensure destination exists
    if not dry:
        dest.mkdir(parents=True, exist_ok=True)

    copied = 0
    for (phase_num, phase_name), items in sorted(groups.items()):
        chosen = select_stride(items, stride=stride, offset=offset)
        if not chosen:
            if verbose:
                print(f"[WARN] No files selected for phase {phase_num}_{phase_name} (stride={stride}, offset={offset})")
            continue

        # Determine output folder
        if flat:
            phase_dest = dest
        else:
            phase_dest = dest / f"{phase_num}_{phase_name}"
            if not dry:
                phase_dest.mkdir(parents=True, exist_ok=True)

        # Copy
        for info in chosen:
            target = phase_dest / info.path.name
            if dry or verbose:
                print(f"{'DRY ' if dry else ''}COPY: {info.path} -> {target}")
            if not dry:
                # Use copy2 to preserve mtime/permissions where possible
                shutil.copy2(info.path, target)
                copied += 1

    if verbose or dry:
        print(f"\nDone. {'(dry-run) ' if dry else ''}Total selected files: {copied if not dry else 'N/A'}")

if __name__ == "__main__":
    # python3 sim_skimmer.py /path/to/output /path/to/selection --stride 200 --offset 10 -v
    # python3 sim_skimmer.py '/Volumes/LRZ/aersph_enroot_automation/runs_results/2025-10-07_13-38-50p960_lp-100p0_vx-0p8_j-5342381_p-0/cfg_2025-10-07_13-38-50p960_lp-100p0_vx-0p8_j-5342381_p-0/output'  '/Users/ioandanielcraciun/Python-Projects/sph2img/simulations/skimmed_sims/cfg_2025-10-07_17-08-02p032_lp-100p0_vx-0p4_j-5342386_p-0/output' --stride 5 --offset 0 -v
    main()
