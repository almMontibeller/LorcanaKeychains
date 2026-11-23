#!/usr/bin/env python3
"""Build flat 1.6 mm loops across all sets and a printable Set 05 underline.

NumPy, Pillow, system GLU/Cairo and the local Bambu runtime are required.
All source projects are preserved. New outputs are native unsliced 3MF files.
"""
from pathlib import Path
import argparse
import collections
import io
import json
import math
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
from PIL import Image, ImageDraw

from rebuild_set04 import area, boundary_loops, extrude, orient
from repair_v1_1 import IDENTITY, NS, read_parts, thumbnail
from standardize_loop_diameters import (
    ROOT, CORE, PROD, TAG, package, digest, bore_index, centre, bounds,
    mesh_stats, extrude_native, write_mesh,
)
from validate_bambu import bambu_command

LOOP_HEIGHT = 1.6
BODY_HEIGHT = 2.
UNDERLINE_WIDTH = .9
COLLECTION = ROOT / 'collection/thin_loops'


def clip(poly, cut, left):
    result = []
    for a, b in zip(poly, poly[1:]+poly[:1]):
        ain, bin_ = (a[0] <= cut, b[0] <= cut) if left else (a[0] >= cut, b[0] >= cut)
        if ain:
            result.append(a)
        if ain != bin_:
            t = (cut-a[0])/(b[0]-a[0])
            result.append((cut, a[1]+t*(b[1]-a[1])))
    cleaned = []
    for p in result:
        if not cleaned or math.dist(p, cleaned[-1]) > 1e-9:
            cleaned.append(p)
    if len(cleaned) > 1 and math.dist(cleaned[0], cleaned[-1]) < 1e-9:
        cleaned.pop()
    return cleaned


def stepped_backing(part, cut):
    """One closed solid: flat 1.6 mm loop, vertical step, flat 2 mm body.

    Split native cap triangles at the step. Use matching vertical bands on
    the outer walls so there are no T junctions or overlapping inner shells.
    """
    loops = orient(boundary_loops(part))
    flat, rotation = extrude_native(loops, part)
    top = [[flat['vertices'][i][:2] for i in face] for face in flat['faces']
           if all(abs(flat['vertices'][i][2]-2) < 1e-8 for i in face)]
    vertices, faces, index = [], [], {}
    cut_edges = {True: collections.Counter(), False: collections.Counter()}
    def vertex(p):
        p = tuple(round(v, 9) for v in p)
        if p not in index:
            index[p] = len(vertices)
            vertices.append(p)
        return index[p]
    def triangle(points):
        f = tuple(vertex(p) for p in points)
        if len(set(f)) < 3:
            return
        a, b, c = (vertices[i] for i in f)
        cross = np.cross(np.subtract(b, a), np.subtract(c, a))
        if float(cross@cross) < 1e-22:
            return
        faces.append(f)
    def quad(a, b, low, high):
        triangle([(a[0], a[1], low), (b[0], b[1], low), (b[0], b[1], high)])
        triangle([(a[0], a[1], low), (b[0], b[1], high), (a[0], a[1], high)])
    for tri in top:
        for left, height in ((True, LOOP_HEIGHT), (False, BODY_HEIGHT)):
            poly = clip(tri, cut, left)
            if len(poly) < 3 or abs(area(poly)) < 1e-12:
                continue
            for a, b in zip(poly, poly[1:]+poly[:1]):
                if abs(a[0]-cut) < 1e-8 and abs(b[0]-cut) < 1e-8:
                    cut_edges[left][tuple(sorted((round(a[1], 9), round(b[1], 9))))] += 1
            for i in range(1, len(poly)-1):
                points = [poly[0], poly[i], poly[i+1]]
                triangle([(x, y, height) for x, y in points])
                triangle([(x, y, 0.) for x, y in reversed(points)])
    for loop in loops:
        for a, b in zip(loop, loop[1:]+loop[:1]):
            pieces = [(a, b)]
            if (a[0] < cut < b[0]) or (b[0] < cut < a[0]):
                t = (cut-a[0])/(b[0]-a[0])
                hit = (cut, a[1]+t*(b[1]-a[1]))
                pieces = [(a, hit), (hit, b)]
            for a, b in pieces:
                quad(a, b, 0., LOOP_HEIGHT)
                if (a[0]+b[0])/2 > cut:
                    quad(a, b, LOOP_HEIGHT, BODY_HEIGHT)
    shared = set(cut_edges[True]) & set(cut_edges[False])
    for y0, y1 in shared:
        if y1-y0 < 1e-8:
            continue
        # Outward normal points towards the low loop (negative X).
        quad((cut, y1), (cut, y0), LOOP_HEIGHT, BODY_HEIGHT)
    result = dict(part, vertices=vertices, faces=faces)
    stats = mesh_stats(result)
    assert stats['degenerate_triangles'] == 0
    return result, dict(loop_thickness_mm=LOOP_HEIGHT, backing_thickness_mm=BODY_HEIGHT,
                       junction_x_mm=cut, junction='vertical step; no sloped transition',
                       tessellation_axis_rotation_degrees=rotation)


def underline_loop(part):
    return next(c for c in boundary_loops(part)
                if 27 < min(x for x, y in c) < 30 and max(x for x, y in c) < 50)


def component_vertices(part, seed):
    neighbors = collections.defaultdict(set)
    for f in part['faces']:
        for i in f:
            neighbors[i].update(f)
    reached, todo = set(), [seed]
    while todo:
        i = todo.pop()
        if i in reached:
            continue
        reached.add(i)
        todo.extend(neighbors[i]-reached)
    return reached


def replace_underline(part):
    old = underline_loop(part)
    xs = np.linspace(28.5, 48.3, 60)
    ys = []
    for x in xs:
        hits = sorted(a[1]+(x-a[0])*(b[1]-a[1])/(b[0]-a[0])
                      for a, b in zip(old, old[1:]+old[:1]) if (a[0] > x) != (b[0] > x))
        ys.append((hits[0]+hits[-1])/2)
    coefficients = np.polyfit(xs, ys, 2)
    curve, derivative = np.poly1d(coefficients), np.polyder(np.poly1d(coefficients))
    points = [(float(x), float(curve(x))) for x in xs]
    def normal(x):
        slope = float(derivative(x))
        return np.array([-slope, 1.])/math.hypot(slope, 1.)
    radius = UNDERLINE_WIDTH/2
    upper = [tuple(np.array(p)+radius*normal(p[0])) for p in points]
    lower = [tuple(np.array(p)-radius*normal(p[0])) for p in points]
    def cap(p, vector):
        angle = math.atan2(vector[1], vector[0])
        return [(p[0]+radius*math.cos(angle-t*math.pi), p[1]+radius*math.sin(angle-t*math.pi))
                for t in np.linspace(0, 1, 17)[1:-1]]
    loop = upper+cap(points[-1], normal(points[-1][0]))+list(reversed(lower))+cap(points[0], -normal(points[0][0]))
    line = extrude(orient([loop]), 2., 1., part)
    seed = next(i for i, v in enumerate(part['vertices']) if v[:2] in old)
    removed = component_vertices(part, seed)
    old_faces = [f for f in part['faces'] if not any(i in removed for i in f)]
    kept_vertices = [i for i in range(len(part['vertices'])) if i not in removed]
    remap = {old: new for new, old in enumerate(kept_vertices)}
    count = len(kept_vertices)
    result = dict(part,
                  vertices=[part['vertices'][i] for i in kept_vertices]+line['vertices'],
                  faces=[tuple(remap[i] for i in f) for f in old_faces]
                        +[tuple(i+count for i in f) for f in line['faces']])
    report = dict(width_mm=UNDERLINE_WIDTH, rounded_end_caps=True, centreline_x_mm=[28.5, 48.3],
                  centreline_quadratic_coefficients=coefficients.tolist(),
                  old_line_triangles_removed=len(part['faces'])-len(old_faces),
                  unchanged_artwork_triangles=len(old_faces), new_line_triangles=len(line['faces']))
    return result, report, old_faces


def write_project(source, target, parts, changed, description):
    data = package(source)
    root = ET.fromstring(data['3D/3dmodel.model'])
    config = ET.fromstring(data['Metadata/model_settings.config'])
    obj = config.find('object')
    assembly = root.find(f"m:resources/m:object[@id='{obj.get('id')}']", NS)
    resources = {}
    for i, component in enumerate(assembly.find('m:components', NS)):
        if i not in changed:
            continue
        path = component.get('{'+PROD+'}path', '3D/3dmodel.model').lstrip('/')
        if path not in resources:
            resources[path] = root if path == '3D/3dmodel.model' else ET.fromstring(data[path])
        oid = component.get('objectid')
        write_mesh(resources[path].find(f"m:resources/m:object[@id='{oid}']", NS), parts[i])
        component.set('transform', ' '.join(map(str, IDENTITY)))
        cfg = obj.find(f"part[@id='{oid}']")
        for md in list(cfg.findall('metadata')):
            if md.get('key', '').startswith('source_'):
                cfg.remove(md)
        cfg.find("metadata[@key='matrix']").set('value', '1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1')
        cfg.find('mesh_stat').set('face_count', str(len(parts[i]['faces'])))
    for path, resource in resources.items():
        if resource is root:
            continue
        if not any(k.startswith('{'+PROD+'}') for e in resource.iter() for k in e.attrib):
            resource.set('xmlns:p', PROD)
        data[path] = ET.tostring(resource, encoding='utf-8', xml_declaration=True)
    name = obj.find("metadata[@key='name']")
    name.set('value', target.stem)
    obj.find('metadata[@face_count]').set('face_count', str(sum(len(p['faces']) for p in parts)))
    md = root.find("m:metadata[@name='Description']", NS)
    if md is None:
        md = ET.SubElement(root, TAG('metadata'), {'name': 'Description'})
    md.text = description
    data['3D/3dmodel.model'] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    data['Metadata/model_settings.config'] = ET.tostring(config, encoding='utf-8', xml_declaration=True)
    data['Metadata/plate_1.png'] = thumbnail(parts, 512)
    data['Metadata/plate_no_light_1.png'] = data['Metadata/plate_1.png']
    data['Metadata/plate_1_small.png'] = thumbnail(parts, 128)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, raw in data.items():
            archive.writestr(name, raw)
    preview = Image.open(io.BytesIO(thumbnail(parts, 1800)))
    bb = bounds(parts[0])
    height = min(1800, math.ceil(1800*(.88*(bb[1][1]-bb[1][0])/(bb[0][1]-bb[0][0])+.12)))
    preview.crop((0, (1800-height)//2, 1800, (1800+height)//2)).save(target.with_name(target.stem+'_preview.png'))


def geometry_checks(source, target, changed, attachment, underline, old_faces):
    old_data, new_data = package(source), package(target)
    old, new = read_parts(old_data), read_parts(new_data)
    assert old_data['Metadata/project_settings.config'] == new_data['Metadata/project_settings.config']
    roots = [ET.fromstring(d['3D/3dmodel.model']) for d in (old_data, new_data)]
    assert ET.tostring(roots[0].find('m:build', NS)) == ET.tostring(roots[1].find('m:build', NS))
    for i in range(1, len(old)):
        if i not in changed:
            assert old[i] == new[i], ('colour geometry changed', i)
    loops = [boundary_loops(p[0]) for p in (old, new)]
    assert len(loops[0]) == len(loops[1])
    # Splitting at the step inserts collinear outline vertices. Compare the
    # actual contours, allowing those extra points without moving the shape.
    for previous, current in (loops, list(reversed(loops))):
        a = np.asarray([p for c in previous for p in c])
        b = np.asarray([p for c in previous for p in c[1:]+c[:1]])
        delta = b-a
        length2 = np.sum(delta*delta, axis=1)
        known = {tuple(round(v, 7) for v in p) for p in a}
        for point in (p for c in current for p in c):
            if tuple(round(v, 7) for v in point) in known:
                continue
            t = np.clip(np.sum((point-a)*delta, axis=1)/length2, 0., 1.)
            distance2 = np.sum((point-(a+t[:, None]*delta))**2, axis=1)
            assert float(np.min(distance2)) < 1e-16, 'backing footprint or bore changed'
    bore = loops[1][bore_index(loops[1])]
    assert all(abs(max(p[k] for p in bore)-min(p[k] for p in bore)-5.5) < 1e-8 for k in (0, 1))
    assert {round(v[2], 8) for v in new[0]['vertices']} == {0., LOOP_HEIGHT, BODY_HEIGHT}
    cut = attachment['junction_x_mm']
    assert all(abs(v[2]) < 1e-8 or abs(v[2]-LOOP_HEIGHT) < 1e-8
               for v in new[0]['vertices'] if v[0] < cut-1e-8)
    assert all(v[0] > cut+.29 for p in new[1:] for v in p['vertices'])
    stats = [mesh_stats(p) for p in new]
    assert stats[0]['degenerate_triangles'] == 0
    for i in range(1, len(old)):
        assert stats[i]['degenerate_triangles'] <= mesh_stats(old[i])['degenerate_triangles']
    if underline:
        for old_f, new_f in zip(old_faces, new[2]['faces']):
            for a, b in zip((old[2]['vertices'][i] for i in old_f), (new[2]['vertices'][i] for i in new_f)):
                assert math.dist(a, b) < 1e-8, 'other ivory artwork changed'
        import rebuild_set05 as raster
        line = underline_loop(new[2])
        line_mask = raster.footprint([line])
        assert not np.any(line_mask & raster.footprint(boundary_loops(new[1]))), 'underline intersects red'
        assert not np.any(line_mask & ~raster.footprint(boundary_loops(new[0]))), 'underline unsupported'
        # Recheck the unchanged reinforced-star footprint, using the flat
        # source backing to keep this width check separate from loop height.
        from validate_set05 import star_connection_checks
        stars = star_connection_checks(old[0], old[0])
    else:
        stars = None
    return new, dict(backing_footprint_and_bore_preserved=True,
                     artwork_clear_of_thinned_region=True, print_settings_byte_identical=True,
                     plate_placement_preserved=True, attachment=attachment,
                     parts=[dict(name=p['name'], **s) for p, s in zip(new, stats)],
                     reinforced_star_check=stars)


def read_toolpaths(path, bbox, slots):
    layers = collections.defaultdict(list)
    x, y, tool, z, width, feature = 0., 0., 0, 0., .42, 'Custom'
    relative, previous_e = True, 0.
    x0, y0 = bbox['x'], bbox['y']
    x1, y1 = x0+bbox['width'], y0+bbox['depth']
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith('; Z_HEIGHT:'):
            z = round(float(line.split(':', 1)[1]), 3)
        elif line.startswith('; LINE_WIDTH:'):
            width = float(line.split(':', 1)[1])
        elif line.startswith('; FEATURE:'):
            feature = line.split(':', 1)[1].strip()
        elif re.fullmatch(r'T\d+', line) and int(line[1:]) < slots:
            tool = int(line[1:])
        elif line in ('M82', 'M83'):
            relative = line == 'M83'
        command = line.split(';', 1)[0].split()
        if not command:
            continue
        values = {k: float(v) for k, v in re.findall(r'([XYZEFIJP])\s*([-+]?(?:\d*\.\d+|\d+))', ' '.join(command[1:]))}
        if command[0] == 'G92':
            previous_e = values.get('E', previous_e)
        if command[0] not in ('G0', 'G1', 'G2', 'G3'):
            continue
        end = values.get('X', x), values.get('Y', y)
        extrusion = values.get('E', 0) if relative else values.get('E', previous_e)-previous_e
        if not relative:
            previous_e = values.get('E', previous_e)
        if extrusion > 0 and ('X' in values or 'Y' in values) and feature not in ('Custom', 'Prime tower'):
            points = [(x, y), end]
            if command[0] in ('G2', 'G3') and ('I' in values or 'J' in values):
                cx, cy = x+values.get('I', 0), y+values.get('J', 0)
                radius = math.hypot(x-cx, y-cy)
                start, stop = math.atan2(y-cy, x-cx), math.atan2(end[1]-cy, end[0]-cx)
                sweep = (stop-start) % math.tau if command[0] == 'G3' else -((start-stop) % math.tau)
                count = max(2, math.ceil(abs(sweep)*radius/.04))
                points = [(cx+radius*math.cos(start+sweep*i/count), cy+radius*math.sin(start+sweep*i/count))
                          for i in range(count+1)]
            if all(x0-.25 <= px <= x1+.25 and y0-.25 <= py <= y1+.25 for px, py in points):
                layers[z].append((points, width, tool))
        x, y = end
    return layers


def draw_bead(draw, points, width, color):
    stroke = max(1, round(width))
    draw.line(points, fill=color, width=stroke, joint='curve')
    radius = stroke/2
    for x, y in (points[0], points[-1]):
        draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=color)


def toolpath_checks(layers, parts, bbox, attachment, underline, *, loop_height=LOOP_HEIGHT, bore_loop=None):
    bb = bounds(parts[0])
    dx, dy = bbox['x']-bb[0][0], bbox['y']-bb[1][0]
    bore = bore_loop if bore_loop is not None else boundary_loops(parts[0])[bore_index(boundary_loops(parts[0]))]
    cx, cy = centre(bore)
    loop_limit_x = max(p[0] for p in bore)+.05
    loop_paths = 0
    too_high = 0
    for z, paths in layers.items():
        for points, width, tool in paths:
            if any(px-dx < loop_limit_x and abs(py-dy-cy) < 5.5 for px, py in points):
                if abs(z-loop_height) < 1e-6:
                    loop_paths += 1
                if z > loop_height+1e-6:
                    too_high += 1
    assert loop_paths and too_high == 0, ('loop not deposited at correct height', loop_paths, too_high)
    result = dict(loop_top_layer_mm=loop_height, loop_top_segments=loop_paths,
                  loop_segments_above_target_height=too_high)
    if underline:
        curve = np.poly1d(underline['centreline_quadratic_coefficients'])
        scale = 40
        per_layer = {}
        for z in (2.2, 2.4, 2.6, 2.8, 3.):
            image = Image.new('L', (960, 400))
            draw = ImageDraw.Draw(image)
            count = 0
            for points, width, tool in layers[z]:
                if tool != 2:
                    continue
                local = [(x-dx, y-dy) for x, y in points]
                if all(27 <= x <= 50 and 8 <= y <= 17 for x, y in local):
                    projected = [((x-27)*scale, (17-y)*scale) for x, y in local]
                    draw_bead(draw, projected, width*scale, 255)
                    count += 1
            array = np.asarray(image).copy()
            yy, xx = np.indices(array.shape)
            local_x, local_y = 27+xx/scale, 17-yy/scale
            # Keep only the underline's own corridor, excluding letter bottoms.
            corridor = (abs(local_y-curve(local_x)) < .75) & (local_x > 27.8) & (local_x < 49.)
            array[~corridor] = 0
            image = Image.fromarray(array).copy()
            seed = (round((28.5-27)*scale), round((17-float(curve(28.5)))*scale))
            assert image.getpixel(seed) == 255, ('underline start is missing', z)
            ImageDraw.floodfill(image, seed, 128)
            points = [(round((x-27)*scale), round((17-float(curve(x)))*scale))
                      for x in np.linspace(28.5, 48.3, 200)]
            assert all(image.getpixel(p) == 128 for p in points), ('broken printed underline', z)
            assert not np.any(np.asarray(image) == 255), ('detached underline deposits', z)
            per_layer[str(z)] = dict(continuous=True, detached_deposits=0, sampled_centreline_points=200,
                                     candidate_segments=count)
        result['underline_layers'] = per_layer
    return result


def render_slice(layers, parts, bbox, colors, output, *, loop_height=LOOP_HEIGHT):
    scale, margin = 32, 65
    im = Image.new('RGB', (math.ceil(bbox['width']*scale)+2*margin,
                          math.ceil(bbox['depth']*scale)+2*margin), '#404443')
    draw = ImageDraw.Draw(im)
    selected = {loop_height, BODY_HEIGHT} | {round(max(v[2] for v in p['vertices']), 3) for p in parts[1:]}
    for z in sorted(selected):
        assert layers[z], ('missing layer', z)
        for points, width, tool in layers[z]:
            projected = [(margin+(x-bbox['x'])*scale, margin+(bbox['y']+bbox['depth']-y)*scale) for x, y in points]
            draw_bead(draw, projected, width*scale, colors[tool])
    im.resize((1800, round(im.height*1800/im.width)), Image.Resampling.LANCZOS).save(output)


def build_one(folder, command):
    number = int(folder.name[4:6])
    old_version, version = ('v1.4', 'v1.5') if number == 4 else ('v1.5', 'v1.6') if number == 5 else ('v1.3', 'v1.4')
    sources = list((folder/old_version).glob('*.3mf'))
    assert len(sources) == 1
    source = sources[0]
    target = folder/version/(folder.name+'_'+version+'.3mf')
    source_hash = digest(source)
    original = read_parts(package(source))
    parts = list(original)
    cut = min(10.5, min(v[0] for p in original[1:] for v in p['vertices'])-.3)
    parts[0], attachment = stepped_backing(original[0], cut)
    changed, underline, old_faces = {0}, None, None
    if number == 5:
        parts[2], underline, old_faces = replace_underline(original[2])
        changed.add(2)
    description = (f'{version}; flat 1.6 mm attachment loop, vertical step to 2 mm backing; '
                   '5.5 mm bore and 10.5 mm nominal outer diameter; original profiles and placement.'
                   + (' Continuous 0.9 mm rounded ivory underline; reinforced stars retained.' if underline else ''))
    write_project(source, target, parts, changed, description)
    parts, geometry = geometry_checks(source, target, changed, attachment, underline, old_faces)
    logs = ROOT/'validation'/folder.name/version
    logs.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='lorcana-thin-loops-') as directory:
        run = subprocess.run(command+['--datadir', directory, '--debug', '2', '--info', '--slice', '1',
                                     '--outputdir', str(logs), str(target)],
                             cwd=logs, capture_output=True, text=True, timeout=180)
    log = run.stdout+run.stderr
    (logs/'slice.log').write_text(log)
    result = json.loads((logs/'result.json').read_text())
    assert run.returncode == result['return_code'] == 0, (target.name, result)
    assert 'manifold = yes' in log
    plate = result['sliced_plates'][0]
    assert plate['warning_message'] == '', (target.name, plate['warning_message'])
    colors = json.loads(package(target)['Metadata/project_settings.config'])['filament_colour']
    channels = [f['id'] for f in plate['filaments']]
    assert channels == list(range(1, len(colors)+1))
    assert all(f['main_used_g'] > 0 for f in plate['filaments'])
    layers = read_toolpaths(logs/'plate_1.gcode', plate['objects'][0]['bbox'], len(colors))
    deposited = toolpath_checks(layers, parts, plate['objects'][0]['bbox'], attachment, underline)
    render_slice(layers, parts, plate['objects'][0]['bbox'], colors, target.with_name(target.stem+'_sliced_preview.png'))
    assert digest(source) == source_hash
    report = dict(project=str(target.relative_to(ROOT)), filename=target.name,
                  source=str(source.relative_to(ROOT)), source_sha256=source_hash, output_sha256=digest(target),
                  geometry=geometry, underline=underline, toolpath_checks=deposited,
                  used_filament_slots=channels, bambu_version='02.08.02.61', slice_result=result,
                  physical_print_verified=False)
    (target.parent/f'Geometry_{version}.json').write_text(json.dumps({k: v for k, v in report.items() if k != 'slice_result'}, indent=2)+'\n')
    (target.parent/f'Validation_{version}.json').write_text(json.dumps(report, indent=2)+'\n')
    readme = (f'# {folder.name[7:].replace("_", " ")} {version}\n\n'
              f'Open [{target.name}]({target.name}) as a project in Bambu Studio.\n\n'
              'The attachment loop is **1.6 mm thick** and joins the original **2 mm backing** '
              'with a flat vertical step. The step is positioned before the artwork so it '
              'remains fully supported. The 5.5 mm bore, nominal 10.5 mm outer diameter, '
              'backing footprint, colours, placement and print profiles are retained.\n\n')
    if underline:
        readme += ('The ivory underline beneath SHIM is redrawn as a smooth **0.9 mm stroke** '
                   'with rounded ends. Other letters, the red panel and reinforced-star '
                   'footprints are preserved. All five ivory layers from Z=2.2 to 3.0 mm '
                   'have a continuous deposited underline with no detached deposits.\n\n')
    readme += ('Bambu Studio imports and slices successfully, uses every intended filament '
               'and reports no plate warnings. Mesh checks confirm a closed manifold backing '
               'with no degenerate triangles. Actual G-code confirms the loop ends at Z=1.6 mm. '
               'Physical printing and chain fit have not been tested.\n\n'
               f'![Actual sliced toolpaths]({target.stem}_sliced_preview.png)\n\n'
               f'[Validation_{version}.json](Validation_{version}.json) contains the geometry, '
               'toolpath checks and slicer results. Reproduce from the repository root with '
               '`python3 tools/refine_loops_and_underline.py`, using NumPy, Pillow and local Bambu Studio.\n')
    (target.parent/'README.md').write_text(readme)
    return target, source, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sets', nargs='*', type=int, help='Build only these set numbers; do not publish collection indexes.')
    args = parser.parse_args()
    command = bambu_command()
    outputs = []
    for folder in sorted((ROOT/'sets').glob('Set_*')):
        if args.sets and int(folder.name[4:6]) not in args.sets:
            continue
        print(folder.name+': building thin loop'+(' and complete underline' if folder.name.startswith('Set_05_') else ''), flush=True)
        outputs.append(build_one(folder, command))
        print(folder.name+': geometry, slice and deposited toolpaths passed', flush=True)
    if args.sets:
        return
    assert len(outputs) == 14
    COLLECTION.mkdir(parents=True, exist_ok=True)
    manifest = dict(loop_thickness_mm=LOOP_HEIGHT, backing_thickness_mm=BODY_HEIGHT,
                    bore_diameter_mm=5.5, outer_diameter_nominal_mm=10.5,
                    projects=[dict(project=r['project'], source=r['source'], source_sha256=r['source_sha256'],
                                   output_sha256=r['output_sha256'], validation=str((p.parent/f'Validation_{p.parent.name}.json').relative_to(ROOT)))
                              for p, _, r in outputs])
    (COLLECTION/'Manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    overview = ('# Thin attachment loops and continuous Set 05 underline\n\n'
                'All fourteen current projects have flat **1.6 mm attachment loops** joining '
                'their **2 mm backing** at a vertical step, retaining the 5.5 mm holes and '
                'nominal 10.5 mm outer diameter. The junction position adapts to keep artwork '
                'fully supported. Set 05 also has a smooth **0.9 mm ivory underline** with rounded ends.\n\n'
                'All fourteen projects pass Bambu slicing, use all intended colours, and '
                'report no plate warnings. Actual toolpaths confirm that every loop ends at '
                '1.6 mm. Set 05’s underline is continuous without detached deposits in all '
                'five ivory layers. Source projects, colour profiles and backing footprints '
                'are preserved. The source Set 14 Caramel mesh retains its four existing '
                'degenerate faces; all rebuilt backings have none. No physical print or chain-fit '
                'test was performed.\n\n| Set | Current project |\n| --- | --- |\n')
    root_readme = (ROOT/'README.md').read_text()
    for target, source, _ in outputs:
        overview += f'| {target.parent.parent.name[4:].replace("_", " ")} | [{target.name}](../../{target.relative_to(ROOT)}) |\n'
        root_readme = root_readme.replace(str(source.relative_to(ROOT)), str(target.relative_to(ROOT))).replace(source.name, target.name)
    overview += '\n[Manifest.json](Manifest.json) records source and output hashes and the per-project validation reports.\n'
    (COLLECTION/'README.md').write_text(overview)
    root_readme = re.sub(r'The latest projects share.*?\n\n',
        'The latest projects have **1.6 mm attachment loops**, a **2 mm backing**, '
        '**5.5 mm holes** and a **10.5 mm nominal outer diameter**. '
        'See [updated projects and validation](collection/thin_loops/README.md).\n\n', root_readme, count=1, flags=re.S)
    if 'python3 tools/refine_loops_and_underline.py' not in root_readme:
        root_readme = root_readme.replace('python3 tools/standardize_loop_diameters.py\n',
                                         'python3 tools/standardize_loop_diameters.py\npython3 tools/refine_loops_and_underline.py\n', 1)
    (ROOT/'README.md').write_text(root_readme)
    archive = ROOT/'archives/Lorcana_Keychains_Thin_Loops.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for target, _, _ in outputs:
            for path in target.parent.iterdir():
                if path.is_file():
                    z.write(path, str(path.relative_to(ROOT)))
        for path in COLLECTION.iterdir():
            if path.is_file():
                z.write(path, str(path.relative_to(ROOT)))
    print('Complete: all 14 projects validated; '+str(archive.relative_to(ROOT)), flush=True)


if __name__ == '__main__':
    main()
