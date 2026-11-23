#!/usr/bin/env python3
"""Build Attack of the Vine v07 from the source-registered SVG."""

import argparse
import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image, ImageDraw, ImageFont
from shapely.affinity import affine_transform
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from full_height_narrow_rims import bore_index, isometric
from rebuild_set04 import boundary_loops, orient
from rebuild_set07 import registered, relief, sample
from rebuild_set09 import SOURCE as PREVIEW_TEMPLATE, preview
from refine_loops_and_underline import write_project
from repair_v02 import NS, read_parts
from standardize_loop_diameters import bounds, centre, digest, package

ROOT = Path(__file__).resolve().parents[1]
SET = ROOT / 'sets/Set_13_Attack_of_the_Vine'
VERSION = 'v07'
RELEASE_DATE = '2026-11-22'
NAME = SET.name + '_' + VERSION
DEST = SET / (VERSION + '_approved')
SOURCE = SET / 'v06' / (SET.name + '_v06.3mf')
VECTOR = DEST / 'Sources/set13_clean_artwork.svg'
ARTWORK = ROOT / 'collection/v01/Sources/lorcana-keychains/sources/13.png'
SVG = {'s': 'http://www.w3.org/2000/svg'}
SETTINGS = 'Metadata/project_settings.config'
MODEL = '3D/3dmodel.model'
PARTS = '3D/Objects/object_1.model'
CONFIG = 'Metadata/model_settings.config'
LIME = '#B4D83D'
SCALE = .138
X_ORIGIN = -5.85
Y_ORIGIN = 41.19
BORDER = 1.12
BACKING_HEIGHT = 2.
TOP = 2.8
LIME_LINE_WIDTH = .34
LIME_WIDTH_SETTINGS = (
    'outer_wall_line_width', 'inner_wall_line_width',
    'top_surface_line_width', 'internal_solid_infill_line_width',
)


def artwork():
    # Convert the shared sampler's output back to source-image coordinates,
    # then register the artwork at the original keychain scale.
    x0, y0 = registered((0., 0.))
    sx = SCALE / (registered((1., 0.))[0] - x0)
    sy = -SCALE / (registered((0., 1.))[1] - y0)
    transform = (sx, 0., 0., sy, X_ORIGIN - sx * x0, Y_ORIGIN - sy * y0)
    paths = ET.parse(VECTOR).getroot().findall('s:g/s:path', SVG)
    shapes = {}
    for path in paths:
        outer, *holes = sample(path.attrib['d'])
        shape = affine_transform(Polygon(outer, holes), transform)
        assert shape.is_valid, path.attrib['id']
        shapes[path.attrib['id']] = shape
    shapes['attack-a1'] = shapes['attack-a1'].union(shapes.pop('tendril'))
    return shapes


def contours(shape):
    return orient([list(ring.coords)[:-1] for ring in (shape.exterior, *shape.interiors)])


def bore_loop(part):
    loops = boundary_loops(part)
    return loops[bore_index(loops, 6.5)]


def geometry(old, glyphs):
    artwork_area = unary_union(list(glyphs.values()))
    skirt = artwork_area.buffer(BORDER, quad_segs=18)
    # Close internal voids and soften the exterior valleys between letters.
    joined = skirt.buffer(1.8, quad_segs=18).buffer(-1.8, quad_segs=18)
    body = skirt.union(joined)
    assert body.geom_type == 'Polygon'
    bore = bore_loop(old[0])
    cx, cy = centre(bore)
    eyelet = Point(round(cx, 6), cy).buffer(5.25, quad_segs=48)
    neck = box(cx, cy - 3.5, 16.1, cy + 3.5)
    outer = unary_union([Polygon(body.exterior), eyelet, neck])
    outer = outer.buffer(.32, quad_segs=12).buffer(-.32, quad_segs=12).simplify(.015)
    assert outer.geom_type == 'Polygon' and not outer.interiors
    base = Polygon(outer.exterior, [bore])
    assert base.is_valid and base.covers(artwork_area)
    purple, _, yellow = old
    return [
        relief([contours(base)], 0., BACKING_HEIGHT, purple),
        relief([contours(shape) for shape in glyphs.values()], BACKING_HEIGHT,
               TOP - BACKING_HEIGHT, dict(yellow, color=LIME, name='Lime Green · lettering and vine', slot=2)),
    ]


def filament_settings(settings):
    # Keep the purple and former yellow PLA profiles. Give the latter the
    # lime display colour and retain the pair's original flush settings.
    reduced = {key: [value[0], value[2]] if isinstance(value, list) and len(value) == 3 else value
               for key, value in settings.items()}
    reduced['filament_colour'][1] = LIME
    reduced['filament_multi_colour'][1] = LIME
    reduced['filament_self_index'] = ['1', '2']
    for key in ('inherits_group', 'different_settings_to_system'):
        reduced[key] = [settings[key][i] for i in (0, 1, 2, 4)]
    reduced['flush_volumes_matrix'] = [settings['flush_volumes_matrix'][i] for i in (0, 2, 6, 8)]
    reduced['flush_volumes_vector'] = [settings['flush_volumes_vector'][i] for i in (0, 1, 4, 5)]
    return reduced


def two_filament_template(data, parts, target):
    model = ET.fromstring(data[MODEL])
    model.find("m:metadata[@name='ModificationDate']", NS).text = RELEASE_DATE
    components = model.find('m:resources/m:object/m:components', NS)
    components.remove(components.find("m:component[@objectid='3']", NS))
    meshes = ET.fromstring(data[PARTS])
    resource = meshes.find('m:resources', NS)
    resource.remove(resource.find("m:object[@id='3']", NS))
    config = ET.fromstring(data[CONFIG])
    obj = config.find('object')
    obj.remove(obj.find("part[@id='3']"))
    lime = obj.find("part[@id='2']")
    lime.find("metadata[@key='name']").set('value', parts[1]['name'])
    for key in LIME_WIDTH_SETTINGS:
        ET.SubElement(lime, 'metadata', {'key': key, 'value': str(LIME_LINE_WIDTH)})
    for path, tree in ((MODEL, model), (PARTS, meshes), (CONFIG, config)):
        data[path] = ET.tostring(tree, encoding='utf-8', xml_declaration=True)
    data[SETTINGS] = json.dumps(filament_settings(json.loads(data[SETTINGS])), indent=2).encode()
    with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
        for name, raw in data.items():
            archive.writestr(name, raw)


def comparison(old, new, target):
    frame = [(min(a[0], b[0]), max(a[1], b[1]))
             for a, b in zip(bounds(old[0]), bounds(new[0]))]
    font_path = next(Path('/usr/share/fonts').rglob('DejaVuSans.ttf'), None)
    font = ImageFont.truetype(str(font_path), 26) if font_path else ImageFont.load_default(size=26)
    with tempfile.TemporaryDirectory() as temp:
        panel = Path(temp) / 'panel.png'
        canvas = None
        for i, (parts, title) in enumerate(((old, 'v06 · Raster trace and split colour'),
                                             (new, 'v07 · Redrawn contours and solid lime'))):
            preview(parts, panel, width=1500, frame=frame)
            with Image.open(panel) as im:
                if canvas is None:
                    canvas = Image.new('RGB', (im.width, 2 * (im.height + 54)), '#f5f5f5')
                y = i * (im.height + 54)
                canvas.paste(im, (0, y + 54))
                ImageDraw.Draw(canvas).text((32, y + 15), title, font=font, fill='#412960')
    canvas.save(target)


def source_overlay(glyphs, target):
    crop = (110, 8, 538, 295)
    factor = 3
    with Image.open(ARTWORK) as source:
        image = source.convert('RGB').crop(crop)
        image = image.resize((image.width * factor, image.height * factor), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(image)
    for shape in glyphs.values():
        for ring in (shape.exterior, *shape.interiors):
            draw.line([(((x - X_ORIGIN) / SCALE - crop[0]) * factor,
                        ((Y_ORIGIN - y) / SCALE - crop[1]) * factor) for x, y in ring.coords],
                      fill='#FA58A0', width=2)
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
    glyphs = artwork()
    parts = geometry(old, glyphs)
    with tempfile.TemporaryDirectory() as temp:
        template = Path(temp) / 'template.3mf'
        two_filament_template(data, parts, template)
        write_project(template, project, parts, {0, 1},
                      'v07; source-traced lettering and vine in solid lime on purple; '
                      '6.5 mm bore, 10.5 mm nominal eyelet, 2 mm backing and 2.8 mm overall height.')
    saved = read_parts(package(project))
    isometric(saved, dest / (NAME + '_isometric.png'))
    comparison(old, saved, dest / (NAME + '_comparison.png'))
    source_overlay(glyphs, dest / (NAME + '_source_overlay.png'))

    scripts = ('rebuild_set13', 'validate_set13', 'full_height_narrow_rims', 'rebuild_set04',
               'rebuild_set05', 'rebuild_set06', 'rebuild_set07', 'rebuild_set09',
               'rebuild_set12', 'refine_loops_and_underline', 'repair_v02',
               'standardize_loop_diameters', 'set_versions', 'validate_bambu', 'validate_set06',
               'validate_set09', 'validate_set12')
    inputs = [SOURCE, ARTWORK, VECTOR] + [ROOT / 'tools' / (name + '.py') for name in scripts]
    snapshot = dest / 'Source_snapshot.zip'
    with ZipFile(snapshot, 'w', ZIP_DEFLATED) as archive:
        for path in inputs[2:]:
            archive.write(path, path.relative_to(ROOT))
    manifest = dict(project=project.name, output_sha256=digest(project),
                    source_snapshot=snapshot.name, source_snapshot_sha256=digest(snapshot),
                    inputs_sha256={str(path.relative_to(ROOT)): digest(path)
                                   for path in [*inputs, PREVIEW_TEMPLATE]})
    (dest / 'Build_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
