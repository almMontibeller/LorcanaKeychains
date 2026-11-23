#!/usr/bin/env python3
"""Build Set 07 v1.6 from source-registered vectors; native four-colour 3MF.

Requires NumPy, Pillow and system GLU/Cairo. Existing projects are untouched.
"""
from pathlib import Path
import copy
import io
import json
import math
import re
import uuid
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
from PIL import Image, ImageDraw

from rebuild_set04 import area, extrude, orient
from rebuild_set05 import contours, dilate, erode
from repair_v1_1 import IDENTITY, NS, read_parts, thumbnail
from standardize_loop_diameters import bounds, digest, mesh_stats, package, write_mesh

ROOT = Path(__file__).resolve().parents[1]
SET = ROOT/'sets/Set_07_Archazias_Island'
VERSION = 'v1.6'
NAME = SET.name+'_'+VERSION
SOURCE = SET/'v1.5'/(SET.name+'_v1.5.3mf')
DEST = SET/VERSION
PROJECT = DEST/(NAME+'.3mf')
VECTOR = Path(__file__).with_name('set07_clean_artwork.svg')
ARTWORK = ROOT/'collection/v1.0/Sources/lorcana-keychains/sources/07.png'
PROD = 'http://schemas.microsoft.com/3dmanufacturing/production/2015/06'
TAG = lambda name: '{'+NS['m']+'}'+name
SVG = {'s': 'http://www.w3.org/2000/svg'}
STEP, ORIGIN = .025, (-1., 44.)
SIZE = (math.ceil(84/STEP), math.ceil(46/STEP))
GREEN = '#639653'
ET.register_namespace('', NS['m'])
ET.register_namespace('p', PROD)


def registered(point):
    # Original alpha crop (101,23,547,278); 40/255 mm per source pixel.
    # Match the native shifted silhouette, not the distorted legacy letters.
    x, y = point
    return (-5.606862745098039+40/255*x, 43.937254901960785-40/255*y)


def pixel(point):
    return ((point[0]-ORIGIN[0])/STEP, (ORIGIN[1]-point[1])/STEP)


def sample(path, closed=True):
    tokens = re.findall(r'[A-Za-z]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?', path)
    loops, points, cursor = [], [], (0., 0.)

    def curve(controls):
        a, b = controls[0], controls[-1]
        dx, dy = b[0]-a[0], b[1]-a[1]
        length = math.hypot(dx, dy)
        deviation = max(abs(dx*(p[1]-a[1])-dy*(p[0]-a[0]))/length
                        if length else math.dist(a, p) for p in controls[1:-1])
        if deviation <= .05 and length <= 3:
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
    if not closed:
        assert not loops
        return [registered(p) for p in points]
    assert not points
    return orient(loops)


def artwork():
    root = ET.parse(VECTOR).getroot()
    return {group: {p.get('id'): sample(p.get('d'), group != 'veins')
                    for p in root.findall(f"s:g[@id='{group}']/s:path", SVG)}
            for group in ('frame', 'owl', 'engraving', 'eyes', 'veins', 'letters')}


def mask(loops):
    image = Image.new('L', SIZE)
    draw = ImageDraw.Draw(image)
    for loop in sorted(orient(loops), key=lambda c: abs(area(c)), reverse=True):
        draw.polygon([pixel(p) for p in loop], fill=255 if area(loop) > 0 else 0)
    return np.asarray(image) > 0


def mask_contours(value):
    return orient(contours(value, STEP, ORIGIN))


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


def geometry(old):
    art = artwork()
    frame = mask(art['frame']['feathered_frame'])
    head = mask(art['owl']['owl_head'])
    engraving = mask(art['engraving']['owl_brow_and_beak'])
    gold_mask = (frame | head) & ~engraving
    green_mask = erode(frame, .30, STEP) & ~dilate(head, .15, STEP)
    vein_image = Image.new('L', SIZE)
    draw = ImageDraw.Draw(vein_image)
    for points in art['veins'].values():
        draw.line([pixel(p) for p in points], fill=255, width=round(.35/STEP), joint='curve')
    green_mask &= np.asarray(vein_image) == 0
    sockets = [dilate(mask(loops), .23, STEP) & erode(gold_mask, .05, STEP) for loops in art['eyes'].values()]
    for socket in sockets:
        assert not np.any(socket & ~gold_mask), 'owl eye socket leaves the face'
    gold = relief([mask_contours(gold_mask)], 2., .6, old[1])
    gold['name'] = 'Caramel — feathered frame and sculpted owl face'
    ivory = merge([relief(list(art['letters'].values()), 2., 1., old[2]),
                   relief(list(art['eyes'].values()), 2.8, .2, old[2])])
    ivory['name'] = 'Ivory White — smooth lettering and owl eyes'
    green = relief([mask_contours(green_mask)]+[mask_contours(s) for s in sockets],
                   2.6, .2, dict(old[0], name='Mistletoe Green — feathered frame and eye sockets',
                                color=GREEN, slot=4))
    return [old[0], gold, ivory, green]


def add_filament(settings):
    """Clone the existing matte PLA profile into slot 4; retain slots 1–3.

    Lists of three are filament-specific in this native A1 project. Flush
    vectors/matrices use separate dimensions and are handled explicitly.
    """
    for key, value in list(settings.items()):
        if isinstance(value, list) and len(value) == 3:
            settings[key] = value+[copy.deepcopy(value[0])]
    settings['filament_colour'][3] = GREEN
    settings['filament_multi_colour'][3] = GREEN
    settings['filament_self_index'][3] = '4'
    for key in ('inherits_group', 'different_settings_to_system'):
        settings[key].append(settings[key][-1])
    settings['flush_volumes_vector'] += ['140', '140']
    previous = settings['flush_volumes_matrix']
    settings['flush_volumes_matrix'] = [previous[i*3+j] if i < 3 and j < 3 else
                                       '0' if i == j else '503' for i in range(4) for j in range(4)]


def preview(parts, output, width=2000):
    image = Image.open(io.BytesIO(thumbnail(parts, width)))
    bb = bounds(parts[0])
    height = math.ceil(width*(.88*(bb[1][1]-bb[1][0])/(bb[0][1]-bb[0][0])+.12))
    image.crop((0, (width-height)//2, width, (width+height)//2)).save(output)


def main():
    data = package(SOURCE)
    old = read_parts(data)
    parts = geometry(old)
    root = ET.fromstring(data['3D/3dmodel.model'])
    config = ET.fromstring(data['Metadata/model_settings.config'])
    obj = config.find('object')
    assembly = root.find(f"m:resources/m:object[@id='{obj.get('id')}']", NS)
    components = assembly.find('m:components', NS)
    resources = {}
    # Add a fourth child resource while retaining the original assembly ID.
    new_component = copy.deepcopy(components[-1])
    resource_path = new_component.get('{'+PROD+'}path').lstrip('/')
    resource = ET.fromstring(data[resource_path])
    resources[resource_path] = resource
    objects = resource.find('m:resources', NS)
    new_id = str(max([int(o.get('id')) for o in objects]+
                     [int(o.get('id')) for o in root.findall('m:resources/m:object', NS)])+1)
    new_object = copy.deepcopy(objects[-1])
    new_object.set('id', new_id)
    new_object.set('{'+PROD+'}UUID', str(uuid.uuid5(uuid.NAMESPACE_URL, NAME+'/green-mesh')))
    objects.append(new_object)
    new_component.set('objectid', new_id)
    new_component.set('{'+PROD+'}UUID', str(uuid.uuid5(uuid.NAMESPACE_URL, NAME+'/green-component')))
    components.append(new_component)
    cfg = copy.deepcopy(obj.findall('part')[-1])
    cfg.set('id', new_id)
    cfg.set('uuid', str(uuid.uuid5(uuid.NAMESPACE_URL, NAME+'/green-part')))
    obj.append(cfg)
    for i in (1, 2, 3):
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
        cfg.find("metadata[@key='extruder']").set('value', str(parts[i]['slot']))
        cfg.find('mesh_stat').set('face_count', str(len(parts[i]['faces'])))
    settings = json.loads(data['Metadata/project_settings.config'])
    add_filament(settings)
    data['Metadata/project_settings.config'] = json.dumps(settings, indent=4).encode()
    obj.find("metadata[@key='name']").set('value', NAME)
    obj.find('metadata[@face_count]').set('face_count', str(sum(len(p['faces']) for p in parts)))
    root.find("m:metadata[@name='Description']", NS).text = (
        'v1.6; source-registered smooth lettering, feathered light-green frame with caramel trim; '
        'owl head with engraved brow/beak and shaped ivory eyes in green sockets; '
        'native 2 mm backing/loop and 6.5 mm bore retained; four matte PLA slots; '
        'caramel top 2.6 mm, green top 2.8 mm, ivory top 3.0 mm; native A1 0.4 mm Arachne profile.')
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
    assert loaded[0] == old[0], 'native backing and loop must remain exact'
    preview(loaded, DEST/(NAME+'_preview.png'))
    print(json.dumps(dict(project=str(PROJECT.relative_to(ROOT)), sha256=digest(PROJECT),
                          source_sha256=digest(SOURCE), vector_sha256=digest(VECTOR),
                          parts=[dict(name=p['name'], slot=p['slot'], **mesh_stats(p)) for p in loaded]), indent=2))


if __name__ == '__main__':
    main()
