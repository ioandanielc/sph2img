# src/sph2img/pvshim.py
from __future__ import annotations
import importlib, sys, types

def enable_stubs() -> bool:
    """
    If real 'paraview' is importable, do nothing and return False.
    Otherwise, install lightweight stub modules so `from paraview...` imports succeed.
    Any actual use will raise a clear RuntimeError.
    """
    try:
        importlib.import_module("paraview")
        return False  # real ParaView present (pvpython/pvbatch), no-op
    except ModuleNotFoundError:
        pass

    # Build a tiny package tree: paraview, paraview.simple, paraview.servermanager, paraview.vtk.util.numpy_support
    pv = types.ModuleType("paraview")
    simple = types.ModuleType("paraview.simple")
    servermanager = types.ModuleType("paraview.servermanager")
    vtk = types.ModuleType("paraview.vtk")
    util = types.ModuleType("paraview.vtk.util")
    numpy_support = types.ModuleType("paraview.vtk.util.numpy_support")

    def _fail(*_a, **_k):
        raise RuntimeError("ParaView is not available. Run this under pvbatch/pvpython.")

    # Minimal symbols used across your codebase; add more only if needed
    simple.LegacyVTKReader = _fail
    servermanager.Fetch = _fail
    numpy_support.vtk_to_numpy = _fail

    # Register stubs
    sys.modules["paraview"] = pv
    sys.modules["paraview.simple"] = simple
    sys.modules["paraview.servermanager"] = servermanager
    sys.modules["paraview.vtk"] = vtk
    sys.modules["paraview.vtk.util"] = util
    sys.modules["paraview.vtk.util.numpy_support"] = numpy_support
    return True
