#!/usr/bin/env python3
"""Build Hyperia City v07 from its editable, source-registered lettering."""

import argparse
import copy
import json
import tempfile
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image, ImageDraw, ImageFont
from shapely.affinity import translate
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from full_height_narrow_rims import isometric
from rebuild_set07 import registered, relief, sample
from rebuild_set09 import preview
from rebuild_set13 import bore_loop, contours
from refine_loops_and_underline import write_project
from repair_v02 import NS, read_parts
from standardize_loop_diameters import bounds, centre, digest, package
from validate_set12 import outlines

ROOT = Path(__file__).resolve().parents[1]
SET = ROOT / 'sets/Set_14_Hyperia_City'
VERSION = 'v07'
NAME = SET.name + '_' + VERSION
DEST = SET / VERSION
SOURCE = SET / 'v06' / (SET.name + '_v06.3mf')
VECTOR = DEST / 'Sources/set14_clean_artwork.svg'
ARTWORK = ROOT / 'collection/v01/Sources/lorcana-keychains/sources/14.png'
MODEL = '3D/3dmodel.model'
PARTS = '3D/Objects/object_1.model'
CONFIG = 'Metadata/model_settings.config'
SETTINGS = 'Metadata/project_settings.config'
PROD = '{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}'
SVG = {'s': 'http://www.w3.org/2000/svg'}
ICE_BLUE = '#9BC8DE'
SCALE = 40 / 247
X_ORIGIN, Y_ORIGIN = -11.78, 44.35
BLUE_WIDTH = .58
COUNTER_BLUE_WIDTH = .45
BACKING_TOP, CARAMEL_TOP, BLUE_TOP, IVORY_TOP = 2., 2.4, 2.6, 3.


def artwork():
    # The shared SVG sampler outputs Set 07 coordinates. Invert that
    # registration and apply the scale and translation for the Set 14 source.
    rx, ry = registered((0., 0.))
    rx1 = registered((1., 0.))[0]
    ry1 = registered((0., 1.))[1]
    glyphs = {}
    for path in ET.parse(VECTOR).getroot().findall('s:g/s:path', SVG):
        rings = [[(X_ORIGIN + SCALE * (x - rx) / (rx1 - rx),
                   Y_ORIGIN - SCALE * (y - ry) / (ry1 - ry)) for x, y in loop]
                 for loop in sample(path.get('d'))]
        glyph = Polygon(rings[0], rings[1:])
        assert glyph.is_valid, path.get('id')
        glyphs[path.get('id')] = glyph
    return glyphs


def close_valleys(shape, radius):
    return shape.union(shape.buffer(radius, quad_segs=12).buffer(-radius, quad_segs=12))


def polygons(shape):
    return [shape] if shape.geom_type == 'Polygon' else list(shape.geoms)


def geometry(old, glyphs):
    letters = unary_union(list(glyphs.values()))
    letter_shells = unary_union([Polygon(p.exterior) for p in glyphs.values()])
    blue = close_valleys(letter_shells.buffer(BLUE_WIDTH, quad_segs=16), .25)
    # Fill pinholes between adjacent outlines. Use a narrower blue band
    # inside the counters so the caramel floor reads through each opening.
    blue = unary_union([Polygon(p.exterior, [r for r in p.interiors if Polygon(r).area > .7])
                        for p in polygons(blue)])
    counter_windows = [Polygon(r).buffer(-COUNTER_BLUE_WIDTH, quad_segs=16)
                       for p in glyphs.values() for r in p.interiors]
    assert all(not window.is_empty for window in counter_windows)
    blue = blue.difference(unary_union(counter_windows)).simplify(.009)
    caramel = close_valleys(blue.buffer(.87, quad_segs=16), 1.05).simplify(.012)
    caramel = unary_union([Polygon(p.exterior, [r for r in p.interiors if Polygon(r).area > 8])
                           for p in polygons(caramel)])
    assert caramel.geom_type == 'Polygon' and caramel.covers(blue)
    assert blue.covers(letters)

    # The broad lower skirt echoes the dimensional lettering in the artwork.
    skirt = caramel.buffer(.52, quad_segs=18)
    skirt = close_valleys(unary_union([skirt, translate(skirt, -.72, -1.34)]), 1.45)
    bore = bore_loop(old[0])
    cx, cy = centre(bore)
    eyelet = Point(round(cx, 6), cy).buffer(5.25, quad_segs=48)
    neck = box(cx, cy - 3.5, 22.8, cy + 3.5)
    outline = close_valleys(unary_union([Polygon(skirt.exterior), eyelet, neck]), .65)
    outline = outline.simplify(.012)
    assert outline.geom_type == 'Polygon' and not outline.interiors
    backing = Polygon(outline.exterior, [bore])
    assert backing.is_valid and backing.covers(caramel)
    return [
        relief([contours(backing)], 0., BACKING_TOP, old[0]),
        relief([contours(caramel)], BACKING_TOP, CARAMEL_TOP - BACKING_TOP, old[1]),
        relief([contours(p) for p in glyphs.values()], BLUE_TOP, IVORY_TOP - BLUE_TOP, old[2]),
        relief([contours(p) for p in polygons(blue)], CARAMEL_TOP, BLUE_TOP - CARAMEL_TOP,
               dict(old[2], name='Ice Blue', color=ICE_BLUE, slot=4)),
    ]


def filament_settings(settings):
    # Retain the three existing slots and append the Ivory Matte PLA preset
    # for the historical Ice Blue colour.
    for key, value in settings.items():
        if isinstance(value, list) and len(value) == 3 and key != 'compatible_printers':
            value.append(copy.deepcopy(value[2]))
    settings['filament_colour'][-1] = ICE_BLUE
    settings['filament_multi_colour'][-1] = ICE_BLUE
    settings['filament_self_index'][-1] = '4'
    for key in ('inherits_group', 'different_settings_to_system'):
        settings[key].append(settings[key][-1])
    settings['flush_volumes_vector'] += ['140', '140']
    old = settings['flush_volumes_matrix']
    settings['flush_volumes_matrix'] = [old[i * 3 + j] if i < 3 and j < 3
                                        else '0' if i == j else '503'
                                        for i in range(4) for j in range(4)]
    return settings


def four_filament_template(data, target):
    root = ET.fromstring(data[MODEL])
    root.find("m:metadata[@name='ModificationDate']", NS).text = '2026-11-22'
    components = root.find('m:resources/m:object/m:components', NS)
    meshes = ET.fromstring(data[PARTS])
    resources = meshes.find('m:resources', NS)
    config = ET.fromstring(data[CONFIG])
    obj = config.find('object')
    new_id = str(max(int(obj.get('id')), *(int(p.get('id')) for p in obj.findall('part'))) + 1)

    component = copy.deepcopy(components[-1])
    component.set('objectid', new_id)
    component.set(PROD + 'UUID', str(uuid.uuid5(uuid.NAMESPACE_URL, NAME + '/blue-component')))
    components.append(component)
    mesh = copy.deepcopy(resources[-1])
    mesh.set('id', new_id)
    mesh.set(PROD + 'UUID', str(uuid.uuid5(uuid.NAMESPACE_URL, NAME + '/blue-mesh')))
    resources.append(mesh)
    part = copy.deepcopy(obj.findall('part')[-1])
    part.set('id', new_id)
    part.set('uuid', str(uuid.uuid5(uuid.NAMESPACE_URL, NAME + '/blue-part')))
    part.find("metadata[@key='name']").set('value', 'Ice Blue')
    part.find("metadata[@key='extruder']").set('value', '4')
    obj.append(part)

    for filename, tree in ((MODEL, root), (PARTS, meshes), (CONFIG, config)):
        data[filename] = ET.tostring(tree, encoding='utf-8', xml_declaration=True)
    settings = filament_settings(json.loads(data[SETTINGS]))
    data[SETTINGS] = json.dumps(settings, indent=2).encode()
    with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
        for filename, raw in data.items():
            archive.writestr(filename, raw)


def comparison(old, new, target):
    frame = [(min(a[0], b[0]), max(a[1], b[1]))
             for a, b in zip(bounds(old[0]), bounds(new[0]))]
    font_path = next(Path('/usr/share/fonts').rglob('DejaVuSans.ttf'), None)
    font = ImageFont.truetype(str(font_path), 25) if font_path else ImageFont.load_default(size=25)
    with tempfile.TemporaryDirectory() as temp:
        panel = Path(temp) / 'panel.png'
        canvas = None
        for i, (parts, label) in enumerate(((old, 'v06 · Raster trace'),
                                             (new, 'v07 · Redrawn lettering and Ice Blue trim'))):
            preview(parts, panel, width=1500, frame=frame)
            with Image.open(panel) as im:
                if canvas is None:
                    canvas = Image.new('RGB', (im.width, 2 * (im.height + 54)), '#f5f5f5')
                y = i * (im.height + 54)
                canvas.paste(im, (0, y + 54))
                ImageDraw.Draw(canvas).text((32, y + 15), label, font=font, fill='#633A22')
    canvas.save(target)


def source_overlay(lettering, target):
    crop = (135, 26, 516, 268)
    factor = 4
    with Image.open(ARTWORK) as source:
        image = Image.new('RGBA', source.size, '#e1e1e1')
        image.alpha_composite(source)
    image = image.convert('RGB').crop(crop)
    image = image.resize((image.width * factor, image.height * factor), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(image)
    for shape in lettering:
        for ring in (shape.exterior, *shape.interiors):
            draw.line([(((x - X_ORIGIN) / SCALE - crop[0]) * factor,
                        ((Y_ORIGIN - y) / SCALE - crop[1]) * factor) for x, y in ring.coords],
                      fill='#EA2796', width=2)
    image.save(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=DEST)
    dest = parser.parse_args().output_dir.resolve()
    project = dest / (NAME + '.3mf')
    if project.exists():
        raise FileExistsError(project)
    data = package(SOURCE)
    old = read_parts(data)
    parts = geometry(old, artwork())
    with tempfile.TemporaryDirectory() as temp:
        template = Path(temp) / 'template.3mf'
        four_filament_template(data, template)
        write_project(template, project, parts, set(range(4)),
                      'v07; redrawn Hyperia City lettering in Ivory White and Ice Blue, '
                      'Caramel relief on Cocoa Brown; 6.5 mm bore, 2 mm backing and 3 mm overall.')
    saved = read_parts(package(project))
    isometric(saved, dest / (NAME + '_isometric.png'))
    comparison(old, saved, dest / (NAME + '_comparison.png'))
    source_overlay(outlines(saved[2]), dest / (NAME + '_source_overlay.png'))


if __name__ == '__main__':
    main()
