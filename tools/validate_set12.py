#!/usr/bin/env python3
"""Check Wilds Unknown v07 mesh, colour separation and Bambu Studio toolpaths."""

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
from PIL import Image, ImageDraw
from shapely.geometry import Polygon
from shapely.ops import unary_union

import rebuild_set12 as build
from rebuild_set04 import area, boundary_loops, orient
from rebuild_set05 import dilate
from refine_loops_and_underline import draw_bead, read_toolpaths, render_slice, toolpath_checks
from repair_v02 import NS, read_parts
from standardize_loop_diameters import bounds, centre, digest, mesh_stats, package
from validate_bambu import bambu_command
from validate_set09 import regions

STEP = .025
SIZE = (3440, 1760)
ORIGIN = (-1., 43.)
SETTINGS = 'Metadata/project_settings.config'


def outlines(part):
    loops = orient(boundary_loops(part))
    shells = [Polygon(c) for c in loops if area(c) > 0]
    holes = [c for c in loops if area(c) < 0]
    return [Polygon(s.exterior, [h for h in holes if s.contains(Polygon(h))]) for s in shells]


def dimensions(parts):
    width, depth = [round(high - low, 3) for low, high in bounds(parts[0])[:2]]
    height = max(bounds(p)[2][1] for p in parts) - min(bounds(p)[2][0] for p in parts)
    return [width, depth, round(height, 3)]


def geometry_checks(project):
    before, after = package(build.SOURCE), package(project)
    old, parts = read_parts(before), read_parts(after)
    assert before[SETTINGS] == after[SETTINGS]
    settings = json.loads(after[SETTINGS])
    assert settings['nozzle_diameter'] == ['0.4'] and settings['wall_generator'] == 'arachne'
    assert float(settings['layer_height']) == .2
    for filename, element in (('3D/3dmodel.model', 'm:build'),
                              ('Metadata/model_settings.config', 'assemble')):
        assert ET.tostring(ET.fromstring(before[filename]).find(element, NS)) == ET.tostring(
            ET.fromstring(after[filename]).find(element, NS))
    assert [p['slot'] for p in parts] == [1, 2, 3]
    assert [p['color'] for p in parts] == [p['color'] for p in old]
    stats = [dict(name=p['name'], slot=p['slot'], **mesh_stats(p)) for p in parts]
    assert all(s['degenerate_triangles'] == 0 for s in stats)
    assert [{round(v[2], 6) for v in p['vertices']} for p in parts] == [
        set(z) for z in build.Z_EXTENTS]

    (base,), leaves, letters = map(outlines, parts)
    assert len(base.interiors) == 1 and len(leaves) == 6 and len(letters) == 12
    assert all(p.is_valid for p in [base, *leaves, *letters])
    bore = build.bore_loop(parts[0])
    assert sorted(bore) == sorted(build.bore_loop(old[0]))
    relief = [*leaves, *letters]
    margin = base.boundary.distance(unary_union(relief))
    min_gap = min(p.distance(q) for p, q in combinations(relief, 2))
    assert min_gap >= .45 and margin >= .89 and all(base.covers(p) for p in relief)
    art = build.artwork()
    for group, meshes in zip(art.values(), (leaves, letters)):
        assert unary_union(list(group.values())).symmetric_difference(unary_union(meshes)).area < 1e-4
    counters = [name for name, p in art['letters'].items() if p.interiors]
    assert counters == ['wilds-d', 'unknown-o']
    assert sum(len(p.interiors) for p in letters) == 2

    old_base, old_leaves, old_letters = map(outlines, old)
    glyph_faces = unary_union([Polygon(glyph.exterior) for glyph in old_letters])
    prior_flecks = sum(p.intersection(glyph_faces).area > .5 * p.area for p in old_leaves)
    assert prior_flecks == 9
    return parts, base, bore, art, dict(
        parts=stats, dimensions_before_mm=dimensions(old), dimensions_mm=dimensions(parts),
        backing_area_before_mm2=round(sum(p.area for p in old_base), 3),
        backing_area_mm2=round(base.area, 3),
        backing_openings_before=sum(len(p.interiors) for p in old_base),
        backing_openings=1, backing_connected_components=1, backing_thickness_mm=2.,
        green_components_before=len(old_leaves), green_flecks_in_letters_before=prior_flecks,
        green_flecks_in_letters=0, green_foliage_components=len(leaves),
        ivory_glyphs=len(letters), ivory_counters_before=sum(len(p.interiors) for p in old_letters),
        ivory_counters=counters, min_relief_gap_mm=round(min_gap, 3),
        min_backing_border_mm=round(margin, 3), fully_supported_relief=True,
        volumetric_colour_overlap=False, bore_centre_mm=centre(bore), bore_mm=6.5,
        bore_coordinates_exactly_preserved=True, eyelet_outer_diameter_nominal_mm=10.5,
        plate_placement_preserved=True, embedded_filament_and_process_settings_byte_identical=True)


def pixel(point, dx=0., dy=0.):
    x, y = point
    return (x - dx - ORIGIN[0]) / STEP, (ORIGIN[1] - y + dy) / STEP


def raster(shape):
    image = Image.new('L', SIZE)
    draw = ImageDraw.Draw(image)
    for polygon in shape.geoms if shape.geom_type == 'MultiPolygon' else [shape]:
        draw.polygon([pixel(p) for p in polygon.exterior.coords], fill=255)
        for hole in polygon.interiors:
            draw.polygon([pixel(p) for p in hole.coords], fill=0)
    return np.asarray(image) == 255


def deposit(paths, slot, dx, dy):
    image = Image.new('L', SIZE)
    draw = ImageDraw.Draw(image)
    for points, width, tool in paths:
        if tool == slot:
            draw_bead(draw, [pixel(p, dx, dy) for p in points], width / STEP, 255)
    return np.asarray(image) == 255


def coverage(deposited, core):
    assert core.any()
    return float(np.count_nonzero(deposited & core) / np.count_nonzero(core))


def slice_checks(project, logs, parts, base, bore, art, plate):
    bbox = plate['objects'][0]['bbox']
    layers = read_toolpaths(logs / 'plate_1.gcode', bbox, 3)
    bb = bounds(parts[0])
    offsets = bbox['x'] - bb[0][0], bbox['y'] - bb[1][0]
    result = toolpath_checks(layers, parts, bbox, {}, None, loop_height=2., bore_loop=bore)
    result['raster_step_mm'] = STEP
    result['bead_edge_tolerance_mm'] = .075

    base_core, bore_core = raster(base.buffer(-.30)), raster(Polygon(bore).buffer(-.25))
    brown = {}
    for z in (.2, 2.):
        raw = deposit(layers[z], 0, *offsets)
        count, connected = regions(raw)
        fraction = coverage(dilate(connected, .075, STEP), base_core)
        assert count == 1 and fraction >= .995 and not np.any(raw & bore_core), (z, count, fraction)
        brown[str(z)] = dict(components=count, core_coverage=round(fraction, 5), open_bore=True)
    result['brown_backing_layers'] = brown

    for slot, (group, shapes) in enumerate(art.items(), start=1):
        field = unary_union(list(shapes.values()))
        allowed = raster(field.buffer(.18))
        cores = {name: raster(shape.buffer(-.17)) for name, shape in shapes.items()}
        counters = [raster(Polygon(hole).buffer(-.25))
                    for shape in shapes.values() for hole in shape.interiors]
        report = {}
        active = [z for z, paths in sorted(layers.items()) if any(t == slot for _, _, t in paths)]
        expected = [round(2. + .2 * i, 1) for i in range(1, 4 if slot == 1 else 6)]
        assert active == expected, (group, active, expected)
        for z in active:
            raw = deposit(layers[z], slot, *offsets)
            count = regions(raw)[0]
            covered = dilate(raw, .075, STEP)
            fractions = {name: round(coverage(covered, core), 5) for name, core in cores.items()}
            assert count == len(shapes), (z, group, count, len(shapes))
            assert min(fractions.values()) >= .99, (z, group, fractions)
            assert not np.any(raw & ~allowed), (z, group, 'deposit outside the intended relief')
            assert all(not np.any(raw & hole) for hole in counters), (z, group, 'filled counter')
            report[str(z)] = dict(components=count, core_coverage=fractions,
                                  clear_counters=len(counters), deposits_outside_relief=0)
        result[group + '_layers'] = report

    render_slice(layers, parts, bbox, [p['color'] for p in parts],
                 project.with_name(project.stem + '_sliced_preview.png'), loop_height=2.)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=build.DEST / (build.NAME + '.3mf'))
    args = parser.parse_args()
    project = args.project.resolve()
    logs = (build.ROOT / 'validation' / build.SET.name / build.VERSION
            if project.parent == build.DEST else project.parent / 'validation')
    parts, base, bore, art, geometry = geometry_checks(project)
    logs.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='wilds-slicer-') as work:
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
    toolpaths = slice_checks(project, logs, parts, base, bore, art, plate)
    report = dict(project=project.name, output_sha256=digest(project),
                  baseline=str(build.SOURCE.relative_to(build.ROOT)),
                  baseline_sha256=digest(build.SOURCE), geometry=geometry, toolpaths=toolpaths,
                  bambu_version=re.search(r'Current BambuStudio Version (\S+)', log).group(1),
                  plate_warnings=plate['warning_message'], physical_print_verified=False)
    (project.parent / ('Validation_' + build.VERSION + '.json')).write_text(
        json.dumps(report, indent=2) + '\n')
    print(f"{project.name} · {geometry['dimensions_mm']} mm · Bambu Studio {report['bambu_version']}")


if __name__ == '__main__':
    main()
