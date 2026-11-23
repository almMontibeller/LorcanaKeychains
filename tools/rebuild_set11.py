#!/usr/bin/env python3
"""Build Winterspell v07 from the Set 11 source-registered SVG."""

import argparse
import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

import rebuild_set07 as curves
from full_height_narrow_rims import bore_index, isometric
from rebuild_set04 import boundary_loops, orient
from rebuild_set09 import preview
from refine_loops_and_underline import write_project
from repair_v02 import read_parts
from standardize_loop_diameters import bounds, centre, digest, package

ROOT = Path(__file__).resolve().parents[1]
SET = ROOT / 'sets/Set_11_Winterspell'
VERSION = 'v07'
NAME = SET.name + '_' + VERSION
SOURCE = SET / 'v06' / (SET.name + '_v06.3mf')
DEST = SET / VERSION
VECTOR = Path(__file__).with_name('set11_clean_artwork.svg')
ARTWORK = ROOT / 'collection/v01/Sources/lorcana-keychains/sources/11.png'
SOURCE_SCALE = .168
FIELD_MARGIN = .72
MARINE_RIM = .85
Z_LEVELS = (0., 2., 2.4, 3.)
SVG = {'s': 'http://www.w3.org/2000/svg'}
SOURCE_FILES = (
    'rebuild_set11.py', 'validate_set11.py', 'set11_clean_artwork.svg',
    'full_height_narrow_rims.py', 'rebuild_set04.py', 'rebuild_set05.py',
    'rebuild_set06.py', 'rebuild_set07.py', 'rebuild_set09.py',
    'refine_loops_and_underline.py', 'repair_v02.py', 'standardize_loop_diameters.py', 'set_versions.py',
    'validate_bambu.py', 'validate_set06.py', 'validate_set09.py',
)


def registered(point):
    x, y = point
    return 10.5 + (x - 77) * SOURCE_SCALE, 26.8 - (y - 68) * SOURCE_SCALE


def source_point(point):
    x, y = point
    return 77 + (x - 10.5) / SOURCE_SCALE, 68 + (26.8 - y) / SOURCE_SCALE


def artwork():
    root = ET.parse(VECTOR).getroot()
    previous = curves.registered
    curves.registered = registered
    try:
        polygons = {}
        for group in ('field', 'letters'):
            for path in root.findall(f"s:g[@id='{group}']/s:path", SVG):
                outer, *holes = curves.sample(path.attrib['d'])
                polygon = Polygon(outer, holes)
                assert polygon.is_valid, path.attrib['id']
                polygons[path.attrib['id']] = polygon
    finally:
        curves.registered = previous
    return polygons.pop('frost'), polygons


def loops(polygon):
    return orient([list(ring.coords)[:-1] for ring in (polygon.exterior, *polygon.interiors)])


def old_bore(part):
    contours = boundary_loops(part)
    return contours[bore_index(contours, 6.5)]


def geometry(old, field_draft, letters):
    support = unary_union(list(letters.values())).buffer(FIELD_MARGIN, quad_segs=12)
    # Blend the margins into the drawn skyline without inheriting raster texture.
    field = field_draft.union(support).buffer(.40).buffer(-.40).simplify(.022)
    assert field.geom_type == 'Polygon' and field.is_valid and not field.interiors
    bore = old_bore(old[0])
    cx, cy = centre(bore)
    eyelet = Point(cx, cy).buffer(5.25, quad_segs=48)
    neck = box(cx, cy - 3.5, 13.8, cy + 3.5)
    base = unary_union([field.buffer(MARINE_RIM, quad_segs=12), eyelet, neck])
    assert base.geom_type == 'Polygon' and base.is_valid and not base.interiors

    shapes = [[orient([list(base.exterior.coords)[:-1], bore])],
              [loops(field)], [loops(letter) for letter in letters.values()]]
    return [curves.relief(section, bottom, top - bottom, template)
            for section, bottom, top, template in zip(shapes, Z_LEVELS, Z_LEVELS[1:], old)]


def comparison(old, new, output):
    frame = [(min(bounds(p[0])[k][0] for p in (old, new)),
              max(bounds(p[0])[k][1] for p in (old, new))) for k in range(3)]
    font_path = next(Path('/usr/share/fonts').rglob('DejaVuSans.ttf'), None)
    font = ImageFont.truetype(str(font_path), 25) if font_path else ImageFont.load_default(size=25)
    canvas = None
    with tempfile.TemporaryDirectory() as folder:
        panel = Path(folder) / 'panel.png'
        for i, (label, parts) in enumerate((('v06 · Original trace', old),
                                           ('v07 · Source-traced lettering', new))):
            preview(parts, panel, 1550, frame)
            with Image.open(panel) as im:
                if canvas is None:
                    canvas = Image.new('RGB', (im.width, 2 * (im.height + 56)), '#f5f5f5')
                offset = i * (im.height + 56)
                canvas.paste(im, (0, offset + 56))
                ImageDraw.Draw(canvas).text((34, offset + 18), label, font=font, fill='#193d58')
    canvas.save(output)


def source_overlay(letters, output):
    with Image.open(ARTWORK) as original:
        canvas = Image.new('RGBA', original.size, '#ffffff')
        canvas.alpha_composite(original.convert('RGBA'))
    x0, y0, x1, y1 = 70, 63, 575, 230
    zoom = 3
    canvas = canvas.convert('RGB').crop((x0, y0, x1, y1)).resize(
        ((x1 - x0) * zoom, (y1 - y0) * zoom), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(canvas)
    for letter in letters.values():
        for contour in loops(letter):
            points = [((x - x0) * zoom, (y - y0) * zoom)
                      for x, y in map(source_point, contour)]
            draw.line(points + points[:1], fill='#af1745', width=2)
    canvas.save(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=DEST)
    args = parser.parse_args()
    dest = args.output_dir.resolve()
    project = dest / (NAME + '.3mf')
    if project.exists():
        raise FileExistsError(project)
    old = read_parts(package(SOURCE))
    field_draft, letters = artwork()
    parts = geometry(old, field_draft, letters)
    write_project(SOURCE, project, parts, {0, 1, 2},
                  'v07; eleven smooth source-traced Winterspell letters, continuous Ice Blue '
                  'field, and solid Marine Blue backing; 6.5 mm bore and 2 mm loop/backing; '
                  'three original filament slots, settings and placement.')
    saved = read_parts(package(project))
    isometric(saved, dest / (NAME + '_isometric.png'))
    comparison(old, saved, dest / (NAME + '_comparison.png'))
    source_overlay(letters, dest / (NAME + '_source_overlay.png'))

    sources = [ROOT / 'tools' / name for name in SOURCE_FILES]
    snapshot = dest / 'Source_snapshot.zip'
    with ZipFile(snapshot, 'w', ZIP_DEFLATED) as archive:
        for path in sources:
            archive.write(path, path.relative_to(ROOT))
    sources += [SOURCE, ARTWORK, ROOT / 'sets/Set_09_Fabled/v06/Set_09_Fabled_v06.3mf']
    manifest = dict(project=project.name, output_sha256=digest(project),
                    source_snapshot=snapshot.name, source_snapshot_sha256=digest(snapshot),
                    inputs_sha256={str(p.relative_to(ROOT)): digest(p) for p in sources})
    (dest / 'Build_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
