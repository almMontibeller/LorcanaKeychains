#!/usr/bin/env python3
"""Check full red face coverage, closed red bowls and completed hood bands."""
import argparse
import json
import math
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import rebuild_set08_v10 as build
import validate_set08 as checks
from validate_set08_v08 import top_loops, plain_face_region
from rebuild_set04 import area, boundary_loops, orient
from validate_bambu import bambu_command

core = build.core
LOGS = build.ROOT/'validation'/build.SET.name/build.VERSION


def pixels(loops, inset=0.):
    return checks.shape_pixels(loops, inset)


def geometry_checks():
    before, after = core.package(build.SOURCE), core.package(build.PROJECT)
    old, parts = core.read_parts(before), core.read_parts(after)
    assert before['Metadata/project_settings.config'] == after['Metadata/project_settings.config']
    roots = [ET.fromstring(d['3D/3dmodel.model']) for d in (before, after)]
    configs = [ET.fromstring(d['Metadata/model_settings.config']) for d in (before, after)]
    red_settings = {m.get('key'): m.get('value') for m in configs[1].find("./object/part[@id='4']").findall('metadata')}
    assert all(red_settings.get(k) == v for k, v in build.RED_FILL_SETTINGS.items())
    assert ET.tostring(roots[0].find('m:build', core.NS)) == ET.tostring(roots[1].find('m:build', core.NS))
    assert ET.tostring(configs[0].find('assemble')) == ET.tostring(configs[1].find('assemble'))
    def points(p):
        return sorted(xy for c in boundary_loops(p) for xy in c)
    a, b = points(old[0]), points(parts[0])
    assert len(a) == len(b) and max(math.dist(p, q) for p, q in zip(a, b)) < 1e-8
    assert [p['slot'] for p in parts] == [1, 2, 3, 4]
    stats = [dict(name=p['name'], slot=p['slot'], **core.mesh_stats(p)) for p in parts]
    assert all(s['degenerate_triangles'] == 0 for s in stats)
    assert {round(v[2], 6) for v in parts[0]['vertices']} == {0., 1.6, 2.}
    art = build.artwork()
    red = build.red_contours(art)
    assert len(red['a_first']) == len(red['a_second']) == 2
    orange = core.footprint_loops(parts[1])
    grooves = top_loops(parts[0], 1.6)
    cap = orient(art['gold']['frame']+orange)
    for shapes in (art['gold'], art['jafar'], art['accents'], red, {'orange': orange, 'grooves': grooves}):
        for loops in shapes.values():
            for c in loops:
                checks.assert_simple(c)
    base = pixels(core.footprint_loops(parts[0]))
    all_gold = pixels(core.footprint_loops(parts[2]))
    assert not all_gold-base, 'unsupported gold'
    assert not pixels(orange, .025)-pixels(art['gold']['frame']), 'unsupported orange'
    assert not pixels(orange, .025) & pixels(cap, .025), 'orange/gold overlap'
    for name, loops in red.items():
        assert not pixels(loops, .025)-pixels(art['jafar'][name]), ('unsupported red', name)
    for name, loops in art['accents'].items():
        assert not pixels(loops, .025) & pixels(cap, .025), ('red eye/gold overlap', name)
    text = set().union(*(pixels(ls) for n, ls in art['gold'].items() if n != 'frame'),
                       *(pixels(ls) for ls in art['jafar'].values()))
    assert not pixels(grooves, .025) & text, 'grooves undermine text'
    assert not pixels(plain_face_region(), .1)-pixels(orange), 'unwanted face decoration'
    counter_areas = {n: abs(area(next(c for c in ls if area(c) < 0)))
                     for n, ls in art['jafar'].items() if len(ls) > 1}
    assert all(a > 2. for a in counter_areas.values())
    return parts, art, red, orange, grooves, cap, dict(parts=stats,
        native_backing_and_eyelet_footprint_preserved=True, plate_placement_preserved=True,
        global_filament_and_process_settings_byte_identical=True,
        red_part_fill_overrides=build.RED_FILL_SETTINGS,
        eyelet=dict(height_mm=2., bore_diameter_mm=6.5, nominal_outer_diameter_mm=10.5, radial_rim_mm=2.),
        red_keyline_mm=build.KEYLINE, red_corner_radius_mm=build.RED_CORNER_RADIUS,
        red_face_top_mm=build.RED_FACE_TOP, red_face_layers=3,
        counter_inset_mm=build.COUNTER_INSET, black_counter_areas_mm2=counter_areas,
        eyes=dict(net_outset_mm=build.EYE_ROUNDING-build.EYE_INSET, corner_radius_mm=build.EYE_ROUNDING),
        hood=dict(bands=5, width_mm=.6, depth_mm=.4, floor_mm=1.6,
                  ends='tangents extended and clipped at inner rim'),
        colour_volume_overlap=False, unsupported_relief=False, central_face='plain orange')


def counter_is_enclosed(deposit, loops):
    """The empty counter must be enclosed by a continuous deposited red ring."""
    counter = next(c for c in loops if area(c) < 0)
    candidates = pixels([counter], .1)
    seed = next(i for i in candidates if not deposit[i])
    width = core.SIZE[0]
    all_points = [p for c in loops for p in c]
    xx = [round((p[0]-core.ORIGIN[0])/core.STEP) for p in all_points]
    yy = [round((core.ORIGIN[1]-p[1])/core.STEP) for p in all_points]
    left, right, top, bottom = min(xx)-5, max(xx)+5, min(yy)-5, max(yy)+5
    seen, todo = {seed}, [seed]
    while todo:
        p = todo.pop()
        x, y = p % width, p//width
        assert left < x < right and top < y < bottom, 'red bowl opens through to the outer edge'
        for q in (p-1, p+1, p-width, p+width):
            if q not in seen and not deposit[q]:
                seen.add(q)
                todo.append(q)
    return len(seen)*core.STEP**2


def rim_end_samples(path, field):
    """Find the entry/exit of an extended band and sample 0.25 mm inboard."""
    width, height = core.SIZE
    samples = []
    for a, b in zip(path, path[1:]):
        count = max(1, math.ceil(math.dist(a, b)/core.STEP))
        for j in range(count):
            t = j/count
            p = (a[0]+t*(b[0]-a[0]), a[1]+t*(b[1]-a[1]))
            x, y = round((p[0]-core.ORIGIN[0])/core.STEP), round((core.ORIGIN[1]-p[1])/core.STEP)
            if 0 <= x < width and 0 <= y < height and field[y*width+x]:
                samples.append((p, y*width+x))
    assert len(samples) > 20
    def inboard(sequence):
        start = sequence[0][0]
        return next(item for item in sequence if math.dist(start, item[0]) >= .25)
    return [inboard(samples), inboard(list(reversed(samples)))]


def slice_checks(parts, art, red, orange, grooves, cap, result):
    plate = result['sliced_plates'][0]
    assert plate['warning_message'] == ''
    assert [f['id'] for f in plate['filaments']] == [1, 2, 3, 4]
    assert all(f['main_used_g'] > 0 for f in plate['filaments'])
    bbox = plate['objects'][0]['bbox']
    layers = checks.read_toolpaths(LOGS/'plate_1.gcode', bbox)
    features = {**red, **art['accents']}
    # Inspect nearly the whole face, including the narrow areas excluded by
    # the old 0.22 mm core test. No bead dilation is used for these percentages.
    full_faces = {n: pixels(ls, .05) for n, ls in features.items()}
    connected_cores = {n: pixels(ls, .10) for n, ls in features.items()}
    face_report, rings = {}, {}
    red_layers = (2.6, 2.8, 3.)
    for z in (2.2, 2.4, *red_layers):
        active = art['accents'] if z < 2.6 else red if z > 2.8 else features
        checks.feature_checks(layers[z], 3, active, connected_cores)
        deposit = checks.deposit(layers[z], 3)
        raw = {n: sum(deposit[i] for i in full_faces[n])/len(full_faces[n]) for n in active}
        for name, fraction in raw.items():
            required = .99 if name in art['accents'] or z == build.RED_FACE_TOP else .98
            assert fraction >= required, ('incomplete full red face', z, name, fraction)
        face_report[str(z)] = raw
        if z >= 2.6:
            rings[str(z)] = {n: dict(closed=True, enclosed_area_mm2=counter_is_enclosed(deposit, red[n]))
                            for n in ('a_first', 'a_second')}
    # Whole hood cores AND both ends of each band must stay open in toolpaths.
    projected_red = bytearray(core.SIZE[0]*core.SIZE[1])
    for z in red_layers:
        deposit = checks.deposit(layers[z], 3)
        projected_red = bytearray(a or b for a, b in zip(projected_red, deposit))
    exposure = unplanned_red_holes(projected_red, features)
    assert all(item['area_mm2'] < .02 for item in exposure), ('gold exposed through all red layers', exposure)
    groove_core = pixels(grooves, .16)
    floor = checks.deposit(layers[1.6], 0)
    assert checks.coverage_with_tolerance(floor, groove_core) > .99
    clear = {}
    for z in (1.8, 2.):
        deposit = checks.deposit(layers[z], 0)
        fraction = sum(not deposit[i] for i in groove_core)/len(groove_core)
        assert fraction > .98
        clear[str(z)] = fraction
    _, _, bands = build.masks(art)
    field = build.engine.raster([art['gold']['frame'][1]])
    near_rim = build.engine.raster([art['gold']['frame'][1]], .5)
    deposited_black = checks.deposit(layers[2.], 0)
    endpoints = {}
    for name, path in build.detail_artwork()['hood'].items():
        entries = rim_end_samples(build.extend(path), field)
        for p, index in entries:
            assert bands[name][index] and not near_rim[index], ('band fails to reach rim', name, p)
            assert not deposited_black[index], ('band end filled by slicer', name, p)
        endpoints[name] = [dict(x_mm=p[0], y_mm=p[1], reaches_rim=True, open_in_slice=True) for p, _ in entries]
    # Gold counters and keylines must remain present alongside fuller red faces.
    gold_top = checks.deposit(layers[2.4], 2)
    red_top = projected_red
    visible = bytearray(a and not b for a, b in zip(gold_top, red_top))
    keylines = {}
    for name, loops in art['jafar'].items():
        expected = pixels(loops, .09)-pixels(red[name], -.09)
        coverage = checks.coverage_with_tolerance(visible, expected)
        assert coverage > .98, ('missing gold keyline', name, coverage)
        keylines[name] = coverage
    counters = {n: [c for c in ls if area(c) < 0] for n, ls in {**art['gold'], **art['jafar']}.items() if n != 'frame'}
    gold_final, red_final = checks.deposit(layers[2.8], 2), projected_red
    for name, holes in counters.items():
        for hole in holes:
            expected = pixels([hole], .25)
            assert expected and not any(gold_final[i] or red_final[i] for i in expected), ('blocked black counter', name)
    for z in (2.6, 2.8):
        checks.feature_checks(layers[z], 1, {'orange_rim_and_face': orange},
                              {'orange_rim_and_face': pixels(orange, .16)})
    centre = pixels(plain_face_region(), .1)
    orange_top = checks.deposit(layers[2.8], 1)
    assert checks.coverage_with_tolerance(orange_top, centre) > .99 and not any(gold_final[i] for i in centre)
    assert not any(p[0] < 9 for z, paths in layers.items() if z > 2. for points, _, _ in paths for p in points)
    settings = json.loads(core.package(build.PROJECT)['Metadata/project_settings.config'])
    render_slice(layers, bbox, settings, build.DEST/(build.NAME+'_sliced_preview.png'))
    return dict(full_red_face_coverage_without_bead_tolerance=face_report,
        red_face_edge_allowance_mm=.05, closed_deposited_a_rings=rings,
        unintended_holes_through_red_layers=exposure, minimum_detected_hole_area_mm2=.015,
        open_groove_core_fraction=clear, hood_band_ends=endpoints,
        gold_keyline_core_coverage=keylines, plain_orange_face=True,
        loop_top_layer_mm=2., detached_red_or_orange_deposits=0)


def unplanned_red_holes(deposit, features):
    expected = bytearray(len(deposit))
    for loops in features.values():
        expected = bytearray(a or b for a, b in zip(expected, build.engine.raster(loops)))
    holes = []
    for c in core.contours(deposit):
        ar = area(c)
        if ar >= 0:
            continue
        crosses = [a[0]*b[1]-b[0]*a[1] for a, b in zip(c, c[1:]+c[:1])]
        x = sum((a[0]+b[0])*cross for a, b, cross in zip(c, c[1:]+c[:1], crosses))/(6*ar)
        y = sum((a[1]+b[1])*cross for a, b, cross in zip(c, c[1:]+c[:1], crosses))/(6*ar)
        index = round((core.ORIGIN[1]-y)/core.STEP)*core.SIZE[0]+round((x-core.ORIGIN[0])/core.STEP)
        if expected[index]:
            holes.append(dict(area_mm2=abs(ar), x_mm=x, y_mm=y))
    return holes


def render_slice(layers, bbox, settings, path):
    width = 1800
    step = bbox['width']/(width-120)
    height = math.ceil(bbox['depth']/step)+120
    with core.Canvas((width, height), (-60*step, bbox['depth']+60*step), step) as c:
        c.background('#404443')
        # Include every relief layer: lower red layers remain visible beneath
        # tiny top-bead gaps and must not be replaced with a gold underlay.
        for z in sorted(k for k in layers if k >= 1.6):
            for points, stroke, slot in layers[z]:
                color = '#222526' if z == 1.6 and slot == 0 else settings['filament_colour'][slot]
                c.stroke([points], stroke, color)
        c.save(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-slice', action='store_true')
    args = parser.parse_args()
    parts, art, red, orange, grooves, cap, geometry = geometry_checks()
    LOGS.mkdir(parents=True, exist_ok=True)
    if not args.reuse_slice:
        with tempfile.TemporaryDirectory(prefix='lorcana-set08-v19-') as directory:
            run = subprocess.run(bambu_command()+['--datadir', directory, '--debug', '2', '--info',
                '--slice', '1', '--outputdir', str(LOGS), str(build.PROJECT)], cwd=LOGS,
                capture_output=True, text=True, timeout=180)
        (LOGS/'slice.log').write_text(run.stdout+run.stderr)
        assert run.returncode == 0
        (LOGS/'project.sha256').write_text(core.digest(build.PROJECT)+'\n')
    else:
        assert (LOGS/'project.sha256').read_text().strip() == core.digest(build.PROJECT), 'stale slice'
    result = json.loads((LOGS/'result.json').read_text())
    assert result['return_code'] == 0 and 'manifold = yes' in (LOGS/'slice.log').read_text()
    toolpaths = slice_checks(parts, art, red, orange, grooves, cap, result)
    report = dict(project=str(build.PROJECT.relative_to(build.ROOT)), sha256=core.digest(build.PROJECT),
        source=str(build.SOURCE.relative_to(build.ROOT)), source_sha256=core.digest(build.SOURCE),
        geometry=geometry, toolpath_checks=toolpaths, physical_print_verified=False, slice_result=result)
    for name, content in [('Validation_v10.json', report),
                          ('Geometry_v10.json', {k: v for k, v in report.items() if k != 'slice_result'})]:
        (build.DEST/name).write_text(json.dumps(content, indent=2)+'\n')
    print(json.dumps(dict(project=report['project'], geometry='passed', toolpaths='passed', sha256=report['sha256']), indent=2))


if __name__ == '__main__':
    main()
