#!/usr/bin/env python3
"""Verify the Wilds Unknown inlay meshes and audit each printed green stroke."""

import argparse
import json
import math
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from itertools import combinations
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

import rebuild_set12_v1_7 as build
from rebuild_set04 import area
from rebuild_set05 import dilate
from refine_loops_and_underline import read_toolpaths, render_slice, toolpath_checks
from repair_v1_1 import NS, read_parts
from standardize_loop_diameters import bounds, digest, mesh_stats, package
from validate_bambu import bambu_command
from validate_set09 import regions
from validate_set12 import SETTINGS, STEP, coverage, deposit, dimensions, outlines, pixel, raster

TOLERANCE = .075
STROKE_EDGE_TOLERANCE = .13
CENTERLINE_SAMPLE = .05


def horizontal_face(part, z, facing):
    triangles = []
    for face in part['faces']:
        points = [part['vertices'][i] for i in face]
        if all(abs(p[2] - z) < 1e-6 for p in points):
            xy = [p[:2] for p in points]
            if area(xy) * facing > 1e-10:
                triangles.append(Polygon(xy))
    return unary_union(triangles)


def check_geometry(project):
    before, after = package(build.SOURCE), package(project)
    old = read_parts(before)
    parts = read_parts(after)
    assert old[0] == parts[0]
    assert [p['color'] for p in parts] == [p['color'] for p in old]
    assert [p['slot'] for p in parts] == [1, 2, 3]
    assert before[SETTINGS] == after[SETTINGS]
    settings = json.loads(after[SETTINGS])
    assert settings['nozzle_diameter'] == ['0.4']
    assert settings['wall_generator'] == 'arachne' and float(settings['layer_height']) == .2
    for filename, element in (('3D/3dmodel.model', 'm:build'),
                              ('Metadata/model_settings.config', 'assemble')):
        assert ET.tostring(ET.fromstring(before[filename]).find(element, NS)) == ET.tostring(
            ET.fromstring(after[filename]).find(element, NS))
    assert [set(round(v[2], 6) for v in p['vertices']) for p in parts] == [
        {0., 2.}, {2., 2.6, 3.}, {2., 2.6, 3.}]

    old_green, green, ivory = old[1], parts[1], parts[2]
    assert green['faces'][:len(old_green['faces'])] == old_green['faces']
    assert np.allclose(green['vertices'][:len(old_green['vertices'])],
                       old_green['vertices'], atol=1e-7, rtol=0)
    stats = [dict(name=p['name'], slot=p['slot'], **mesh_stats(p)) for p in parts]
    assert all(s['degenerate_triangles'] == 0 for s in stats)
    assert abs(sum(s['volume_mm3'] for s in stats) -
               sum(mesh_stats(p)['volume_mm3'] for p in old)) < .002

    width, lines, groups = build.artwork()
    strokes = {name: shape for group in groups.values() for name, shape in group.items()}
    letters = build.glyph_footprints(old[2])
    assert len(strokes) == 26 and groups.keys() == letters.keys()
    stroke_gap = min(a.distance(b) for a, b in combinations(strokes.values(), 2))
    assert stroke_gap > 2 * STROKE_EDGE_TOLERANCE
    margin = min(letters[name].boundary.distance(shape)
                 for name, group in groups.items() for shape in group.values())
    assert margin >= build.MIN_IVORY_MARGIN
    field = unary_union(list(letters.values()))
    ink = unary_union(list(strokes.values()))
    assert field.contains(ink)
    for part, z, facing, expected in (
            (green, build.TOP, 1, ink),
            (green, build.INLAY_FLOOR, -1, ink),
            (ivory, build.INLAY_FLOOR, 1, ink),
            (ivory, build.TOP, 1, field.difference(ink)),
            (ivory, 2., -1, field)):
        assert horizontal_face(part, z, facing).symmetric_difference(expected).area < 1e-4

    report = dict(dimensions_mm=dimensions(parts), parts=stats,
                  nominal_stroke_width_mm=round(width, 4), stroke_count=len(strokes),
                  strokes_per_letter={name: len(group) for name, group in groups.items()},
                  narrowest_ivory_margin_mm=round(margin, 4),
                  minimum_stroke_gap_mm=round(stroke_gap, 4),
                  inlay_depth_mm=round(build.TOP - build.INLAY_FLOOR, 4),
                  ivory_support_thickness_mm=round(build.INLAY_FLOOR - 2., 4),
                  face_and_inlays_flush=True, backing_and_foliage_geometry_preserved=True,
                  letter_footprint_preserved=True, plate_placement_preserved=True,
                  embedded_settings_byte_identical=True)
    return parts, old_green, lines, strokes, letters, report


def check_toolpaths(project, logs, plate, parts, old_green, lines, strokes, letters):
    bbox = plate['objects'][0]['bbox']
    layers = read_toolpaths(logs / 'plate_1.gcode', bbox, 3)
    bb = bounds(parts[0])
    offsets = bbox['x'] - bb[0][0], bbox['y'] - bb[1][0]
    bore = build.baseline.bore_loop(parts[0])
    report = toolpath_checks(layers, parts, bbox, {}, None, loop_height=2., bore_loop=bore)
    report['raster_step_mm'] = STEP
    report['green_edge_audit_tolerance_mm'] = STROKE_EDGE_TOLERANCE
    report['bead_coverage_tolerance_mm'] = TOLERANCE

    field = unary_union(list(letters.values()))
    ink = unary_union(list(strokes.values()))
    leaf_field = unary_union(outlines(old_green))
    active_green = [z for z, paths in sorted(layers.items()) if any(t == 1 for _, _, t in paths)]
    assert active_green == [2.2, 2.4, 2.6, 2.8, 3.]
    foliage_allowed = raster(leaf_field.buffer(.18))
    whole_core = raster(field.buffer(-.13))
    lower_layers = {}
    for z in (2.2, 2.4, 2.6):
        green = deposit(layers[z], 1, *offsets)
        ivory = deposit(layers[z], 2, *offsets)
        foliage_count, glyph_count = regions(green)[0], regions(ivory)[0]
        assert foliage_count == 6 and glyph_count == 12 and not np.any(green & ~foliage_allowed)
        assert coverage(dilate(ivory, TOLERANCE, STEP), whole_core) >= .995
        lower_layers[str(z)] = dict(foliage_components=foliage_count, ivory_components=glyph_count)
    report['lower_relief_layers'] = lower_layers

    allowed = raster(ink.buffer(STROKE_EDGE_TOLERANCE))
    inlay_cores = {name: raster(shape.buffer(-.105)) for name, shape in strokes.items()}
    ivory_cores = {name: raster(glyph.difference(ink).buffer(-.12))
                   for name, glyph in letters.items()}
    counters = [raster(Polygon(hole).buffer(-.25))
                for glyph in letters.values() for hole in glyph.interiors]
    samples = {}
    for name, line in lines.items():
        points = [pixel(line.interpolate(d).coords[0])
                  for d in np.linspace(0., line.length, math.ceil(line.length / CENTERLINE_SAMPLE) + 1)]
        samples[name] = tuple(zip(*((round(y), round(x)) for x, y in points)))

    inlay_layers = {}
    for z in (2.8, 3.):
        green = deposit(layers[z], 1, *offsets)
        ivory = deposit(layers[z], 2, *offsets)
        green_count, ivory_count = regions(green)[0], regions(ivory)[0]
        assert green_count == len(strokes) and ivory_count == len(letters), (z, green_count, ivory_count)
        assert not np.any(green & ~allowed), (z, 'green outside inlays')
        assert all(not np.any((green | ivory) & counter) for counter in counters)
        green_covered = dilate(green, TOLERANCE, STEP)
        ivory_covered = dilate(ivory, TOLERANCE, STEP)
        green_report = {}
        for name, core in inlay_cores.items():
            raw_fraction = coverage(green, core)
            center = green_covered[samples[name]]
            assert center.all() and raw_fraction >= .98, (z, name, raw_fraction)
            green_report[name] = dict(raw_core_coverage=round(raw_fraction, 5),
                                      centerline_samples=len(center), centerline_complete=True)
        ivory_coverage = {name: round(coverage(ivory_covered, core), 5)
                          for name, core in ivory_cores.items()}
        combined = coverage(green_covered | ivory_covered, whole_core)
        assert min(ivory_coverage.values()) >= .995 and combined >= .998
        inlay_layers[str(z)] = dict(green_components=green_count, ivory_components=ivory_count,
                                    green_outside_intended_strokes=0, clear_counters=len(counters),
                                    inlays=green_report, ivory_core_coverage=ivory_coverage,
                                    combined_glyph_core_coverage=round(combined, 5))
    report['inlay_layers'] = inlay_layers

    # Include the foliage's actual top layer along with the taller green inlays.
    render_slice(layers, parts + [old_green], bbox, [p['color'] for p in parts],
                 project.with_name(project.stem + '_sliced_preview.png'), loop_height=2.)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=build.DEST / (build.NAME + '.3mf'))
    args = parser.parse_args()
    project = args.project.resolve()
    base = build.baseline
    logs = (base.ROOT / 'validation' / base.SET.name / build.VERSION
            if project.parent == build.DEST else project.parent / 'validation')
    *details, geometry = check_geometry(project)
    logs.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='wilds-inlay-') as work:
        run = subprocess.run(bambu_command() + ['--datadir', str(Path(work) / 'settings'),
                             '--debug', '2', '--info', '--slice', '1', '--outputdir',
                             str(logs), str(project)], cwd=work, capture_output=True,
                             text=True, timeout=180)
    log = run.stdout + run.stderr
    (logs / 'slice.log').write_text(log)
    assert run.returncode == 0 and 'manifold = yes' in log, log[-4000:]
    sliced = json.loads((logs / 'result.json').read_text())
    assert sliced['return_code'] == 0 and math.isclose(sliced['layer_height'], .2, abs_tol=1e-6)
    plate = sliced['sliced_plates'][0]
    assert plate['warning_message'] == ''
    assert [f['id'] for f in plate['filaments']] == [1, 2, 3]
    assert all(f['main_used_g'] > 0 for f in plate['filaments'])
    toolpaths = check_toolpaths(project, logs, plate, *details)
    report = dict(project=project.name, output_sha256=digest(project),
                  baseline=str(build.SOURCE.relative_to(base.ROOT)),
                  baseline_sha256=digest(build.SOURCE), geometry=geometry, toolpaths=toolpaths,
                  bambu_version=re.search(r'Current BambuStudio Version (\S+)', log).group(1),
                  plate_warnings=plate['warning_message'],
                  estimated_print_minutes=round(plate['total_predication'] / 60, 1),
                  filament_changes=plate['filament_change_times'], physical_print_verified=False)
    (project.parent / ('Validation_' + build.VERSION + '.json')).write_text(
        json.dumps(report, indent=2) + '\n')
    print(f"{project.name} · all 26 strokes continuous on both inlay layers")


if __name__ == '__main__':
    main()
