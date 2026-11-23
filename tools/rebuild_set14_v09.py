#!/usr/bin/env python3
"""Build Hyperia City v09 with tapered blue contours over the v08 artwork."""

import argparse
import math
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points, substring, unary_union

import rebuild_set14 as original
import rebuild_set14_v08 as previous
from full_height_narrow_rims import isometric
from rebuild_set07 import registered, relief, sample
from rebuild_set09 import preview
from rebuild_set13 import contours
from refine_loops_and_underline import write_project
from repair_v02 import read_parts
from standardize_loop_diameters import bounds, package
from validate_set12 import outlines

ROOT, SET = previous.ROOT, previous.SET
VERSION = 'v09'
NAME = SET.name + '_' + VERSION
DEST = SET / VERSION
SOURCE = previous.DEST / (previous.NAME + '.3mf')
VECTOR = DEST / 'Sources/set14_blue_highlights.svg'
BLUE_WIDTH = .66
TIP_WIDTH = .50
FADE_STEP = .18
BLUE_LINE_WIDTH = .36
WIDTH_SETTINGS = ('outer_wall_line_width', 'inner_wall_line_width',
                  'top_surface_line_width', 'internal_solid_infill_line_width')


def tapered_end(edge, start_width, end_width):
    # Include the sampled path vertices so interpolating the taper follows
    # the SVG curve even when a corner falls between two equally spaced points.
    vertices = list(edge.coords)
    distances = [0.]
    for a, b in zip(vertices, vertices[1:]):
        distances.append(distances[-1] + math.dist(a, b))
    count = math.ceil(edge.length / FADE_STEP)
    distances = sorted(set(distances) | {edge.length * i / count for i in range(count + 1)})
    sections = []
    for distance in distances:
        t = min(1., distance / edge.length)
        blend = t * t * (3. - 2. * t)
        radius = start_width + (end_width - start_width) * blend
        sections.append(edge.interpolate(distance).buffer(radius, quad_segs=12))
    return [a.union(b).convex_hull for a, b in zip(sections, sections[1:])]


def band_for(path, letter, edge):
    width = float(path.get('data-width-mm', BLUE_WIDTH))
    start = float(path.get('data-fade-start-mm'))
    end = edge.length - float(path.get('data-fade-end-mm'))
    assert 0. < start < end < edge.length and width >= TIP_WIDTH
    middle = substring(edge, start, end).buffer(width, quad_segs=16)
    start_fade = tapered_end(substring(edge, 0., start), TIP_WIDTH, width)
    end_fade = tapered_end(substring(edge, end, edge.length), width, TIP_WIDTH)
    band = letter.intersection(unary_union([middle, *start_fade, *end_fade]))
    # Remove tiny buffer vertices before extrusion while keeping the blue
    # footprint inside the ivory that supports it.
    band = band.buffer(-.006, quad_segs=8).simplify(.004)
    assert band.geom_type == 'Polygon' and band.is_valid and not band.interiors, path.get('id')
    return band


def highlights(letters):
    x0, y0 = registered((0., 0.))
    sx = original.SCALE / (registered((1., 0.))[0] - x0)
    sy = -original.SCALE / (registered((0., 1.))[1] - y0)
    bands = {}
    for path in ET.parse(VECTOR).getroot().findall('s:g/s:path', original.SVG):
        letter = letters[path.get('data-letter')]
        points = sample(path.get('d'), closed=False)
        guide = [Point(original.X_ORIGIN + (x - x0) * sx,
                       original.Y_ORIGIN + (y - y0) * sy) for x, y in points]
        # Match the sampled letter edges so that a small registration error
        # cannot pinch a narrow band where it turns a corner.
        edge = LineString([nearest_points(letter.boundary, point)[0] for point in guide])
        bands[path.get('id')] = band_for(path, letter, edge)
    return bands


def blue_template(data, target):
    config = ET.fromstring(data[previous.CONFIG])
    blue = config.find("object/part/metadata[@key='extruder'][@value='3']/..")
    for key in WIDTH_SETTINGS:
        ET.SubElement(blue, 'metadata', {'key': key, 'value': str(BLUE_LINE_WIDTH)})
    config_bytes = ET.tostring(config, encoding='utf-8', xml_declaration=True)
    with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
        for name, raw in data.items():
            archive.writestr(name, config_bytes if name == previous.CONFIG else raw)


def comparison(old, new, target):
    frame = bounds(old[0])
    font_path = next(Path('/usr/share/fonts').rglob('DejaVuSans.ttf'), None)
    font = ImageFont.truetype(str(font_path), 25) if font_path else ImageFont.load_default(size=25)
    with tempfile.TemporaryDirectory() as directory:
        panel = Path(directory) / 'panel.png'
        canvas = None
        for i, (parts, label) in enumerate(((old, 'v08 · Blue upper edges'),
                                             (new, 'v09 · Tapered blue contours'))):
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
    blue = highlights(original.artwork())
    blue_part = relief([contours(p) for p in blue.values()], previous.IVORY_TOP,
                       previous.BLUE_TOP - previous.IVORY_TOP, old[2])
    with tempfile.TemporaryDirectory() as directory:
        template = Path(directory) / 'blue-template.3mf'
        blue_template(data, template)
        write_project(template, project, [*old[:2], blue_part], {2},
                      'v09; Ice Blue follows the tops and upper side contours and tapers at the ends. '
                      'Ivory White lettering, Cocoa Brown padding, and a 6.5 mm bore.')
    saved = read_parts(package(project))
    isometric(saved, dest / (NAME + '_isometric.png'))
    comparison(old, saved, dest / (NAME + '_comparison.png'))
    original.source_overlay(outlines(saved[2]), dest / (NAME + '_source_overlay.png'))


if __name__ == '__main__':
    main()
