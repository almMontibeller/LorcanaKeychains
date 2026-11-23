#!/usr/bin/env python3
"""Verify the tapered blue bands in the saved Hyperia City A1 project."""

import argparse
import json
import math
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

import rebuild_set14_v09 as build
from refine_loops_and_underline import read_toolpaths, render_slice, toolpath_checks
from repair_v02 import NS, read_parts
from standardize_loop_diameters import bounds, digest, mesh_stats, package
from validate_bambu import bambu_command
from validate_set09 import regions
from validate_set12 import STEP, deposit, dimensions, outlines, raster
from validate_set14 import COUNTERS, EDGE_TOLERANCE, deposited_coverage


def geometry_checks(project):
    before, after = package(build.SOURCE), package(project)
    old, parts = read_parts(before), read_parts(after)
    assert parts[:2] == old[:2] and dimensions(parts) == dimensions(old)
    assert [p['slot'] for p in parts] == [1, 2, 3]
    assert [p['color'] for p in parts] == [p['color'] for p in old]
    assert before[build.previous.SETTINGS] == after[build.previous.SETTINGS]
    settings = json.loads(after[build.previous.SETTINGS])
    assert settings['printer_model'] == 'Bambu Lab A1'
    assert settings['nozzle_diameter'] == ['0.4'] and settings['wall_generator'] == 'arachne'
    assert float(settings['layer_height']) == .2
    for path, key in ((build.previous.MODEL, 'm:build'), (build.previous.CONFIG, 'assemble')):
        assert ET.tostring(ET.fromstring(before[path]).find(key, NS)) == ET.tostring(
            ET.fromstring(after[path]).find(key, NS))
    config = ET.fromstring(after[build.previous.CONFIG])
    width_part = config.find("object/part/metadata[@key='extruder'][@value='3']/..")
    for key in build.WIDTH_SETTINGS:
        assert float(width_part.find(f"metadata[@key='{key}']").get('value')) == build.BLUE_LINE_WIDTH
    stats = [dict(name=p['name'], slot=p['slot'], **mesh_stats(p)) for p in parts]
    assert all(s['degenerate_triangles'] == 0 for s in stats)
    assert [{round(v[2], 6) for v in p['vertices']} for p in parts] == [
        {0., 2.}, {2., 2.8}, {2.8, 3.}]

    (base,), letters, blue = map(outlines, parts)
    expected_letters = build.original.artwork()
    expected_blue = build.highlights(expected_letters)
    ivory_area, blue_area = unary_union(letters), unary_union(blue)
    assert len(letters) == len(expected_letters) == 11
    assert len(blue) == len(expected_blue) == 18
    assert len(base.interiors) == 1 and base.covers(ivory_area)
    assert all(p.is_valid for p in [base, *letters, *blue])
    assert blue_area.difference(ivory_area).area < 1e-8
    assert blue_area.symmetric_difference(unary_union(list(expected_blue.values()))).area < 1e-5
    counters = {name: Polygon(expected_letters[name].interiors[0]) for name in COUNTERS}
    assert sum(len(p.interiors) for p in letters) == len(counters)
    report = dict(parts=stats, dimensions_mm=dimensions(parts),
                  backing_height_mm=2., bore_diameter_mm=6.5, eyelet_outer_diameter_nominal_mm=10.5,
                  backing_and_letter_meshes_match_v08=True, filament_and_process_settings_match_v08=True,
                  blue_part_line_width_override_mm=build.BLUE_LINE_WIDTH,
                  letters=list(expected_letters), counters=list(counters), blue_accents=list(expected_blue),
                  blue_area_before_mm2=round(unary_union(outlines(old[2])).area, 3),
                  blue_area_mm2=round(blue_area.area, 3), fully_supported_relief=True,
                  plate_transform_preserved=True)
    return parts, base, expected_letters, expected_blue, counters, report


def bead_footprint(paths, slot, dx, dy):
    # Evaluate connectivity in millimetres to avoid counting a diagonal
    # raster pixel at a curve as a separate piece of extruded filament.
    return unary_union([LineString([(x - dx, y - dy) for x, y in points]).buffer(width / 2)
                        for points, width, tool in paths if tool == slot])


def slice_checks(project, logs, plate, parts, base, letters, blue, counters):
    bbox = plate['objects'][0]['bbox']
    layers = read_toolpaths(logs / 'plate_1.gcode', bbox, len(parts))
    bb = bounds(parts[0])
    offsets = bbox['x'] - bb[0][0], bbox['y'] - bb[1][0]
    bore = build.original.bore_loop(parts[0])
    result = toolpath_checks(layers, parts, bbox, {}, None, loop_height=2., bore_loop=bore)
    active = {i: [z for z, paths in sorted(layers.items()) if any(t == i for _, _, t in paths)]
              for i in range(len(parts))}
    assert active == {0: [round(i * .2, 1) for i in range(1, 11)],
                      1: [2.2, 2.4, 2.6, 2.8], 2: [3.]}, active
    result.update(raster_step_mm=STEP, bead_edge_tolerance_mm=EDGE_TOLERANCE,
                  active_layers_by_colour={p['name']: active[i] for i, p in enumerate(parts)})

    bore_core = raster(Polygon(bore).buffer(-.25))
    result['backing_layers'] = {}
    for z in active[0]:
        raw = deposit(layers[z], 0, *offsets)
        assert not np.any(raw & bore_core), (z, 'blocked bore')
        if z in (.2, 2.):
            count, backing = regions(raw)
            coverage = deposited_coverage(backing, {'backing': base.buffer(-.30)})['backing']
            assert count == 1 and coverage >= .995, (z, count, coverage)
            result['backing_layers'][str(z)] = dict(components=count, core_coverage=coverage)
    result['bore_clear_on_all_layers'] = True

    openings = {name: raster(p.buffer(-.24)) for name, p in counters.items()}
    assert all(mask.any() for mask in openings.values())
    result['ivory_layers'] = {}
    for slot, designs, threshold in ((1, letters, .995), (2, blue, .99)):
        footprint = unary_union(list(designs.values()))
        allowed = raster(footprint.buffer(.16))
        cores = {name: p.buffer(-.16) for name, p in designs.items()}
        for z in active[slot]:
            mask = deposit(layers[z], slot, *offsets)
            beads = bead_footprint(layers[z], slot, *offsets)
            components = len(build.original.polygons(beads))
            coverage = deposited_coverage(mask, cores)
            assert components == len(designs) and min(coverage.values()) >= threshold, (
                z, components, coverage)
            assert not np.any(mask & ~allowed), (z, 'extrusion outside the intended design')
            assert all(not np.any(mask & opening) for opening in openings.values())
            audit = dict(components=components, core_coverage=coverage, clear_counters=list(openings))
            if slot == 1:
                result['ivory_layers'][str(z)] = audit
            else:
                result['blue_layer'] = dict(z_mm=z, **audit)

    visible = {zs[-1]: [path for height in zs for path in layers[height]] for zs in active.values()}
    render_slice(visible, parts, bbox, [p['color'] for p in parts],
                 project.with_name(project.stem + '_sliced_preview.png'), loop_height=2.)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=build.DEST / (build.NAME + '.3mf'))
    project = parser.parse_args().project.resolve()
    logs = (build.ROOT / 'validation' / build.SET.name / build.VERSION
            if project.parent == build.DEST else project.parent / 'validation')
    *geometry, report = geometry_checks(project)
    logs.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='hyperia-slicer-') as work:
        run = subprocess.run(bambu_command() + ['--datadir', work, '--debug', '2', '--info',
                             '--slice', '1', '--outputdir', str(logs), str(project)],
                             cwd=logs, capture_output=True, text=True, timeout=180)
    log = run.stdout + run.stderr
    (logs / 'slice.log').write_text(log)
    assert run.returncode == 0 and 'manifold = yes' in log, log[-4000:]
    sliced = json.loads((logs / 'result.json').read_text())
    assert sliced['return_code'] == 0 and math.isclose(sliced['layer_height'], .2, abs_tol=1e-6)
    plate = sliced['sliced_plates'][0]
    assert plate['warning_message'] == ''
    assert [f['id'] for f in plate['filaments']] == [1, 2, 3]
    assert all(f['main_used_g'] > 0 for f in plate['filaments'])
    toolpaths = slice_checks(project, logs, plate, *geometry)
    result = dict(project=project.name, output_sha256=digest(project),
                  baseline=str(build.SOURCE.relative_to(build.ROOT)), baseline_sha256=digest(build.SOURCE),
                  geometry=report, toolpaths=toolpaths,
                  bambu_version=re.search(r'Current BambuStudio Version (\S+)', log).group(1),
                  plate_warnings=plate['warning_message'], physical_print_verified=False)
    (project.parent / ('Validation_' + build.VERSION + '.json')).write_text(
        json.dumps(result, indent=2) + '\n')
    print(f"{project.name} · {report['dimensions_mm']} mm · Bambu Studio {result['bambu_version']}")


if __name__ == '__main__':
    main()
