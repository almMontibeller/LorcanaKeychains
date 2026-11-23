#!/usr/bin/env python3
"""Validate the Set 14 export and its A1 0.4 mm toolpaths."""

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
from shapely import maximum_inscribed_circle
from shapely.geometry import Polygon
from shapely.ops import unary_union

import rebuild_set14 as build
from rebuild_set05 import dilate
from refine_loops_and_underline import read_toolpaths, render_slice, toolpath_checks
from repair_v02 import NS, read_parts
from standardize_loop_diameters import bounds, centre, digest, mesh_stats, package
from validate_bambu import bambu_command
from validate_set09 import regions
from validate_set12 import STEP, coverage, deposit, dimensions, outlines, raster

COUNTERS = ('hyperia-p', 'hyperia-r', 'hyperia-a')
EDGE_TOLERANCE = .075


def geometry_checks(project):
    before, after = package(build.SOURCE), package(project)
    old, parts = read_parts(before), read_parts(after)
    settings = json.loads(after[build.SETTINGS])
    assert settings == build.filament_settings(json.loads(before[build.SETTINGS]))
    assert settings['printer_model'] == 'Bambu Lab A1'
    assert settings['nozzle_diameter'] == ['0.4'] and settings['wall_generator'] == 'arachne'
    assert float(settings['layer_height']) == .2
    for path, key in ((build.MODEL, 'm:build'), (build.CONFIG, 'assemble')):
        assert ET.tostring(ET.fromstring(before[path]).find(key, NS)) == ET.tostring(
            ET.fromstring(after[path]).find(key, NS))
    assert [p['slot'] for p in parts] == [1, 2, 3, 4]
    assert [p['color'] for p in parts] == [p['color'] for p in old] + [build.ICE_BLUE]
    stats = [dict(name=p['name'], slot=p['slot'], **mesh_stats(p)) for p in parts]
    assert all(s['degenerate_triangles'] == 0 for s in stats)
    assert [{round(v[2], 6) for v in p['vertices']} for p in parts] == [
        {0., 2.}, {2., 2.4}, {2.6, 3.}, {2.4, 2.6}]

    (base,), (caramel,), ivory, (blue,) = map(outlines, parts)
    bore = build.bore_loop(parts[0])
    assert sorted(bore) == sorted(build.bore_loop(old[0]))
    bore_centre = centre(bore)
    radial_rim = [math.dist(p, bore_centre) - 3.25
                  for p in base.exterior.coords if p[0] <= bore_centre[0]]
    assert 1.99 <= min(radial_rim) <= max(radial_rim) <= 2.01
    assert len(base.interiors) == 1
    assert all(p.is_valid for p in (base, caramel, blue, *ivory))
    glyphs = build.artwork()
    lettering = unary_union(list(glyphs.values()))
    assert len(ivory) == len(glyphs) == 11
    assert unary_union(ivory).symmetric_difference(lettering).area < 1e-5
    assert tuple(name for name, p in glyphs.items() if p.interiors) == COUNTERS
    assert sum(len(p.interiors) for p in ivory) == len(COUNTERS)
    gap = min(a.distance(b) for a, b in combinations(ivory, 2))
    rim = base.boundary.distance(caramel)
    assert gap >= .45 and rim >= .48
    assert base.covers(caramel) and caramel.covers(blue) and blue.covers(lettering)
    assert all(abs(a - b) < .25 for a, b in zip(dimensions(old), dimensions(parts)))

    windows = {}
    for name in COUNTERS:
        opening = Polygon(glyphs[name].interiors[0])
        window = opening.difference(blue)
        diameter = 2 * maximum_inscribed_circle(window).length
        assert window.geom_type == 'Polygon' and diameter >= .45 and caramel.covers(window)
        windows[name] = window
    report = dict(parts=stats, dimensions_before_mm=dimensions(old), dimensions_mm=dimensions(parts),
                  backing_connected_components=1, backing_height_mm=2., bore_diameter_mm=6.5,
                  bore_centre_mm=bore_centre, bore_coordinates_exactly_preserved=True,
                  eyelet_outer_diameter_nominal_mm=10.5,
                  outer_eyelet_sampled_rim_width_mm=[round(min(radial_rim), 3), round(max(radial_rim), 3)],
                  backing_margin_mm=round(rim, 3),
                  minimum_letter_gap_mm=round(gap, 3), letters=list(glyphs), counters=list(windows),
                  blue_outer_band_mm=build.BLUE_WIDTH, blue_counter_band_mm=build.COUNTER_BLUE_WIDTH,
                  counter_window_diameters_mm={
                      name: round(2 * maximum_inscribed_circle(p).length, 3) for name, p in windows.items()},
                  fully_supported_relief=True, plate_transform_preserved=True)
    return parts, base, bore, caramel, blue, glyphs, windows, report


def deposited_coverage(mask, shapes):
    expanded = dilate(mask, EDGE_TOLERANCE, STEP)
    return {name: round(coverage(expanded, raster(shape)), 5) for name, shape in shapes.items()}


def slice_checks(project, logs, plate, parts, base, bore, caramel, blue, glyphs, windows):
    bbox = plate['objects'][0]['bbox']
    layers = read_toolpaths(logs / 'plate_1.gcode', bbox, len(parts))
    bb = bounds(parts[0])
    offsets = bbox['x'] - bb[0][0], bbox['y'] - bb[1][0]
    result = toolpath_checks(layers, parts, bbox, {}, None, loop_height=2., bore_loop=bore)
    result.update(raster_step_mm=STEP, bead_edge_tolerance_mm=EDGE_TOLERANCE)
    active = {slot: [z for z, paths in sorted(layers.items()) if any(t == slot for _, _, t in paths)]
              for slot in range(4)}
    assert active == {0: [round(i * .2, 1) for i in range(1, 11)],
                      1: [2.2, 2.4], 2: [2.8, 3.], 3: [2.6]}, active
    result['active_layers_by_colour'] = {p['name']: active[i] for i, p in enumerate(parts)}

    result['backing_layers'] = {}
    bore_core = raster(Polygon(bore).buffer(-.25))
    for z in active[0]:
        raw = deposit(layers[z], 0, *offsets)
        assert not np.any(raw & bore_core), (z, 'blocked bore')
        if z not in (.2, 2.):
            continue
        count, connected = regions(raw)
        fraction = deposited_coverage(connected, {'backing': base.buffer(-.30)})['backing']
        assert count == 1 and fraction >= .995, (z, count, fraction)
        result['backing_layers'][str(z)] = dict(components=count, core_coverage=fraction, open_bore=True)
    result['bore_clear_on_all_backing_layers'] = True

    result['caramel_layers'] = {}
    for z in active[1]:
        drawn = deposit(layers[z], 1, *offsets)
        count, connected = regions(drawn)
        fractions = deposited_coverage(connected, {'caramel': caramel.buffer(-.23), **windows})
        assert count == 1 and min(fractions.values()) >= .995, (z, count, fractions)
        result['caramel_layers'][str(z)] = dict(components=count, core_coverage=fractions)

    blue_drawn = deposit(layers[2.6], 3, *offsets)
    blue_count, blue_connected = regions(blue_drawn)
    blue_core = blue.buffer(-.15)
    letter_bands = {}
    for name, glyph in glyphs.items():
        shell = Polygon(glyph.exterior)
        band = shell.buffer(.31).difference(shell.buffer(.19)).intersection(blue_core)
        letter_bands[name] = band
        if name in COUNTERS:
            opening = Polygon(glyph.interiors[0])
            band = opening.buffer(-.17).difference(opening.buffer(-.28)).intersection(blue_core)
            letter_bands[name + '-counter-rim'] = band
    fractions = deposited_coverage(blue_connected, {'blue': blue_core, **letter_bands})
    assert blue_count == 1 and min(fractions.values()) >= .995, (blue_count, fractions)
    assert all(not np.any(blue_drawn & raster(p.buffer(-.16))) for p in windows.values())
    result['blue_layer'] = dict(z_mm=2.6, components=blue_count, core_coverage=fractions,
                                clear_counter_windows=list(windows))

    result['ivory_layers'] = {}
    ivory_cores = {name: p.buffer(-.17) for name, p in glyphs.items()}
    for z in active[2]:
        drawn = deposit(layers[z], 2, *offsets)
        count, _ = regions(drawn)
        fractions = deposited_coverage(drawn, ivory_cores)
        assert count == len(glyphs) and min(fractions.values()) >= .995, (z, count, fractions)
        assert all(not np.any(drawn & raster(p.buffer(-.15))) for p in windows.values())
        result['ivory_layers'][str(z)] = dict(components=count, core_coverage=fractions,
                                              clear_counters=list(windows))

    render_slice(layers, parts, bbox, [p['color'] for p in parts],
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
    assert [f['id'] for f in plate['filaments']] == [1, 2, 3, 4]
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
