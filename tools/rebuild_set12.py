#!/usr/bin/env python3
"""Build Wilds Unknown v07 from the editable Set 12 outline paths."""

import argparse
import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from shapely.affinity import affine_transform
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from full_height_narrow_rims import bore_index, isometric
from rebuild_set04 import boundary_loops, orient
from rebuild_set07 import registered, relief, sample
from rebuild_set09 import preview
from refine_loops_and_underline import write_project
from repair_v02 import read_parts
from standardize_loop_diameters import bounds, centre, digest, package

ROOT = Path(__file__).resolve().parents[1]
SET = ROOT / 'sets/Set_12_Wilds_Unknown'
VERSION = 'v07'
NAME = SET.name + '_' + VERSION
SOURCE = SET / 'v06' / (SET.name + '_v06.3mf')
DEST = SET / VERSION
VECTOR = DEST / 'Sources/set12_clean_artwork.svg'
ARTWORK = ROOT / 'collection/v01/Sources/lorcana-keychains/sources/12.png'
SVG = {'s': 'http://www.w3.org/2000/svg'}
SOURCE_SCALE = .138
BORDER = .92
NOTCH_RADIUS = 2.6
Z_EXTENTS = ((0., 2.), (2., 2.6), (2., 3.))


def artwork():
    # Convert the coordinates returned by the shared sampler back to SVG
    # coordinates, then apply this set's registration in one affine transform.
    origin = registered((0., 0.))
    sx = registered((1., 0.))[0] - origin[0]
    sy = registered((0., 1.))[1] - origin[1]
    x, y = SOURCE_SCALE / sx, -SOURCE_SCALE / sy
    transform = (x, 0., 0., y, 10.25 - 63 * SOURCE_SCALE - x * origin[0],
                 41.236 - y * origin[1])

    def source_polygon(path):
        outer, *holes = sample(path.get('d'))
        return affine_transform(Polygon(outer, holes), transform)

    root = ET.parse(VECTOR).getroot()
    return {group: {path.get('id'): source_polygon(path)
                    for path in root.findall(f"s:g[@id='{group}']/s:path", SVG)}
            for group in ('foliage', 'letters')}


def contours(section):
    return orient([list(ring.coords)[:-1]
                   for ring in (section.exterior, *section.interiors)])


def bore_loop(part):
    loops = boundary_loops(part)
    return loops[bore_index(loops, 6.5)]


def geometry(old):
    art = artwork()
    shapes = [shape for group in art.values() for shape in group.values()]
    assert all(shape.is_valid for shape in shapes)
    margin = unary_union(shapes).buffer(BORDER, quad_segs=16)
    # Round off the gaps between neighbouring strokes while retaining the
    # outlines of the ornaments and the two rows of lettering.
    closed = margin.buffer(NOTCH_RADIUS, quad_segs=16).buffer(-NOTCH_RADIUS, quad_segs=16)
    field = margin.union(closed)
    assert field.geom_type == 'Polygon'
    field = Polygon(field.exterior)

    bore = bore_loop(old[0])
    cx, cy = centre(bore)
    ring = Point(cx, cy).buffer(5.25, quad_segs=48)
    neck = box(cx, cy - 3.5, 13.8, cy + 3.5)
    base = unary_union([field, ring, neck]).buffer(.30).buffer(-.30).simplify(.018)
    assert base.geom_type == 'Polygon' and not base.interiors
    base = Polygon(base.exterior, [bore])
    assert base.is_valid and all(base.covers(shape) for shape in shapes)
    sections = [[contours(base)]] + [
        [contours(shape) for shape in group.values()] for group in art.values()]
    return [relief(loops, z0, z1 - z0, template)
            for loops, (z0, z1), template in zip(sections, Z_EXTENTS, old)]


def comparison(old, new, target):
    frame = [(min(a[0], b[0]), max(a[1], b[1]))
             for a, b in zip(bounds(old[0]), bounds(new[0]))]
    font_path = next(Path('/usr/share/fonts').rglob('DejaVuSans.ttf'), None)
    font = ImageFont.truetype(str(font_path), 26) if font_path else ImageFont.load_default(size=26)
    panels = []
    with tempfile.TemporaryDirectory() as temp:
        panel = Path(temp) / 'model.png'
        for parts, title in ((old, 'v06 · Previous artwork and backing'),
                             (new, 'v07 · Smooth contours and continuous backing')):
            preview(parts, panel, width=1500, frame=frame)
            with Image.open(panel) as im:
                canvas = Image.new('RGB', (im.width, im.height + 54), '#f5f5f5')
                canvas.paste(im, (0, 54))
            ImageDraw.Draw(canvas).text((32, 15), title, fill='#3c3027', font=font)
            panels.append(canvas)
    canvas = Image.new('RGB', (panels[0].width, sum(p.height for p in panels)))
    canvas.paste(panels[0], (0, 0))
    canvas.paste(panels[1], (0, panels[0].height))
    canvas.save(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=DEST)
    args = parser.parse_args()
    dest = args.output_dir.resolve()
    project = dest / (NAME + '.3mf')
    if project.exists():
        raise FileExistsError(project)
    old = read_parts(package(SOURCE))
    write_project(SOURCE, project, geometry(old), {0, 1, 2},
                  'v07; smooth source-traced ivory lettering and green foliage; '
                  'continuous cocoa brown backing; 6.5 mm bore, 10.5 mm nominal eyelet, '
                  '2 mm backing and 3 mm overall height; original filament and process settings.')
    parts = read_parts(package(project))
    preview(parts, dest / (NAME + '_preview.png'))
    isometric(parts, dest / (NAME + '_isometric.png'))
    comparison(old, parts, dest / (NAME + '_comparison.png'))

    shared = ('full_height_narrow_rims', 'rebuild_set04', 'rebuild_set05',
              'rebuild_set07', 'rebuild_set09', 'refine_loops_and_underline',
              'repair_v02', 'standardize_loop_diameters', 'set_versions', 'validate_bambu')
    script = Path(__file__)
    inputs = [SOURCE, VECTOR, ARTWORK, script, script.with_name('validate_set12.py')] + [
        ROOT / 'tools' / (name + '.py') for name in shared]
    (dest / 'Build_manifest.json').write_text(json.dumps(
        dict(project=project.name, output_sha256=digest(project),
             inputs_sha256={str(p.resolve().relative_to(ROOT)): digest(p) for p in inputs}),
        indent=2) + '\n')


if __name__ == '__main__':
    main()
