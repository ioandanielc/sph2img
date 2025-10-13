# src/sph2img/utils/parser_utils.py
from __future__ import annotations

# --- path bootstrap: make `sph2img` importable even when run as a script -----
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]   # repo root (sph2img/)
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
# ---------------------------------------------------------------------------

import json
from typing import Any, List, Type

from sph2img.utils.pvlog import get_logger

logger = get_logger(__name__)

__all__ = [
    "load_file",
    "list_of_str_to",
    "list_of_lists_of_str_to",
    "csv_to_lists",
    "save_variable_json",
]


def load_file(path: str) -> List[str]:
    """Reads a file and returns a list of non-empty, stripped lines."""
    p = Path(path).expanduser().resolve()
    with p.open("r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f]
    out = [ln for ln in lines if ln]
    return out


def list_of_str_to(lst: List[str], target_type: Type) -> List[Any]:
    """
    Convert a list of strings to a list of ``target_type``.
    Example: ``list_of_str_to(["1", "2"], int) -> [1, 2]``
    """
    return [target_type(x) for x in lst]


def list_of_lists_of_str_to(lst: List[List[str]], target_type: Type) -> List[List[Any]]:
    """
    Convert a list of lists of strings to a list of lists of ``target_type``.
    Example: ``list_of_lists_of_str_to([["1.1","2.2"],["3.3"]], float) -> [[1.1, 2.2], [3.3]]``
    """
    return [[target_type(x) for x in sublist] for sublist in lst]


def csv_to_lists(path: str) -> List[List[float]]:
    """
    Reads a .csv file into a list of lists of floats.
    Each line is split by commas; empty lines are ignored.
    """
    p = Path(path).expanduser().resolve()
    data: List[List[float]] = []
    with p.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            # split by comma and convert each to float (allow spaces around commas)
            parts = [tok.strip() for tok in line.split(",")]
            row = [float(x) for x in parts if x != ""]
            data.append(row)
    return data


def save_variable_json(var: Any, parent_path: str, file_name: str) -> None:
    """Save a Python variable to ``parent_path/file_name.json`` as pretty JSON."""
    parent = Path(parent_path).expanduser().resolve()
    parent.mkdir(parents=True, exist_ok=True)
    path = parent / f"{file_name}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(var, f, indent=2, ensure_ascii=False)


