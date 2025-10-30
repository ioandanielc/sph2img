# src/sph2img/selectors.py
from __future__ import annotations
import os, re, socket
from pathlib import Path

# Map hostname patterns to a stable alias (so LRZ node churn doesn't matter)
HOST_GROUPS = {
    r"^lrz-hgx-h100-\d+$": "lrz-ai",
    r"^login-\d+$":        "lrz-login",
    r"^MacBook-.*":        "mac",
}

def pick_alias() -> str:
    # 1) explicit selector wins
    a = os.getenv("HOST_ALIAS")
    if a:
        return a
    # 2) derive from short hostname
    host = socket.gethostname().split(".", 1)[0]
    for pat, alias in HOST_GROUPS.items():
        if re.match(pat, host):
            return alias
    # 3) fallback: use the hostname itself
    return host

def auto_host_config(cfg_dir: Path) -> Path | None:
    """
    Return the first existing JSON host override file, or None.
    Search order:
      host-<alias>.json → host-<hostname>.json → config.local.json
    """
    alias = pick_alias()
    host  = socket.gethostname().split(".", 1)[0]
    for cand in (
        cfg_dir / f"host-{alias}.json",
        cfg_dir / f"host-{host}.json",
        cfg_dir / "config.local.json",
    ):
        if cand.exists():
            return cand
    return None
