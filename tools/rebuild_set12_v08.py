#!/usr/bin/env python3
"""Build Wilds Unknown v08 with flush green accents in the ivory lettering."""

import argparse
import json
import math
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from shapely.affinity import affine_transform
from shapely.geometry import LineString
from shapely.ops import unary_union

import rebuild_set12 as baseline
from full_height_narrow_rims import isometric
from rebuild_set07 import merge, registered, relief, sample
from rebuild_set09 import preview
from refine_loops_and_underline import write_project
from repair_v02 import read_parts
from standardize_loop_diameters import bounds, digest, mesh_stats, package
from validate_set12 import outlines

VERSION = 'v08'
NAME = baseline.SET.name + '_' + VERSION
SOURCE = baseline.DEST / (baseline.NAME + '.3mf')
DEST = baseline.SET / (VERSION + '_approved')
VECTOR = DEST / 'Sources/set12_green_accents.svg'
INLAY_FLOOR = 2.6
TOP = 3.
MIN_IVORY_MARGIN = .58


def artwork():
    root = ET.parse(VECTOR).getroot()
    group = root.find('s:g', baseline.SVG)
    scale = baseline.SOURCE_SCALE
    width = float(group.get('stroke-width')) * scale

    # The shared Bézier sampler returns coordinates in Set 07's registration.
    # Undo that registration and apply the Set 12 reference image transform.
    x0, y0 = registered((0., 0.))
    sx = scale / (registered((1., 0.))[0] - x0)
    sy = -scale / (registered((0., 1.))[1] - y0)
    transform = (sx, 0., 0., sy, 10.25 - 63 * scale - sx * x0, 41.236 - sy * y0)

    lines = {}
    strokes = {}
    for path in group.findall('s:path', baseline.SVG):
        name = path.get('id')
        line = affine_transform(LineString(sample(path.get('d'), closed=False)), transform)
        assert line.is_simple and name not in lines
        lines[name] = line
        strokes.setdefault(path.get('data-letter'), {})[name] = line.buffer(width / 2, quad_segs=12)
    return width, lines, strokes


def glyph_footprints(part):
    saved = outlines(part)
    letters = baseline.artwork()['letters']
    assert len(letters) == len(saved)
    result = {}
    for name, shape in letters.items():
        matches = [p for p in saved if p.covers(shape.representative_point())]
        assert len(matches) == 1
        result[name] = matches[0]
    assert len({p.wkb for p in result.values()}) == len(saved)
    return result


def face_on_top(part, face):
    return all(math.isclose(part['vertices'][i][2], TOP, abs_tol=1e-7) for i in face)


def pocketed_ivory(ivory, cap, inlays):
    """Replace the old flat cap with the pocketed cap and reversed pocket faces."""
    vertices, faces, index = [], [], {}

    def add_face(part, face):
        ids = []
        for i in face:
            point = tuple(round(v, 8) for v in part['vertices'][i])
            if point not in index:
                index[point] = len(vertices)
                vertices.append(point)
            ids.append(index[point])
        faces.append(tuple(ids))

    for face in ivory['faces']:
        if not face_on_top(ivory, face):
            add_face(ivory, face)
    for face in cap['faces']:
        if face_on_top(cap, face):
            add_face(cap, face)
    for face in inlays['faces']:
        if not face_on_top(inlays, face):
            add_face(inlays, reversed(face))
    part = dict(ivory, vertices=vertices, faces=faces)
    assert mesh_stats(part)['degenerate_triangles'] == 0
    return part


def geometry(old):
    _, _, strokes = artwork()
    glyphs = glyph_footprints(old[2])
    assert strokes.keys() == glyphs.keys()
    tops, green = [], []
    for name, glyph in glyphs.items():
        accents = list(strokes[name].values())
        mask = unary_union(accents)
        top = glyph.difference(mask)
        assert top.geom_type == 'Polygon' and top.is_valid
        assert len(top.interiors) == len(glyph.interiors) + len(accents)
        assert glyph.covers(mask) and glyph.boundary.distance(mask) >= MIN_IVORY_MARGIN, name
        tops.append(baseline.contours(top))
        green.extend(baseline.contours(accent) for accent in accents)

    height = TOP - INLAY_FLOOR
    inlays = relief(green, INLAY_FLOOR, height, old[1])
    cap = relief(tops, INLAY_FLOOR, height, old[2])
    ivory = pocketed_ivory(old[2], cap, inlays)
    return [old[0], merge([old[1], inlays]), ivory]


def comparison(old, new, target):
    font_path = next(Path('/usr/share/fonts').rglob('DejaVuSans.ttf'), None)
    font = ImageFont.truetype(str(font_path), 26) if font_path else ImageFont.load_default(size=26)
    frame = bounds(old[0])
    labels = ('v07 · Plain ivory lettering', 'v08 · Green strokes in the ivory')
    canvas = None
    with tempfile.TemporaryDirectory() as temp:
        panel = Path(temp) / 'model.png'
        for i, (parts, label) in enumerate(zip((old, new), labels)):
            preview(parts, panel, width=1500, frame=frame)
            with Image.open(panel) as im:
                panel_height = im.height + 54
                if canvas is None:
                    canvas = Image.new('RGB', (im.width, panel_height * 2), '#f5f5f5')
                canvas.paste(im, (0, i * panel_height + 54))
            ImageDraw.Draw(canvas).text((32, i * panel_height + 15), label, fill='#3c3027', font=font)
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
    write_project(SOURCE, project, geometry(old), {1, 2},
                  'v08; source-traced dark green strokes inlaid flush with all twelve ivory '
                  'letters; continuous ivory support and v07 backing, eyelet and profile.')
    saved = read_parts(package(project))
    preview(saved, dest / (NAME + '_preview.png'))
    isometric(saved, dest / (NAME + '_isometric.png'))
    comparison(old, saved, dest / (NAME + '_comparison.png'))

    script = Path(__file__).resolve()
    inputs = [SOURCE, VECTOR, script, script.with_name('validate_set12_v08.py')]
    previous = json.loads((baseline.DEST / 'Build_manifest.json').read_text())['inputs_sha256']
    inputs.extend(baseline.ROOT / p for p in previous)
    (dest / 'Build_manifest.json').write_text(json.dumps(
        dict(project=project.name, output_sha256=digest(project),
             inputs_sha256={str(p.relative_to(baseline.ROOT)): digest(p) for p in inputs}),
        indent=2) + '\n')


if __name__ == '__main__':
    main()
