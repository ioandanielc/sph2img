# src/sph2img/utils/__init__.py
"""Stages subpackages and modules for sph2img.

Import submodules explicitly to keep imports fast and avoid side effects.
"""
__all__ = [
    "gif_maker",
    "screencapture_slice_composite",
    "screencapture_through_milestones",
    "slice_creator",
    "slice_hide_and_show",
    "slice_mover",
    "sph_creator"
]
