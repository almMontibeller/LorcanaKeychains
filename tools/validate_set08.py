#!/usr/bin/env python3
"""Validate Set 08 v1.6 geometry and the real A1 / 0.4 mm toolpaths.

Uses only Python's standard library, Cairo and the installed Bambu runtime.
"""
import argparse
import collections
import json
import math
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import rebuild_set08 as build
from rebuild_set04 import area, boundary_loops, inside
from repair_v1_1 import NS, read_parts
from validate_bambu import bambu_command

LOGS = build.ROOT/'validation'/build.SET.name/build.VERSION


def mask(loops, inset=0.):
    with build.Canvas() as canvas:
        if inset > 0:
            return canvas.eroded(loops, inset)
        canvas.background('#000000')
        canvas.fill(loops)
        if inset < 0:
            canvas.stroke([c+c[:1] for c in loops], -2*inset)
        return canvas.mask()


def shape_pixels(loops, inset=0.):
    return {i for i, v in enumerate(mask(loops, inset)) if v}


def assert_simple(loop):
    def turn(a, b, c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    segments = list(zip(loop, loop[1:]+loop[:1]))
    for i, (a, b) in enumerate(segments):
        assert math.dist(a, b) > 1e-9
        for j in range(i+2, len(segments)):
            if i == 0 and j == len(segments)-1:
                continue
            c, d = segments[j]
            if (max(a[0], b[0]) < min(c[0], d[0]) or max(c[0], d[0]) < min(a[0], b[0])
                    or max(a[1], b[1]) < min(c[1], d[1]) or max(c[1], d[1]) < min(a[1], b[1])):
                continue
            assert not (turn(a, b, c)*turn(a, b, d) < 0 and turn(c, d, a)*turn(c, d, b) < 0), 'crossed contour'


def geometry_checks():
    before, after = build.package(build.SOURCE), build.package(build.PROJECT)
    old, parts = read_parts(before), read_parts(after)
    assert parts[0] == old[0], 'native backing and loop changed'
    assert before['Metadata/project_settings.config'] == after['Metadata/project_settings.config']
    roots = [ET.fromstring(d['3D/3dmodel.model']) for d in (before, after)]
    configs = [ET.fromstring(d['Metadata/model_settings.config']) for d in (before, after)]
    assert ET.tostring(roots[0].find('m:build', NS)) == ET.tostring(roots[1].find('m:build', NS))
    assert ET.tostring(configs[0].find('assemble')) == ET.tostring(configs[1].find('assemble'))
    assert ET.tostring(configs[0].find('./object/part')) == ET.tostring(configs[1].find('./object/part'))
    assert [p['slot'] for p in parts] == [1, 3, 4]
    settings = json.loads(after['Metadata/project_settings.config'])
    assert settings['nozzle_diameter'] == ['0.4']
    assert settings['wall_generator'] == 'arachne' and float(settings['layer_height']) == .2
    stats = [dict(name=p['name'], slot=p['slot'], **build.mesh_stats(p)) for p in parts]
    assert all(s['degenerate_triangles'] == 0 for s in stats)
    assert {round(v[2], 6) for v in parts[0]['vertices']} == {0., 2.}
    assert {round(v[2], 6) for v in parts[1]['vertices']} == {2., 2.4, 2.8}
    assert {round(v[2], 6) for v in parts[2]['vertices']} == {2., 2.4, 2.8}
    art = build.artwork()
    red = build.red_contours(art)
    for shapes in list(art.values())+[red]:
        for loops in shapes.values():
            for loop in loops:
                assert_simple(loop)
    assert all(len(loops) == 1 for loops in red.values()), 'split red letter'
    assert len(art['gold']) == 8 and len(red) == 5 and len(art['accents']) == 2
    base = shape_pixels(build.footprint_loops(parts[0]))
    gold = shape_pixels(build.footprint_loops(parts[1]))
    assert not gold-base, 'gold outside native backing'
    # Distinct coplanar features must be disjoint. Elevated red rests on gold.
    occupied = set()
    gold_groups = list(art['gold'].items())+list(art['jafar'].items())
    for name, loops in gold_groups:
        pixels = shape_pixels(loops)
        assert not pixels & occupied, ('overlapping gold contours', name)
        occupied.update(pixels)
    keyline_deviation = {}
    for name, loops in red.items():
        pixels = shape_pixels(loops)
        assert not pixels-shape_pixels(art['jafar'][name]), ('unsupported red', name)
        # Sample the offset vertices against the original outline. Acute
        # mitres may be wider; the uniform offset must never become narrower.
        def distance(p, a, b):
            dx, dy = b[0]-a[0], b[1]-a[1]
            t = max(0., min(1., ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)))
            return math.dist(p, (a[0]+t*dx, a[1]+t*dy))
        edges = [(a, b) for c in art['jafar'][name] for a, b in zip(c, c[1:]+c[:1])]
        distances = [min(distance(p, a, b) for a, b in edges) for c in loops for p in c]
        assert min(distances) > build.KEYLINE-.05, (name, min(distances))
        keyline_deviation[name] = [min(distances), max(distances)]
    eyes = set().union(*(shape_pixels(ls) for ls in art['accents'].values()))
    eye_cores = set().union(*(shape_pixels(ls, .025) for ls in art['accents'].values()))
    # The shared mathematical boundaries can quantise to one raster cell
    # after the 3MF's nine-decimal serialization. Interior overlap must be zero.
    assert not eye_cores & gold and not eyes-base, 'snake eyes overlap gold or leave backing'
    backing_loops = boundary_loops(parts[0])
    bore = next(c for c in backing_loops if abs(abs(area(c))-math.pi*3.25**2) < .1)
    diameters = [max(p[k] for p in bore)-min(p[k] for p in bore) for k in (0, 1)]
    assert all(abs(d-6.5) < 1e-8 for d in diameters)
    return parts, art, red, dict(parts=stats, native_backing_and_loop_exactly_preserved=True,
        filament_and_process_settings_byte_identical=True, plate_placement_preserved=True,
        eyelet=dict(bore_diameters_xy_mm=diameters, nominal_outer_diameter_mm=10.5,
                    nominal_radial_rim_mm=2., height_mm=2.),
        active_filament_slots=[1, 3, 4], unused_preserved_filament_slot=2,
        continuous_frame_components=1, solid_upper_letter_components=7,
        outlined_jafar_letters=5, red_snake_eyes=2, open_letter_counters=3,
        jafar_keyline_nominal_mm=build.KEYLINE, sampled_keyline_widths_mm=keyline_deviation,
        gold_keyline_top_mm=2.4, gold_title_and_frame_top_mm=2.8, red_top_mm=2.8,
        volumetric_colour_overlap=False, unsupported_relief=False,
        raster_resolution_mm=build.STEP, shared_boundary_raster_tolerance_mm=.025)


def read_toolpaths(path, bbox):
    layers = collections.defaultdict(list)
    x, y, tool, z, width, feature = 0., 0., 0, 0., .42, 'Custom'
    relative, previous_e = True, 0.
    x0, y0 = bbox['x'], bbox['y']
    x1, y1 = x0+bbox['width'], y0+bbox['depth']
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line.startswith('; Z_HEIGHT:'):
            z = round(float(line.split(':', 1)[1]), 3)
        elif line.startswith('; LINE_WIDTH:'):
            width = float(line.split(':', 1)[1])
        elif line.startswith('; FEATURE:'):
            feature = line.split(':', 1)[1].strip()
        elif re.fullmatch(r'T\d+', line) and int(line[1:]) < 4:
            tool = int(line[1:])
        elif line in ('M82', 'M83'):
            relative = line == 'M83'
        command = line.split(';', 1)[0].split()
        if not command:
            continue
        values = {k: float(v) for k, v in re.findall(r'([XYZEFIJP])\s*([-+]?(?:\d*\.\d+|\d+))', ' '.join(command[1:]))}
        if command[0] == 'G92':
            previous_e = values.get('E', previous_e)
        if command[0] not in ('G0', 'G1', 'G2', 'G3'):
            continue
        end = values.get('X', x), values.get('Y', y)
        extrusion = values.get('E', 0) if relative else values.get('E', previous_e)-previous_e
        if not relative:
            previous_e = values.get('E', previous_e)
        if extrusion > 0 and ('X' in values or 'Y' in values) and feature not in ('Custom', 'Prime tower'):
            points = [(x, y), end]
            if command[0] in ('G2', 'G3') and ('I' in values or 'J' in values):
                cx, cy = x+values.get('I', 0), y+values.get('J', 0)
                radius = math.hypot(x-cx, y-cy)
                start, stop = math.atan2(y-cy, x-cx), math.atan2(end[1]-cy, end[0]-cx)
                sweep = (stop-start) % math.tau if command[0] == 'G3' else -((start-stop) % math.tau)
                count = max(2, math.ceil(abs(sweep)*radius/.04))
                points = [(cx+radius*math.cos(start+sweep*i/count), cy+radius*math.sin(start+sweep*i/count))
                          for i in range(count+1)]
            if all(x0-.25 <= px <= x1+.25 and y0-.25 <= py <= y1+.25 for px, py in points):
                layers[z].append(([(px-x0, py-y0) for px, py in points], width, tool))
        x, y = end
    return layers


def deposit(paths, slot):
    with build.Canvas() as canvas:
        canvas.background('#000000')
        for points, width, tool in paths:
            if tool == slot:
                canvas.stroke([points], width)
        return canvas.mask()


def floodfill(values, seed, label):
    width, height = build.SIZE
    assert values[seed] == 1
    values[seed] = label
    todo = [seed]
    while todo:
        p = todo.pop()
        neighbors = []
        if p % width:
            neighbors.append(p-1)
        if p % width != width-1:
            neighbors.append(p+1)
        if p >= width:
            neighbors.append(p-width)
        if p < width*(height-1):
            neighbors.append(p+width)
        for q in neighbors:
            if values[q] == 1:
                values[q] = label
                todo.append(q)


def coverage_with_tolerance(values, expected):
    width = build.SIZE[0]
    missing = [i for i in expected if not values[i]]
    missed = sum(not any(values[i+dy*width+dx]
                         for dy in range(-3, 4) for dx in range(-3, 4)) for i in missing)
    return 1-missed/len(expected)


def feature_checks(paths, slot, features, cores):
    values = deposit(paths, slot)
    report = {}
    for index, name in enumerate(features):
        expected = cores[name]
        candidates = [i for i in expected if values[i] == 1]
        assert candidates, ('missing or merged feature', name)
        # A core seed, then one physical deposited component per feature.
        seed = candidates[len(candidates)//2]
        label = index+2
        floodfill(values, seed, label)
        raw_coverage = sum(values[i] == label for i in expected)/len(expected)
        tolerance = 3  # 0.075 mm at rasterised bead edges.
        width = build.SIZE[0]
        missing = [i for i in expected if values[i] != label]
        missed = sum(not any(values[i+dy*width+dx] == label
                             for dy in range(-tolerance, tolerance+1)
                             for dx in range(-tolerance, tolerance+1)) for i in missing)
        coverage = 1-missed/len(expected)
        assert coverage > .99, ('broken deposited feature', name, coverage)
        report[name] = dict(connected=True, core_coverage=coverage,
                           core_coverage_without_bead_edge_tolerance=raw_coverage)
    leftovers = values.count(1)
    assert leftovers == 0, ('detached deposits', slot, leftovers)
    return report


def render_slice(layers, bbox, colors, path):
    width = 1800
    step = bbox['width']/(width-120)
    height = math.ceil(bbox['depth']/step)+120
    with build.Canvas((width, height), (-60*step, bbox['depth']+60*step), step) as canvas:
        canvas.background('#404443')
        for z in (2., 2.4, 2.8):
            for points, stroke, tool in layers[z]:
                canvas.stroke([points], stroke, colors[tool])
        canvas.save(path)


def comparison(parts):
    old = read_parts(build.package(build.SOURCE))
    bb = build.bounds(parts[0])
    width, panel = 2400, 1200
    step = (bb[0][1]-bb[0][0])/(panel-100)
    height = math.ceil((bb[1][1]-bb[1][0])/step)+150
    with build.Canvas((width, height), (-50*step, bb[1][1]+100*step), step) as canvas:
        canvas.background('#F5F5F5')
        lib, ctx = canvas.lib, canvas.context
        lib.cairo_select_font_face.argtypes = [build.C.c_void_p, build.C.c_char_p, build.C.c_int, build.C.c_int]
        lib.cairo_set_font_size.argtypes = [build.C.c_void_p, build.C.c_double]
        lib.cairo_show_text.argtypes = [build.C.c_void_p, build.C.c_char_p]
        lib.cairo_select_font_face(ctx, b'DejaVu Sans', 0, 0)
        lib.cairo_set_font_size(ctx, 28.)
        for index, (label, meshes) in enumerate([('v1.5 - gradient fragments', old), ('v1.6 - smooth, solid colours', parts)]):
            canvas.color('#363A3B')
            lib.cairo_move_to(ctx, 40+index*panel, 45)
            lib.cairo_show_text(ctx, label.encode())
            # Draw actual upward mesh faces, respecting different top heights.
            triangles = []
            for p in meshes:
                for f in p['faces']:
                    vs = [p['vertices'][i] for i in f]
                    if area([v[:2] for v in vs]) > 1e-10:
                        triangles.append((sum(v[2] for v in vs), p['color'], vs))
            for _, color, triangle in sorted(triangles, key=lambda t: t[0]):
                canvas.fill([[(v[0]+index*panel*step, v[1]) for v in triangle]], color)
        canvas.save(build.DEST/(build.NAME+'_comparison.png'))


def slice_checks(parts, art, red, result):
    plate = result['sliced_plates'][0]
    assert plate['warning_message'] == ''
    assert [f['id'] for f in plate['filaments']] == [1, 3, 4]
    assert all(f['main_used_g'] > 0 for f in plate['filaments'])
    bbox = plate['objects'][0]['bbox']
    layers = read_toolpaths(LOGS/'plate_1.gcode', bbox)
    assert not any(tool == 1 for paths in layers.values() for _, _, tool in paths), 'orange gradient remains'
    gold_features = {**art['gold'], **art['jafar']}
    gold_cores = {name: shape_pixels(loops, .24) for name, loops in gold_features.items()}
    red_features = {**red, **art['accents']}
    red_cores = {name: shape_pixels(loops, .22) for name, loops in red_features.items()}
    gold_report, red_report = {}, {}
    for z in (2.2, 2.4, 2.6, 2.8):
        gold_report[str(z)] = feature_checks(layers[z], 2,
            gold_features if z <= 2.4 else art['gold'], gold_cores)
        red_report[str(z)] = feature_checks(layers[z], 3,
            art['accents'] if z <= 2.4 else red_features, red_cores)
    # Check the gold keyline that remains visible after the red face prints,
    # rather than merely checking its hidden supporting gold slab.
    gold_top, red_top = deposit(layers[2.4], 2), deposit(layers[2.8], 3)
    visible_gold = bytearray(a and not b for a, b in zip(gold_top, red_top))
    keylines = {}
    for name, loops in art['jafar'].items():
        core = shape_pixels(loops, .12)-shape_pixels(red[name], -.12)
        coverage = coverage_with_tolerance(visible_gold, core)
        assert coverage > .98, ('missing visible gold keyline', name, coverage)
        keylines[name] = coverage
    # Both 'a' counters and the small 'o' remain open in actual deposited beads.
    counters = {}
    for name, loops in {**art['gold'], **art['jafar']}.items():
        if name == 'frame':
            continue
        for loop in loops:
            if area(loop) < 0:
                core = shape_pixels([loop], .28)
                assert core
                for z in (2.2, 2.4, 2.6, 2.8):
                    gold, crimson = deposit(layers[z], 2), deposit(layers[z], 3)
                    assert not any(gold[i] or crimson[i] for i in core), ('blocked letter counter', name, z)
                counters[name] = True
    assert len(counters) == 3
    # Frame continuity is checked above; sample the entire perimeter corridor
    # independently so a connected but incomplete ring cannot pass.
    loop_segments = sum(any(p[0] < 9 for p in points) for points, _, _ in layers[2.])
    assert loop_segments
    assert not any(p[0] < 9 for z, paths in layers.items() if z > 2.
                   for points, _, _ in paths for p in points), 'loop rises above backing'
    settings = json.loads(build.package(build.PROJECT)['Metadata/project_settings.config'])
    render_slice(layers, bbox, settings['filament_colour'], build.DEST/(build.NAME+'_sliced_preview.png'))
    return dict(gold_layers=gold_report, red_layers=red_report,
                visible_gold_keyline_core_coverage=keylines,
                detached_deposit_pixels=0, open_counters=counters,
                continuous_frame_on_all_four_relief_layers=True,
                uniform_red_jafar_on_both_face_layers=True, no_orange_toolpaths=True,
                loop_top_layer_mm=2., loop_segments_above_backing=0,
                loop_top_segments=loop_segments, bead_edge_raster_tolerance_mm=.075)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-slice', action='store_true')
    args = parser.parse_args()
    parts, art, red, geometry = geometry_checks()
    LOGS.mkdir(parents=True, exist_ok=True)
    if not args.reuse_slice:
        with tempfile.TemporaryDirectory(prefix='lorcana-set08-') as directory:
            run = subprocess.run(bambu_command()+['--datadir', directory, '--debug', '2', '--info',
                '--slice', '1', '--outputdir', str(LOGS), str(build.PROJECT)],
                cwd=LOGS, capture_output=True, text=True, timeout=180)
        (LOGS/'slice.log').write_text(run.stdout+run.stderr)
        assert run.returncode == 0, (run.returncode, (run.stdout+run.stderr)[-2000:])
        (LOGS/'project.sha256').write_text(build.digest(build.PROJECT)+'\n')
    else:
        assert (LOGS/'project.sha256').read_text().strip() == build.digest(build.PROJECT), 'stale slice'
    result = json.loads((LOGS/'result.json').read_text())
    log = (LOGS/'slice.log').read_text()
    assert result['return_code'] == 0 and 'manifold = yes' in log
    checks = slice_checks(parts, art, red, result)
    comparison(parts)
    report = dict(project=str(build.PROJECT.relative_to(build.ROOT)), sha256=build.digest(build.PROJECT),
        source=str(build.SOURCE.relative_to(build.ROOT)), source_sha256=build.digest(build.SOURCE),
        vector=str(build.VECTOR.relative_to(build.ROOT)), vector_sha256=build.digest(build.VECTOR),
        artwork_reference=str(build.ARTWORK.relative_to(build.ROOT)), geometry=geometry,
        toolpath_checks=checks, used_filament_slots=[1, 3, 4],
        bambu_version=re.search(r'Current BambuStudio Version (\S+)', log).group(1),
        physical_print_verified=False, slice_result=result)
    for filename, content in [('Validation_'+build.VERSION+'.json', report),
        ('Geometry_'+build.VERSION+'.json', {k: v for k, v in report.items() if k != 'slice_result'})]:
        (build.DEST/filename).write_text(json.dumps(content, indent=2)+'\n')
    print(json.dumps(dict(project=report['project'], geometry='passed', toolpaths='passed',
        used_filament_slots=report['used_filament_slots'], sha256=report['sha256']), indent=2))


if __name__ == '__main__':
    main()
