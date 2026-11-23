#!/usr/bin/env python3
"""Build Set 10 v1.6 with smooth contours and a solid charcoal background."""
from pathlib import Path
import argparse
import json
import math
import shutil
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFont

import rebuild_set07 as curves
from rebuild_set04 import area, boundary_loops, orient
from rebuild_set09 import preview
from full_height_narrow_rims import bore_index, isometric
from refine_loops_and_underline import write_project
from repair_v1_1 import read_parts
from standardize_loop_diameters import bounds, centre, digest, mesh_stats, package

ROOT = next(p for p in Path(__file__).resolve().parents
            if (p/'sets/Set_10_Whispers_in_the_Well/v1.5/Set_10_Whispers_in_the_Well_v1.5.3mf').is_file())
SET = ROOT/'sets/Set_10_Whispers_in_the_Well'
VERSION = 'v1.6'
NAME = SET.name+'_'+VERSION
SOURCE = SET/'v1.5'/(SET.name+'_v1.5.3mf')
DEST = SET/VERSION
PROJECT = DEST/(NAME+'.3mf')
VECTOR = Path(__file__).with_name('set10_clean_artwork.svg')
ARTWORK = ROOT/'collection/v1.0/Sources/lorcana-keychains/sources/10.png'
SCALE = 40/288
STEP, ORIGIN = .025, (-1., 41.)
SIZE = (2360, 1680)
SVG = {'s': 'http://www.w3.org/2000/svg'}
GROUPS = ('background', 'gold_letters', 'grey_letters', 'gold_ornaments', 'grey_ornaments')


def registered(point):
    x, y = point
    return 10.5+(x-138)*SCALE, 39.97222222222222-y*SCALE


def artwork():
    previous = curves.registered
    curves.registered = registered
    try:
        root = ET.parse(VECTOR).getroot()
        return {g: {p.get('id'): curves.sample(p.get('d'))
                    for p in root.findall(f"s:g[@id='{g}']/s:path", SVG)} for g in GROUPS}
    finally:
        curves.registered = previous


def pixel(point):
    return (point[0]-ORIGIN[0])/STEP, (ORIGIN[1]-point[1])/STEP


def mask(loops):
    import numpy as np
    im = Image.new('L', SIZE)
    draw = ImageDraw.Draw(im)
    for c in sorted(orient(loops), key=lambda c: abs(area(c)), reverse=True):
        draw.polygon([pixel(p) for p in c], fill=255 if area(c) > 0 else 0)
    return np.asarray(im) > 0


def backing(old, art):
    loops = boundary_loops(old)
    hole = loops[bore_index(loops, 6.5)]
    cx, cy = centre(hole)
    left = registered((134, 0))[0]
    join = cx+math.sqrt(5.25**2-3.5**2)
    alpha = math.asin(3.5/5.25)
    angles = [-alpha]+[-i*math.tau/160 for i in range(161)
                      if alpha < i*math.tau/160 < math.tau-alpha]+[-math.tau+alpha]
    arc = [(cx+5.25*math.cos(a), cy+5.25*math.sin(a)) for a in angles]
    outer = art['background']['title_field'][0]
    first, last = registered((134, 105)), registered((134, 175))
    if math.dist(outer[0], first) > 1e-8:
        outer = list(reversed(outer))
        i = min(range(len(outer)), key=lambda i: math.dist(outer[i], first))
        outer = outer[i:]+outer[:i]
    assert math.dist(outer[0], first) < 1e-8 and math.dist(outer[-1], last) < 1e-8
    # Omit the redundant straight-left segment endpoints around the neck;
    # the edge is spliced at exactly cy +/- 3.5 mm.
    outer = outer+[(left, cy-3.5), (join, cy-3.5)]+arc[1:-1]+[
        (join, cy+3.5), (left, cy+3.5)]
    return orient([outer, hole])


def features(art, colour):
    return dict(art[colour+'_letters'], **art[colour+'_ornaments'])


def geometry(old):
    art = artwork()
    base = curves.relief([backing(old[0], art)], 0., 2., old[0])
    grey = curves.relief(list(features(art, 'grey').values()), 2., .8, old[1])
    gold = curves.relief(list(features(art, 'gold').values()), 2., .8, old[2])
    return [base, grey, gold]


def comparison(old, new):
    font = ImageFont.truetype(str(next(Path('/usr/share/fonts').rglob('DejaVuSans.ttf'))), 24)
    frame = [(min(bounds(p[0])[k][0] for p in (old, new)),
              max(bounds(p[0])[k][1] for p in (old, new))) for k in range(3)]
    panels = []
    for label, parts in [('v1.5 — previous', old), ('v1.6 — smooth contours and solid background', new)]:
        temp = DEST/'comparison_panel.png'
        preview(parts, temp, 1300, frame)
        im = Image.open(temp).convert('RGB')
        panel = Image.new('RGB', (1300, im.height+65), '#f5f5f5')
        panel.paste(im, (0, 65))
        ImageDraw.Draw(panel).text((25, 18), label, font=font, fill='#363a3b')
        panels.append(panel)
        temp.unlink()
    result = Image.new('RGB', (2600, max(p.height for p in panels)), '#f5f5f5')
    for x, panel in zip((0, 1300), panels):
        result.paste(panel, (x, 0))
    result.save(DEST/(NAME+'_comparison.png'))


def source_overlay(art):
    original = Image.open(ARTWORK).convert('RGBA')
    canvas = Image.new('RGBA', original.size, '#f5f5f5')
    canvas.alpha_composite(original)
    canvas = canvas.convert('RGB').resize((1944, 900))
    draw = ImageDraw.Draw(canvas)
    for group in GROUPS[1:]:
        for ls in art[group].values():
            for c in ls:
                points = [((138+(x-10.5)/SCALE)*3,
                           (39.97222222222222-y)/SCALE*3) for x, y in c]
                draw.line(points+points[:1], fill='#e43a50', width=2)
    canvas.save(DEST/(NAME+'_source_overlay.png'))


def main():
    global DEST, PROJECT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, help='Write a reproduction to a fresh directory.')
    args = parser.parse_args()
    if args.output_dir:
        DEST = args.output_dir.resolve()
        PROJECT = DEST/(NAME+'.3mf')
    if PROJECT.exists():
        raise FileExistsError(f'{PROJECT} already exists; preserve saved releases.')
    source_hash = digest(SOURCE)
    old = read_parts(package(SOURCE))
    parts = geometry(old)
    write_project(SOURCE, PROJECT, parts, {0, 1, 2},
        'v1.6; explicit smooth source-traced WHISPERS / IN THE / WELL lettering; '
        'complete upper gold wisp and continuous grey underline; solid Charcoal background '
        'with 7 mm eyelet neck; exact v1.5 bore coordinates and centre; 6.5 mm bore, '
        'nominal 10.5 mm eyelet, 2 mm backing and loop, relief 2–2.8 mm; '
        'three original filament profiles, process settings and placement retained.')
    loaded = read_parts(package(PROJECT))
    preview(loaded, DEST/(NAME+'_preview.png'))
    isometric(loaded, DEST/(NAME+'_isometric.png'))
    comparison(old, loaded)
    source_overlay(artwork())
    snapshots = DEST/'Sources'
    snapshots.mkdir(exist_ok=True)
    sources = [Path(__file__), VECTOR, ARTWORK, Path(__file__).with_name('validate_set10.py')]+[
        Path(__file__).with_name(n+'.py') for n in
        ('rebuild_set04', 'rebuild_set05', 'rebuild_set06', 'rebuild_set07', 'rebuild_set09',
         'full_height_narrow_rims', 'refine_loops_and_underline', 'repair_v1_1',
         'standardize_loop_diameters', 'validate_bambu', 'validate_set06', 'validate_set09')]
    for src in sources:
        shutil.copy2(src, snapshots/src.name)
    manifest = dict(project=str(PROJECT.relative_to(ROOT)) if PROJECT.is_relative_to(ROOT) else str(PROJECT),
        output_sha256=digest(PROJECT), baseline=str(SOURCE.relative_to(ROOT)),
        baseline_sha256=source_hash, source_artwork=str(ARTWORK.relative_to(ROOT)),
        source_artwork_sha256=digest(ARTWORK), vector_sha256=digest(VECTOR),
        source_snapshots={p.name: digest(p) for p in sorted(snapshots.iterdir())},
        parts=[dict(name=p['name'], slot=p['slot'], **mesh_stats(p)) for p in loaded])
    (DEST/'Build_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    assert digest(SOURCE) == source_hash
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    main()
