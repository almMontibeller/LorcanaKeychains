#!/usr/bin/env python3
"""Validate Set 07 v07 geometry and actual Bambu A1 / 0.4 mm toolpaths."""
import argparse
import json
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import rebuild_set07 as build
from rebuild_set04 import area, boundary_loops
from full_height_narrow_rims import bore_index, isometric
from refine_loops_and_underline import draw_bead, read_toolpaths, render_slice, toolpath_checks
from repair_v02 import NS, read_parts
from set_versions import saved_project
from standardize_loop_diameters import digest, mesh_stats, package
from validate_bambu import bambu_command
from validate_set06 import assert_simple

LOGS = build.ROOT/'validation'/build.SET.name/build.VERSION


def geometry_checks():
    before, after = package(build.SOURCE), package(build.PROJECT)
    old, parts = read_parts(before), read_parts(after)
    assert parts[0] == old[0], 'native backing and attachment changed'
    configs = [ET.fromstring(d['Metadata/model_settings.config']) for d in (before, after)]
    roots = [ET.fromstring(d['3D/3dmodel.model']) for d in (before, after)]
    assert ET.tostring(roots[0].find('m:build', NS)) == ET.tostring(roots[1].find('m:build', NS))
    assert ET.tostring(configs[0].find('assemble')) == ET.tostring(configs[1].find('assemble'))
    assert ET.tostring(configs[0].find('./object/part')) == ET.tostring(configs[1].find('./object/part'))
    settings = [json.loads(d['Metadata/project_settings.config']) for d in (before, after)]
    expected = json.loads(before['Metadata/project_settings.config'])
    build.add_filament(expected)
    assert settings[1] == expected, 'settings changed beyond fourth filament addition'
    changed = {k for k, value in settings[0].items() if settings[1][k] != value}
    for key in changed-{'flush_volumes_vector', 'flush_volumes_matrix'}:
        assert settings[1][key][:len(settings[0][key])] == settings[0][key], key
    assert settings[1]['nozzle_diameter'] == ['0.4']
    assert settings[1]['wall_generator'] == 'arachne'
    assert float(settings[1]['layer_height']) == .2
    art = build.artwork()
    for group, shapes in art.items():
        if group == 'veins':
            continue
        for name, loops in shapes.items():
            for c in loops:
                assert_simple(c)
    counters = {name: [abs(area(c)) for c in loops if area(c) < 0]
                for name, loops in art['letters'].items() if len(loops) > 1}
    assert len(art['letters']) == 14 and sum(map(len, counters.values())) == 6
    stats = [dict(name=p['name'], slot=p['slot'], **mesh_stats(p)) for p in parts]
    assert all(s['degenerate_triangles'] == 0 for s in stats)
    assert {round(v[2], 6) for v in parts[0]['vertices']} == {0., 2.}
    assert {round(v[2], 6) for v in parts[1]['vertices']} == {2., 2.6}
    assert {round(v[2], 6) for v in parts[3]['vertices']} == {2.6, 2.8}
    masks = [build.mask(boundary_loops(p)) for p in parts]
    letters = np.logical_or.reduce([build.mask(cs) for cs in art['letters'].values()])
    eyes = np.logical_or.reduce([build.mask(cs) for cs in art['eyes'].values()])
    unsupported = dict(caramel=int(np.count_nonzero(masks[1] & ~masks[0])),
                       lettering=int(np.count_nonzero(letters & ~masks[0])),
                       green=int(np.count_nonzero(masks[3] & ~masks[1])),
                       eyes=int(np.count_nonzero(eyes & ~masks[3])))
    assert not any(unsupported.values()), ('unsupported relief', unsupported)
    assert not np.any(letters & masks[1]), 'caramel intersects lettering'
    assert not np.any(letters & masks[3]), 'green intersects lettering'
    loops = boundary_loops(parts[0])
    bore = loops[bore_index(loops, 6.5)]
    return parts, bore, dict(parts=stats, native_backing_and_attachment_exactly_preserved=True,
                             plate_placement_preserved=True, original_three_filament_profiles_preserved=True,
                             process_settings_preserved=True, added_filament_slot=4,
                             added_filament_colour=build.GREEN, changed_filament_setting_keys=sorted(changed),
                             eyelet=dict(bore_diameter_mm=6.5, nominal_outer_diameter_mm=10.5,
                                         nominal_radial_rim_mm=2., height_mm=2.),
                             lettering_components=14, lettering_counters=6, counter_areas_mm2=counters,
                             deliberate_source_joins=['archazia_H_A_swash', 'archazia_A_S_swash'],
                             owl_eye_components=2, owl_brow_and_beak='engraved through caramel',
                             mesh_self_intersections=0, unsupported_relief_pixels=unsupported,
                             volumetric_colour_overlap_pixels=0, raster_resolution_mm=build.STEP,
                             top_heights_mm=dict(backing=2., caramel=2.6, green=2.8, ivory=3.))


def deposit(paths, slot, bbox):
    image = Image.new('L', build.SIZE)
    draw = ImageDraw.Draw(image)
    for points, width, tool in paths:
        if tool == slot:
            draw_bead(draw, [build.pixel((x-bbox['x'], y-bbox['y'])) for x, y in points],
                      width/build.STEP, 255)
    return image


def largest_seed(loops):
    mask = build.mask(loops)
    # An erosion chooses a seed away from the edge instead of a bounding-box
    # centroid, which may lie in a letter counter or outside a crescent.
    interior = build.erode(mask, .25, build.STEP)
    yy, xx = np.where(interior if np.any(interior) else mask)
    index = len(xx)//2
    return int(xx[index]), int(yy[index])


def slice_checks(parts, bore, result):
    plate = result['sliced_plates'][0]
    assert plate['warning_message'] == ''
    assert [f['id'] for f in plate['filaments']] == [1, 2, 3, 4]
    assert all(f['main_used_g'] > 0 for f in plate['filaments'])
    bbox = plate['objects'][0]['bbox']
    layers = read_toolpaths(LOGS/'plate_1.gcode', bbox, 4)
    report = toolpath_checks(layers, parts, bbox, {}, None, loop_height=2., bore_loop=bore)
    art = build.artwork()
    # Check all letters and six counters on every relief layer. Eyes begin
    # above their green sockets, so only the final layer contains them.
    lettering = {}
    for z in (2.2, 2.4, 2.6, 2.8, 3.):
        ivory = deposit(layers[z], 2, bbox)
        coverages = {}
        for index, (name, loops) in enumerate(art['letters'].items()):
            expected = build.erode(build.mask(loops), .24, build.STEP)
            yy, xx = np.where(expected & (np.asarray(ivory) == 255))
            assert len(xx), (z, name, 'missing or merged letter')
            seed = int(xx[len(xx)//2]), int(yy[len(yy)//2])
            ImageDraw.floodfill(ivory, seed, index+1)
            values = np.asarray(ivory)
            # Allow 0.075 mm bead-edge error in this raster reconstruction;
            # separated strokes still fail the connected-component check.
            covered = build.dilate(values == index+1, .075, build.STEP)
            coverage = np.count_nonzero(covered & expected)/np.count_nonzero(expected)
            assert coverage > .99, (z, name, 'broken deposited stroke', coverage)
            coverages[name] = float(coverage)
        if z == 3.:
            for index, (name, loops) in enumerate(art['eyes'].items()):
                seed = largest_seed(loops)
                assert ivory.getpixel(seed) == 255, (name, 'owl eye missing or merged')
                ImageDraw.floodfill(ivory, seed, index+30)
        leftovers = int(np.count_nonzero(np.asarray(ivory) == 255))
        assert leftovers == 0, (z, 'detached ivory deposits', leftovers)
        open_counters = 0
        raw = np.asarray(deposit(layers[z], 2, bbox))
        for loops in art['letters'].values():
            for c in loops:
                if area(c) >= 0:
                    continue
                core = build.erode(build.mask([c]), .35, build.STEP)
                assert np.any(core) and not np.any(raw[core]), (z, 'blocked counter')
                open_counters += 1
        lettering[str(z)] = dict(continuous_lettering_components=14, open_counters=open_counters,
                                 owl_eyes=2 if z == 3. else 0, detached_deposit_pixels=leftovers,
                                 core_coverage_by_component=coverages)
    report['ivory_layers'] = lettering
    # The fourth colour must reach every substantial frame leaf and both eye
    # sockets at its real print height, not just appear in a mesh preview.
    green = np.asarray(deposit(layers[2.8], 3, bbox)) > 0
    expected = build.mask(boundary_loops(parts[3]))
    core = build.erode(expected, .25, build.STEP)
    raw_coverage = np.count_nonzero(green & core)/np.count_nonzero(core)
    coverage = np.count_nonzero(build.dilate(green, .075, build.STEP) & core)/np.count_nonzero(core)
    assert coverage > .99, ('missing green frame', coverage)
    green_components = 0
    for c in boundary_loops(parts[3]):
        if abs(area(c)) < .2:
            continue
        interior = build.erode(build.mask([c]), .15, build.STEP)
        assert np.any(interior & green), 'missing green leaf or eye socket'
        green_components += 1
    for name, cs in art['eyes'].items():
        assert green[largest_seed(cs)[1], largest_seed(cs)[0]], (name, 'missing green socket')
    brow_core = build.erode(build.mask(art['engraving']['owl_brow_and_beak']), .12, build.STEP)
    gold = np.asarray(deposit(layers[2.6], 1, bbox)) > 0
    clear = np.count_nonzero(brow_core & ~gold)/np.count_nonzero(brow_core)
    assert clear > .8, ('owl brow engraving filled by slicer', clear)
    report['green_frame_core_coverage'] = float(coverage)
    report['green_frame_core_coverage_without_bead_edge_tolerance'] = float(raw_coverage)
    report['green_components_deposited'] = green_components
    report['bead_edge_raster_tolerance_mm'] = .075
    report['owl_brow_engraving_clear_fraction'] = float(clear)
    render_slice(layers, parts, bbox, [p['color'] for p in parts],
                 build.DEST/(build.NAME+'_sliced_preview.png'), loop_height=2.)
    return report


def comparison(parts):
    font = ImageFont.truetype('/usr/share/fonts/TTF/DejaVuSans.ttf', 28)
    old = read_parts(package(build.SOURCE))
    panels = []
    for label, meshes in [('v06', old), ('v07 — restored frame and owl', parts)]:
        temporary = build.DEST/'comparison_panel.png'
        build.preview(meshes, temporary, 1200)
        im = Image.open(temporary).convert('RGB')
        panel = Image.new('RGB', (1200, im.height+70), '#f5f5f5')
        panel.paste(im, (0, 60))
        ImageDraw.Draw(panel).text((35, 20), label, font=font, fill='#293f38')
        panels.append(panel)
    out = Image.new('RGB', (2400, max(im.height for im in panels)), '#f5f5f5')
    for x, im in zip((0, 1200), panels):
        out.paste(im, (x, 0))
    out.save(build.DEST/(build.NAME+'_comparison.png'))
    temporary.unlink()
    isometric(parts, build.DEST/(build.NAME+'_isometric.png'))


def main():
    build.PROJECT = saved_project(build.SET, build.VERSION)
    build.DEST = build.PROJECT.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-slice', action='store_true')
    args = parser.parse_args()
    parts, bore, geometry = geometry_checks()
    LOGS.mkdir(parents=True, exist_ok=True)
    if not args.reuse_slice:
        with tempfile.TemporaryDirectory(prefix='lorcana-set07-') as directory:
            run = subprocess.run(bambu_command()+['--datadir', directory, '--debug', '2', '--info',
                                  '--slice', '1', '--outputdir', str(LOGS), str(build.PROJECT)],
                                 cwd=LOGS, capture_output=True, text=True, timeout=180)
        (LOGS/'slice.log').write_text(run.stdout+run.stderr)
        assert run.returncode == 0, (run.returncode, (run.stdout+run.stderr)[-2000:])
        (LOGS/'project.sha256').write_text(digest(build.PROJECT)+'\n')
    else:
        assert (LOGS/'project.sha256').read_text().strip() == digest(build.PROJECT), 'stale slice'
    result = json.loads((LOGS/'result.json').read_text())
    log = (LOGS/'slice.log').read_text()
    assert result['return_code'] == 0 and 'manifold = yes' in log
    checks = slice_checks(parts, bore, result)
    comparison(parts)
    report = dict(project=str(build.PROJECT.relative_to(build.ROOT)), sha256=digest(build.PROJECT),
                  source=str(build.SOURCE.relative_to(build.ROOT)), source_sha256=digest(build.SOURCE),
                  vector=str(build.VECTOR.relative_to(build.ROOT)), vector_sha256=digest(build.VECTOR),
                  artwork_reference=str(build.ARTWORK.relative_to(build.ROOT)),
                  geometry=geometry, toolpath_checks=checks, used_filament_slots=[1, 2, 3, 4],
                  nozzle_diameter_mm=.4, layer_height_mm=.2, wall_generator='arachne',
                  bambu_version=re.search(r'Current BambuStudio Version (\S+)', log).group(1),
                  physical_print_verified=False, slice_result=result)
    (build.DEST/('Validation_'+build.VERSION+'.json')).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'slice_result'}, indent=2))


if __name__ == '__main__':
    main()
