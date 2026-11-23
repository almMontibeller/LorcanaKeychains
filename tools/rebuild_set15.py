#!/usr/bin/env python3
"""Build and slice Into the Inkdark v1.0 from the saved artwork paths."""

import argparse
import json
import math
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from itertools import combinations
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
from PIL import Image, ImageDraw
from shapely.affinity import affine_transform
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

from full_height_narrow_rims import isometric
from rebuild_set04 import orient
from rebuild_set05 import dilate
from rebuild_set07 import registered, relief, sample
from refine_loops_and_underline import read_toolpaths, render_slice, toolpath_checks, write_project
from repair_v1_1 import NS, read_parts
from standardize_loop_diameters import bounds, digest, mesh_stats, package
from validate_bambu import bambu_command
from validate_set09 import regions
from validate_set12 import STEP, coverage, deposit, dimensions, outlines, raster

ROOT = Path(__file__).resolve().parents[1]
SET = ROOT / 'sets/Set_15_Into_the_Inkdark'
VERSION = 'v1.0'
DEST = SET / VERSION
NAME = SET.name + '_' + VERSION
VECTOR = DEST / 'Sources/set15_artwork.svg'
ARTWORK = SET / 'originals/en_jbs83nhsz6.webp'
TEMPLATE = ROOT / 'sets/Set_14_Hyperia_City/v1.5/Set_14_Hyperia_City_v1.5.3mf'
TITLE = 'Into the Inkdark'
DATE = '2026-11-22'
SOURCE_URL = 'https://disneylorcana.com/en/product/into-the-inkdark/'
SVG = {'s': 'http://www.w3.org/2000/svg'}
SETTINGS = 'Metadata/project_settings.config'
CONFIG = 'Metadata/model_settings.config'
MODEL = '3D/3dmodel.model'
COLORS = ('#152338', '#C9D5E0', '#21B7C7')
PART_NAMES = ('Deep Navy · backing and eyelet', 'Silver Gray · INTO THE', 'Teal · INKDARK')
GROUPS = ('into-the', 'inkdark')
WORD_PREFIXES = (('into-', 'the-'), ('inkdark-',))
SCALE = .115  # mm per source pixel
ORIGIN = (4.33, 32.7175)
HEIGHT, TOP = 2., 2.8
BORE_RADIUS, EYELET_RADIUS = 3.25, 5.25
EYELET = (EYELET_RADIUS, ORIGIN[1] - 154 * SCALE)
EXPECTED_COUNTERS = ('into-o', 'inkdark-d', 'inkdark-a')
BEAD_TOLERANCE = .075
SOURCE_SCRIPTS = ('rebuild_set15', 'full_height_narrow_rims', 'rebuild_set04', 'rebuild_set05',
                  'rebuild_set06', 'rebuild_set07', 'rebuild_set09', 'rebuild_set12',
                  'refine_loops_and_underline', 'repair_v1_1', 'standardize_loop_diameters',
                  'validate_bambu', 'validate_set06', 'validate_set09', 'validate_set12')


def artwork():
    """Undo the shared SVG sampler's Set 07 registration and set this logo's scale."""
    x0, y0 = registered((0., 0.))
    sx = SCALE / (registered((1., 0.))[0] - x0)
    sy = -SCALE / (registered((0., 1.))[1] - y0)
    transform = (sx, 0., 0., sy, ORIGIN[0] - sx * x0, ORIGIN[1] - sy * y0)

    def shape(path):
        outer, *holes = sample(path.get('d'))
        polygon = affine_transform(Polygon(outer, holes), transform)
        assert polygon.is_valid, path.get('id')
        return polygon

    svg = ET.parse(VECTOR).getroot()
    silhouette = shape(svg.find("s:g[@id='backing']/s:path", SVG))
    words = [{p.get('id'): shape(p) for p in svg.findall(f"s:g[@id='{group}']/s:path", SVG)}
             for group in GROUPS]
    return silhouette, words


def backing(silhouette):
    x, y = EYELET
    eyelet = Point(EYELET).buffer(EYELET_RADIUS, quad_segs=48)
    neck = box(x, y - 3.35, x + 6.45, y + 3.35)
    attachment = eyelet.union(neck)
    # Fillet the shoulder junctions near the loop. Keep the source's other corners.
    shoulder = box(x - 1, y - 6, x + 7, y + 6)
    joined = silhouette.union(attachment)
    local = joined.intersection(shoulder)
    fill = local.buffer(.65, quad_segs=12).buffer(-.65, quad_segs=12)
    outer = joined.union(fill).simplify(.008)
    bore = Point(EYELET).buffer(BORE_RADIUS, quad_segs=48)
    base = Polygon(outer.exterior, [bore.exterior])
    assert base.is_valid and not outer.interiors
    return base


def mesh_parts(template, silhouette, words):
    def contours(polygon):
        return orient([list(ring.coords)[:-1] for ring in (polygon.exterior, *polygon.interiors)])

    base = backing(silhouette)
    solids = [([base], 0., HEIGHT)]
    solids.extend((word.values(), HEIGHT, TOP - HEIGHT) for word in words)
    return [relief([contours(shape) for shape in shapes], z, height,
                   dict(part, name=name, color=color))
            for part, name, color, (shapes, z, height) in zip(
                template, PART_NAMES, COLORS, solids, strict=True)]


def project_settings(original):
    return dict(original, filament_colour=list(COLORS), filament_multi_colour=list(COLORS))


def export(parts, data, target, work):
    model = ET.fromstring(data[MODEL])
    for key, value in {'Title': TITLE, 'Source': SOURCE_URL, 'CreationDate': DATE,
                       'ModificationDate': DATE}.items():
        model.find(f"m:metadata[@name='{key}']", NS).text = value
    config = ET.fromstring(data[CONFIG])
    config.find("plate/metadata[@key='plater_name']").set('value', TITLE)
    for part, name in zip(config.findall('object/part'), PART_NAMES, strict=True):
        part.find("metadata[@key='name']").set('value', name)
    data[MODEL] = ET.tostring(model, encoding='utf-8', xml_declaration=True)
    data[CONFIG] = ET.tostring(config, encoding='utf-8', xml_declaration=True)
    data[SETTINGS] = json.dumps(project_settings(json.loads(data[SETTINGS])), indent=2).encode()
    template = work / 'template.3mf'
    with ZipFile(template, 'w', ZIP_DEFLATED) as archive:
        for key, value in data.items():
            archive.writestr(key, value)
    write_project(template, target, parts, {0, 1, 2},
                  'v1.0; silver-gray and teal title on a 2 mm navy backing; '
                  '6.5 mm bore and 10.5 mm nominal eyelet.')


def source_overlay(parts, target):
    """Register outlines from the saved 3MF over the original WebP."""
    with Image.open(ARTWORK) as original:
        image = Image.new('RGBA', (original.width + 46, original.height), '#676B72')
        image.alpha_composite(original.convert('RGBA'), (46, 0))
    factor = 3
    image = image.convert('RGB').resize((image.width * factor, image.height * factor),
                                       Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(image)
    for part, color in zip(parts, ('#FFAA58', '#FF72BB', '#FF72BB'), strict=True):
        for polygon in outlines(part):
            for ring in (polygon.exterior, *polygon.interiors):
                points = [(((x - ORIGIN[0]) / SCALE + 46) * factor,
                           (ORIGIN[1] - y) / SCALE * factor) for x, y in ring.coords]
                draw.line(points, fill=color, width=2, joint='curve')
    image.save(target)


def geometry_checks(project, template_settings, silhouette, words):
    data = package(project)
    parts = read_parts(data)
    assert json.loads(data[SETTINGS]) == project_settings(template_settings)
    assert [(p['slot'], p['color'], p['name']) for p in parts] == list(
        zip((1, 2, 3), COLORS, PART_NAMES, strict=True))
    stats = [dict(slot=p['slot'], name=p['name'], **mesh_stats(p)) for p in parts]
    assert all(part['degenerate_triangles'] == 0 for part in stats)
    assert [{v[2] for v in p['vertices']} for p in parts] == [{0., HEIGHT}, {HEIGHT, TOP}, {HEIGHT, TOP}]
    (base,), *raised = map(outlines, parts)
    assert base.is_valid and len(base.interiors) == 1
    assert base.symmetric_difference(backing(silhouette)).area < 1e-5
    bore = Polygon(base.interiors[0])
    assert all(abs(a - b - 2 * BORE_RADIUS) < 1e-6 for a, b in zip(bore.bounds[2:], bore.bounds[:2]))
    assert abs(base.bounds[0] - (EYELET[0] - EYELET_RADIUS)) < 1e-6

    glyphs = {}
    for word, actual in zip(words, raised, strict=True):
        assert len(word) == len(actual) == 7 and all(p.is_valid for p in actual)
        for name, expected in word.items():
            shape = min(actual, key=lambda p: p.centroid.distance(expected.centroid))
            assert shape.symmetric_difference(expected).area < 1e-5, name
            glyphs[name] = shape
    assert tuple(name for name, shape in glyphs.items() if shape.interiors) == EXPECTED_COUNTERS
    art = unary_union(list(glyphs.values()))
    clearance = min(a.distance(b) for a, b in combinations(glyphs.values(), 2))
    border = base.boundary.distance(art)
    assert base.covers(art) and border >= .45 and clearance >= .45, (border, clearance)
    return parts, base, bore, glyphs, dict(
        dimensions_mm=dimensions(parts), parts=stats, backing_height_mm=HEIGHT,
        bore_diameter_mm=2 * BORE_RADIUS, eyelet_diameter_nominal_mm=2 * EYELET_RADIUS,
        rim_nominal_mm=EYELET_RADIUS - BORE_RADIUS, bore_centre_mm=EYELET,
        minimum_backing_border_mm=round(border, 3), minimum_letter_gap_mm=round(clearance, 3),
        letters=len(glyphs), counters=EXPECTED_COUNTERS, fully_supported_relief=True)


def slice_checks(project, logs, parts, base, bore, glyphs):
    logs.mkdir()
    command = bambu_command() + ['--datadir', str(logs / 'settings'), '--debug', '2', '--info',
                                 '--slice', '1', '--outputdir', str(logs), str(project)]
    run = subprocess.run(command, cwd=logs, capture_output=True, text=True, timeout=180)
    log = run.stdout + run.stderr
    (logs / 'slice.log').write_text(log)
    assert run.returncode == 0 and 'manifold = yes' in log, log[-4000:]
    result = json.loads((logs / 'result.json').read_text())
    assert result['return_code'] == 0 and math.isclose(result['layer_height'], .2, abs_tol=1e-6)
    plate, = result['sliced_plates']
    assert plate['warning_message'] == ''
    assert [f['id'] for f in plate['filaments']] == [1, 2, 3]
    assert all(f['main_used_g'] > 0 for f in plate['filaments'])
    bbox = plate['objects'][0]['bbox']
    gcode = logs / 'plate_1.gcode'
    layers = read_toolpaths(gcode, bbox, 3)
    x, y = [pair[0] for pair in bounds(parts[0])[:2]]
    offsets = bbox['x'] - x, bbox['y'] - y
    toolpaths = toolpath_checks(layers, parts, bbox, {}, None, loop_height=HEIGHT,
                                bore_loop=list(bore.exterior.coords)[:-1])
    base_core = raster(base.buffer(-.30))
    bore_core = raster(bore.buffer(-.25))
    backing_layers = {}
    for z in (round(step * .2, 1) for step in range(1, 11)):
        drawn = deposit(layers[z], 0, *offsets)
        count, connected = regions(drawn)
        assert not np.any(drawn & bore_core), (z, 'filled bore')
        # Interior infill beads can fall just short of nominal contact at a wall.
        tolerant_count, _ = regions(dilate(drawn, BEAD_TOLERANCE, STEP))
        assert tolerant_count == 1, (z, count, tolerant_count)
        backing_layers[str(z)] = dict(components=count, components_with_bead_tolerance=tolerant_count,
                                      open_bore=True)
        if z in (.2, HEIGHT):
            assert count == 1, (z, count)
            fraction = coverage(dilate(connected, BEAD_TOLERANCE, STEP), base_core)
            assert fraction >= .995, (z, fraction)
            backing_layers[str(z)]['core_coverage'] = round(fraction, 5)

    expected_layers = [2.2, 2.4, 2.6, 2.8]
    relief_layers = {str(z): {} for z in expected_layers}
    for slot, prefixes in enumerate(WORD_PREFIXES, start=1):
        expected_word = {name: shape for name, shape in glyphs.items() if name.startswith(prefixes)}
        allowed = raster(unary_union(list(expected_word.values())).buffer(.20))
        cores = {name: raster(shape.buffer(-.18)) for name, shape in expected_word.items()}
        counters = {name: raster(Polygon(shape.interiors[0]).buffer(-.24))
                    for name, shape in expected_word.items() if shape.interiors}
        assert all(core.any() for core in counters.values())
        active = [z for z in sorted(layers) if any(t == slot for _, _, t in layers[z])]
        assert active == expected_layers, (slot, active)
        for z in active:
            drawn = deposit(layers[z], slot, *offsets)
            count, _ = regions(drawn)
            covered = dilate(drawn, BEAD_TOLERANCE, STEP)
            fractions = {name: round(coverage(covered, core), 5) for name, core in cores.items()}
            assert count == len(expected_word), (z, slot, count)
            assert min(fractions.values()) >= .99, (z, slot, fractions)
            assert not np.any(drawn & ~allowed), (z, slot, 'deposit outside its intended footprint')
            assert all(not np.any(drawn & hole) for hole in counters.values()), (z, slot, 'filled counter')
            relief_layers[str(z)][str(slot + 1)] = dict(
                letters=count, core_coverage=fractions, clear_counters=list(counters))
    for z in expected_layers:
        silver = deposit(layers[z], 1, *offsets)
        teal = deposit(layers[z], 2, *offsets)
        assert not np.any(silver & teal), (z, 'colors overlap')

    render_slice(layers, parts, bbox, [part['color'] for part in parts],
                 project.with_name(project.stem + '_sliced_preview.png'), loop_height=HEIGHT)
    toolpaths.update(backing_layers=backing_layers, relief_layers=relief_layers,
                     raster_step_mm=STEP, bead_edge_tolerance_mm=BEAD_TOLERANCE,
                     relief_colors_disjoint=True)
    return toolpaths, result, re.search(r'Current BambuStudio Version (\S+)', log).group(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=DEST)
    dest = parser.parse_args().output_dir.resolve()
    target = dest / (NAME + '.3mf')
    if target.exists():
        raise FileExistsError(target)

    data = package(TEMPLATE)
    template_settings = json.loads(data[SETTINGS])
    assert template_settings['printer_model'] == 'Bambu Lab A1'
    assert template_settings['nozzle_diameter'] == ['0.4'] and float(template_settings['layer_height']) == .2
    assert template_settings['wall_generator'] == 'arachne'
    silhouette, words = artwork()
    parts = mesh_parts(read_parts(data), silhouette, words)
    with tempfile.TemporaryDirectory(prefix='inkdark-build-') as directory:
        work = Path(directory)
        project = work / target.name
        export(parts, data, project, work)
        saved, base, bore, glyphs, geometry = geometry_checks(project, template_settings, silhouette, words)
        source_overlay(saved, work / (NAME + '_source_overlay.png'))
        isometric(saved, work / (NAME + '_isometric.png'))
        toolpaths, result, version = slice_checks(project, work / 'slice', saved, base, bore, glyphs)
        report = dict(project=target.name, project_sha256=digest(project), geometry=geometry,
                      toolpaths=toolpaths, bambu_studio=version,
                      plate_warning=result['sliced_plates'][0]['warning_message'],
                      physical_print_verified=False)
        (work / 'Validation_v1.0.json').write_text(json.dumps(report, indent=2) + '\n')

        sources = [VECTOR, *(ROOT / 'tools' / (name + '.py') for name in SOURCE_SCRIPTS)]
        snapshot = work / 'Source_snapshot.zip'
        with ZipFile(snapshot, 'w', ZIP_DEFLATED) as archive:
            for path in sources:
                archive.write(path, path.relative_to(ROOT))
        manifest = dict(input_sha256={str(path.relative_to(ROOT)): digest(path)
                                      for path in [TEMPLATE, ARTWORK, *sources]},
                        source_snapshot_sha256=digest(snapshot), project_sha256=digest(project))
        (work / 'Build_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')

        logs = dest / 'Slice'
        logs.mkdir(parents=True, exist_ok=True)
        for name in ('slice.log', 'result.json', 'plate_1.gcode'):
            shutil.copyfile(work / 'slice' / name, logs / name)
        for path in (*work.glob('*.png'), *work.glob('*.json'), snapshot):
            shutil.copyfile(path, dest / path.name)
        with project.open('rb') as built, target.open('xb') as final:
            shutil.copyfileobj(built, final)
    print(f'{target.name} · {geometry["dimensions_mm"]} mm · Bambu Studio {version}')


if __name__ == '__main__':
    main()
