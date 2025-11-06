#!/usr/bin/env python3
# Minimal, CLI-capable, schema-preserving config tool with box aliases
# and duplicate "box" keys in JSON. Produces a JSON document that preserves
# duplicate "box" keys by rendering them at the same object level.

from __future__ import annotations
import argparse, json, re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Used ONLY when --testing is set AND --in-xml is not provided.
DEFAULT_XML = r"""<?xml version="1.0" encoding="UTF-8"?>
<config>
  <domain>
    <dimensions>3</dimensions>
    <domain_min>-0.000212 -0.000212 -0.000312</domain_min>
    <domain_max>0.001212 0.000212 0.000112</domain_max>
    <gravity>
      <acceleration>0.0 0.0 -9.81</acceleration>
      <damping_time>0.0</damping_time>
    </gravity>
    <ambient_pressure>101325.0</ambient_pressure>
    <ambient_temperature>300.0</ambient_temperature>
  </domain>
  <reference_values>
    <length>8e-05</length>
    <velocity>5.0</velocity>
  </reference_values>
  <sph><particle_spacing>4e-06</particle_spacing></sph>
  <phases>
    <substrate>
      <type>solid</type><material>TI64</material>
      <initial_conditions><density>4400.0</density><temperature>300.0</temperature></initial_conditions>
      <eos><speed_of_sound>50.0</speed_of_sound></eos>
    </substrate>
    <melt>
      <type>liquid</type><material>TI64</material>
      <initial_conditions><density>4400.0</density><velocity>0.0 0.0 0.0</velocity><temperature>300.0</temperature></initial_conditions>
      <eos><speed_of_sound>50.0</speed_of_sound></eos>
    </melt>
    <gas>
      <type>gas</type><material>REAL_AR</material>
      <initial_conditions><density>1.6116</density><velocity>0.0 0.0 0.0</velocity><temperature>300.0</temperature></initial_conditions>
      <eos><speed_of_sound>50.0</speed_of_sound></eos>
    </gas>
    <isothermal_walls>
      <type>wall</type>
      <thermal_boundary_condition><type>temperature</type><value>300.0</value></thermal_boundary_condition>
    </isothermal_walls>
  </phases>
  <phase_interfaces>
    <melt_gas_interface><phases>melt gas</phases><model>TI64_AIR</model></melt_gas_interface>
  </phase_interfaces>
  <phase_changes><melt_substrate_phase_change>melt substrate</melt_substrate_phase_change></phase_changes>
  <geometry>
    <input_bodies>
      <frame>
        <phase>isothermal_walls</phase><width>1.2e-05</width>
        <min_point>-0.0002 -0.0002 -0.0003</min_point>
        <max_point>0.0012 0.0002 0.0001</max_point>
      </frame>
      <box><phase>substrate</phase><min_point>-0.0002 -0.0002 -0.0003</min_point><max_point>0.0012 0.0002 0.0</max_point></box>
      <box><phase>gas</phase><min_point>-0.0002 -0.0002 0.0</min_point><max_point>0.0012 0.0002 0.0001</max_point></box>
    </input_bodies>
  </geometry>
  <lasers>
    <single_gaussian_laser>
      <physics>
        <shape>
          <cutoff_radius>8e-05</cutoff_radius><spot_radius>4e-05</spot_radius>
          <center>0.0 0.0 5e-05</center><direction>0.0 0.0 -1.0</direction>
        </shape>
        <absorptance>0.2</absorptance><power_magnitude_expression>999</power_magnitude_expression>
        <motion>
          <velocity>0.666 0.0 0.0</velocity><center>0.0 0.0 0.0</center><axis>0.0 0.0 1.0</axis><angular_frequency>0.0</angular_frequency>
        </motion>
      </physics>
      <numerics>
        <number_of_rays>50000</number_of_rays>
        <ray_domain><min>-0.000212 -0.000212 -0.000312</min><max>0.001212 0.000212 0.000112</max></ray_domain>
      </numerics>
    </single_gaussian_laser>
  </lasers>
  <sim_control>
    <tend>1.25e-05</tend><dt_output>2.5e-07</dt_output><output_type>vtk</output_type>
    <freq_monitor_state>1</freq_monitor_state><freq_log_output>1</freq_log_output><freq_checkpoint>5000</freq_checkpoint>
  </sim_control>
  <rendering>
    <domain><min>-0.00016 -0.00016 -0.000296</min><max>0.00116 0.00016 9.6e-05</max></domain>
    <resolution>512 256 256</resolution>
  </rendering>
</config>
"""

# Python-only registry to resolve duplicate <box> selections without changing schema.
BOX_NAME_REGISTRY: Dict[str, Dict[str, List[float] | str]] = {
    "substrate_box": {"phase": "substrate", "min_point": [-0.0002, -0.0002, -0.0003], "max_point": [0.0012, 0.0002, 0.0]},
    "gas_box":       {"phase": "gas",       "min_point": [-0.0002, -0.0002,  0.0   ], "max_point": [0.0012, 0.0002, 0.0001]},
}

def _vec_close(a: List[float], b: List[float], tol: float = 1e-12) -> bool:
    return len(a) == len(b) and all(abs(x - y) <= tol for x, y in zip(a, b))

def _parse_vec(s: str) -> List[float]:
    return [float(x) for x in s.strip().split()]

SEGMENT_RE = re.compile(r"(?P<tag>[A-Za-z0-9_]+)(?:\[name=(?P<name>[A-Za-z0-9_\-\.]+)\])?")

def split_path(path: str) -> List[dict]:
    if not path.startswith("/"):
        raise ValueError(f"path must start with '/': {path}")
    out = []
    for seg in filter(None, path.split("/")):
        m = SEGMENT_RE.fullmatch(seg)
        if not m: raise ValueError(f"bad segment: {seg}")
        tag, name = m.group("tag"), m.group("name")
        if name is not None and tag != "box":
            raise ValueError("Only <box> supports [name=...]")
        out.append({"tag": tag, "name": name})
    return out

def find_box_by_name(input_bodies: ET.Element, name: str) -> ET.Element:
    if name not in BOX_NAME_REGISTRY:
        raise KeyError(f"Unknown box alias {name!r}")
    sig = BOX_NAME_REGISTRY[name]
    cands = []
    for b in input_bodies.findall("box"):
        phase = (b.findtext("phase") or "").strip()
        minp  = _parse_vec(b.findtext("min_point") or "")
        maxp  = _parse_vec(b.findtext("max_point") or "")
        if phase == sig["phase"] and _vec_close(minp, sig["min_point"]) and _vec_close(maxp, sig["max_point"]):
            cands.append(b)
    if not cands: raise KeyError(f"No <box> matches alias {name!r}")
    if len(cands) > 1: raise KeyError(f"Ambiguous alias {name!r}")
    return cands[0]

def _is_number(s: str) -> bool:
    try: float(s); return True
    except Exception: return False

def infer_leaf_type(text_value: str) -> Dict[str, Any]:
    toks = (text_value or "").strip().split()
    if not toks: return {"kind": "string"}
    if len(toks) == 1: return {"kind": "number"} if _is_number(toks[0]) else {"kind": "string"}
    if all(_is_number(t) for t in toks): return {"kind": "vec", "n": len(toks)}
    return {"kind": "string"}

def build_schema(root: ET.Element) -> Dict[str, Dict[str, Any]]:
    schema: Dict[str, Dict[str, Any]] = {}
    def walk(node: ET.Element, cur_path: str):
        kids = [c for c in node if isinstance(c.tag, str)]
        if not kids:
            schema[cur_path] = infer_leaf_type(node.text or "")
        else:
            for c in kids:
                walk(c, f"{cur_path}/{c.tag}")
    walk(root, "")
    return {(k if k.startswith("/") else "/" + k): v for k, v in schema.items()}

def coerce_value(expected: Dict[str, Any], value: Any, path: str) -> str:
    k = expected["kind"]
    if k == "number":
        if isinstance(value, (int, float)): return str(value)
        if isinstance(value, str) and _is_number(value): return value
        raise TypeError(f"{path}: expected number")
    if k == "vec":
        n = expected["n"]
        if isinstance(value, (list, tuple)) and len(value) == n and all(isinstance(x, (int, float, str)) for x in value):
            vals = []
            for x in value:
                if isinstance(x, str) and not _is_number(x):
                    raise TypeError(f"{path}: non-numeric vector element")
                vals.append(float(x) if not isinstance(x, (int, float)) else x)
            return " ".join(str(x) for x in vals)
        if isinstance(value, str):
            toks = value.strip().split()
            if len(toks) == n and all(_is_number(t) for t in toks):
                return value
        raise TypeError(f"{path}: expected vec<{n}>")
    return str(value)

def select_node(root: ET.Element, path: str) -> ET.Element:
    segs = split_path(path)
    cur = root
    for i, spec in enumerate(segs):
        tag, name = spec["tag"], spec["name"]
        last = (i == len(segs) - 1)
        if tag == "box":
            if name is None: raise ValueError(f"{path}: <box> requires [name=...]")
            ib = cur.find("./geometry/input_bodies") if cur.tag == "config" else cur
            if ib is None or ib.tag != "input_bodies":
                raise KeyError(f"{path}: could not locate <input_bodies>")
            cur = find_box_by_name(ib, name)
        else:
            children = [c for c in cur.findall(tag)]
            if not children: raise KeyError(f"{path}: missing <{tag}> under <{cur.tag}>")
            if len(children) > 1 and not last:
                raise KeyError(f"{path}: multiple <{tag}> under <{cur.tag}>")
            cur = children[0]
    return cur

def apply_updates(xml_str: str, updates: List[Tuple[str, Any]]) -> str:
    root = ET.fromstring(xml_str)
    schema = build_schema(root)
    for path, val in updates:
        node = select_node(root, path)
        if any(isinstance(c.tag, str) for c in node):
            raise ValueError(f"{path}: not a leaf")
        schema_key = re.sub(r"\[name=[^\]]+\]", "", path)
        expected = schema.get(schema_key) or infer_leaf_type(node.text or "")
        node.text = coerce_value(expected, val, path)
    return ET.tostring(root, encoding="unicode")

def as_num(s: str):
    s = s.strip()
    try:
        i = int(s, 10); return i
    except Exception:
        return float(s)

def as_num_list(s: str):
    return [as_num(t) for t in s.strip().split()]

def child(node: ET.Element, name: str) -> ET.Element:
    el = node.find(name)
    if el is None: raise KeyError(f"Missing <{name}> under <{node.tag}>")
    return el

def txt(n: ET.Element) -> str: return (n.text or "").strip()

def parse_full(xml_str: str):
    root = ET.fromstring(xml_str)
    dom = child(root, "domain")
    domain = {
        "dimensions": as_num(txt(child(dom, "dimensions"))),
        "domain_min": as_num_list(txt(child(dom, "domain_min"))),
        "domain_max": as_num_list(txt(child(dom, "domain_max"))),
        "gravity": {"acceleration": as_num_list(txt(child(child(dom, "gravity"), "acceleration"))),
                    "damping_time": as_num(txt(child(child(dom, "gravity"), "damping_time")))},
        "ambient_pressure": as_num(txt(child(dom, "ambient_pressure"))),
        "ambient_temperature": as_num(txt(child(dom, "ambient_temperature"))),
    }
    ref = child(root, "reference_values")
    reference_values = {"length": as_num(txt(child(ref, "length"))), "velocity": as_num(txt(child(ref, "velocity")))}
    sph = {"particle_spacing": as_num(txt(child(child(root, "sph"), "particle_spacing")))}
    phases = {}
    phases_node = child(root, "phases")
    def parse_phase(pnode: ET.Element, has_vel: bool):
        ic = child(pnode, "initial_conditions")
        p = {"type": txt(child(pnode, "type")),
             "material": txt(child(pnode, "material")),
             "initial_conditions": {"density": as_num(txt(child(ic, "density"))),
                                    "temperature": as_num(txt(child(ic, "temperature")))},
             "eos": {"speed_of_sound": as_num(txt(child(child(pnode, "eos"), "speed_of_sound")))}}
        if has_vel: p["initial_conditions"]["velocity"] = as_num_list(txt(child(ic, "velocity")))
        return p
    phases["substrate"] = parse_phase(child(phases_node, "substrate"), False)
    phases["melt"] = parse_phase(child(phases_node, "melt"), True)
    phases["gas"] = parse_phase(child(phases_node, "gas"), True)
    iw = child(phases_node, "isothermal_walls")
    phases["isothermal_walls"] = {"type": txt(child(iw, "type")),
                                  "thermal_boundary_condition": {"type": txt(child(child(iw, "thermal_boundary_condition"), "type")),
                                                                 "value": as_num(txt(child(child(iw, "thermal_boundary_condition"), "value")))}}    
    pi = child(root, "phase_interfaces")
    mgi = child(pi, "melt_gas_interface")
    phase_interfaces = {"melt_gas_interface": {"phases": txt(child(mgi, "phases")).split(), "model": txt(child(mgi, "model"))}}
    pc = child(root, "phase_changes")
    phase_changes = {"melt_substrate_phase_change": txt(child(pc, "melt_substrate_phase_change")).split()}
    geom = child(root, "geometry")
    ib_frame = child(child(geom, "input_bodies"), "frame")
    geometry_no_boxes = {"input_bodies": {"frame": {
        "phase": txt(child(ib_frame, "phase")),
        "width": as_num(txt(child(ib_frame, "width"))),
        "min_point": as_num_list(txt(child(ib_frame, "min_point"))),
        "max_point": as_num_list(txt(child(ib_frame, "max_point"))),
    }}}
    boxes = []
    for b in child(geom, "input_bodies").findall("box"):
        boxes.append({
            "phase": txt(child(b, "phase")),
            "min_point": as_num_list(txt(child(b, "min_point"))),
            "max_point": as_num_list(txt(child(b, "max_point"))),
        })
    lasers_node = child(root, "lasers")
    sgl = child(lasers_node, "single_gaussian_laser")
    shape = child(child(sgl, "physics"), "shape")
    motion = child(child(sgl, "physics"), "motion")
    numerics = child(sgl, "numerics")
    lasers = {"single_gaussian_laser": {
        "physics": {"shape": {"cutoff_radius": as_num(txt(child(shape, "cutoff_radius"))),
                              "spot_radius": as_num(txt(child(shape, "spot_radius"))),
                              "center": as_num_list(txt(child(shape, "center"))),
                              "direction": as_num_list(txt(child(shape, "direction")))},
                    "absorptance": as_num(txt(child(child(sgl, "physics"), "absorptance"))),
                    "power_magnitude_expression": as_num(txt(child(child(sgl, "physics"), "power_magnitude_expression"))),
                    "motion": {"velocity": as_num_list(txt(child(motion, "velocity"))),
                               "center": as_num_list(txt(child(motion, "center"))),
                               "axis": as_num_list(txt(child(motion, "axis"))),
                               "angular_frequency": as_num(txt(child(motion, "angular_frequency")))} },
        "numerics": {"number_of_rays": as_num(txt(child(numerics, "number_of_rays"))),
                     "ray_domain": {"min": as_num_list(txt(child(child(numerics, "ray_domain"), "min"))),
                                    "max": as_num_list(txt(child(child(numerics, "ray_domain"), "max")))}}}}
    sc = child(root, "sim_control")
    sim_control = {"tend": as_num(txt(child(sc, "tend"))),
                   "dt_output": as_num(txt(child(sc, "dt_output"))),
                   "output_type": txt(child(sc, "output_type")),
                   "freq_monitor_state": as_num(txt(child(sc, "freq_monitor_state"))),
                   "freq_log_output": as_num(txt(child(sc, "freq_log_output"))),
                   "freq_checkpoint": as_num(txt(child(sc, "freq_checkpoint")))}    
    rend = child(root, "rendering")
    rendering = {"domain": {"min": as_num_list(txt(child(child(rend, "domain"), "min"))),
                            "max": as_num_list(txt(child(child(rend, "domain"), "max"))) },
                 "resolution": as_num_list(txt(child(rend, "resolution")))}
    core = {"domain": domain, "reference_values": reference_values, "sph": sph, "phases": phases,
            "phase_interfaces": phase_interfaces, "phase_changes": phase_changes,
            "geometry": geometry_no_boxes, "lasers": lasers, "sim_control": sim_control, "rendering": rendering}
    return core, boxes

def jdump_atom(x: Any) -> str: return json.dumps(x, ensure_ascii=False, separators=(",", ":"))

def render_value(val: Any, level: int, path: Tuple[str, ...]) -> str:
    if isinstance(val, dict): return render_object(val, level, path)
    if isinstance(val, list):
        if not val: return "[]"
        lines = ["["]
        for i, v in enumerate(val):
            lines.append("\t"*(level+1) + render_value(v, level+1, path) + ("," if i < len(val) - 1 else ""))
        lines.append("\t"*level + "]")
        return "\n".join(lines)
    return jdump_atom(val)

INJECTED_BOXES: List[Dict[str, Any]] = []

def render_object(obj: dict, level: int, path: Tuple[str, ...]) -> str:
    inject_here = (len(path) == 2 and path[0] == "geometry" and path[1] == "input_bodies")
    items = list(obj.items())
    lines = ["{"]
    for i, (k, v) in enumerate(items):
        comma = (i < len(items) - 1) or (inject_here and INJECTED_BOXES)
        lines.append("\t"*(level+1) + jdump_atom(k) + ": " + render_value(v, level+1, path+(k,)) + ("," if comma else ""))
    if inject_here and INJECTED_BOXES:
        for j, box in enumerate(INJECTED_BOXES):
            lines.append("\t"*(level+1) + jdump_atom("box") + ": " + render_value(box, level+1, path+("box",)) + ("," if j < len(INJECTED_BOXES)-1 else ""))
    lines.append("\t"*level + "}")
    return "\n".join(lines)

def render_document(core: dict, boxes: List[Dict[str, Any]]) -> str:
    global INJECTED_BOXES
    INJECTED_BOXES = boxes
    return render_object(core, 0, ())

def parse_value(s: str) -> Any:
    try:
        return json.loads(s)
    except Exception:
        return s

def main(argv=None):
    p = argparse.ArgumentParser(
        description="Update config XML and emit JSON (preserving duplicate <box> entries via repeated keys)."
    )
    p.add_argument("--in-xml", dest="in_xml", type=Path,
                   help="Input XML path. If omitted and --testing is set, uses internal DEFAULT_XML.")
    p.add_argument("--out-json", type=Path, required=True, help="Write JSON to this path.")
    p.add_argument("--set", dest="sets", action="append", nargs=2, metavar=("PATH", "VALUE"),
                   help="Set a leaf PATH to VALUE. VALUE can be JSON (e.g., [1,2,3] or 6.5). Can repeat.")
    p.add_argument("--testing", action="store_true",
                   help="Use internal DEFAULT_XML if --in-xml not provided; also applies a small demo update set.")
    args = p.parse_args(argv)

    if args.in_xml is not None:
        xml_str = args.in_xml.read_text(encoding="utf-8")
    elif args.testing:
        xml_str = DEFAULT_XML
    else:
        raise SystemExit("ERROR: --in-xml is required (or use --testing).")

    updates: List[Tuple[str, Any]] = []
    if args.testing:
        updates.extend([
            ("/reference_values/velocity", 6.5),
            ("/geometry/input_bodies/box[name=gas_box]/min_point", [-0.0001, -0.0001, 0.0]),
            ("/geometry/input_bodies/box[name=substrate_box]/max_point", [0.002, 0.00025, 0.0]),
            ("/lasers/single_gaussian_laser/physics/motion/velocity", [0.8, 0.0, 0.0]),
            ("/rendering/resolution", [640, 320, 320]),
        ])
    if args.sets:
        for path, value in args.sets:
            updates.append((path, parse_value(value)))

    if updates:
        xml_str = apply_updates(xml_str, updates)

    core, boxes = parse_full(xml_str)
    json_text = render_document(core, boxes)

    # Ensure parent exists before writing
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json_text, encoding="utf-8")
    print(json_text)

if __name__ == "__main__":
    # IMPORTANT: Call main() normally so CLI args are honored.
    main()

