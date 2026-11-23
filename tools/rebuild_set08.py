#!/usr/bin/env python3
"""Build Set 08 v07: smooth gold rim/title and solid red outlined Jafar.

Uses Python's standard library and the system Cairo/GLU libraries. Native
backing, placement and all filament/process profiles remain unchanged.
"""
from pathlib import Path
import collections
import ctypes as C
import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
import zipfile

from rebuild_set04 import area, boundary_loops, extrude, inside, orient, simplify_open
from repair_v02 import IDENTITY, NS, cairo_library, read_parts, thumbnail

ROOT = Path(__file__).resolve().parents[1]
SET = ROOT/'sets/Set_08_Reign_of_Jafar'
VERSION = 'v07'
NAME = SET.name+'_'+VERSION
SOURCE = SET/'v06'/(SET.name+'_v06.3mf')
DEST = SET/VERSION
PROJECT = DEST/(NAME+'.3mf')
VECTOR = Path(__file__).with_name('set08_clean_artwork.svg')
ARTWORK = ROOT/'collection/v01/Sources/lorcana-keychains/sources/08.png'
STEP, ORIGIN, SIZE = .025, (-1., 43.), (2960, 1800)
KEYLINE = .45
PROD = 'http://schemas.microsoft.com/3dmanufacturing/production/2015/06'
TAG = lambda name: '{'+NS['m']+'}'+name
SVG = {'s': 'http://www.w3.org/2000/svg'}
ET.register_namespace('', NS['m'])
ET.register_namespace('p', PROD)


def package(path):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        return {n: archive.read(n) for n in archive.namelist()}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bounds(part):
    return [(min(v[k] for v in part['vertices']), max(v[k] for v in part['vertices'])) for k in range(3)]


def footprint_loops(part):
    """Footprint from all downward faces, including different relief bottoms."""
    counts = collections.Counter()
    for face in part['faces']:
        if area([part['vertices'][i][:2] for i in face]) < -1e-12:
            counts.update(tuple(sorted((face[n], face[(n+1) % 3]))) for n in range(3))
    adjacent = collections.defaultdict(list)
    for (a, b), count in counts.items():
        if count == 1:
            adjacent[a].append(b)
            adjacent[b].append(a)
    assert all(len(neighbors) == 2 for neighbors in adjacent.values())
    remaining, loops = set(adjacent), []
    while remaining:
        first = min(remaining)
        current, previous, loop = first, None, []
        while True:
            remaining.remove(current)
            loop.append(part['vertices'][current][:2])
            following = next(n for n in adjacent[current] if n != previous)
            previous, current = current, following
            if current == first:
                break
        loops.append(loop)
    return orient(loops)


def registered(point):
    # Original crop (169,0,1211,685), 40/685 mm per pixel. The native source
    # silhouette at source x=171 is x=10.55; source y=684 is y=.8.
    x, y = point
    return (10.55+(x-171)*40/685, .8+(684-y)*40/685)


def sample(path):
    tokens = re.findall(r'[A-Za-z]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?', path)
    loops, points, cursor = [], [], (0., 0.)

    def curve(controls):
        a, b = controls[0], controls[-1]
        dx, dy = b[0]-a[0], b[1]-a[1]
        length = math.hypot(dx, dy)
        deviation = max(abs(dx*(p[1]-a[1])-dy*(p[0]-a[0]))/length
                        if length else math.dist(a, p) for p in controls[1:-1])
        if deviation <= .07 and length <= 4:
            points.append(b)
            return
        rows = [controls]
        while len(rows[-1]) > 1:
            rows.append([tuple((u[k]+v[k])/2 for k in (0, 1))
                         for u, v in zip(rows[-1], rows[-1][1:])])
        curve([row[0] for row in rows])
        curve([row[-1] for row in reversed(rows)])

    i = 0
    while i < len(tokens):
        command = tokens[i]
        i += 1
        count = {'M': 2, 'L': 2, 'C': 6, 'Q': 4, 'Z': 0}[command]
        values = list(map(float, tokens[i:i+count]))
        i += count
        if command == 'M':
            assert not points
            cursor = tuple(values)
            points.append(cursor)
        elif command == 'L':
            cursor = tuple(values)
            points.append(cursor)
        elif command in ('C', 'Q'):
            curve([cursor]+[tuple(values[j:j+2]) for j in range(0, count, 2)])
            cursor = tuple(values[-2:])
        else:
            if math.dist(points[0], points[-1]) < 1e-8:
                points.pop()
            loops.append([registered(p) for p in points])
            points = []
    assert not points
    return orient(loops)


def artwork():
    root = ET.parse(VECTOR).getroot()
    return {group: {p.get('id'): sample(p.get('d'))
                    for p in root.findall(f"s:g[@id='{group}']/s:path", SVG)}
            for group in ('gold', 'jafar', 'accents')}


class Canvas:
    """Small Cairo wrapper for previews, offsets and toolpath verification."""
    def __init__(self, size=SIZE, origin=ORIGIN, step=STEP):
        self.size, self.origin, self.step = size, origin, step
        self.lib = cairo_library()
        declarations = {
            'cairo_image_surface_get_data': (C.POINTER(C.c_ubyte), [C.c_void_p]),
            'cairo_image_surface_get_stride': (C.c_int, [C.c_void_p]),
            'cairo_surface_flush': (None, [C.c_void_p]),
            'cairo_new_path': (None, [C.c_void_p]),
            'cairo_set_fill_rule': (None, [C.c_void_p, C.c_int]),
            'cairo_set_operator': (None, [C.c_void_p, C.c_int]),
            'cairo_set_line_width': (None, [C.c_void_p, C.c_double]),
            'cairo_set_line_join': (None, [C.c_void_p, C.c_int]),
            'cairo_set_line_cap': (None, [C.c_void_p, C.c_int]),
            'cairo_stroke': (None, [C.c_void_p]),
        }
        for name, (restype, args) in declarations.items():
            function = getattr(self.lib, name)
            function.restype, function.argtypes = restype, args
        self.surface = self.lib.cairo_image_surface_create(0, *size)
        self.context = self.lib.cairo_create(self.surface)
        self.lib.cairo_set_antialias(self.context, 1)
        self.lib.cairo_set_fill_rule(self.context, 1)
        self.lib.cairo_set_line_join(self.context, 1)
        self.lib.cairo_set_line_cap(self.context, 1)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.lib.cairo_destroy(self.context)
        self.lib.cairo_surface_destroy(self.surface)

    def color(self, color):
        self.lib.cairo_set_source_rgb(self.context, *(int(color[i:i+2], 16)/255 for i in (1, 3, 5)))

    def background(self, color):
        self.color(color)
        self.lib.cairo_paint(self.context)

    def point(self, p):
        return (p[0]-self.origin[0])/self.step, (self.origin[1]-p[1])/self.step

    def path(self, loops):
        self.lib.cairo_new_path(self.context)
        for loop in loops:
            for i, p in enumerate(loop):
                (self.lib.cairo_move_to if i == 0 else self.lib.cairo_line_to)(self.context, *self.point(p))
            self.lib.cairo_close_path(self.context)

    def fill(self, loops, color='#FFFFFF'):
        self.color(color)
        self.path(loops)
        self.lib.cairo_fill(self.context)

    def stroke(self, paths, width, color='#FFFFFF'):
        self.color(color)
        self.lib.cairo_set_line_width(self.context, width/self.step)
        self.lib.cairo_new_path(self.context)
        for points in paths:
            for i, p in enumerate(points):
                (self.lib.cairo_move_to if i == 0 else self.lib.cairo_line_to)(self.context, *self.point(p))
        self.lib.cairo_stroke(self.context)

    def eroded(self, loops, radius):
        self.background('#000000')
        self.fill(loops)
        self.stroke([c+c[:1] for c in loops], 2*radius, '#000000')
        return self.mask()

    def mask(self):
        self.lib.cairo_surface_flush(self.surface)
        stride = self.lib.cairo_image_surface_get_stride(self.surface)
        data = C.string_at(self.lib.cairo_image_surface_get_data(self.surface), stride*self.size[1])
        assert stride == self.size[0]*4
        return bytearray(v > 127 for v in data[0::4])

    def save(self, path):
        assert self.lib.cairo_surface_write_to_png(self.surface, str(path).encode()) == 0


def contours(mask):
    """Trace a Cairo offset at 0.025 mm, simplify within 0.015 mm."""
    width, height = SIZE
    points = ((1, 0), (2, 1), (1, 2), (0, 1))
    cases = {1: [(3, 0)], 2: [(0, 1)], 3: [(3, 1)], 4: [(1, 2)],
             5: [(3, 0), (1, 2)], 6: [(0, 2)], 7: [(3, 2)],
             8: [(2, 3)], 9: [(2, 0)], 10: [(0, 1), (2, 3)],
             11: [(2, 1)], 12: [(1, 3)], 13: [(1, 0)], 14: [(0, 3)]}
    adjacent = collections.defaultdict(list)
    for y in range(height-1):
        row = y*width
        for x in range(width-1):
            k = row+x
            case = mask[k]+2*mask[k+1]+4*mask[k+width+1]+8*mask[k+width]
            for a, b in cases.get(case, ()):
                p, q = [(2*x+points[e][0], 2*y+points[e][1]) for e in (a, b)]
                adjacent[p].append(q)
                adjacent[q].append(p)
    assert all(len(v) == 2 for v in adjacent.values())
    remaining, loops = set(adjacent), []
    while remaining:
        first = min(remaining)
        current, previous, loop = first, None, []
        while True:
            remaining.remove(current)
            loop.append((ORIGIN[0]+current[0]/2*STEP, ORIGIN[1]-current[1]/2*STEP))
            following = next(p for p in adjacent[current] if p != previous)
            previous, current = current, following
            if current == first:
                break
        opposite = max(range(len(loop)), key=lambda i: math.dist(loop[0], loop[i]))
        loop = (simplify_open(loop[:opposite+1], .015)[:-1]
                + simplify_open(loop[opposite:]+loop[:1], .015)[:-1])
        if abs(area(loop)) > .02:
            loops.append(loop)
    return orient(loops)


def mesh_stats(part):
    edges = collections.Counter((f[i], f[(i+1) % 3]) for f in part['faces'] for i in range(3))
    assert all(value == edges[(b, a)] == 1 for (a, b), value in edges.items())
    volume, degenerate = 0., 0
    for face in part['faces']:
        a, b, c = [part['vertices'][i] for i in face]
        u, v = [b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)]
        cross = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
        degenerate += sum(t*t for t in cross) < 1e-22
        volume += (a[0]*(b[1]*c[2]-b[2]*c[1])+a[1]*(b[2]*c[0]-b[0]*c[2])+a[2]*(b[0]*c[1]-b[1]*c[0]))/6
    assert volume > 0
    return dict(closed_manifold=True, degenerate_triangles=degenerate, volume_mm3=volume)


def relief(shapes, bottom, height, template):
    vertices, faces = [], []
    for loops in shapes:
        flat = [p for c in loops for p in c]
        for degrees in (0, 17, 31, 47):
            angle = math.radians(degrees)
            co, si = math.cos(angle), math.sin(angle)
            rotated = [[(x*co-y*si, x*si+y*co) for x, y in c] for c in loops]
            try:
                part = extrude(rotated, bottom, height, template)
            except AssertionError:
                continue
            part['vertices'] = [(*flat[i % len(flat)], v[2]) for i, v in enumerate(part['vertices'])]
            if mesh_stats(part)['degenerate_triangles'] == 0:
                break
        else:
            raise AssertionError('Unable to tessellate contours')
        faces.extend(tuple(i+len(vertices) for i in face) for face in part['faces'])
        vertices.extend(part['vertices'])
    return dict(template, vertices=vertices, faces=faces)


def merge(parts):
    vertices, faces = [], []
    for part in parts:
        faces.extend(tuple(i+len(vertices) for i in f) for f in part['faces'])
        vertices.extend(part['vertices'])
    return dict(parts[0], vertices=vertices, faces=faces)


def red_contours(art):
    with Canvas() as canvas:
        return {name: contours(canvas.eroded(loops, KEYLINE)) for name, loops in art['jafar'].items()}


def geometry(old):
    art = artwork()
    red = red_contours(art)
    gold = merge([relief(list(art['gold'].values()), 2., .8, old[2]),
                  relief(list(art['jafar'].values()), 2., .4, old[2])])
    gold['name'] = 'Sunflower Yellow — continuous rim, Reign of and Jafar keylines'
    crimson = merge([relief(list(red.values()), 2.4, .4, old[3]),
                     relief(list(art['accents'].values()), 2., .8, old[3])])
    crimson['name'] = 'Red — uniform Jafar faces and snake eyes'
    return [old[0], gold, crimson]


def preview(parts, path, width=1800):
    bb = bounds(parts[0])
    step = (bb[0][1]-bb[0][0])/(width-120)
    height = math.ceil((bb[1][1]-bb[1][0])/step)+120
    with Canvas((width, height), (bb[0][0]-60*step, bb[1][1]+60*step), step) as canvas:
        canvas.background('#F5F5F5')
        for part in parts:
            canvas.fill(footprint_loops(part), part['color'])
        canvas.save(path)


def write_mesh(obj, part):
    obj.remove(obj.find(TAG('mesh')))
    mesh = ET.SubElement(obj, TAG('mesh'))
    vs, fs = ET.SubElement(mesh, TAG('vertices')), ET.SubElement(mesh, TAG('triangles'))
    for v in part['vertices']:
        ET.SubElement(vs, TAG('vertex'), dict(zip(('x', 'y', 'z'), (f'{n:.9f}' for n in v))))
    for face in part['faces']:
        ET.SubElement(fs, TAG('triangle'), dict(zip(('v1', 'v2', 'v3'), map(str, face))))


def main():
    data = package(SOURCE)
    old = read_parts(data)
    parts = geometry(old)
    root = ET.fromstring(data['3D/3dmodel.model'])
    config = ET.fromstring(data['Metadata/model_settings.config'])
    obj = config.find('object')
    assembly = root.find(f"m:resources/m:object[@id='{obj.get('id')}']", NS)
    components = assembly.find('m:components', NS)
    unused = components[1]
    obj.remove(obj.find(f"part[@id='{unused.get('objectid')}']"))
    components.remove(unused)
    resources = {}
    for i in (1, 2):
        component = components[i]
        oid = component.get('objectid')
        path = component.get('{'+PROD+'}path').lstrip('/')
        if path not in resources:
            resources[path] = ET.fromstring(data[path])
        write_mesh(resources[path].find(f"m:resources/m:object[@id='{oid}']", NS), parts[i])
        component.set('transform', ' '.join(map(str, IDENTITY)))
        cfg = obj.find(f"part[@id='{oid}']")
        for md in list(cfg.findall('metadata')):
            if md.get('key', '').startswith('source_'):
                cfg.remove(md)
        cfg.find("metadata[@key='name']").set('value', parts[i]['name'])
        cfg.find("metadata[@key='matrix']").set('value', '1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1')
        stat = cfg.find('mesh_stat')
        stat.set('face_count', str(len(parts[i]['faces'])))
        for key in ('edges_fixed', 'degenerate_facets', 'facets_removed', 'facets_reversed', 'backwards_edges'):
            if key in stat.attrib:
                stat.set(key, '0')
    # Remove the obsolete gradient object itself as well as its component.
    unused_path = unused.get('{'+PROD+'}path').lstrip('/')
    if unused_path not in resources:
        resources[unused_path] = ET.fromstring(data[unused_path])
    unused_resources = resources[unused_path].find('m:resources', NS)
    unused_resources.remove(unused_resources.find(f"m:object[@id='{unused.get('objectid')}']", NS))
    obj.find("metadata[@key='name']").set('value', NAME)
    obj.find('metadata[@face_count]').set('face_count', str(sum(len(p['faces']) for p in parts)))
    root.find("m:metadata[@name='Description']", NS).text = (
        'v07; smooth continuous gold rim and solid Reign of; red Jafar with uniform '
        '0.45 mm gold keylines, no source gradients or bevel fragments; native '
        '2 mm backing and loop, 6.5 mm bore, plate placement and all profiles retained; '
        'gold keyline top 2.4 mm; gold title/frame and solid red top 2.8 mm; '
        'active slots 1 Charcoal, 3 Sunflower Yellow, 4 Red; slot 2 unused.')
    for path, resource in resources.items():
        if not any(k.startswith('{'+PROD+'}') for e in resource.iter() for k in e.attrib):
            resource.set('xmlns:p', PROD)
        data[path] = ET.tostring(resource, encoding='utf-8', xml_declaration=True)
    data['3D/3dmodel.model'] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    data['Metadata/model_settings.config'] = ET.tostring(config, encoding='utf-8', xml_declaration=True)
    data['Metadata/plate_1.png'] = thumbnail(parts, 512)
    data['Metadata/plate_no_light_1.png'] = data['Metadata/plate_1.png']
    data['Metadata/plate_1_small.png'] = thumbnail(parts, 128)
    DEST.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(PROJECT, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path, raw in data.items():
            archive.writestr(path, raw)
    loaded = read_parts(package(PROJECT))
    assert loaded[0] == old[0]
    assert package(PROJECT)['Metadata/project_settings.config'] == data['Metadata/project_settings.config']
    preview(loaded, DEST/(NAME+'_preview.png'))
    print(json.dumps(dict(project=str(PROJECT.relative_to(ROOT)), sha256=digest(PROJECT),
                          source_sha256=digest(SOURCE), vector_sha256=digest(VECTOR),
                          parts=[dict(name=p['name'], slot=p['slot'], **mesh_stats(p)) for p in loaded]), indent=2))


if __name__ == '__main__':
    main()
