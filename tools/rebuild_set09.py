#!/usr/bin/env python3
"""Build Set 09 v07: clean lettering and a solid book-shaped backing.

Uses the v06 native Bambu project, explicit source-registered SVG curves,
NumPy/Pillow and system Cairo/GLU. No historical releases are rebuilt.
"""
from pathlib import Path
import argparse
import io
import json
import math
import shutil
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import rebuild_set07 as curves
from rebuild_set04 import area, boundary_loops, orient
from rebuild_set05 import contours, erode
from full_height_narrow_rims import bore_index, isometric
from refine_loops_and_underline import write_project
from repair_v02 import read_parts, thumbnail
from standardize_loop_diameters import bounds, centre, digest, mesh_stats, package

ROOT = next(p for p in Path(__file__).resolve().parents
            if (p/'sets/Set_09_Fabled/v06/Set_09_Fabled_v06.3mf').is_file())
SET = ROOT/'sets/Set_09_Fabled'
VERSION = 'v07'
NAME = SET.name+'_'+VERSION
SOURCE = SET/'v06'/(SET.name+'_v06.3mf')
DEST = SET/(VERSION+'_approved')
PROJECT = DEST/(NAME+'.3mf')
VECTOR = Path(__file__).with_name('set09_clean_artwork.svg')
ARTWORK = ROOT/'collection/v01/Sources/lorcana-keychains/sources/09.png'
SCALE = 84/653
STEP, ORIGIN = .025, (-1., 35.)
SIZE = (3920, 1440)
KEYLINE = .50
SVG = {'s': 'http://www.w3.org/2000/svg'}


def registered(point):
    x, y = point
    return 10.5+(x-101)*SCALE, 33.375-(y+2)*SCALE


def artwork():
    # Reuse the adaptive Bézier sampler with this artwork's registration.
    previous = curves.registered
    curves.registered = registered
    try:
        root = ET.parse(VECTOR).getroot()
        return {g: {p.get('id'): curves.sample(p.get('d'))
                    for p in root.findall(f"s:g[@id='{g}']/s:path", SVG)}
                for g in ('background', 'letters', 'ornaments')}
    finally:
        curves.registered = previous


def pixel(point):
    return (point[0]-ORIGIN[0])/STEP, (ORIGIN[1]-point[1])/STEP


def mask(loops):
    image = Image.new('L', SIZE)
    draw = ImageDraw.Draw(image)
    for c in sorted(orient(loops), key=lambda c: abs(area(c)), reverse=True):
        draw.polygon([pixel(p) for p in c], fill=255 if area(c) > 0 else 0)
    return np.asarray(image) > 0


def purple_contours(art):
    return {name: orient(contours(erode(mask(ls), KEYLINE, STEP), STEP, ORIGIN))
            for name, ls in art['letters'].items()}


def backing(old, art):
    """Splice an exact circular eyelet into the field's straight left edge.

    The 7 mm wide neck and 10.5 mm outer circle form one contour with the
    background. Preserve every v06 bore coordinate, avoiding raster offsets.
    """
    previous = boundary_loops(old)
    hole = previous[bore_index(previous, 6.5)]
    cx, cy = centre(hole)
    left = registered((97, 0))[0]
    join = cx+math.sqrt(5.25**2-3.5**2)
    alpha = math.asin(3.5/5.25)
    angles = [-alpha]+[-i*math.tau/160 for i in range(161)
                      if alpha < i*math.tau/160 < math.tau-alpha]+[-math.tau+alpha]
    arc = [(cx+5.25*math.cos(a), cy+5.25*math.sin(a)) for a in angles]
    outer = art['background']['book_field'][0]
    # The closing segment goes from source (97,225) to (97,50).
    first, last = registered((97, 50)), registered((97, 225))
    if math.dist(outer[0], first) > 1e-8:
        outer = list(reversed(outer))
        index = min(range(len(outer)), key=lambda i: math.dist(outer[i], first))
        outer = outer[index:]+outer[:index]
    assert math.dist(outer[0], first) < 1e-8 and math.dist(outer[-1], last) < 1e-8
    outer = outer+[(left, cy-3.5), (join, cy-3.5)]+arc[1:-1]+[
        (join, cy+3.5), (left, cy+3.5)]
    return orient([outer, hole])


def geometry(old):
    art = artwork()
    base = curves.relief([backing(old[0], art)], 0., 2., old[0])
    base['name'] = 'Marine Blue'
    gold = curves.relief(list(art['letters'].values())+list(art['ornaments'].values()),
                         2., .6, old[1])
    purple = curves.relief(list(purple_contours(art).values()), 2.6, .4, old[2])
    return [base, gold, purple]


def preview(parts, path, width=1800, frame=None):
    # A common framing box makes physical scale identical in comparisons.
    framing = frame or bounds(parts[0])
    phantom = dict(parts[0], vertices=[(x, y, 0.) for x in framing[0]
                                      for y in framing[1]], faces=[])
    im = Image.open(io.BytesIO(thumbnail(parts+[phantom], width))).convert('RGB')
    height = math.ceil(width*(.88*(framing[1][1]-framing[1][0])/
                              (framing[0][1]-framing[0][0])+.12))
    im.crop((0, (width-height)//2, width, (width+height)//2)).save(path)


def comparison(old, new):
    font = next(Path('/usr/share/fonts').rglob('DejaVuSans.ttf'))
    font = ImageFont.truetype(str(font), 25)
    frame = [(min(bounds(p[0])[k][0] for p in (old, new)),
              max(bounds(p[0])[k][1] for p in (old, new))) for k in range(3)]
    panels = []
    for label, parts in [('v06 — previous', old), ('v07 — clean contours and solid background', new)]:
        temp = DEST/'comparison_panel.png'
        preview(parts, temp, 1300, frame)
        im = Image.open(temp).convert('RGB')
        panel = Image.new('RGB', (im.width, im.height+65), '#f5f5f5')
        panel.paste(im, (0, 65))
        ImageDraw.Draw(panel).text((30, 18), label, font=font, fill='#193d58')
        panels.append(panel)
        temp.unlink()
    result = Image.new('RGB', (2600, max(p.height for p in panels)), '#f5f5f5')
    for x, im in zip((0, 1300), panels):
        result.paste(im, (x, 0))
    result.save(DEST/(NAME+'_comparison.png'))


def source_overlay(art):
    """Retain a registration proof against the supplied artwork."""
    original = Image.open(ARTWORK).convert('RGBA')
    canvas = Image.new('RGBA', original.size, 'white')
    canvas.alpha_composite(original)
    canvas = canvas.convert('RGB').resize((1700, 506))
    draw = ImageDraw.Draw(canvas)
    for group in ('letters', 'ornaments'):
        for ls in art[group].values():
            for c in ls:
                points = [((101+(x-10.5)/SCALE)*2,
                           ((33.375-y)/SCALE-2)*2) for x, y in c]
                draw.line(points+points[:1], fill='#e43a50', width=2)
    canvas.save(DEST/(NAME+'_source_overlay.png'))


def main():
    global DEST, PROJECT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, help='Write a reproduction to a new directory.')
    args = parser.parse_args()
    if args.output_dir:
        DEST = args.output_dir.resolve()
        PROJECT = DEST/(NAME+'.3mf')
    if PROJECT.exists():
        raise FileExistsError(f'{PROJECT} already exists; preserve saved releases. Build a new version instead.')
    source_hash = digest(SOURCE)
    old = read_parts(package(SOURCE))
    parts = geometry(old)
    write_project(SOURCE, PROJECT, parts, {0, 1, 2},
        'v07; explicit smooth Fabled lettering with continuous 0.50 mm gold keylines; '
        'complete open-book top ornament and continuous underline; solid Marine Blue '
        'book-shaped background and 7 mm wide eyelet neck; exact v06 6.5 mm bore '
        'and centre, nominal 10.5 mm outer eyelet, uniform 2 mm backing/loop; '
        'gold 2–2.6 mm and purple 2.6–3 mm without volumetric overlaps; '
        'all three original filament profiles, process settings and placement retained.')
    loaded = read_parts(package(PROJECT))
    preview(loaded, DEST/(NAME+'_preview.png'))
    isometric(loaded, DEST/(NAME+'_isometric.png'))
    comparison(old, loaded)
    source_overlay(artwork())
    snapshots = DEST/'Sources'
    snapshots.mkdir(exist_ok=True)
    sources = [Path(__file__), VECTOR, Path(__file__).with_name('validate_set09.py'),
               ARTWORK]+[Path(__file__).with_name(n+'.py') for n in
                   ('rebuild_set04', 'rebuild_set05', 'rebuild_set06', 'rebuild_set07',
                    'full_height_narrow_rims', 'refine_loops_and_underline',
                    'repair_v02', 'standardize_loop_diameters', 'set_versions', 'validate_bambu', 'validate_set06')]
    for src in sources:
        shutil.copy2(src, snapshots/src.name)
    manifest = dict(project=str(PROJECT.relative_to(ROOT)) if PROJECT.is_relative_to(ROOT) else str(PROJECT),
                    output_sha256=digest(PROJECT),
                    baseline=str(SOURCE.relative_to(ROOT)), baseline_sha256=source_hash,
                    source_artwork=str(ARTWORK.relative_to(ROOT)),
                    source_artwork_sha256=digest(ARTWORK), vector_sha256=digest(VECTOR),
                    source_snapshots={p.name: digest(p) for p in sorted(snapshots.iterdir())},
                    parts=[dict(name=p['name'], slot=p['slot'], **mesh_stats(p)) for p in loaded])
    (DEST/'Build_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    assert digest(SOURCE) == source_hash
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
