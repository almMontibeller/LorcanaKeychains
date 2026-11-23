#!/usr/bin/env python3
"""Repair 3MF project metadata without changing the v1.1 mesh resources.

Uses Python's standard library and the system Cairo library for mesh thumbnails.
Run from any directory: python3 tools/repair_v1_1.py
"""
from pathlib import Path
import collections
import ctypes as C
import hashlib
import json
import math
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "sets"
DEST = ROOT / "collection" / "v1.2"
NS = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
PROD = "{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}"
IDENTITY = [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]


def transform(vertex, matrix):
    return tuple(sum(vertex[j] * matrix[j * 3 + i] for j in range(3)) + matrix[9 + i] for i in range(3))


def read_parts(data):
    root = ET.fromstring(data["3D/3dmodel.model"])
    config = ET.fromstring(data["Metadata/model_settings.config"])
    settings = json.loads(data["Metadata/project_settings.config"])
    main_object = config.find("object")
    assembly = root.find(f"m:resources/m:object[@id='{main_object.get('id')}']", NS)
    parts = []
    for component in assembly.findall("m:components/m:component", NS):
        object_id = component.get("objectid")
        path = component.get(PROD + "path", "3D/3dmodel.model").lstrip("/")
        part_root = ET.fromstring(data[path])
        mesh = part_root.find(f"m:resources/m:object[@id='{object_id}']/m:mesh", NS)
        matrix = list(map(float, component.get("transform", " ".join(map(str, IDENTITY))).split()))
        vertices = [transform(tuple(float(v.get(k)) for k in ("x", "y", "z")), matrix)
                    for v in mesh.find("m:vertices", NS)]
        faces = [tuple(int(f.get(k)) for k in ("v1", "v2", "v3")) for f in mesh.find("m:triangles", NS)]
        metadata = {m.get("key"): m.get("value") for m in main_object.find(f"part[@id='{object_id}']").findall("metadata")}
        slot = int(metadata["extruder"])
        edges = collections.Counter(tuple(sorted((f[i], f[(i + 1) % 3]))) for f in faces for i in range(3))
        assert all(count == 2 for count in edges.values()), (path, object_id, "nonmanifold mesh")
        assert all(math.isfinite(value) for vertex in vertices for value in vertex)
        assert 1 <= slot <= len(settings["filament_colour"])
        parts.append(dict(name=metadata["name"], slot=slot, color=settings["filament_colour"][slot - 1], vertices=vertices, faces=faces))
    return parts


def cairo_library():
    lib = C.CDLL("libcairo.so.2")
    declarations = {
        "cairo_image_surface_create": (C.c_void_p, [C.c_int, C.c_int, C.c_int]),
        "cairo_create": (C.c_void_p, [C.c_void_p]),
        "cairo_set_source_rgb": (None, [C.c_void_p, C.c_double, C.c_double, C.c_double]),
        "cairo_set_antialias": (None, [C.c_void_p, C.c_int]),
        "cairo_paint": (None, [C.c_void_p]),
        "cairo_move_to": (None, [C.c_void_p, C.c_double, C.c_double]),
        "cairo_line_to": (None, [C.c_void_p, C.c_double, C.c_double]),
        "cairo_close_path": (None, [C.c_void_p]),
        "cairo_fill": (None, [C.c_void_p]),
        "cairo_surface_write_to_png": (C.c_int, [C.c_void_p, C.c_char_p]),
        "cairo_destroy": (None, [C.c_void_p]),
        "cairo_surface_destroy": (None, [C.c_void_p]),
    }
    for name, (restype, argtypes) in declarations.items():
        function = getattr(lib, name)
        function.restype, function.argtypes = restype, argtypes
    return lib


def thumbnail(parts, size):
    cairo = cairo_library()
    surface = cairo.cairo_image_surface_create(0, size, size)
    context = cairo.cairo_create(surface)
    cairo.cairo_set_source_rgb(context, 0.96, 0.96, 0.96)
    cairo.cairo_paint(context)
    cairo.cairo_set_antialias(context, 1)  # Avoid seams between coplanar triangles.
    vertices = [v for part in parts for v in part["vertices"]]
    x0, y0 = (min(v[i] for v in vertices) for i in range(2))
    x1, y1 = (max(v[i] for v in vertices) for i in range(2))
    scale = size * 0.88 / max(x1 - x0, y1 - y0)
    triangles = []
    for part in parts:
        for face in part["faces"]:
            a, b, c = (part["vertices"][i] for i in face)
            if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) > 1e-10:
                triangles.append((sum(v[2] for v in (a, b, c)), part["color"], (a, b, c)))
    for _, color, triangle in sorted(triangles, key=lambda t: t[0]):
        cairo.cairo_set_source_rgb(context, *(int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)))
        for i, v in enumerate(triangle):
            point = ((v[0] - (x0 + x1) / 2) * scale + size / 2,
                     size / 2 - (v[1] - (y0 + y1) / 2) * scale)
            (cairo.cairo_move_to if i == 0 else cairo.cairo_line_to)(context, *point)
        cairo.cairo_close_path(context)
        cairo.cairo_fill(context)
    with tempfile.TemporaryDirectory(prefix="lorcana-thumbnail-") as directory:
        path = Path(directory) / "preview.png"
        assert cairo.cairo_surface_write_to_png(surface, str(path).encode()) == 0
        png = path.read_bytes()
    cairo.cairo_destroy(context)
    cairo.cairo_surface_destroy(surface)
    return png


def repair(path):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        data = {name: archive.read(name) for name in archive.namelist()}
    original_models = {name: raw for name, raw in data.items() if name.endswith(".model")}
    parts = read_parts(data)
    settings = json.loads(data["Metadata/project_settings.config"])
    colors = settings["filament_colour"]
    count = len(colors)
    updates = {
        "filament_map": ["1"] * count,
        "filament_map_2": ["1"] * count,
        "filament_nozzle_map": ["0"] * count,
        "filament_volume_map": ["0"] * count,
        "filament_self_index": [str(i + 1) for i in range(count)],
        "filament_multi_colour": colors[:],
        "filament_colour_type": ["1"] * count,
        "flush_volumes_vector": ["140"] * (count * 2),
    }
    if path.name.startswith("Set_08_"):
        updates["wipe_tower_y"] = ["180"]
    for key in list(settings):
        if key == "filament_is_mixed" or key.startswith("filament_mixed_"):
            default = "0" if key in {"filament_is_mixed", "filament_mixed_gradient", "filament_mixed_gradient_per_part"} else ""
            updates[key] = [default] * count
    changes = {key: {"before": settings.get(key), "after": value} for key, value in updates.items() if settings.get(key) != value}
    settings.update(updates)
    data["Metadata/project_settings.config"] = json.dumps(settings, indent=4).encode()
    config = ET.fromstring(data["Metadata/model_settings.config"])
    for name in config.findall("./object/metadata[@key='name']"):
        name.set("value", name.get("value").replace("v1.1", "v1.2"))
    plate = config.find("plate")
    for key, value in [("thumbnail_file", "Metadata/plate_1.png"), ("thumbnail_no_light_file", "Metadata/plate_no_light_1.png")]:
        ET.SubElement(plate, "metadata", {"key": key, "value": value})
    data["Metadata/model_settings.config"] = ET.tostring(config, encoding="utf-8", xml_declaration=True)
    data["Metadata/plate_1.png"] = thumbnail(parts, 512)
    data["Metadata/plate_no_light_1.png"] = data["Metadata/plate_1.png"]
    data["Metadata/plate_1_small.png"] = thumbnail(parts, 128)
    name = path.name.replace("v1.1", "v1.2")
    output_dir = path.parent.parent / "v1.2"
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / name
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for member, raw in data.items():
            archive.writestr(member, raw)
    with zipfile.ZipFile(destination) as archive:
        assert archive.testzip() is None
        for member, raw in original_models.items():
            assert archive.read(member) == raw, (name, member, "geometry changed")
        for member in archive.namelist():
            if member.endswith(".rels"):
                for relationship in ET.fromstring(archive.read(member)):
                    target = relationship.get("Target", "")
                    if target.startswith("/"):
                        assert target.lstrip("/") in archive.namelist(), (name, "missing relationship", target)
    return {
        "filename": name,
        "source_filename": path.name,
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "output_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "geometry_resources_byte_identical": True,
        "mesh_parts": [{"name": part["name"], "slot": part["slot"], "color": part["color"], "triangles": len(part["faces"])} for part in parts],
        "settings_changes": changes,
        "added_thumbnails": ["Metadata/plate_1.png", "Metadata/plate_no_light_1.png", "Metadata/plate_1_small.png"],
    }


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    reports = []
    for path in sorted(SOURCE.glob("Set_*/v1.1/Set_*.3mf")):
        reports.append(repair(path))
        print(path.name, "->", reports[-1]["filename"], flush=True)
    assert len(reports) == 14
    (DEST / "Repair_details.json").write_text(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
