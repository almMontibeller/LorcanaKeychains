#!/usr/bin/env python3
"""Set 08 v1.7: orange rim/head details and engraved black cobra-hood bands.

Python standard library + system Cairo/GLU. Preserve v1.6 projects and text.
"""
import collections
import copy
from array import array
import json
import math
import tempfile
import uuid
import xml.etree.ElementTree as ET
import zipfile

import rebuild_set08 as core
from rebuild_set04 import area, boundary_loops, orient, triangulate
from repair_v1_1 import IDENTITY, NS, read_parts, thumbnail

ROOT, SET = core.ROOT, core.SET
VERSION = 'v1.7'
NAME = SET.name+'_'+VERSION
SOURCE = core.PROJECT
DEST = SET/VERSION
PROJECT = DEST/(NAME+'.3mf')
VECTOR = core.VECTOR.with_name('set08_serpent_detail.svg')
COMPARISON_SOURCE = SOURCE
GROOVE_WIDTH, GROOVE_DEPTH = .6, .4


def configure(version):
    """Select a detail revision while retaining the v1.6 text prerequisite."""
    global VERSION, NAME, DEST, PROJECT, VECTOR, COMPARISON_SOURCE
    assert version in ('v1.7', 'v1.8')
    VERSION = version
    NAME = SET.name+'_'+VERSION
    DEST = SET/VERSION
    PROJECT = DEST/(NAME+'.3mf')
    VECTOR = core.VECTOR.with_name('set08_serpent_detail.svg' if version == 'v1.7'
                                  else 'set08_serpent_detail_v1_8.svg')
    COMPARISON_SOURCE = SOURCE if version == 'v1.7' else SET/'v1.7'/(SET.name+'_v1.7.3mf')


def open_path(path):
    # Reuse the established adaptive Bézier sampler; the artificial closing
    # edge is omitted when the returned centre line is stroked.
    return core.sample(path+' Z')[0]


def artwork():
    root = ET.parse(VECTOR).getroot()
    art = {}
    for group in ('orange', 'face_lines', 'hood'):
        art[group] = {p.get('id'): (core.sample(p.get('d')) if group == 'orange'
                     else open_path(p.get('d')))
                     for p in root.findall(f"s:g[@id='{group}']/s:path", core.SVG)}
    return art


def raster(loops, inset=0.):
    with core.Canvas() as c:
        if inset > 0:
            return c.eroded(loops, inset)
        c.background('#000000')
        c.fill(loops)
        if inset < 0:
            c.stroke([l+l[:1] for l in loops], -2*inset)
        return c.mask()


def stroke(paths, width):
    with core.Canvas() as c:
        c.background('#000000')
        c.stroke(paths, width)
        return c.mask()


def components(part):
    adjacent = collections.defaultdict(set)
    for f in part['faces']:
        for i in f:
            adjacent[i].update(f)
    remaining, parts = set(adjacent), []
    while remaining:
        reached, todo = set(), [min(remaining)]
        while todo:
            i = todo.pop()
            if i in reached:
                continue
            reached.add(i)
            todo.extend(adjacent[i]-reached)
        remaining -= reached
        indices = sorted(reached)
        remap = {old: new for new, old in enumerate(indices)}
        parts.append(dict(part, vertices=[part['vertices'][i] for i in indices],
                          faces=[tuple(remap[i] for i in f) for f in part['faces'] if f[0] in reached]))
    return parts


def masks(old):
    art, clean = artwork(), core.artwork()
    frame = clean['gold']['frame']
    inner = frame[1]
    # Orange stays inside the gold frame and away from the red eye openings.
    safe_frame = raster(frame, .25)
    inner_band = stroke([inner+inner[:1]], 1.9)
    inner_clearance = stroke([inner+inner[:1]], .7)
    face = raster(art['orange']['serpent_face'])
    face_lines = stroke(list(art['face_lines'].values()), .4)
    orange = bytearray(ok and ((band and not clear) or head) and not line
        for ok, band, clear, head, line in zip(safe_frame, inner_band, inner_clearance, face, face_lines))
    # Source-traced hood bands stop just short of raised letters and rim.
    field = raster([inner], .30)
    text = [loops for name, loops in clean['gold'].items() if name != 'frame']+list(clean['jafar'].values())
    keepouts = bytearray(len(field))
    for loops in text:
        region = raster(loops, -.22)
        keepouts = bytearray(a or b for a, b in zip(keepouts, region))
    band_masks = {}
    for name, path in art['hood'].items():
        line = stroke([path], GROOVE_WIDTH)
        band_masks[name] = bytearray(a and b and not c for a, b, c in zip(line, field, keepouts))
    hood = bytearray(any(values) for values in zip(*band_masks.values()))
    return orange, hood, band_masks


def planar(loops):
    """Tessellate while preserving exact coordinates and avoiding GLU ties."""
    native = [p for c in loops for p in c]
    for degrees in (0, 17, 31, 47):
        co, si = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
        rotated = [[(x*co-y*si, x*si+y*co) for x, y in c] for c in loops]
        try:
            _, faces = triangulate(rotated)
        except AssertionError:
            continue
        if all(abs(area([native[i] for i in f])) > 1e-12 for f in faces):
            return native, faces
    raise AssertionError('Cannot tessellate relief surface')


def recessed(outline, recesses, bottom, surface, floor, template):
    """One manifold solid with blind recesses; no stacked shells or overlaps."""
    outline, recesses = orient(outline), orient(recesses)
    top_loops = orient(outline+recesses)
    vertices, faces, lookup = [], [], {}

    def vertex(xy, z):
        key = tuple(round(n, 9) for n in (*xy, z))
        if key not in lookup:
            lookup[key] = len(vertices)
            vertices.append(key)
        return lookup[key]

    def cap(loops, z, reverse=False):
        xy, triangles = planar(loops)
        for f in triangles:
            ids = tuple(vertex(xy[i], z) for i in f)
            faces.append(tuple(reversed(ids)) if reverse else ids)

    def walls(loops, z0, z1):
        for loop in loops:
            for a, b in zip(loop, loop[1:]+loop[:1]):
                aa, bb, cc, dd = vertex(a, z0), vertex(b, z0), vertex(b, z1), vertex(a, z1)
                faces.extend([(aa, bb, cc), (aa, cc, dd)])

    cap(outline, bottom, reverse=True)
    cap(top_loops, surface)
    cap(recesses, floor)
    walls(outline, bottom, surface)
    walls([list(reversed(c)) for c in recesses], floor, surface)
    part = dict(template, vertices=vertices, faces=faces)
    assert core.mesh_stats(part)['degenerate_triangles'] == 0
    return part


def geometry(old):
    orange_mask, hood_mask, _ = masks(old)
    orange, hood = core.contours(orange_mask), core.contours(hood_mask)
    base = recessed(boundary_loops(old[0]), hood, 0., 2., 2.-GROOVE_DEPTH, old[0])
    base['name'] = 'Charcoal — engraved cobra hood, backing and loop'
    gold_components = components(old[1])
    frame = max(gold_components, key=lambda p: core.bounds(p)[0][1]-core.bounds(p)[0][0])
    gold = core.merge([recessed(boundary_loops(frame), orange, 2., 2.8, 2.4, frame)]
                      +[p for p in gold_components if p is not frame])
    gold['name'] = 'Sunflower Yellow — smooth rim, lettering and serpent highlights'
    accent = core.relief([orange], 2.4, .4,
        dict(old[1], slot=2, color='#E68B31', name='Pumpkin Orange — inset rim and sculpted serpent face'))
    return [base, accent, gold, old[2]]


def preview(parts, path, width=1800, isometric=False):
    """Lit mesh preview; recessed charcoal floors are shaded by their depth."""
    yaw, elevation = math.radians(8), math.radians(52)
    right = (math.cos(yaw), -math.sin(yaw), 0.) if isometric else (1., 0., 0.)
    up = (math.sin(yaw)*math.sin(elevation), math.cos(yaw)*math.sin(elevation), math.cos(elevation)) if isometric else (0., 1., 0.)
    camera = (right[1]*up[2], -right[0]*up[2], right[0]*up[1]-right[1]*up[0])
    dot = lambda a, b: sum(x*y for x, y in zip(a, b))
    projected = [(dot(v, right), dot(v, up)) for p in parts for v in p['vertices']]
    x0, x1 = min(p[0] for p in projected), max(p[0] for p in projected)
    y0, y1 = min(p[1] for p in projected), max(p[1] for p in projected)
    step = (x1-x0)/(width-120)
    height = math.ceil((y1-y0)/step)+120
    triangles = []
    for part in parts:
        rgb = [int(part['color'][i:i+2], 16) for i in (1, 3, 5)]
        for face in part['faces']:
            a, b, c = [part['vertices'][i] for i in face]
            u, v = [b[i]-a[i] for i in range(3)], [c[i]-a[i] for i in range(3)]
            normal = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
            length = math.sqrt(dot(normal, normal))
            if dot(normal, camera) <= 0 or not length:
                continue
            normal = tuple(n/length for n in normal)
            shade = 1. if normal[2] > .99 else .55+.2*max(0., dot(normal, camera))
            if part['slot'] == 1 and max(a[2], b[2], c[2]) < 1.61:
                shade *= .60
            color = '#'+''.join(f'{round(n*shade):02X}' for n in rgb)
            xy = [(dot(v, right), dot(v, up)) for v in (a, b, c)]
            depths = [dot(v, camera) for v in (a, b, c)]
            triangles.append((sum(depths)/3, color, xy, depths))
    with core.Canvas((width, height), (x0-60*step, y1+60*step), step) as canvas:
        canvas.background('#F5F5F5')
        if isometric:
            # A depth buffer is needed: large backing triangles can cross
            # many raised letters and cannot be sorted by mean depth.
            pixels = bytearray(b'\xf5\xf5\xf5\xff')*(width*height)
            buffer = array('f', [-1e30])*(width*height)
            for _, color, xy, depths in triangles:
                points = [(*canvas.point(p), d) for p, d in zip(xy, depths)]
                y_start = max(0, math.ceil(min(p[1] for p in points)-.5))
                y_end = min(height-1, math.floor(max(p[1] for p in points)-.5))
                rgb = bytes([int(color[i:i+2], 16) for i in (5, 3, 1)]+[255])
                for row in range(y_start, y_end+1):
                    yy = row+.5
                    hits = []
                    for a, b in zip(points, points[1:]+points[:1]):
                        if min(a[1], b[1]) <= yy < max(a[1], b[1]):
                            t = (yy-a[1])/(b[1]-a[1])
                            hits.append((a[0]+t*(b[0]-a[0]), a[2]+t*(b[2]-a[2])))
                    if len(hits) != 2:
                        continue
                    left, right_hit = sorted(hits)
                    if right_hit[0]-left[0] < 1e-12:
                        continue
                    start = max(0, math.ceil(left[0]-.5))
                    stop = min(width-1, math.floor(right_hit[0]-.5))
                    change = (right_hit[1]-left[1])/(right_hit[0]-left[0])
                    depth = left[1]+(start+.5-left[0])*change
                    for column in range(start, stop+1):
                        index = row*width+column
                        if depth > buffer[index]:
                            buffer[index] = depth
                            pixels[index*4:index*4+4] = rgb
                        depth += change
            canvas.lib.cairo_surface_flush(canvas.surface)
            target = canvas.lib.cairo_image_surface_get_data(canvas.surface)
            core.C.memmove(target, bytes(pixels), len(pixels))
            canvas.lib.cairo_surface_mark_dirty.argtypes = [core.C.c_void_p]
            canvas.lib.cairo_surface_mark_dirty(canvas.surface)
        else:
            for _, color, xy, _ in sorted(triangles, key=lambda t: t[0]):
                canvas.fill([xy], color)
        canvas.save(path)


def main():
    data = core.package(SOURCE)
    old = read_parts(data)
    parts = geometry(old)
    root = ET.fromstring(data['3D/3dmodel.model'])
    config = ET.fromstring(data['Metadata/model_settings.config'])
    obj = config.find('object')
    assembly = root.find(f"m:resources/m:object[@id='{obj.get('id')}']", NS)
    children = assembly.find('m:components', NS)
    resource_path = children[1].get('{'+core.PROD+'}path').lstrip('/')
    resource = ET.fromstring(data[resource_path])
    resources = resource.find('m:resources', NS)
    used_ids = {int(o.get('id')) for o in resources}
    assert 2 not in used_ids
    new_mesh = copy.deepcopy(resources.find("m:object[@id='3']", NS))
    new_mesh.set('id', '2')
    new_mesh.set('{'+core.PROD+'}UUID', str(uuid.uuid5(uuid.NAMESPACE_URL, NAME+'/orange-mesh')))
    resources.append(new_mesh)
    child = copy.deepcopy(children[1])
    child.set('objectid', '2')
    child.set('{'+core.PROD+'}UUID', str(uuid.uuid5(uuid.NAMESPACE_URL, NAME+'/orange-component')))
    children.insert(1, child)
    cfg = copy.deepcopy(obj.find("part[@id='3']"))
    cfg.set('id', '2')
    cfg.set('uuid', str(uuid.uuid5(uuid.NAMESPACE_URL, NAME+'/orange-part')))
    obj.insert(list(obj).index(obj.find("part[@id='3']")), cfg)
    for index in (0, 1, 2):
        child = children[index]
        oid = child.get('objectid')
        core.write_mesh(resources.find(f"m:object[@id='{oid}']", NS), parts[index])
        child.set('transform', ' '.join(map(str, IDENTITY)))
        cfg = obj.find(f"part[@id='{oid}']")
        for md in list(cfg.findall('metadata')):
            if md.get('key', '').startswith('source_'):
                cfg.remove(md)
        cfg.find("metadata[@key='name']").set('value', parts[index]['name'])
        cfg.find("metadata[@key='extruder']").set('value', str(parts[index]['slot']))
        cfg.find("metadata[@key='matrix']").set('value', '1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1')
        cfg.find('mesh_stat').set('face_count', str(len(parts[index]['faces'])))
    obj.find("metadata[@key='name']").set('value', NAME)
    obj.find('metadata[@face_count]').set('face_count', str(sum(len(p['faces']) for p in parts)))
    root.find("m:metadata[@name='Description']", NS).text = (
        VERSION+'; solid-colour v1.6 lettering retained; smooth orange inset rim and serpent face, '
        + ('gold brows/muzzle and red eyes; ' if artwork()['face_lines'] else
           'plain orange face between red eyes with gold surrounds; no central chevron; ')
        + 'five source-traced cobra hood bands engraved '
        '0.4 mm into 2 mm charcoal backing, 0.6 mm nominal grooves; 1.6 mm minimum floor; '
        'native backing silhouette, flat 2 mm eyelet, 6.5 mm bore and all profiles retained; '
        'all four native filament slots active; maximum height 2.8 mm.')
    if not any(k.startswith('{'+core.PROD+'}') for e in resource.iter() for k in e.attrib):
        resource.set('xmlns:p', core.PROD)
    data[resource_path] = ET.tostring(resource, encoding='utf-8', xml_declaration=True)
    data['3D/3dmodel.model'] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    data['Metadata/model_settings.config'] = ET.tostring(config, encoding='utf-8', xml_declaration=True)
    # Shade the recessed floors in the gallery thumbnail as in the relief
    # preview. The actual model still uses one charcoal filament throughout.
    floor_faces = [f for f in parts[0]['faces'] if all(abs(parts[0]['vertices'][i][2]-1.6) < 1e-7 for i in f)]
    other_faces = [f for f in parts[0]['faces'] if not all(abs(parts[0]['vertices'][i][2]-1.6) < 1e-7 for i in f)]
    lit = [dict(parts[0], faces=other_faces), dict(parts[0], faces=floor_faces, color='#202324')]+parts[1:]
    data['Metadata/plate_1.png'] = thumbnail(lit, 512)
    data['Metadata/plate_no_light_1.png'] = data['Metadata/plate_1.png']
    data['Metadata/plate_1_small.png'] = thumbnail(lit, 128)
    DEST.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(PROJECT, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path, raw in data.items():
            archive.writestr(path, raw)
    loaded = read_parts(core.package(PROJECT))
    assert loaded[3] == old[2], 'v1.6 red lettering and eyes changed'
    preview(loaded, DEST/(NAME+'_preview.png'))
    preview(loaded, DEST/(NAME+'_isometric.png'), isometric=True)
    comparison(read_parts(core.package(COMPARISON_SOURCE)), loaded)
    head_preview(loaded, DEST/(NAME+'_head_preview.png'))
    print(json.dumps(dict(project=str(PROJECT.relative_to(ROOT)), sha256=core.digest(PROJECT),
        parts=[dict(slot=p['slot'], **core.mesh_stats(p)) for p in loaded]), indent=2))


def head_preview(parts, path):
    """Large front view of the actual head geometry for artwork review."""
    left, top = core.registered((585, -10))
    right, bottom = core.registered((795, 130))
    width = 1000
    step = (right-left)/(width-80)
    height = math.ceil((top-bottom)/step)+80
    triangles = []
    for part in parts:
        for face in part['faces']:
            vs = [part['vertices'][i] for i in face]
            if area([v[:2] for v in vs]) > 1e-12:
                triangles.append((sum(v[2] for v in vs), part['color'], [v[:2] for v in vs]))
    with core.Canvas((width, height), (left-40*step, top+40*step), step) as canvas:
        canvas.background('#F5F5F5')
        for _, color, xy in sorted(triangles, key=lambda t: t[0]):
            canvas.fill([xy], color)
        canvas.save(path)


def comparison(old, parts, *, before_label=None, after_label=None, destination=None):
    with tempfile.TemporaryDirectory(prefix='lorcana-set08-preview-') as directory:
        paths = [core.Path(directory)/f'{i}.png' for i in (0, 1)]
        for meshes, path in zip((old, parts), paths):
            preview(meshes, path, width=1200)
        raw = paths[0].read_bytes()
        height = int.from_bytes(raw[20:24], 'big')
        with core.Canvas((2400, height+75), (0, 0), 1.) as canvas:
            lib, ctx = canvas.lib, canvas.context
            declarations = {
                'cairo_image_surface_create_from_png': (core.C.c_void_p, [core.C.c_char_p]),
                'cairo_set_source_surface': (None, [core.C.c_void_p, core.C.c_void_p, core.C.c_double, core.C.c_double]),
                'cairo_select_font_face': (None, [core.C.c_void_p, core.C.c_char_p, core.C.c_int, core.C.c_int]),
                'cairo_set_font_size': (None, [core.C.c_void_p, core.C.c_double]),
                'cairo_show_text': (None, [core.C.c_void_p, core.C.c_char_p]),
            }
            for name, (restype, argtypes) in declarations.items():
                getattr(lib, name).restype, getattr(lib, name).argtypes = restype, argtypes
            canvas.background('#F5F5F5')
            for i, path in enumerate(paths):
                surface = lib.cairo_image_surface_create_from_png(str(path).encode())
                lib.cairo_set_source_surface(ctx, surface, i*1200, 75)
                lib.cairo_paint(ctx)
                lib.cairo_surface_destroy(surface)
                canvas.color('#363A3B')
                lib.cairo_select_font_face(ctx, b'DejaVu Sans', 0, 0)
                lib.cairo_set_font_size(ctx, 28.)
                lib.cairo_move_to(ctx, i*1200+40, 45)
                label = (before_label or COMPARISON_SOURCE.parent.name) if i == 0 else (after_label or VERSION+(
                    ' - orange serpent and engraved hood' if artwork()['face_lines'] else ' - corrected cobra head'))
                lib.cairo_show_text(ctx, label.encode())
            canvas.save(destination or DEST/(NAME+'_comparison.png'))


if __name__ == '__main__':
    main()
