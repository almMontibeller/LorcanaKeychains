#!/usr/bin/env python3
"""Validate Set 09 v1.6 meshes and actual Bambu A1 / 0.4 mm toolpaths."""
import argparse
import json
import math
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw

import rebuild_set09 as build
from rebuild_set04 import area, boundary_loops
from rebuild_set05 import dilate, erode
from full_height_narrow_rims import bore_index
from refine_loops_and_underline import draw_bead, read_toolpaths, render_slice, toolpath_checks
from repair_v1_1 import NS, read_parts
from standardize_loop_diameters import bounds, centre, digest, mesh_stats, package
from validate_bambu import bambu_command
from validate_set06 import assert_simple

LOGS = build.ROOT/'validation'/build.SET.name/build.VERSION


def regions(mask):
    """Four-neighbour components using row spans, avoiding a pixel flood fill."""
    parents, runs, previous = [], [], []

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    for y, row in enumerate(mask):
        edges = np.flatnonzero(np.diff(np.pad(row.astype(np.int8), (1, 1))))
        current = []
        cursor = 0
        for left, right in zip(edges[::2], edges[1::2]):
            index = len(parents)
            parents.append(index)
            while cursor < len(previous) and previous[cursor][1] <= left:
                cursor += 1
            j = cursor
            while j < len(previous) and previous[j][0] < right:
                parents[root(previous[j][2])] = root(index)
                j += 1
            current.append((left, right, index))
            runs.append((y, left, right, index))
        previous = current
    sizes = {}
    for y, left, right, index in runs:
        group = root(index)
        sizes[group] = sizes.get(group, 0)+int(right-left)
    largest = np.zeros_like(mask)
    if sizes:
        winner = max(sizes, key=sizes.get)
        for y, left, right, index in runs:
            if root(index) == winner:
                largest[y, left:right] = True
    return len(sizes), largest


def components(mask):
    return regions(mask)[0]


def geometry_checks():
    before, after = package(build.SOURCE), package(build.PROJECT)
    old, parts = read_parts(before), read_parts(after)
    assert before['Metadata/project_settings.config'] == after['Metadata/project_settings.config']
    roots = [ET.fromstring(d['3D/3dmodel.model']) for d in (before, after)]
    configs = [ET.fromstring(d['Metadata/model_settings.config']) for d in (before, after)]
    assert ET.tostring(roots[0].find('m:build', NS)) == ET.tostring(roots[1].find('m:build', NS))
    assert ET.tostring(configs[0].find('assemble')) == ET.tostring(configs[1].find('assemble'))
    settings = json.loads(after['Metadata/project_settings.config'])
    assert settings['nozzle_diameter'] == ['0.4']
    assert settings['wall_generator'] == 'arachne'
    assert float(settings['layer_height']) == .2
    assert [p['slot'] for p in parts] == [1, 2, 3]
    stats = [dict(name=p['name'], slot=p['slot'], **mesh_stats(p)) for p in parts]
    assert all(s['degenerate_triangles'] == 0 for s in stats)
    loops = [boundary_loops(p) for p in parts]
    assert len(loops[0]) == 2, 'backing must have one outer contour and only the eyelet hole'
    old_loops = boundary_loops(old[0])
    old_bore = old_loops[bore_index(old_loops, 6.5)]
    bore = loops[0][bore_index(loops[0], 6.5)]
    assert sorted(bore) == sorted(old_bore), 'bore vertices changed'
    assert centre(bore) == centre(old_bore)
    art = build.artwork()
    purple = build.purple_contours(art)
    for shapes in (*art.values(), purple, {'backing': loops[0]}):
        for cs in shapes.values():
            for c in cs:
                assert_simple(c)
    masks = [build.mask(ls) for ls in loops]
    assert components(masks[0]) == 1, 'background or eyelet disconnected'
    unsupported = dict(gold=int(np.count_nonzero(masks[1] & ~masks[0])),
                       purple=int(np.count_nonzero(masks[2] & ~masks[1])))
    assert not any(unsupported.values()), unsupported
    for p, levels in zip(parts, ({0., 2.}, {2., 2.6}, {2.6, 3.})):
        assert {round(v[2], 6) for v in p['vertices']} == levels
    purple_counts = {name: components(build.mask(cs)) for name, cs in purple.items()}
    assert all(n == 1 for n in purple_counts.values()), purple_counts
    counters = {name: sum(area(c) < 0 for c in cs) for name, cs in purple.items()}
    assert sum(counters.values()) == 3 and counters['B'] == 2 and counters['D'] == 1
    old_area = sum(area(c) for c in build.orient(old_loops))
    new_area = sum(area(c) for c in build.orient(loops[0]))
    outline = max(loops[0], key=lambda c: abs(area(c)))
    cx, cy = centre(bore)
    radii = [math.dist(p, (cx, cy))-3.25 for p in outline if p[0] <= cx]
    assert min(radii) > 1.999999 and max(radii) < 2.000001
    return parts, bore, dict(parts=stats, dimensions_mm=[b-a for a, b in bounds(parts[0])[:2]]+[3.],
        backing_area_before_mm2=old_area, backing_area_after_mm2=new_area,
        added_backing_area_mm2=new_area-old_area,
        connected_backing_components=1, backing_openings=1,
        eyelet=dict(bore_diameter_mm=6.5, bore_coordinates_exactly_preserved=True,
                    centre_mm=centre(bore), nominal_outer_diameter_mm=10.5,
                    radial_rim_mm=2., height_mm=2., neck_width_mm=7.),
        gold_keyline_mm=build.KEYLINE, purple_components=purple_counts,
        purple_counters=counters, purple_top_mm=3., gold_top_mm=2.6,
        unsupported_relief_pixels=unsupported, raster_resolution_mm=build.STEP,
        volumetric_colour_overlap=False, self_intersecting_contours=0,
        plate_placement_preserved=True, filament_and_process_settings_byte_identical=True)


def deposit(paths, slot, bbox):
    im = Image.new('L', build.SIZE)
    draw = ImageDraw.Draw(im)
    for points, width, tool in paths:
        if tool == slot:
            draw_bead(draw, [build.pixel((x-bbox['x'], y-bbox['y'])) for x, y in points],
                      width/build.STEP, 255)
    return im


def feature_check(image, shapes, z, inset=.18, occluders=None):
    raw = np.asarray(image)
    report = {}
    deposit_count = components(raw == 255)
    assert deposit_count == len(shapes), (z, 'detached or merged deposits', deposit_count, len(shapes))
    for name, cs in shapes.items():
        footprint = build.mask(cs)
        expected = erode(footprint, inset, build.STEP)
        full_core = expected
        if occluders and name in occluders:
            # Check the gold border that remains exposed after the purple
            # cap is printed. Tiny solid-infill voids buried under that cap
            # are reported separately from breaks in the visible outline.
            expected = erode(footprint, .12, build.STEP) & ~dilate(
                build.mask(occluders[name]), .12, build.STEP)
        assert np.any(expected), (name, 'feature too small')
        yy, xx = np.where(expected & (raw == 255))
        assert len(xx), (z, name, 'missing feature')
        connected = image.copy()
        ImageDraw.floodfill(connected, (int(xx[len(xx)//2]), int(yy[len(yy)//2])), 128)
        component = np.asarray(connected) == 128
        covered = dilate(component, .075, build.STEP)
        coverage = np.count_nonzero(expected & covered)/np.count_nonzero(expected)
        assert coverage > .99, (z, name, 'broken deposited stroke', coverage)
        raw_coverage = np.count_nonzero(expected & (raw == 255))/np.count_nonzero(expected)
        outside = int(np.count_nonzero(component & ~dilate(footprint, .2, build.STEP)))
        assert outside == 0, (z, name, 'joined to another feature', outside)
        full_coverage = np.count_nonzero(covered & full_core)/np.count_nonzero(full_core)
        report[name] = dict(connected_visible_core_coverage=float(coverage),
                           raw_visible_core_coverage=float(raw_coverage),
                           connected_full_core_coverage=float(full_coverage))
    # Test the holes independently; hollow B/D and book pages must stay open.
    holes = 0
    for cs in shapes.values():
        for c in cs:
            if area(c) < 0:
                core = erode(build.mask([c]), .22, build.STEP)
                assert np.any(core) and not np.any(raw[core]), (z, 'closed counter')
                holes += 1
    return dict(features=report, clear_counters=holes, connected_deposit_components=deposit_count,
                detached_or_merged_components=0)


def slice_checks(parts, bore, result):
    plate = result['sliced_plates'][0]
    assert plate['warning_message'] == ''
    assert [f['id'] for f in plate['filaments']] == [1, 2, 3]
    assert all(f['main_used_g'] > 0 for f in plate['filaments'])
    bbox = plate['objects'][0]['bbox']
    layers = read_toolpaths(LOGS/'plate_1.gcode', bbox, 3)
    report = toolpath_checks(layers, parts, bbox, {}, None, loop_height=2., bore_loop=bore)
    base_image = deposit(layers[2.], 0, bbox)
    interior = erode(build.mask(boundary_loops(parts[0])), .28, build.STEP)
    deposited_components, deposited = regions(np.asarray(base_image) == 255)
    covered = dilate(deposited, .075, build.STEP)
    coverage = np.count_nonzero(covered & interior)/np.count_nonzero(interior)
    assert coverage > .995, ('broken deposited background', coverage)
    art = build.artwork()
    gold = dict(art['letters'], **art['ornaments'])
    purple = build.purple_contours(art)
    report['gold_layers'] = {str(z): feature_check(deposit(layers[z], 1, bbox), gold, z, occluders=purple)
                             for z in (2.2, 2.4, 2.6)}
    report['purple_layers'] = {str(z): feature_check(deposit(layers[z], 2, bbox), purple, z, .12)
                               for z in (2.8, 3.)}
    report['background_top_connected_core_coverage'] = float(coverage)
    report['background_top_deposit_components'] = deposited_components
    report['bead_edge_raster_tolerance_mm'] = .075
    render_slice(layers, parts, bbox, [p['color'] for p in parts],
                 build.DEST/(build.NAME+'_sliced_preview.png'), loop_height=2.)
    return report


def main():
    global LOGS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-slice', action='store_true', help='Reuse only if project SHA-256 matches.')
    parser.add_argument('--project', type=build.Path, help='Validate a reproduction, with logs beside it.')
    args = parser.parse_args()
    if args.project:
        build.PROJECT = args.project.resolve()
        build.DEST = build.PROJECT.parent
        LOGS = build.DEST/'validation'
    parts, bore, geometry = geometry_checks()
    (build.DEST/('Geometry_'+build.VERSION+'.json')).write_text(json.dumps(geometry, indent=2)+'\n')
    LOGS.mkdir(parents=True, exist_ok=True)
    sha = digest(build.PROJECT)
    if args.reuse_slice:
        assert (LOGS/'project.sha256').read_text().strip() == sha
        result = json.loads((LOGS/'result.json').read_text())
        log = (LOGS/'slice.log').read_text()
    else:
        with tempfile.TemporaryDirectory(prefix='lorcana-set09-') as directory:
            run = subprocess.run(bambu_command()+['--datadir', directory, '--debug', '2', '--info',
                '--slice', '1', '--outputdir', str(LOGS), str(build.PROJECT)],
                cwd=LOGS, capture_output=True, text=True, timeout=180)
        log = run.stdout+run.stderr
        (LOGS/'slice.log').write_text(log)
        assert run.returncode == 0, log[-5000:]
        result = json.loads((LOGS/'result.json').read_text())
        (LOGS/'project.sha256').write_text(sha+'\n')
    assert result['return_code'] == 0 and 'manifold = yes' in log
    report = dict(project=str(build.PROJECT.relative_to(build.ROOT))
                  if build.PROJECT.is_relative_to(build.ROOT) else str(build.PROJECT), output_sha256=sha,
        baseline=str(build.SOURCE.relative_to(build.ROOT)), baseline_sha256=digest(build.SOURCE),
        geometry=geometry, toolpaths=slice_checks(parts, bore, result),
        bambu_version=re.search(r'Current BambuStudio Version (\S+)', log).group(1),
        physical_print_verified=False, slice_result=result)
    (build.DEST/('Validation_'+build.VERSION+'.json')).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'slice_result'}, indent=2))


if __name__ == '__main__':
    main()
