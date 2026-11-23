#!/usr/bin/env python3
"""Build Hyperia City v1.7 with blue upper edges on ivory over Cocoa Brown."""

import argparse
import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import LineString

import rebuild_set14 as previous
from full_height_narrow_rims import isometric
from rebuild_set07 import registered, relief, sample
from rebuild_set09 import preview
from rebuild_set13 import contours
from refine_loops_and_underline import write_project
from repair_v1_1 import NS, read_parts
from standardize_loop_diameters import bounds, package
from validate_set12 import outlines

ROOT, SET = previous.ROOT, previous.SET
VERSION = 'v1.7'
NAME = SET.name + '_' + VERSION
DEST = SET / VERSION
SOURCE = previous.DEST / (previous.NAME + '.3mf')
VECTOR = DEST / 'Sources/set14_blue_highlights.svg'
BACKING_TOP, IVORY_TOP, BLUE_TOP = 2., 2.8, 3.
BLUE_WIDTH = .66
SLOTS = (0, 2, 3)
MODEL, PARTS, CONFIG, SETTINGS = previous.MODEL, previous.PARTS, previous.CONFIG, previous.SETTINGS


def highlights(letters):
    x0, y0 = registered((0., 0.))
    sx = previous.SCALE / (registered((1., 0.))[0] - x0)
    sy = -previous.SCALE / (registered((0., 1.))[1] - y0)
    paths = ET.parse(VECTOR).getroot().findall('s:g/s:path', previous.SVG)
    bands = {}
    for path in paths:
        points = sample(path.get('d'), closed=False)
        edge = LineString([(previous.X_ORIGIN + (x - x0) * sx,
                            previous.Y_ORIGIN + (y - y0) * sy) for x, y in points])
        letter = letters[path.get('data-letter')]
        band = letter.intersection(edge.buffer(BLUE_WIDTH, quad_segs=16))
        assert band.geom_type == 'Polygon' and band.is_valid and not band.interiors, path.get('id')
        bands[path.get('id')] = band
    return bands


def geometry(old, letters, blue):
    return [
        old[0],
        relief([contours(p) for p in letters.values()], BACKING_TOP, IVORY_TOP - BACKING_TOP,
               dict(old[2], slot=2)),
        relief([contours(p) for p in blue.values()], IVORY_TOP, BLUE_TOP - IVORY_TOP,
               dict(old[3], slot=3)),
    ]


def filament_settings(settings):
    # Four-value printer coordinates are independent of filament slots.
    printer_fields = {'head_wrap_detect_zone', 'printable_area'}
    reduced = {key: [value[i] for i in SLOTS]
               if isinstance(value, list) and len(value) == 4 and key not in printer_fields else value
               for key, value in settings.items()}
    reduced['filament_self_index'] = ['1', '2', '3']
    for key in ('inherits_group', 'different_settings_to_system'):
        reduced[key] = [settings[key][i] for i in (0, 1, 2, 4, 5)]
    reduced['flush_volumes_matrix'] = [settings['flush_volumes_matrix'][4 * i + j]
                                       for i in SLOTS for j in SLOTS]
    reduced['flush_volumes_vector'] = [settings['flush_volumes_vector'][2 * i + j]
                                       for i in SLOTS for j in (0, 1)]
    return reduced


def three_filament_template(data, target):
    root = ET.fromstring(data[MODEL])
    root.find("m:metadata[@name='ModificationDate']", NS).text = '2026-11-22'
    components = root.find('m:resources/m:object/m:components', NS)
    components.remove(components.find("m:component[@objectid='2']", NS))
    meshes = ET.fromstring(data[PARTS])
    resources = meshes.find('m:resources', NS)
    resources.remove(resources.find("m:object[@id='2']", NS))
    config = ET.fromstring(data[CONFIG])
    obj = config.find('object')
    obj.remove(obj.find("part[@id='2']"))
    for part, slot in zip(obj.findall('part'), (1, 2, 3)):
        part.find("metadata[@key='extruder']").set('value', str(slot))
    for filename, tree in ((MODEL, root), (PARTS, meshes), (CONFIG, config)):
        data[filename] = ET.tostring(tree, encoding='utf-8', xml_declaration=True)
    settings = filament_settings(json.loads(data[SETTINGS]))
    data[SETTINGS] = json.dumps(settings, indent=2).encode()
    with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
        for filename, raw in data.items():
            archive.writestr(filename, raw)


def comparison(old, new, target):
    frame = bounds(old[0])
    font_path = next(Path('/usr/share/fonts').rglob('DejaVuSans.ttf'), None)
    font = ImageFont.truetype(str(font_path), 25) if font_path else ImageFont.load_default(size=25)
    with tempfile.TemporaryDirectory() as directory:
        panel = Path(directory) / 'panel.png'
        canvas = None
        for i, (parts, label) in enumerate(((old, 'v1.6 · Caramel padding and full blue outline'),
                                             (new, 'v1.7 · Cocoa Brown padding and blue upper edges'))):
            preview(parts, panel, width=1500, frame=frame)
            with Image.open(panel) as im:
                if canvas is None:
                    canvas = Image.new('RGB', (im.width, 2 * (im.height + 54)), '#f5f5f5')
                y = i * (im.height + 54)
                canvas.paste(im, (0, y + 54))
                ImageDraw.Draw(canvas).text((32, y + 15), label, font=font, fill='#633A22')
    canvas.save(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=DEST)
    dest = parser.parse_args().output_dir.resolve()
    project = dest / (NAME + '.3mf')
    if project.exists():
        raise FileExistsError(project)
    data = package(SOURCE)
    old = read_parts(data)
    letters = previous.artwork()
    parts = geometry(old, letters, highlights(letters))
    with tempfile.TemporaryDirectory() as directory:
        template = Path(directory) / 'template.3mf'
        three_filament_template(data, template)
        write_project(template, project, parts, {1, 2},
                      'v1.7; Ivory White lettering directly on Cocoa Brown, with Ice Blue '
                      'along the upper edges. 6.5 mm bore, 2 mm backing and 3 mm overall.')
    saved = read_parts(package(project))
    isometric(saved, dest / (NAME + '_isometric.png'))
    comparison(old, saved, dest / (NAME + '_comparison.png'))
    previous.source_overlay(outlines(saved[2]), dest / (NAME + '_source_overlay.png'))


if __name__ == '__main__':
    main()
