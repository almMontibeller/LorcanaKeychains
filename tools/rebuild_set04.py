#!/usr/bin/env python3
"""Rebuild Set 04 from explicit clean vector letters, using stdlib + libGLU.

Run: python3 tools/rebuild_set04.py
The v03 project supplies profiles, colour assignments, placement and backing.
The SVG supplies letter shapes, not an automatically thresholded texture.
"""
from pathlib import Path
import argparse
import collections
import ctypes as C
import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
import zipfile

from repair_v02 import read_parts, thumbnail, NS, IDENTITY
from set_versions import saved_project

ROOT = Path(__file__).resolve().parents[1]
SET = ROOT / 'sets' / 'Set_04_Ursulas_Return'
SOURCE = SET / 'v03' / 'Set_04_Ursulas_Return_v03.3mf'
VERSION = 'v05'
DEST = SET / VERSION
VECTOR = Path(__file__).with_name('set04_clean_letters_v05.svg')
NAME = f'Set_04_Ursulas_Return_{VERSION}'
CORE = NS['m']
PROD = 'http://schemas.microsoft.com/3dmanufacturing/production/2015/06'
ET.register_namespace('', CORE)
ET.register_namespace('p', PROD)
TAG = lambda name: '{' + CORE + '}' + name


def configure(version):
    global VERSION, DEST, VECTOR, NAME
    VERSION = version
    DEST = SET / VERSION
    VECTOR = Path(__file__).with_name('set04_clean_letters.svg' if version == 'v04' else 'set04_clean_letters_v05.svg')
    NAME = f'Set_04_Ursulas_Return_{VERSION}'


def project_path():
    return saved_project(SET, VERSION)


def area(points):
    return sum(a[0]*b[1] - b[0]*a[1] for a, b in zip(points, points[1:] + points[:1])) / 2


def inside(point, loop):
    x, y = point
    odd = False
    for a, b in zip(loop, loop[1:] + loop[:1]):
        if (a[1] > y) != (b[1] > y) and x < a[0] + (y-a[1])*(b[0]-a[0])/(b[1]-a[1]):
            odd = not odd
    return odd


def orient(loops):
    result = []
    for i, loop in enumerate(loops):
        depth = sum(inside(loop[0], other) for j, other in enumerate(loops) if j != i)
        result.append(loop if (area(loop) > 0) == (depth % 2 == 0) else list(reversed(loop)))
    return result


def svg_loops(path):
    """Sample absolute M/L/H/V/Q/C/Z paths at <=0.04 mm curve spacing."""
    tokens = re.findall(r'[A-Za-z]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?', path)
    loops, points, cursor = [], [], (0., 0.)
    i = 0
    while i < len(tokens):
        cmd = tokens[i]
        i += 1
        count = {'M': 2, 'L': 2, 'H': 1, 'V': 1, 'C': 6, 'Q': 4, 'Z': 0}[cmd]
        values = list(map(float, tokens[i:i+count]))
        i += count
        if cmd == 'M':
            assert not points
            cursor = tuple(values)
            points.append(cursor)
        elif cmd in ('L', 'H', 'V'):
            cursor = tuple(values) if cmd == 'L' else (values[0], cursor[1]) if cmd == 'H' else (cursor[0], values[0])
            points.append(cursor)
        elif cmd in ('C', 'Q'):
            controls = [cursor] + [tuple(values[j:j+2]) for j in range(0, len(values), 2)]
            length = sum(math.dist(a, b) for a, b in zip(controls, controls[1:]))
            steps = max(6, math.ceil(length / .65))
            for n in range(1, steps + 1):
                t = n / steps
                q = controls
                while len(q) > 1:
                    q = [tuple((1-t)*a[k] + t*b[k] for k in (0, 1)) for a, b in zip(q, q[1:])]
                points.append(q[0])
            cursor = controls[-1]
        else:
            if math.dist(points[0], points[-1]) < 1e-8:
                points.pop()
            loops.append(points)
            points = []
    assert not points
    # Registration against v03: top U and lower R swash at their original size.
    scale = 40 / 336 / 2
    return orient([[(14.36 + (x-67)*scale, 2.7 + (665-y)*scale) for x, y in loop] for loop in loops])


def boundary_loops(part):
    """Read the footprint from existing downward-facing bottom triangles."""
    vertices = part['vertices']
    z0 = min(v[2] for v in vertices)
    counts = collections.Counter()
    for face in part['faces']:
        if all(abs(vertices[i][2] - z0) < 1e-6 for i in face):
            counts.update(tuple(sorted((face[n], face[(n+1) % 3]))) for n in range(3))
    adjacent = collections.defaultdict(list)
    for (a, b), count in counts.items():
        if count == 1:
            adjacent[a].append(b)
            adjacent[b].append(a)
    assert all(len(neighbors) == 2 for neighbors in adjacent.values())
    remaining = set(adjacent)
    loops = []
    while remaining:
        first = min(remaining)
        current, previous = first, None
        loop = []
        while True:
            remaining.remove(current)
            loop.append(vertices[current][:2])
            following = next(n for n in adjacent[current] if n != previous)
            previous, current = current, following
            if current == first:
                break
        loops.append(loop)
    return sorted(loops, key=lambda loop: abs(area(loop)), reverse=True)


def simplify_open(points, tolerance):
    a, b = points[0], points[-1]
    dx, dy = b[0]-a[0], b[1]-a[1]
    denom = dx*dx + dy*dy
    distances = []
    for p in points[1:-1]:
        t = max(0, min(1, ((p[0]-a[0])*dx + (p[1]-a[1])*dy)/denom)) if denom else 0
        distances.append(math.dist(p, (a[0]+t*dx, a[1]+t*dy)))
    if not distances or max(distances) <= tolerance:
        return [a, b]
    index = distances.index(max(distances)) + 1
    return simplify_open(points[:index+1], tolerance)[:-1] + simplify_open(points[index:], tolerance)


def clean_backing(part):
    loops = boundary_loops(part)
    outer, hole = loops[:2]
    assert 15.8 < abs(area(hole)) < 16.1, 'second loop must be the 4.5 mm keyring hole'
    original = [(min(p[k] for p in outer), max(p[k] for p in outer)) for k in (0, 1)]
    opposite = max(range(len(outer)), key=lambda i: math.dist(outer[0], outer[i]))
    outer = simplify_open(outer[:opposite+1], .16)[:-1] + simplify_open(outer[opposite:] + outer[:1], .16)[:-1]
    # Corner cutting removes the noisy alpha/texture outline.
    for _ in range(3):
        outer = [tuple((1-t)*a[k]+t*b[k] for k in (0, 1))
                 for a, b in zip(outer, outer[1:]+outer[:1]) for t in (.25, .75)]
    bounds = [(min(p[k] for p in outer), max(p[k] for p in outer)) for k in (0, 1)]
    outer = [tuple(original[k][0]+(p[k]-bounds[k][0])*(original[k][1]-original[k][0])/(bounds[k][1]-bounds[k][0]) for k in (0, 1)) for p in outer]
    # Keep the outer footprint; enlarge the bore by 0.5 mm in radius so the
    # purple rim is approximately 2.5 mm wide instead of 3 mm.
    cx, cy = [(min(p[k] for p in hole)+max(p[k] for p in hole))/2 for k in (0, 1)]
    hole = [(cx+2.75*math.cos(i*math.tau/128), cy+2.75*math.sin(i*math.tau/128)) for i in range(128)]
    return orient([outer, hole]), len(loops)-2


def triangulate(loops):
    """GLU's contour tessellator handles counters without extra Python packages."""
    lib = C.CDLL('libGLU.so.1')
    lib.gluNewTess.restype = C.c_void_p
    lib.gluTessCallback.argtypes = [C.c_void_p, C.c_uint, C.c_void_p]
    lib.gluTessProperty.argtypes = [C.c_void_p, C.c_uint, C.c_double]
    lib.gluTessNormal.argtypes = [C.c_void_p, C.c_double, C.c_double, C.c_double]
    lib.gluTessBeginPolygon.argtypes = [C.c_void_p, C.c_void_p]
    lib.gluTessEndPolygon.argtypes = [C.c_void_p]
    lib.gluTessBeginContour.argtypes = [C.c_void_p]
    lib.gluTessEndContour.argtypes = [C.c_void_p]
    lib.gluTessVertex.argtypes = [C.c_void_p, C.POINTER(C.c_double), C.c_void_p]
    lib.gluDeleteTess.argtypes = [C.c_void_p]
    tess = lib.gluNewTess()
    vertices = [p for loop in loops for p in loop]
    coords = [(C.c_double*3)(x, y, 0) for x, y in vertices]
    primitives, errors = [], []
    @C.CFUNCTYPE(None, C.c_uint)
    def begin(mode):
        primitives.append((mode, []))
    @C.CFUNCTYPE(None, C.c_void_p)
    def vertex(index):
        primitives[-1][1].append(int(index)-1)
    @C.CFUNCTYPE(None)
    def end():
        pass
    @C.CFUNCTYPE(None, C.c_uint)
    def error(code):
        errors.append(int(code))
    for event, callback in [(100100, begin), (100101, vertex), (100102, end), (100103, error)]:
        lib.gluTessCallback(tess, event, callback)
    lib.gluTessNormal(tess, 0, 0, 1)
    lib.gluTessProperty(tess, 100140, 100130)  # winding odd: explicit letter counters
    lib.gluTessBeginPolygon(tess, None)
    offset = 0
    for loop in loops:
        lib.gluTessBeginContour(tess)
        for _ in loop:
            lib.gluTessVertex(tess, coords[offset], C.c_void_p(offset+1))
            offset += 1
        lib.gluTessEndContour(tess)
    lib.gluTessEndPolygon(tess)
    lib.gluDeleteTess(tess)
    assert not errors, ('invalid or intersecting vector contours', errors)
    triangles = []
    for mode, indices in primitives:
        if mode == 4:
            candidates = [indices[i:i+3] for i in range(0, len(indices), 3)]
        elif mode == 5:
            candidates = [indices[i:i+3] if i % 2 == 0 else [indices[i+1], indices[i], indices[i+2]] for i in range(len(indices)-2)]
        elif mode == 6:
            candidates = [[indices[0], indices[i], indices[i+1]] for i in range(1, len(indices)-1)]
        else:
            raise AssertionError(mode)
        for triangle in candidates:
            a = area([vertices[i] for i in triangle])
            triangles.append(tuple(triangle if a >= 0 else reversed(triangle)))
    # GLU can emit a zero-area diagonal between aligned, nonadjacent serif
    # corners. Flip its internal diagonal, preserving every contour vertex.
    for _ in range(100):
        bad = next((i for i, t in enumerate(triangles) if abs(area([vertices[j] for j in t])) < 1e-12), None)
        if bad is None:
            break
        t = triangles[bad]
        fixed = False
        for n in range(3):
            a, b, c = t[n], t[(n+1) % 3], t[(n+2) % 3]
            for j, other in enumerate(triangles):
                if j == bad or a not in other or b not in other:
                    continue
                d = next(p for p in other if p not in (a, b))
                candidates = [(c, d, a), (d, c, b)]
                areas = [area([vertices[k] for k in candidate]) for candidate in candidates]
                if min(map(abs, areas)) < 1e-12:
                    continue
                if not math.isclose(sum(map(abs, areas)), abs(area([vertices[k] for k in other])), abs_tol=1e-9):
                    continue
                triangles[bad], triangles[j] = [candidate if ar > 0 else tuple(reversed(candidate)) for candidate, ar in zip(candidates, areas)]
                fixed = True
                break
            if fixed:
                break
        assert fixed, ('cannot repair degenerate tessellation', t)
    else:
        raise AssertionError('too many degenerate tessellation faces')
    expected = sum(area(loop) for loop in loops)
    actual = sum(area([vertices[i] for i in t]) for t in triangles)
    assert math.isclose(expected, actual, abs_tol=1e-7), (expected, actual)
    return vertices, triangles


def extrude(loops, bottom, height, template):
    xy, top = triangulate(loops)
    count = len(xy)
    vertices = [(x, y, z) for z in (bottom, bottom+height) for x, y in xy]
    faces = [tuple(reversed(t)) for t in top] + [tuple(i+count for i in t) for t in top]
    offset = 0
    for loop in loops:
        for i in range(len(loop)):
            a, b = offset+i, offset+(i+1) % len(loop)
            faces.extend([(a, b, b+count), (a, b+count, a+count)])
        offset += len(loop)
    edges = collections.Counter(tuple(sorted((t[i], t[(i+1) % 3]))) for t in faces for i in range(3))
    assert set(edges.values()) == {2}, 'mesh must be a closed manifold'
    # A directed edge must appear once in each direction, not twice in one.
    directed = collections.Counter((t[i], t[(i+1) % 3]) for t in faces for i in range(3))
    assert all(directed[(b, a)] == value == 1 for (a, b), value in directed.items())
    return dict(template, vertices=vertices, faces=faces)


def thin_attachment(part):
    """Lower only the eyelet top, with a 2.5 mm transition into the backing.

    Split all crossing faces at the transition planes before moving vertices,
    so a large top triangle cannot spread the slope beneath the lettering.
    """
    cuts = (10.5, 13.0)
    def clip(poly, limit, keep_right):
        output = []
        for a, b in zip(poly, poly[1:]+poly[:1]):
            a_in = a[0] >= limit if keep_right else a[0] <= limit
            b_in = b[0] >= limit if keep_right else b[0] <= limit
            if a_in:
                output.append(a)
            if a_in != b_in:
                t = (limit-a[0])/(b[0]-a[0])
                output.append((limit, a[1]+t*(b[1]-a[1]), a[2]+t*(b[2]-a[2])))
        result = []
        for p in output:
            if not result or math.dist(result[-1], p) > 1e-8:
                result.append(p)
        if len(result)>1 and math.dist(result[0], result[-1]) < 1e-8:
            result.pop()
        return result
    vertices, faces, index = [], [], {}
    def vertex(p):
        height = 1.6 + .4*min(1, max(0, (p[0]-cuts[0])/(cuts[1]-cuts[0])))
        point = (round(p[0], 9), round(p[1], 9), round(p[2]*height/2, 9))
        if point not in index:
            index[point] = len(vertices)
            vertices.append(point)
        return index[point]
    for face in part['faces']:
        tri = [part['vertices'][i] for i in face]
        pieces = [clip(tri, cuts[0], False), clip(clip(tri, cuts[0], True), cuts[1], False), clip(tri, cuts[1], True)]
        for poly in pieces:
            if len(poly) < 3:
                continue
            for i in range(1, len(poly)-1):
                face = tuple(vertex(p) for p in (poly[0], poly[i], poly[i+1]))
                if len(set(face)) == 3:
                    faces.append(face)
    edges = collections.Counter(tuple(sorted((f[i], f[(i+1) % 3]))) for f in faces for i in range(3))
    assert set(edges.values()) == {2}, 'stepped eyelet must remain a closed manifold'
    assert max(v[2] for v in vertices if v[0] <= cuts[0]) == 1.6
    assert max(v[2] for v in vertices if v[0] >= cuts[1]) == 2
    return dict(part, vertices=vertices, faces=faces)


def main():
    with zipfile.ZipFile(SOURCE) as archive:
        data = {name: archive.read(name) for name in archive.namelist()}
    original = read_parts(data)
    base, removed = clean_backing(original[0])
    artwork = ET.parse(VECTOR).getroot()
    groups = artwork.findall('{http://www.w3.org/2000/svg}g')
    loops = [base] + [sum((svg_loops(p.get('d')) for p in group), []) for group in groups]
    parts = [extrude(contours, 0 if i == 0 else 2, 2 if i == 0 else .8, original[i]) for i, contours in enumerate(loops)]
    parts[0] = thin_attachment(parts[0])
    DEST.mkdir(parents=True, exist_ok=True)
    root = ET.fromstring(data['3D/3dmodel.model'])
    mesh_root = ET.fromstring(data['3D/Objects/object_1.model'])
    config = ET.fromstring(data['Metadata/model_settings.config'])
    assembly = root.find('m:resources/m:object', NS)
    total_faces = sum(len(p['faces']) for p in parts)
    config.find("./object/metadata[@key='name']").set('value', f'Ursula’s Return {VERSION}')
    config.find('./object/metadata[@face_count]').set('face_count', str(total_faces))
    for component, part in zip(assembly.find(TAG('components')), parts):
        oid = component.get('objectid')
        component.set('transform', ' '.join(map(str, IDENTITY)))
        obj = mesh_root.find(f"m:resources/m:object[@id='{oid}']", NS)
        obj.remove(obj.find(TAG('mesh')))
        mesh = ET.SubElement(obj, TAG('mesh'))
        vertices = ET.SubElement(mesh, TAG('vertices'))
        triangles = ET.SubElement(mesh, TAG('triangles'))
        for v in part['vertices']:
            ET.SubElement(vertices, TAG('vertex'), dict(zip(('x', 'y', 'z'), (f'{x:.9f}' for x in v))))
        for face in part['faces']:
            ET.SubElement(triangles, TAG('triangle'), dict(zip(('v1', 'v2', 'v3'), map(str, face))))
        cfg = config.find(f"./object/part[@id='{oid}']")
        for md in list(cfg.findall('metadata')):
            if md.get('key', '').startswith('source_'):
                cfg.remove(md)
        cfg.find("metadata[@key='matrix']").set('value', '1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1')
        cfg.find('mesh_stat').set('face_count', str(len(part['faces'])))
    root.find("m:metadata[@name='Description']", NS).text = f'{VERSION}; clean vector lettering; flat backing down; 5.5 mm bore; 1.6 mm eyelet; 2 mm backing; 0.20 mm layers.'
    # ElementTree drops the p declaration on a resource with no p attributes.
    # Keep it because the native resource still declares requiredextensions="p".
    mesh_root.set('xmlns:p', PROD) if not any(k.startswith('{'+PROD+'}') for e in mesh_root.iter() for k in e.attrib) else None
    data['3D/3dmodel.model'] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    data['3D/Objects/object_1.model'] = ET.tostring(mesh_root, encoding='utf-8', xml_declaration=True)
    data['Metadata/model_settings.config'] = ET.tostring(config, encoding='utf-8', xml_declaration=True)
    # Retain the proven A1 / 0.4 mm / 0.20 mm process and filament profiles.
    data['Metadata/plate_1.png'] = thumbnail(parts, 512)
    data['Metadata/plate_no_light_1.png'] = data['Metadata/plate_1.png']
    data['Metadata/plate_1_small.png'] = thumbnail(parts, 128)
    output = DEST / (NAME + '.3mf')
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, raw in data.items():
            archive.writestr(name, raw)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        loaded = read_parts({name: archive.read(name) for name in archive.namelist()})
        assert [p['slot'] for p in loaded] == [1, 2, 3]
        assert archive.read('Metadata/project_settings.config') == data['Metadata/project_settings.config']
    (DEST / (NAME + '_preview.png')).write_bytes(thumbnail(parts, 1600))
    # The exact polygons are retained for independent footprint/support checks.
    report = dict(filename=output.name, source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                  output_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                  vector_source=str(VECTOR.relative_to(ROOT)),
                  tiny_backing_holes_removed=removed,
                  attachment=dict(bore_diameter_mm=5.5, nominal_rim_width_mm=2.5, eyelet_thickness_mm=1.6, backing_thickness_mm=2.0, thickness_transition_x_mm=[10.5,13.0]),
                  settings_unchanged=True, dimensions_mm=[round(max(v[k] for p in parts for v in p['vertices'])-min(v[k] for p in parts for v in p['vertices']), 5) for k in range(3)],
                  parts=[dict(name=p['name'], slot=p['slot'], triangles=len(p['faces'])) for p in parts])
    (DEST / f'Geometry_{VERSION}.json').write_text(json.dumps(report, indent=2))
    (DEST / 'footprints.json').write_text(json.dumps(loops))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', choices=['v04', 'v05'], default='v05')
    configure(parser.parse_args().version)
    main()
