#!/usr/bin/env python3
"""Validate the saved Set 13 mesh and its Bambu Studio toolpaths."""

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
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

import rebuild_set13 as build
from rebuild_set05 import dilate
from refine_loops_and_underline import read_toolpaths, render_slice, toolpath_checks
from repair_v1_1 import NS, read_parts
from standardize_loop_diameters import bounds, centre, digest, mesh_stats, package
from validate_bambu import bambu_command
from validate_set09 import regions
from validate_set12 import STEP, coverage, deposit, dimensions, outlines, raster

EXPECTED_COUNTERS = ('attack-a1', 'attack-a2', 'of-o')


def geometry_checks(project):
    before, after = package(build.SOURCE), package(project)
    old, parts = read_parts(before), read_parts(after)
    settings = json.loads(after[build.SETTINGS])
    assert settings == build.filament_settings(json.loads(before[build.SETTINGS]))
    assert settings['nozzle_diameter'] == ['0.4'] and settings['wall_generator'] == 'arachne'
    assert float(settings['layer_height']) == .2
    for path, key in ((build.MODEL, 'm:build'), (build.CONFIG, 'assemble')):
        assert ET.tostring(ET.fromstring(before[path]).find(key, NS)) == ET.tostring(
            ET.fromstring(after[path]).find(key, NS))
    lime_part = ET.fromstring(after[build.CONFIG]).find("object/part[@id='2']")
    for key in build.LIME_WIDTH_SETTINGS:
        assert float(lime_part.find(f"metadata[@key='{key}']").get('value')) == build.LIME_LINE_WIDTH
    assert [(p['slot'], p['color']) for p in parts] == [(1, old[0]['color']), (2, build.LIME)]
    stats = [dict(name=p['name'], slot=p['slot'], **mesh_stats(p)) for p in parts]
    assert all(s['degenerate_triangles'] == 0 for s in stats)
    assert [{v[2] for v in p['vertices']} for p in parts] == [
        {0., build.BACKING_HEIGHT}, {build.BACKING_HEIGHT, build.TOP}]

    (base,), lettering = map(outlines, parts)
    bore = build.bore_loop(parts[0])
    assert len(base.interiors) == 1 and sorted(bore) == sorted(build.bore_loop(old[0]))
    assert base.is_valid and all(p.is_valid for p in lettering)
    glyphs = build.artwork()
    artwork = unary_union(list(glyphs.values()))
    assert len(lettering) == len(glyphs) == 17
    assert unary_union(lettering).symmetric_difference(artwork).area < 1e-5
    assert tuple(name for name, p in glyphs.items() if p.interiors) == EXPECTED_COUNTERS
    assert sum(len(p.interiors) for p in lettering) == len(EXPECTED_COUNTERS)
    border = base.boundary.distance(artwork)
    gap = min(a.distance(b) for a, b in combinations(lettering, 2))
    assert base.covers(artwork) and border >= 1.09 and gap >= .45
    original_outline, = outlines(old[0])
    assert all(abs(a - b) < .25 for a, b in zip(dimensions(old), dimensions(parts)))
    data = dict(parts=stats, dimensions_before_mm=dimensions(old), dimensions_mm=dimensions(parts),
                backing_area_before_mm2=round(original_outline.area, 3), backing_area_mm2=round(base.area, 3),
                backing_connected_components=1, backing_openings=1, backing_height_mm=build.BACKING_HEIGHT,
                bore_centre_mm=centre(bore), bore_diameter_mm=6.5, bore_coordinates_exactly_preserved=True,
                eyelet_outer_diameter_nominal_mm=10.5, minimum_letter_gap_mm=round(gap, 3),
                minimum_backing_border_mm=round(border, 3), counters=EXPECTED_COUNTERS,
                letter_count=len(lettering) - 2, punctuation_components=2, fully_supported_relief=True,
                lime_line_width_override_mm=build.LIME_LINE_WIDTH, plate_placement_preserved=True)
    return parts, base, bore, glyphs, data


def slice_checks(project, logs, parts, base, bore, glyphs, plate):
    bbox = plate['objects'][0]['bbox']
    layers = read_toolpaths(logs / 'plate_1.gcode', bbox, 2)
    bb = bounds(parts[0])
    offsets = bbox['x'] - bb[0][0], bbox['y'] - bb[1][0]
    result = toolpath_checks(layers, parts, bbox, {}, None, loop_height=build.BACKING_HEIGHT, bore_loop=bore)
    result.update(raster_step_mm=STEP, bead_edge_tolerance_mm=.075, backing_layers={}, lime_layers={})
    base_core = raster(base.buffer(-.30))
    bore_core = raster(Polygon(bore).buffer(-.25))
    for z in (.2, 2.):
        backing = deposit(layers[z], 0, *offsets)
        count, connected = regions(backing)
        fraction = coverage(dilate(connected, .075, STEP), base_core)
        assert count == 1 and fraction >= .995 and not np.any(backing & bore_core), (z, count, fraction)
        result['backing_layers'][str(z)] = dict(
            components=count, core_coverage=round(fraction, 5), open_bore=True)

    artwork = unary_union(list(glyphs.values()))
    allowed = raster(artwork.buffer(.18))
    cores = {name: raster(shape.buffer(-.17)) for name, shape in glyphs.items()}
    # Isolate the curled portion to check it independently of the large A.
    curl = glyphs['attack-a1'].buffer(-.17).intersection(box(12., 25.5, 17.4, 34.))
    cores['tendril'] = raster(curl)
    counters = {name: raster(Polygon(glyphs[name].interiors[0]).buffer(-.25))
                for name in EXPECTED_COUNTERS}
    assert all(core.any() for core in counters.values())
    active = [z for z, paths in sorted(layers.items()) if any(t == 1 for _, _, t in paths)]
    assert active == [2.2, 2.4, 2.6, 2.8], active
    for z in active:
        drawn = deposit(layers[z], 1, *offsets)
        count, _ = regions(drawn)
        covered = dilate(drawn, .075, STEP)
        fractions = {name: round(coverage(covered, core), 5) for name, core in cores.items()}
        assert count == len(glyphs), (z, count)
        assert min(fractions.values()) >= .99, (z, fractions)
        assert not np.any(drawn & ~allowed), (z, 'lime outside its intended footprint')
        assert all(not np.any(drawn & hole) for hole in counters.values()), (z, 'filled counter')
        result['lime_layers'][str(z)] = dict(
            components=count, core_coverage=fractions, clear_counters=list(counters))
    render_slice(layers, parts, bbox, [p['color'] for p in parts],
                 project.with_name(project.stem + '_sliced_preview.png'), loop_height=build.BACKING_HEIGHT)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=build.DEST / (build.NAME + '.3mf'))
    project = parser.parse_args().project.resolve()
    logs = (build.ROOT / 'validation' / build.SET.name / build.VERSION
            if project.parent == build.DEST else project.parent / 'validation')
    parts, base, bore, glyphs, geometry = geometry_checks(project)
    logs.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='vine-slicer-') as work:
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
    assert [f['id'] for f in plate['filaments']] == [1, 2]
    assert all(f['main_used_g'] > 0 for f in plate['filaments'])
    toolpaths = slice_checks(project, logs, parts, base, bore, glyphs, plate)
    report = dict(project=project.name, output_sha256=digest(project),
                  baseline=str(build.SOURCE.relative_to(build.ROOT)), baseline_sha256=digest(build.SOURCE),
                  geometry=geometry, toolpaths=toolpaths,
                  bambu_version=re.search(r'Current BambuStudio Version (\S+)', log).group(1),
                  plate_warnings=plate['warning_message'], physical_print_verified=False)
    (project.parent / ('Validation_' + build.VERSION + '.json')).write_text(
        json.dumps(report, indent=2) + '\n')
    print(f"{project.name} · {geometry['dimensions_mm']} mm · Bambu Studio {report['bambu_version']}")


if __name__ == '__main__':
    main()
