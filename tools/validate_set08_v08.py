#!/usr/bin/env python3
"""Validate Set 08 v08's orange accents and actual engraved hood toolpaths."""
import argparse
import json
import math
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import rebuild_set08_v08 as build
import validate_set08 as checks
from rebuild_set04 import area, boundary_loops, orient

core = build.core
LOGS = build.ROOT/'validation'/build.SET.name/build.VERSION


def plain_face_region():
    return core.sample('M 672 67 L 710 67 L 710 91 L 672 91 Z')


def pixels(loops, inset=0.):
    return checks.shape_pixels(loops, inset)


def top_loops(part, height):
    """Read all upward faces at a selected physical surface height."""
    vertices = part['vertices']
    faces = [tuple(reversed(f)) for f in part['faces']
             if all(abs(vertices[i][2]-height) < 1e-7 for i in f)
             and area([vertices[i][:2] for i in f]) > 1e-12]
    return core.footprint_loops(dict(part, faces=faces))


def geometry_checks():
    before, after = core.package(build.SOURCE), core.package(build.PROJECT)
    old, parts = core.read_parts(before), core.read_parts(after)
    assert before['Metadata/project_settings.config'] == after['Metadata/project_settings.config']
    roots = [ET.fromstring(d['3D/3dmodel.model']) for d in (before, after)]
    configs = [ET.fromstring(d['Metadata/model_settings.config']) for d in (before, after)]
    assert ET.tostring(roots[0].find('m:build', core.NS)) == ET.tostring(roots[1].find('m:build', core.NS))
    assert ET.tostring(configs[0].find('assemble')) == ET.tostring(configs[1].find('assemble'))
    assert parts[3] == old[2], 'v07 red lettering/eyes changed'
    old_gold, new_gold = build.components(old[1]), build.components(parts[2])
    def text_components(items):
        frame = max(items, key=lambda p: core.bounds(p)[0][1]-core.bounds(p)[0][0])
        return [(p['vertices'], p['faces']) for p in items if p is not frame]
    assert text_components(old_gold) == text_components(new_gold), 'v07 gold lettering/keylines changed'
    def boundary_points(part):
        return sorted(p for c in boundary_loops(part) for p in c)
    a, b = boundary_points(old[0]), boundary_points(parts[0])
    assert len(a) == len(b)
    deviation = max(math.dist(p, q) for p, q in zip(a, b))
    assert deviation < 1e-8, 'native backing/eyelet footprint changed'
    assert {round(v[2], 6) for v in parts[0]['vertices']} == {0., 1.6, 2.}
    assert [p['slot'] for p in parts] == [1, 2, 3, 4]
    assert {round(v[2], 6) for v in parts[1]['vertices']} == {2.4, 2.8}
    stats = [dict(name=p['name'], slot=p['slot'], **core.mesh_stats(p)) for p in parts]
    assert all(s['degenerate_triangles'] == 0 for s in stats)
    orange = core.footprint_loops(parts[1])
    grooves = top_loops(parts[0], 1.6)
    frame = boundary_loops(max(old_gold, key=lambda p: core.bounds(p)[0][1]-core.bounds(p)[0][0]))
    gold_cap = orient(frame+orange)
    for loops in (orange, grooves, gold_cap):
        for loop in loops:
            checks.assert_simple(loop)
    clean = core.artwork()
    text_pixels = set().union(*(pixels(ls) for n, ls in clean['gold'].items() if n != 'frame'),
                             *(pixels(ls) for ls in clean['jafar'].values()))
    groove_pixels = pixels(grooves)
    assert not groove_pixels & text_pixels, 'engraving undermines lettering'
    assert not groove_pixels-pixels([frame[1]]), 'engraving leaves interior hood'
    assert not pixels(orange, .025)-pixels(frame), 'orange leaves its gold support'
    assert not pixels(orange, .025) & pixels(gold_cap, .025), 'orange intersects gold cap'
    eyes = set().union(*(pixels(ls, .025) for ls in clean['accents'].values()))
    assert not eyes & pixels(orange), 'orange fills red eyes'
    if not build.artwork()['face_lines']:
        # The source artwork has a plain face here. This also prevents the
        # removed central chevron from reappearing as gold geometry.
        central = pixels(plain_face_region(), .1)
        assert not central-pixels(orange), 'plain face contains a gold interruption'
        assert not central & pixels(gold_cap), 'central chevron remains in gold cap'
        previous = core.read_parts(core.package(build.COMPARISON_SOURCE))
        assert parts[0] == previous[0], 'cobra hood or backing changed during face correction'
        assert parts[3] == previous[3], 'red lettering or eyes changed during face correction'
        old_orange, new_orange = pixels(core.footprint_loops(previous[1])), pixels(orange)
        allowed = pixels(core.sample('M 660 61 L 720 61 L 720 98 L 660 98 Z'))
        assert not old_orange-new_orange, 'orange detail was removed outside the face correction'
        assert not (new_orange-old_orange)-allowed, 'orange detail changed outside the central face'
    removed = core.mesh_stats(old[0])['volume_mm3']-stats[0]['volume_mm3']
    expected = sum(area(c) for c in grooves)*build.GROOVE_DEPTH
    assert math.isclose(removed, expected, abs_tol=1e-6)
    assert math.isclose(core.mesh_stats(old[1])['volume_mm3'],
                        stats[2]['volume_mm3']+stats[1]['volume_mm3'], abs_tol=1e-6)
    bore = next(c for c in boundary_loops(parts[0]) if abs(abs(area(c))-math.pi*3.25**2) < .1)
    assert all(abs(max(p[k] for p in bore)-min(p[k] for p in bore)-6.5) < 1e-8 for k in (0, 1))
    return old, parts, orange, grooves, gold_cap, dict(parts=stats,
        native_backing_and_eyelet_contours_preserved=True, contour_max_deviation_mm=deviation,
        red_lettering_and_eyes_exactly_preserved=True, gold_lettering_and_keylines_exactly_preserved=True,
        filament_and_process_settings_byte_identical=True, plate_placement_preserved=True,
        eyelet=dict(height_mm=2., bore_diameter_mm=6.5, outer_diameter_nominal_mm=10.5, radial_rim_mm=2.),
        hood=dict(source_bands=5, groove_width_mm=build.GROOVE_WIDTH, groove_depth_mm=build.GROOVE_DEPTH,
                  minimum_backing_floor_mm=1.6, removed_volume_mm3=removed,
                  groove_components=sum(area(c) > 0 for c in grooves)),
        orange=dict(inset_rim_nominal_width_mm=.6, colour_depth_mm=.4,
                    serpent_details=['cheeks', 'gold_eye_surrounds']+(
                        ['gold_forehead_muzzle_chevron'] if build.artwork()['face_lines'] else ['plain_orange_centre'])),
        active_filament_slots=[1, 2, 3, 4], volumetric_colour_overlap=False,
        unsupported_relief=False, shared_boundary_raster_tolerance_mm=.025)


def render_slice(layers, bbox, settings, path):
    width = 1800
    step = bbox['width']/(width-120)
    height = math.ceil(bbox['depth']/step)+120
    with core.Canvas((width, height), (-60*step, bbox['depth']+60*step), step) as c:
        c.background('#404443')
        for z in (1.6, 2., 2.4, 2.8):
            for points, stroke, slot in layers[z]:
                color = '#222526' if z == 1.6 else settings['filament_colour'][slot]
                c.stroke([points], stroke, color)
        c.save(path)


def slice_checks(parts, orange, grooves, gold_cap, result):
    plate = result['sliced_plates'][0]
    assert plate['warning_message'] == ''
    assert [f['id'] for f in plate['filaments']] == [1, 2, 3, 4]
    assert all(f['main_used_g'] > 0 for f in plate['filaments'])
    bbox = plate['objects'][0]['bbox']
    layers = checks.read_toolpaths(LOGS/'plate_1.gcode', bbox)
    # The physical floor must print at 1.6 mm and stay empty on both layers
    # above it; checking a mesh render alone would miss filled engraving.
    groove_core = pixels(grooves, .16)
    floor = checks.deposit(layers[1.6], 0)
    floor_coverage = checks.coverage_with_tolerance(floor, groove_core)
    assert floor_coverage > .99, ('missing engraving floor', floor_coverage)
    clear = {}
    for z in (1.8, 2.):
        deposited = checks.deposit(layers[z], 0)
        fraction = sum(not deposited[i] for i in groove_core)/len(groove_core)
        assert fraction > .98, ('engraving filled by slicer', z, fraction)
        clear[str(z)] = fraction
    # Every source band has substantial open grooves in the final toolpaths.
    old = core.read_parts(core.package(build.SOURCE))
    _, _, band_masks = build.masks(old)
    top_black = checks.deposit(layers[2.], 0)
    bands = {}
    for name, band in band_masks.items():
        core_pixels = groove_core & {i for i, value in enumerate(band) if value}
        assert len(core_pixels) > 100
        fraction = sum(not top_black[i] for i in core_pixels)/len(core_pixels)
        assert fraction > .98, (name, 'missing hood band', fraction)
        bands[name] = fraction
    art = core.artwork()
    red = core.footprint_loops(parts[3])
    red_letters = core.red_contours(art)
    red_features = {**red_letters, **art['accents']}
    red_cores = {name: pixels(ls, .22) for name, ls in red_features.items()}
    gold_letters = {name: ls for name, ls in art['gold'].items() if name != 'frame'}
    all_gold_letters = {**gold_letters, **art['jafar']}
    gold_cores = {name: pixels(ls, .24) for name, ls in all_gold_letters.items()}
    frame = art['gold']['frame']
    ignore_frame = build.raster(frame, -.15)
    def in_frame(p):
        xx = round((p[0]-core.ORIGIN[0])/core.STEP)
        yy = round((core.ORIGIN[1]-p[1])/core.STEP)
        return 0 <= xx < core.SIZE[0] and 0 <= yy < core.SIZE[1] and ignore_frame[yy*core.SIZE[0]+xx]
    gold_report, red_report, orange_report, gold_cap_report = {}, {}, {}, {}
    for z in (2.2, 2.4, 2.6, 2.8):
        filtered = [(points, width, tool) for points, width, tool in layers[z]
                    if tool != 2 or not all(in_frame(p) for p in points)]
        gold_report[str(z)] = checks.feature_checks(filtered, 2,
            all_gold_letters if z <= 2.4 else gold_letters, gold_cores)
        red_report[str(z)] = checks.feature_checks(layers[z], 3,
            art['accents'] if z <= 2.4 else red_features, red_cores)
        if z >= 2.6:
            orange_report[str(z)] = checks.feature_checks(layers[z], 1,
                {'continuous_rim_and_serpent_face': orange},
                {'continuous_rim_and_serpent_face': pixels(orange, .16)})
            gold = checks.deposit(layers[z], 2)
            coverage = checks.coverage_with_tolerance(gold, pixels(gold_cap, .10))
            assert coverage > .98, ('lost gold rim/head highlights', z, coverage)
            gold_cap_report[str(z)] = coverage
    face_report = {}
    if build.artwork()['face_lines']:
        face = build.artwork()['face_lines']['forehead_and_muzzle']
        line_core = build.stroke([face], .14)
        v_pixels = {i for i, v in enumerate(line_core) if v}
        v_coverage = checks.coverage_with_tolerance(checks.deposit(layers[2.8], 2), v_pixels)
        assert v_coverage > .98, ('missing serpent forehead detail', v_coverage)
        face_report['forehead_chevron_coverage'] = v_coverage
    else:
        centre = pixels(plain_face_region(), .1)
        coverage_by_layer = {}
        for z in (2.6, 2.8):
            orange_deposit, gold_deposit = checks.deposit(layers[z], 1), checks.deposit(layers[z], 2)
            coverage = checks.coverage_with_tolerance(orange_deposit, centre)
            assert coverage > .99 and not any(gold_deposit[i] for i in centre), ('central face is not plain orange', z)
            coverage_by_layer[str(z)] = coverage
        face_report['plain_orange_central_face_coverage'] = coverage_by_layer
    gold_top, red_top = checks.deposit(layers[2.4], 2), checks.deposit(layers[2.8], 3)
    visible_gold = bytearray(a and not b for a, b in zip(gold_top, red_top))
    keylines = {}
    for name, loops in art['jafar'].items():
        expected = pixels(loops, .12)-pixels(red_letters[name], -.12)
        coverage = checks.coverage_with_tolerance(visible_gold, expected)
        assert coverage > .98, ('lost Jafar keyline', name, coverage)
        keylines[name] = coverage
    open_counters = 0
    for name, loops in all_gold_letters.items():
        for loop in loops:
            if area(loop) < 0:
                counter = pixels([loop], .28)
                for z in (2.2, 2.4, 2.6, 2.8):
                    gold, red_deposit = checks.deposit(layers[z], 2), checks.deposit(layers[z], 3)
                    assert not any(gold[i] or red_deposit[i] for i in counter), ('blocked counter', name, z)
                open_counters += 1
    assert open_counters == 3
    assert any(p[0] < 9 for points, _, _ in layers[2.] for p in points)
    assert not any(p[0] < 9 for z, paths in layers.items() if z > 2.
                   for points, _, _ in paths for p in points)
    settings = json.loads(core.package(build.PROJECT)['Metadata/project_settings.config'])
    render_slice(layers, bbox, settings, build.DEST/(build.NAME+'_sliced_preview.png'))
    return dict(groove_floor_coverage=floor_coverage, open_groove_core_fraction=clear,
        open_fraction_by_source_hood_band=bands, gold_lettering_layers=gold_report,
        red_layers=red_report, orange_layers=orange_report,
        gold_rim_and_head_core_coverage=gold_cap_report, **face_report,
        visible_jafar_keyline_core_coverage=keylines, open_letter_counters=open_counters,
        loop_top_layer_mm=2., detached_letter_or_orange_deposit_pixels=0,
        bead_edge_raster_tolerance_mm=.075,
        slice_preview_note='Actual deposited layers; recessed charcoal floors shaded darker to show depth.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-slice', action='store_true')
    args = parser.parse_args()
    old, parts, orange, grooves, gold_cap, geometry = geometry_checks()
    LOGS.mkdir(parents=True, exist_ok=True)
    if not args.reuse_slice:
        from validate_bambu import bambu_command
        with tempfile.TemporaryDirectory(prefix='lorcana-set08-v17-') as directory:
            run = subprocess.run(bambu_command()+['--datadir', directory, '--debug', '2', '--info',
                '--slice', '1', '--outputdir', str(LOGS), str(build.PROJECT)],
                cwd=LOGS, capture_output=True, text=True, timeout=180)
        (LOGS/'slice.log').write_text(run.stdout+run.stderr)
        assert run.returncode == 0
        (LOGS/'project.sha256').write_text(core.digest(build.PROJECT)+'\n')
    else:
        assert (LOGS/'project.sha256').read_text().strip() == core.digest(build.PROJECT), 'stale slice'
    result = json.loads((LOGS/'result.json').read_text())
    log = (LOGS/'slice.log').read_text()
    assert result['return_code'] == 0 and 'manifold = yes' in log
    toolpaths = slice_checks(parts, orange, grooves, gold_cap, result)
    report = dict(project=str(build.PROJECT.relative_to(build.ROOT)), sha256=core.digest(build.PROJECT),
        source=str(build.SOURCE.relative_to(build.ROOT)), source_sha256=core.digest(build.SOURCE),
        detail_vector=str(build.VECTOR.relative_to(build.ROOT)), detail_vector_sha256=core.digest(build.VECTOR),
        lettering_vector_sha256=core.digest(core.VECTOR), geometry=geometry, toolpath_checks=toolpaths,
        used_filament_slots=[1, 2, 3, 4], physical_print_verified=False,
        bambu_version=re.search(r'Current BambuStudio Version (\S+)', log).group(1), slice_result=result)
    for name, content in [('Validation_'+build.VERSION+'.json', report),
                          ('Geometry_'+build.VERSION+'.json', {k: v for k, v in report.items() if k != 'slice_result'})]:
        (build.DEST/name).write_text(json.dumps(content, indent=2)+'\n')
    print(json.dumps(dict(project=report['project'], geometry='passed', toolpaths='passed',
        used_filament_slots=report['used_filament_slots'], sha256=report['sha256']), indent=2))


if __name__ == '__main__':
    main()
