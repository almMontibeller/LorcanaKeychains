#!/usr/bin/env python3
"""Rebuild Set 05's continuous colour panel and reinforced star connections.

Requires NumPy and Pillow, plus the existing system Cairo/GLU libraries.
v04 replaces the red mesh; v05 adds rounded supports to the purple backing.
Ivory artwork, placement, filaments and process settings are retained.
No STL files are generated.
"""
from pathlib import Path
import argparse
import collections
import hashlib
import io
import json
import math
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
from PIL import Image, ImageDraw

from rebuild_set04 import area, boundary_loops, extrude, inside, orient, simplify_open
from repair_v02 import IDENTITY, NS, read_parts, thumbnail

ROOT = Path(__file__).resolve().parents[1]
SET = ROOT / 'sets/Set_05_Shimmering_Skies'
SOURCE = SET / 'v04/Set_05_Shimmering_Skies_v04.3mf'
ARTWORK = ROOT / 'collection/v01/Sources/lorcana-keychains/sources/05.png'
VERSION = 'v05'
DEST = SET / VERSION
NAME = f'Set_05_Shimmering_Skies_{VERSION}'
PROJECT = DEST / (NAME + '.3mf')
STEP = .025
PAD = 4.
WIDTH, HEIGHT = math.ceil(103 / STEP), math.ceil(47 / STEP)
PURPLE_OUTLINE = .45
RED_OPENING = .30
# Each independent capsule joins a star's centre directly to the main body.
# Rounded wider feet spread the load instead of ending at a pointed tip.
STAR_SUPPORTS = [
    dict(name='upper_left', star=(27.6, 32.35), anchor=(29.4, 25.5)),
    dict(name='upper_centre', star=(33.6, 32.3), anchor=(33.8, 26.5)),
    dict(name='upper_right', star=(38.8, 31.7), anchor=(39.1, 27.5)),
    dict(name='lower', star=(45.45, 9.55), anchor=(45.9, 14.3)),
    dict(name='right_upper', star=(90.45, 20.9), anchor=(83.8, 21.7)),
    dict(name='right_lower', star=(92.25, 13.25), anchor=(84., 13.8)),
]
STAR_RADIUS, ANCHOR_RADIUS, ROOT_FILLET = 1.7, 2.25, .7
CORE = NS['m']
PROD = 'http://schemas.microsoft.com/3dmanufacturing/production/2015/06'
TAG = lambda name: '{' + CORE + '}' + name
ET.register_namespace('', CORE)
ET.register_namespace('p', PROD)


def configure(version):
    global VERSION, SOURCE, DEST, NAME, PROJECT
    VERSION = version
    SOURCE = SET / ('v03/Set_05_Shimmering_Skies_v03.3mf' if version == 'v04'
                    else 'v04/Set_05_Shimmering_Skies_v04.3mf')
    DEST = SET / version
    NAME = f'Set_05_Shimmering_Skies_{version}'
    PROJECT = DEST / (NAME + '.3mf')


def project_data(path):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        return {n: archive.read(n) for n in archive.namelist()}


def xy_pixel(p):
    return ((p[0] + PAD) / STEP, (43 - p[1]) / STEP)


def footprint(loops):
    image = Image.new('L', (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    for loop in sorted(orient(loops), key=lambda c: abs(area(c)), reverse=True):
        draw.polygon([xy_pixel(p) for p in loop], fill=255 if area(loop) > 0 else 0)
    return np.asarray(image) > 0


def dilate(mask, radius, step=STEP):
    """Circular binary dilation; prefix sums avoid a square pixel kernel."""
    r = round(radius / step)
    if not r:
        return mask.copy()
    padded = np.pad(mask, ((0, 0), (r, r)))
    sums = np.pad(np.cumsum(padded, axis=1, dtype=np.int32), ((0, 0), (1, 0)))
    result = np.zeros_like(mask)
    spans = collections.defaultdict(list)
    for dy in range(-r, r + 1):
        spans[math.floor(math.sqrt(r*r - dy*dy))].append(dy)
    for span, offsets in spans.items():
        horizontal = sums[:, r+span+1:r+span+1+mask.shape[1]] > sums[:, r-span:r-span+mask.shape[1]]
        for dy in offsets:
            if dy > 0:
                result[dy:] |= horizontal[:-dy]
            elif dy < 0:
                result[:dy] |= horizontal[-dy:]
            else:
                result |= horizontal
    return result


def erode(mask, radius, step=STEP):
    return ~dilate(~mask, radius, step=step)


def contours(mask, step=STEP, origin=(-PAD, 43.)):
    """Marching squares with separate diagonal islands and no touching rings.

    Integer half-pixel endpoints keep neighboring cells exactly registered.
    The contours are simplified by at most 0.025 mm before tessellation.
    """
    a = np.pad(mask, 1)
    cells = (a[:-1, :-1].astype(np.uint8) + 2*a[:-1, 1:]
             + 4*a[1:, 1:] + 8*a[1:, :-1])
    # Clockwise edge midpoints: top, right, bottom, left.
    points = ((1, 0), (2, 1), (1, 2), (0, 1))
    cases = {1: [(3, 0)], 2: [(0, 1)], 3: [(3, 1)], 4: [(1, 2)],
             5: [(3, 0), (1, 2)], 6: [(0, 2)], 7: [(3, 2)],
             8: [(2, 3)], 9: [(2, 0)], 10: [(0, 1), (2, 3)],
             11: [(2, 1)], 12: [(1, 3)], 13: [(1, 0)], 14: [(0, 3)]}
    adjacent = collections.defaultdict(list)
    for case, edges in cases.items():
        ys, xs = np.where(cells == case)
        for y, x in zip(ys.tolist(), xs.tolist()):
            for e0, e1 in edges:
                ends = [(2*x + points[e][0], 2*y + points[e][1]) for e in (e0, e1)]
                adjacent[ends[0]].append(ends[1])
                adjacent[ends[1]].append(ends[0])
    assert all(len(v) == 2 for v in adjacent.values()), 'open or touching raster contour'
    remaining, loops = set(adjacent), []
    while remaining:
        first = min(remaining)
        current, previous, loop = first, None, []
        while True:
            remaining.remove(current)
            loop.append((origin[0] + (current[0]/2 - 1)*step,
                         origin[1] - (current[1]/2 - 1)*step))
            following = next(p for p in adjacent[current] if p != previous)
            previous, current = current, following
            if current == first:
                break
        opposite = max(range(len(loop)), key=lambda i: math.dist(loop[0], loop[i]))
        loop = (simplify_open(loop[:opposite+1], .025)[:-1]
                + simplify_open(loop[opposite:] + loop[:1], .025)[:-1])
        if abs(area(loop)) > .015:
            loops.append(loop)
    return orient(loops)


def main_panel():
    """Use the complete title silhouette, independent of its RGB gradient.

    Register it using the v02 builder's crop, scale and backing offsets,
    also used by v03. Detached stars and the added keyring stay purple.
    """
    artwork = Image.open(ARTWORK).convert('RGBA')
    a = np.asarray(artwork)
    yy, xx = np.where(a[:, :, 3] > 140)
    crop = (max(0, int(xx.min())-2), max(0, int(yy.min())-2),
            min(artwork.width, int(xx.max())+3), min(artwork.height, int(yy.max())+3))
    alpha = np.asarray(artwork.crop(crop))[:, :, 3] > 135
    h, w = alpha.shape
    scale = min(84/w, 40/h)
    yy, xx = np.where(alpha)
    shift = (10.55 - xx.min()*scale, .8 - (h-yy.max())*scale)
    component = Image.fromarray(alpha.astype(np.uint8)*255).copy()
    seed = (700-crop[0], 250-crop[1])
    assert component.getpixel(seed) == 255
    ImageDraw.floodfill(component, seed, 128)
    loops = contours(np.asarray(component) == 128, step=scale,
                     origin=(shift[0], h*scale+shift[1]))
    # Fill the title's outer contour; letter counters will be defined by the
    # native ivory mesh and the explicit uniform purple outlines below.
    outer = max(loops, key=lambda c: abs(area(c)))
    # Remove subpixel alpha stair steps while staying within the purple base.
    for _ in range(2):
        outer = [tuple((1-t)*p[k]+t*q[k] for k in (0, 1))
                 for p, q in zip(outer, outer[1:]+outer[:1]) for t in (.25, .75)]
    return erode(footprint([outer]), .10)


def build_red(original):
    base = footprint(boundary_loops(original[0]))
    ivory = footprint(boundary_loops(original[2]))
    field = main_panel() & erode(base, .85)
    # Avoid thin red channels alongside letters: a 0.45 mm purple keyline is
    # applied equally to BOTH words, swashes and counters.
    red = field & ~dilate(ivory, PURPLE_OUTLINE)
    # Remove slivers narrower than 0.6 mm without moving the ivory geometry.
    red = dilate(erode(red, RED_OPENING), RED_OPENING) & red
    loops = contours(red)
    # Drop microscopic isolated flecks, but retain intentional letter counters.
    loops = [loop for loop in loops if abs(area(loop)) >= .18]
    assert not np.any(footprint(loops) & ~base)
    assert not np.any(footprint(loops) & ivory)
    return extrude(loops, 2., .4, original[1]), loops


def star_support_mask():
    image = Image.new('L', (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    for support in STAR_SUPPORTS:
        a, b = support['star'], support['anchor']
        length = math.dist(a, b)
        nx, ny = -(b[1]-a[1])/length, (b[0]-a[0])/length
        poly = [(p[0]+sign*radius*nx, p[1]+sign*radius*ny)
                for p, radius, sign in [(a, STAR_RADIUS, 1), (b, ANCHOR_RADIUS, 1),
                                        (b, ANCHOR_RADIUS, -1), (a, STAR_RADIUS, -1)]]
        draw.polygon([xy_pixel(p) for p in poly], fill=255)
        for p, radius in [(a, STAR_RADIUS), (b, ANCHOR_RADIUS)]:
            x, y = xy_pixel(p)
            r = radius/STEP
            draw.ellipse((x-r, y-r, x+r, y+r), fill=255)
    return np.asarray(image) > 0


def reinforce_stars(part):
    loops = boundary_loops(part)
    base = footprint(loops)
    supports = star_support_mask()
    reinforced = base | supports
    # Round reentrant corners only around the six new joints. Closing adds
    # material and fills the small stress-raising voids between nearby stars.
    local = dilate(supports, ROOT_FILLET + .1)
    rounded = erode(dilate(reinforced, ROOT_FILLET), ROOT_FILLET)
    reinforced |= rounded & local
    outer = max(contours(reinforced), key=lambda c: abs(area(c)))
    # Retain the native eyelet bore, rather than rasterising the ring opening.
    bore = next(c for c in loops if 15.7 < abs(area(c)) < 15.9)
    result = orient([outer, bore])
    return extrude(result, 0., 2., part), result


def write_mesh(obj, part):
    obj.remove(obj.find(TAG('mesh')))
    mesh = ET.SubElement(obj, TAG('mesh'))
    vs, fs = ET.SubElement(mesh, TAG('vertices')), ET.SubElement(mesh, TAG('triangles'))
    for v in part['vertices']:
        ET.SubElement(vs, TAG('vertex'), dict(zip(('x', 'y', 'z'), (f'{n:.9f}' for n in v))))
    for f in part['faces']:
        ET.SubElement(fs, TAG('triangle'), dict(zip(('v1', 'v2', 'v3'), map(str, f))))


def main():
    data = project_data(SOURCE)
    original = read_parts(data)
    if VERSION == 'v04':
        red, loops = build_red(original)
        parts = [original[0], red, original[2]]
        changed = 1
    else:
        base, loops = reinforce_stars(original[0])
        parts = [base, original[1], original[2]]
        changed = 0
    root = ET.fromstring(data['3D/3dmodel.model'])
    mesh_root = ET.fromstring(data['3D/Objects/object_1.model'])
    config = ET.fromstring(data['Metadata/model_settings.config'])
    assembly = root.find('m:resources/m:object', NS)
    component = assembly.find('m:components', NS)[changed]
    oid = component.get('objectid')
    component.set('transform', ' '.join(map(str, IDENTITY)))
    write_mesh(mesh_root.find(f"m:resources/m:object[@id='{oid}']", NS), parts[changed])
    config.find("./object/metadata[@key='name']").set('value', f'Shimmering Skies {VERSION}')
    config.find('./object/metadata[@face_count]').set('face_count', str(sum(len(p['faces']) for p in parts)))
    cfg = config.find(f"./object/part[@id='{oid}']")
    for md in list(cfg.findall('metadata')):
        if md.get('key', '').startswith('source_'):
            cfg.remove(md)
    cfg.find("metadata[@key='name']").set('value', 'Red — continuous title panel' if changed == 1
                                              else 'Purple — reinforced star supports')
    cfg.find("metadata[@key='matrix']").set('value', '1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1')
    cfg.find('mesh_stat').set('face_count', str(len(parts[changed]['faces'])))
    root.find("m:metadata[@name='Description']", NS).text = (
        f'{VERSION}; continuous red inset across both words; purple outer border and '
        '0.45 mm letter keylines; 2 mm backing; 0.4 mm red relief; 1 mm ivory relief; '
        + ('original v03 backing and eyelet; ' if VERSION == 'v04' else
           'six rounded purple star supports; nominal 3.4 mm necks and 4.5 mm feet; ')
        + 'original ivory artwork; 0.20 mm layers.')
    if not any(k.startswith('{'+PROD+'}') for e in mesh_root.iter() for k in e.attrib):
        mesh_root.set('xmlns:p', PROD)
    data['3D/3dmodel.model'] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    data['3D/Objects/object_1.model'] = ET.tostring(mesh_root, encoding='utf-8', xml_declaration=True)
    data['Metadata/model_settings.config'] = ET.tostring(config, encoding='utf-8', xml_declaration=True)
    data['Metadata/plate_1.png'] = thumbnail(parts, 512)
    data['Metadata/plate_no_light_1.png'] = data['Metadata/plate_1.png']
    data['Metadata/plate_1_small.png'] = thumbnail(parts, 128)
    DEST.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(PROJECT, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, raw in data.items():
            archive.writestr(name, raw)
    loaded = read_parts(project_data(PROJECT))
    assert all(loaded[i] == original[i] for i in range(3) if i != changed)
    assert project_data(PROJECT)['Metadata/project_settings.config'] == project_data(SOURCE)['Metadata/project_settings.config']
    preview = Image.open(io.BytesIO(thumbnail(parts, 1800)))
    preview.crop((0, 470, 1800, 1330)).save(DEST / (NAME + '_preview.png'))
    (DEST / ('red_footprint.json' if changed == 1 else 'backing_footprint.json')).write_text(json.dumps(loops))
    report = dict(filename=PROJECT.name, source=str(SOURCE.relative_to(ROOT)),
                  source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                  output_sha256=hashlib.sha256(PROJECT.read_bytes()).hexdigest(),
                  design=('Uniform red inset across the complete title, with purple border and letter keylines'
                          if VERSION == 'v04' else
                          'Six broad rounded star supports, retaining the continuous red panel and ivory artwork'),
                  raster_step_mm=STEP, contour_simplification_mm=.025,
                  nominal_purple_letter_outline_mm=PURPLE_OUTLINE,
                  red_opening_diameter_mm=2*RED_OPENING,
                  original_backing_and_eyelet_unchanged=changed == 1,
                  original_red_mesh_unchanged=changed == 0, original_ivory_mesh_unchanged=True,
                  filament_and_process_settings_byte_identical=True,
                  dimensions_mm=[round(max(v[k] for p in parts for v in p['vertices'])
                                       - min(v[k] for p in parts for v in p['vertices']), 5) for k in range(3)],
                  parts=[dict(name=p['name'], slot=p['slot'], triangles=len(p['faces'])) for p in loaded])
    if VERSION == 'v05':
        report['star_supports'] = dict(connections=STAR_SUPPORTS,
                                      nominal_neck_width_mm=2*STAR_RADIUS,
                                      nominal_anchor_width_mm=2*ANCHOR_RADIUS,
                                      root_fillet_radius_mm=ROOT_FILLET,
                                      backing_thickness_mm=2.)
    (DEST / f'Geometry_{VERSION}.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', choices=['v04', 'v05'], default='v05')
    configure(parser.parse_args().version)
    main()
