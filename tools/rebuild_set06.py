#!/usr/bin/env python3
"""Rebuild Azurite Sea's relief from clean source-registered vector contours.

Keep the native backing, eyelet, placement, colours and A1 0.4 mm profiles.
v07 refines the artwork; v08 thickens only the blue wave bodies.
Requires NumPy, Pillow and the system Cairo/GLU libraries. No STL export.
"""
from pathlib import Path
import argparse
import io
import json
import math
import re
import xml.etree.ElementTree as ET
import zipfile

from PIL import Image

from rebuild_set04 import area, extrude, orient
from repair_v02 import IDENTITY, NS, read_parts, thumbnail
from standardize_loop_diameters import bounds, digest, mesh_stats, package, write_mesh

ROOT = Path(__file__).resolve().parents[1]
SET = ROOT / 'sets/Set_06_Azurite_Sea'
VERSION = 'v08'
SOURCE = SET / 'v07/Set_06_Azurite_Sea_v07.3mf'
DEST = SET / VERSION
NAME = f'Set_06_Azurite_Sea_{VERSION}'
PROJECT = DEST / (NAME + '.3mf')
VECTOR = Path(__file__).with_name('set06_clean_artwork.svg')
WAVE_VECTOR = Path(__file__).with_name('set06_thicker_waves.svg')
ARTWORK = ROOT / 'collection/v01/Sources/lorcana-keychains/sources/06.png'
SVG = {'s': 'http://www.w3.org/2000/svg'}
PROD = 'http://schemas.microsoft.com/3dmanufacturing/production/2015/06'
TAG = lambda name: '{' + NS['m'] + '}' + name
ET.register_namespace('', NS['m'])
ET.register_namespace('p', PROD)


def configure(version):
    global VERSION, SOURCE, DEST, NAME, PROJECT
    VERSION = version
    previous = 'v06' if version == 'v07' else 'v07'
    SOURCE = SET / previous / f'Set_06_Azurite_Sea_{previous}.3mf'
    DEST = SET / VERSION
    NAME = f'Set_06_Azurite_Sea_{VERSION}'
    PROJECT = DEST / (NAME + '.3mf')


def registered(point):
    # The archived artwork crops to (0, 2, 850, 502), at 0.08 mm/pixel.
    # Native silhouette/eyelet offsets translate its x by 10.55 mm and its
    # inverted original-image y by 40.88 mm. No fitting to the distorted text.
    x, y = point
    return (10.55 + .08*x, 40.88 - .08*y)


def sample_path(path):
    """Sample explicit M/L/C/Q/Z paths to <0.008 mm curve chord error."""
    tokens = re.findall(r'[A-Za-z]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?', path)
    loops, points, cursor = [], [], (0., 0.)

    def curve(controls):
        a, b = controls[0], controls[-1]
        dx, dy = b[0]-a[0], b[1]-a[1]
        length = math.hypot(dx, dy)
        deviation = max((abs(dx*(p[1]-a[1])-dy*(p[0]-a[0])) / length
                         if length else math.dist(a, p)) for p in controls[1:-1])
        if deviation <= .1 and length <= 5:
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
            controls = [cursor]+[tuple(values[j:j+2]) for j in range(0, count, 2)]
            curve(controls)
            cursor = controls[-1]
        else:
            if math.dist(points[0], points[-1]) < 1e-8:
                points.pop()
            loops.append([registered(p) for p in points])
            points = []
    assert not points
    return orient(loops)


def artwork():
    root = ET.parse(VECTOR).getroot()
    art = {group: {p.get('id'): sample_path(p.get('d'))
                   for p in root.findall(f"s:g[@id='{group}']/s:path", SVG)}
           for group in ('gold', 'ice')}
    if VERSION == 'v08':
        waves = ET.parse(WAVE_VECTOR).getroot()
        art['ice'] = {p.get('id'): sample_path(p.get('d'))
                      for p in waves.findall("s:g[@id='ice']/s:path", SVG)}
    return art


def preview(parts, output):
    image = Image.open(io.BytesIO(thumbnail(parts, 2000)))
    box = bounds(parts[0])
    height = math.ceil(2000*(.88*(box[1][1]-box[1][0])/(box[0][1]-box[0][0])+.12))
    image.crop((0, (2000-height)//2, 2000, (2000+height)//2)).save(output)


def relief(shapes, height, template):
    """Tessellate independent shapes without altering their native contours.

    A rotated tessellation frame avoids GLU degeneracies at aligned serif
    corners. The final mesh always uses the exact original vector points.
    """
    vertices, faces = [], []
    for loops in shapes.values():
        flat = [p for loop in loops for p in loop]
        for angle in (0, 17, 31, 47):
            co, si = math.cos(math.radians(angle)), math.sin(math.radians(angle))
            rotated = [[(x*co-y*si, x*si+y*co) for x, y in c] for c in loops]
            try:
                part = extrude(rotated, 2., height, template)
            except AssertionError:
                continue
            part['vertices'] = [(*flat[i % len(flat)], v[2])
                                for i, v in enumerate(part['vertices'])]
            if mesh_stats(part)['degenerate_triangles'] == 0:
                break
        else:
            raise AssertionError('Unable to tessellate artwork without degeneracies')
        faces.extend(tuple(i+len(vertices) for i in f) for f in part['faces'])
        vertices.extend(part['vertices'])
    return dict(template, vertices=vertices, faces=faces)


def main():
    data = package(SOURCE)
    original = read_parts(data)
    art = artwork()
    parts = [original[0], relief(art['ice'], .4, original[1]),
             original[2] if VERSION == 'v08' else relief(art['gold'], .8, original[2])]

    root = ET.fromstring(data['3D/3dmodel.model'])
    config = ET.fromstring(data['Metadata/model_settings.config'])
    obj = config.find('object')
    assembly = root.find(f"m:resources/m:object[@id='{obj.get('id')}']", NS)
    resources = {}
    for index in ((1,) if VERSION == 'v08' else (1, 2)):
        component = assembly.find('m:components', NS)[index]
        oid = component.get('objectid')
        path = component.get('{'+PROD+'}path').lstrip('/')
        if path not in resources:
            resources[path] = ET.fromstring(data[path])
        write_mesh(resources[path].find(f"m:resources/m:object[@id='{oid}']", NS), parts[index])
        component.set('transform', ' '.join(map(str, IDENTITY)))
        cfg = obj.find(f"part[@id='{oid}']")
        for md in list(cfg.findall('metadata')):
            if md.get('key', '').startswith('source_'):
                cfg.remove(md)
        cfg.find("metadata[@key='name']").set('value',
            ('Ice Blue — fuller swept wave accents' if VERSION == 'v08' else
             'Ice Blue — two swept wave accents') if index == 1 else
            'Sunflower Yellow — clean Azurite Sea letters')
        cfg.find("metadata[@key='matrix']").set('value', '1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1')
        stat = cfg.find('mesh_stat')
        stat.set('face_count', str(len(parts[index]['faces'])))
        for key in ('edges_fixed', 'degenerate_facets', 'facets_removed', 'facets_reversed', 'backwards_edges'):
            if key in stat.attrib:
                stat.set(key, '0')
    obj.find("metadata[@key='name']").set('value', f'Azurite Sea {VERSION}')
    obj.find('metadata[@face_count]').set('face_count', str(sum(len(p['faces']) for p in parts)))
    root.find("m:metadata[@name='Description']", NS).text = (
        f'{VERSION}; source-traced smooth lettering with ten independent letters, elongated '
        'A counter, triangular SEA counter and open R bowl; no texture holes or '
        'letter bridges; two swept foam ribbons, no upper ice-blue fleck; '
        + ('fuller wave bodies beneath the preserved v07 crests; original v07 gold mesh; '
           if VERSION == 'v08' else '') + 'unchanged '
        '2 mm backing/loop, 6.5 mm bore, 2 mm nominal radial rim; 0.4 mm ice relief, '
        '0.8 mm gold relief; original A1 0.4 mm nozzle / 0.20 mm Arachne profiles.')
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
    assert loaded[0] == original[0], 'native backing must remain exact'
    if VERSION == 'v08':
        assert loaded[2] == original[2], 'v07 lettering must remain exact'
    assert package(PROJECT)['Metadata/project_settings.config'] == data['Metadata/project_settings.config']
    preview(loaded, DEST/(NAME+'_preview.png'))
    print(json.dumps(dict(project=str(PROJECT.relative_to(ROOT)), sha256=digest(PROJECT),
                          source_sha256=digest(SOURCE), vector_sha256=digest(VECTOR),
                          wave_vector_sha256=digest(WAVE_VECTOR) if VERSION == 'v08' else None,
                          shapes={g: list(shapes) for g, shapes in art.items()},
                          areas_mm2={g: sum(area(c) for loops in shapes.values() for c in loops)
                                     for g, shapes in art.items()}), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', choices=['v07', 'v08'], default='v08')
    configure(parser.parse_args().version)
    main()
