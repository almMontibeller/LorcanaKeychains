#!/usr/bin/env python3
"""Audit Set 10 v07 geometry and deposited A1 / 0.4 mm toolpaths."""
import argparse
import json
import math
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw

import rebuild_set10 as build
from rebuild_set04 import area, boundary_loops
from rebuild_set05 import dilate, erode
from full_height_narrow_rims import bore_index
from refine_loops_and_underline import draw_bead, read_toolpaths, render_slice, toolpath_checks
from repair_v02 import NS, read_parts
from standardize_loop_diameters import bounds, centre, digest, mesh_stats, package
from validate_bambu import bambu_command
from validate_set06 import assert_simple
from validate_set09 import components, regions

LOGS = build.ROOT/'validation'/build.SET.name/build.VERSION


def geometry_checks():
    before, after = package(build.SOURCE), package(build.PROJECT)
    old, parts = read_parts(before), read_parts(after)
    assert before['Metadata/project_settings.config'] == after['Metadata/project_settings.config']
    roots = [ET.fromstring(d['3D/3dmodel.model']) for d in (before, after)]
    configs = [ET.fromstring(d['Metadata/model_settings.config']) for d in (before, after)]
    assert ET.tostring(roots[0].find('m:build', NS)) == ET.tostring(roots[1].find('m:build', NS))
    assert ET.tostring(configs[0].find('assemble')) == ET.tostring(configs[1].find('assemble'))
    settings = json.loads(after['Metadata/project_settings.config'])
    assert settings['nozzle_diameter'] == ['0.4'] and settings['wall_generator'] == 'arachne'
    assert float(settings['layer_height']) == .2
    assert [p['slot'] for p in parts] == [1, 2, 3]
    stats = [dict(name=p['name'], slot=p['slot'], **mesh_stats(p)) for p in parts]
    assert all(s['degenerate_triangles'] == 0 for s in stats)
    loops = [boundary_loops(p) for p in parts]
    assert len(loops[0]) == 2, 'background must have only the eyelet hole'
    old_loops = boundary_loops(old[0])
    old_bore = old_loops[bore_index(old_loops, 6.5)]
    bore = loops[0][bore_index(loops[0], 6.5)]
    assert sorted(bore) == sorted(old_bore)
    art = build.artwork()
    for group, shapes in dict(art, backing={'backing': loops[0]}).items():
        for name, cs in shapes.items():
            for c in cs:
                try:
                    assert_simple(c)
                except AssertionError as exc:
                    raise AssertionError((group, name, str(exc))) from exc
    masks = [build.mask(ls) for ls in loops]
    assert components(masks[0]) == 1
    unsupported = {p['name']: int(np.count_nonzero(m & ~masks[0]))
                   for p, m in zip(parts[1:], masks[1:])}
    assert not any(unsupported.values()), unsupported
    overlap = int(np.count_nonzero(masks[1] & masks[2]))
    assert overlap == 0, ('overlapping colour volumes', overlap)
    for p, levels in zip(parts, ({0., 2.}, {2., 2.8}, {2., 2.8})):
        assert {round(v[2], 6) for v in p['vertices']} == levels
    features = {colour: {name: components(erode(build.mask(cs), .075, build.STEP))
                         for name, cs in build.features(art, colour).items()}
                for colour in ('grey', 'gold')}
    assert all(n == 1 for group in features.values() for n in group.values()), features
    counters = {name: sum(area(c) < 0 for c in cs)
                for name, cs in build.features(art, 'gold').items()}
    assert sum(counters.values()) == 2 and counters['P'] == counters['R'] == 1, counters
    for i, colour in ((1, 'grey'), (2, 'gold')):
        assert components(erode(masks[i], .075, build.STEP)) == len(features[colour]), (colour, 'joined features')
    old_area = sum(area(c) for c in build.orient(old_loops))
    new_area = sum(area(c) for c in build.orient(loops[0]))
    outline = max(loops[0], key=lambda c: abs(area(c)))
    cx, cy = centre(bore)
    radii = [math.dist(p, (cx, cy))-3.25 for p in outline if p[0] <= cx]
    assert 1.999999 < min(radii) <= max(radii) < 2.000001
    return parts, bore, dict(parts=stats, dimensions_mm=[b-a for a, b in bounds(parts[0])[:2]]+[2.8],
        backing_area_before_mm2=old_area, backing_area_after_mm2=new_area,
        added_backing_area_mm2=new_area-old_area, backing_openings_before=len(old_loops)-1,
        connected_backing_components=1, backing_openings=1,
        eyelet=dict(bore_diameter_mm=6.5, bore_coordinates_exactly_preserved=True,
                    centre_mm=centre(bore), nominal_outer_diameter_mm=10.5,
                    radial_rim_mm=2., height_mm=2., neck_width_mm=7.),
        feature_components=features, gold_counters=counters, unsupported_relief_pixels=unsupported,
        raster_resolution_mm=build.STEP, volumetric_colour_overlap=False,
        self_intersecting_contours=0, plate_placement_preserved=True,
        filament_and_process_settings_byte_identical=True)


def deposit(paths, slot, bbox):
    im = Image.new('L', build.SIZE)
    draw = ImageDraw.Draw(im)
    for points, width, tool in paths:
        if tool == slot:
            draw_bead(draw, [build.pixel((x-bbox['x'], y-bbox['y'])) for x, y in points],
                      width/build.STEP, 255)
    return im


def feature_check(image, shapes, z, inset=.12):
    raw = np.asarray(image)
    report = {}
    count = components(raw == 255)
    assert count == len(shapes), (z, 'detached or merged deposits', count, len(shapes))
    for name, cs in shapes.items():
        footprint = build.mask(cs)
        expected = erode(footprint, inset, build.STEP)
        assert np.any(expected), (name, 'feature too small')
        yy, xx = np.where(expected & (raw == 255))
        assert len(xx), (z, name, 'missing feature')
        connected = image.copy()
        ImageDraw.floodfill(connected, (int(xx[len(xx)//2]), int(yy[len(yy)//2])), 128)
        component = np.asarray(connected) == 128
        covered = dilate(component, .075, build.STEP)
        coverage = np.count_nonzero(expected & covered)/np.count_nonzero(expected)
        assert coverage > .99, (z, name, 'broken deposited stroke', coverage)
        outside = int(np.count_nonzero(component & ~dilate(footprint, .2, build.STEP)))
        assert outside == 0, (z, name, 'joined to another feature', outside)
        report[name] = dict(connected_core_coverage=float(coverage),
            raw_core_coverage=float(np.count_nonzero(expected & (raw == 255))/np.count_nonzero(expected)))
    holes = 0
    for cs in shapes.values():
        for c in cs:
            if area(c) < 0:
                core = erode(build.mask([c]), .22, build.STEP)
                assert np.any(core) and not np.any(raw[core]), (z, 'closed counter')
                holes += 1
    return dict(features=report, clear_counters=holes, connected_deposit_components=count,
                detached_or_merged_components=0)


def slice_checks(parts, bore, result):
    plate = result['sliced_plates'][0]
    assert plate['warning_message'] == ''
    assert [f['id'] for f in plate['filaments']] == [1, 2, 3]
    assert all(f['main_used_g'] > 0 for f in plate['filaments'])
    bbox = plate['objects'][0]['bbox']
    layers = read_toolpaths(LOGS/'plate_1.gcode', bbox, 3)
    report = toolpath_checks(layers, parts, bbox, {}, None, loop_height=2., bore_loop=bore)
    # Preserve the native assembly placement: the new field's minimum Y is
    # above zero. Map world G-code back to mesh coordinates, not to its bbox.
    bb = bounds(parts[0])
    offset = dict(x=bbox['x']-bb[0][0], y=bbox['y']-bb[1][0])
    interior = erode(build.mask(boundary_loops(parts[0])), .28, build.STEP)
    deposited_components, deposited = regions(np.asarray(deposit(layers[2.], 0, offset)) == 255)
    covered = dilate(deposited, .075, build.STEP)
    coverage = np.count_nonzero(covered & interior)/np.count_nonzero(interior)
    assert deposited_components == 1 and coverage > .995, ('broken deposited background', coverage)
    art = build.artwork()
    for colour, slot in (('grey', 1), ('gold', 2)):
        report[colour+'_layers'] = {str(z): feature_check(deposit(layers[z], slot, offset),
            build.features(art, colour), z) for z in (2.2, 2.4, 2.6, 2.8)}
    report['background_top_connected_core_coverage'] = float(coverage)
    report['background_top_deposit_components'] = deposited_components
    report['bead_edge_raster_tolerance_mm'] = .075
    render_slice(layers, parts, bbox, [p['color'] for p in parts],
                 build.DEST/(build.NAME+'_sliced_preview.png'), loop_height=2.)
    return report


def main():
    global LOGS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-slice', action='store_true')
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
        with tempfile.TemporaryDirectory(prefix='lorcana-set10-') as directory:
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
                  if build.PROJECT.is_relative_to(build.ROOT) else str(build.PROJECT),
        output_sha256=sha, baseline=str(build.SOURCE.relative_to(build.ROOT)),
        baseline_sha256=digest(build.SOURCE), geometry=geometry,
        toolpaths=slice_checks(parts, bore, result),
        bambu_version=re.search(r'Current BambuStudio Version (\S+)', log).group(1),
        physical_print_verified=False, slice_result=result)
    (build.DEST/('Validation_'+build.VERSION+'.json')).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'slice_result'}, indent=2))


if __name__ == '__main__':
    main()
