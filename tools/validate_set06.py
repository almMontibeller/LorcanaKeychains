#!/usr/bin/env python3
"""Check Set 06's relief and its actual A1 / 0.4 mm Bambu toolpaths.

Verifies backing/settings preservation, closed meshes, support and separation,
then every relief layer's ten letters, two waves and three open counters.
Requires NumPy, Pillow, GLU/Cairo and the installed Bambu Studio runtime.
"""
import argparse
import json
import math
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import rebuild_set06 as build
from rebuild_set04 import area, boundary_loops, inside, orient
from rebuild_set05 import footprint, STEP, xy_pixel
from refine_loops_and_underline import draw_bead, read_toolpaths, render_slice, toolpath_checks
from full_height_narrow_rims import bore_index, isometric
from repair_v02 import NS, read_parts
from set_versions import saved_project
from standardize_loop_diameters import bounds, digest, mesh_stats, package
from validate_bambu import bambu_command

LOGS = build.ROOT / 'validation' / build.SET.name / build.VERSION
LETTER_SEEDS = dict(azurite_A=(222, 300), azurite_Z=(287, 275),
                    azurite_U=(373, 180), azurite_R=(485, 130),
                    azurite_I=(588, 220), azurite_T=(666, 200),
                    azurite_E=(743, 210), sea_S=(516, 411),
                    sea_E=(563, 390), sea_A=(727, 385))
WAVE_SEEDS = dict(left_wave=(282, 360), right_wave=(787, 309))
COUNTER_PROBES = dict(elongated_A=(201, 140), elongated_A_upper=(205, 112),
                      R_bowl=(508, 137), triangular_SEA_A=(700, 366))


def distance_between_contours(first, second):
    """Exact vertex-to-segment minimum in both directions for sampled curves."""
    def one_way(cs, ds):
        p = np.asarray([p for c in cs for p in c])
        a = np.asarray([p for c in ds for p in c])
        b = np.asarray([p for c in ds for p in c[1:]+c[:1]])
        d = b-a
        t = np.clip(np.sum((p[:, None]-a)*d, axis=2)/np.sum(d*d, axis=1), 0, 1)
        return float(np.sqrt(np.sum((p[:, None]-(a+t[:, :, None]*d))**2, axis=2)).min())
    return min(one_way(first, second), one_way(second, first))


def assert_simple(loop):
    """Check nonadjacent contour segments for crossings/touches."""
    a, b = np.asarray(loop), np.asarray(loop[1:]+loop[:1])
    d = b-a
    cross = lambda u, v: u[..., 0]*v[..., 1]-u[..., 1]*v[..., 0]
    for i in range(len(loop)):
        j = np.arange(i+2, len(loop))
        if i == 0:
            j = j[j != len(loop)-1]
        if not len(j):
            continue
        box = np.all(np.maximum(np.minimum(a[i], b[i]), np.minimum(a[j], b[j])) <=
                     np.minimum(np.maximum(a[i], b[i]), np.maximum(a[j], b[j]))+1e-10, axis=1)
        j = j[box]
        if not len(j):
            continue
        den = cross(d[i], d[j])
        nonparallel = abs(den) > 1e-12
        q = a[j]-a[i]
        t = np.zeros(len(j))
        u = np.zeros(len(j))
        np.divide(cross(q, d[j]), den, out=t, where=nonparallel)
        np.divide(cross(q, d[i]), den, out=u, where=nonparallel)
        crossing = nonparallel & (t >= -1e-9) & (t <= 1+1e-9) & (u >= -1e-9) & (u <= 1+1e-9)
        collinear = ~nonparallel & (abs(cross(q, d[i])) < 1e-10)
        assert not np.any(crossing | collinear), ('self-intersecting contour', i, j[crossing | collinear])


def mesh_checks():
    data, old_data = package(build.PROJECT), package(build.SOURCE)
    parts, old_parts = read_parts(data), read_parts(old_data)
    assert parts[0] == old_parts[0], 'backing or attachment changed'
    if build.VERSION == 'v08':
        assert parts[2] == old_parts[2], 'v07 gold lettering changed'
    assert data['Metadata/project_settings.config'] == old_data['Metadata/project_settings.config']
    settings = json.loads(data['Metadata/project_settings.config'])
    assert settings['nozzle_diameter'] == ['0.4']
    assert settings['wall_generator'] == 'arachne'
    assert float(settings['layer_height']) == .2
    roots = [ET.fromstring(d['3D/3dmodel.model']) for d in (old_data, data)]
    assert ET.tostring(roots[0].find('m:build', NS)) == ET.tostring(roots[1].find('m:build', NS))
    configs = [ET.fromstring(d['Metadata/model_settings.config']) for d in (old_data, data)]
    assert ET.tostring(configs[0].find('assemble')) == ET.tostring(configs[1].find('assemble'))
    assert ET.tostring(configs[0].find('./object/part')) == ET.tostring(configs[1].find('./object/part'))
    comp = roots[0].find('.//m:component', NS)
    resource = comp.get('{'+build.PROD+'}path').lstrip('/')
    meshpath = f"m:resources/m:object[@id='{comp.get('objectid')}']/m:mesh"
    assert ET.tostring(ET.fromstring(old_data[resource]).find(meshpath, NS)) == ET.tostring(
        ET.fromstring(data[resource]).find(meshpath, NS)), 'backing XML changed'
    if build.VERSION == 'v08':
        goldcomp = roots[0].findall('.//m:component', NS)[2]
        goldpath = f"m:resources/m:object[@id='{goldcomp.get('objectid')}']/m:mesh"
        goldresource = goldcomp.get('{'+build.PROD+'}path').lstrip('/')
        assert ET.tostring(ET.fromstring(old_data[goldresource]).find(goldpath, NS)) == ET.tostring(
            ET.fromstring(data[goldresource]).find(goldpath, NS)), 'gold XML changed'
        assert ET.tostring(configs[0].find('./object').findall('part')[2]) == ET.tostring(
            configs[1].find('./object').findall('part')[2]), 'gold part settings changed'
    stats = [dict(name=p['name'], slot=p['slot'], **mesh_stats(p)) for p in parts]
    assert all(p['degenerate_triangles'] == 0 for p in stats)
    assert {round(v[2], 6) for v in parts[0]['vertices']} == {0., 2.}
    for p, top in zip(parts[1:], (2.4, 2.8)):
        assert {round(v[2], 6) for v in p['vertices']} == {2., top}
    art = build.artwork()
    for group in art.values():
        for loops in group.values():
            for loop in loops:
                assert_simple(loop)
            for counter in loops[1:]:
                assert all(inside(p, loops[0]) for p in counter), 'counter exits its letter'
    bases, ice, gold = [footprint(boundary_loops(p)) for p in parts]
    assert not np.any(ice & ~bases), 'unsupported ice relief'
    assert not np.any(gold & ~bases), 'unsupported gold relief'
    assert not np.any(ice & gold), 'overlapping colours'
    pairs = []
    letters = list(art['gold'].items())
    for i, (name, loops) in enumerate(letters):
        for other, other_loops in letters[i+1:]:
            gap = distance_between_contours(loops, other_loops)
            assert gap >= .45, (name, other, 'less than 0.45 mm clearance', gap)
            if gap < .85:
                pairs.append(dict(letters=[name, other], gap_mm=round(gap, 5)))
    counters = {}
    old_loops = orient(boundary_loops(old_parts[2]))
    for name in ('azurite_A', 'azurite_R', 'sea_A'):
        loop = art['gold'][name][1]
        centre = tuple(sum(p[k] for p in loop)/len(loop) for k in (0, 1))
        old_counter = next((c for c in old_loops if area(c) < 0 and inside(centre, c)), None)
        # Use a known interior probe to match the old tiny A counter, whose
        # centre does not coincide with the restored elongated triangle.
        if name == 'azurite_A':
            old_counter = next(c for c in old_loops if area(c) < 0 and inside(build.registered((201, 197)), c))
        if name == 'sea_A':
            old_counter = next(c for c in old_loops if area(c) < 0 and inside(build.registered((700, 365)), c))
        counters[name] = dict(area_mm2=round(abs(area(loop)), 4),
                              previous_area_mm2=round(abs(area(old_counter)), 4) if old_counter else None)
    assert len(boundary_loops(parts[1])) == 2, 'there should be only two ice contours'
    assert len(boundary_loops(parts[2])) == 13, 'ten gold letters and three counters required'
    bore = boundary_loops(parts[0])[bore_index(boundary_loops(parts[0]), 6.5)]
    geometry = dict(parts=stats, backing_xml_and_coordinates_exactly_preserved=True,
                    eyelet=dict(bore_diameter_mm=6.5, nominal_outer_diameter_mm=10.5,
                                nominal_radial_rim_mm=2., height_mm=2.),
                    plate_placement_preserved=True, filament_and_process_settings_byte_identical=True,
                    self_intersections=0, unsupported_relief_pixels=0, relief_overlap_pixels=0,
                    raster_check_resolution_mm=STEP, gold_letter_components=10, gold_counters=3,
                    ice_components=2, minimum_letter_clearance_mm=min(p['gap_mm'] for p in pairs),
                    close_letter_pairs=pairs, counters=counters,
                    relief_heights_mm=dict(ice=.4, gold=.8))
    if build.VERSION == 'v08':
        # Check that thickening only replaces the underside of each ribbon:
        # the initial M + three C commands describe its original upper crests.
        oldroot = ET.parse(build.VECTOR).getroot()
        newroot = ET.parse(build.WAVE_VECTOR).getroot()
        oldwaves = {p.get('id'): p.get('d').split()[:24]
                    for p in oldroot.findall("s:g[@id='ice']/s:path", build.SVG)}
        newwaves = {p.get('id'): p.get('d').split()[:24]
                    for p in newroot.findall("s:g[@id='ice']/s:path", build.SVG)}
        assert oldwaves == newwaves, 'upper wave crests changed'
        oldice = orient(boundary_loops(old_parts[1]))
        changes = {}
        for name, loops in art['ice'].items():
            newarea = sum(area(c) for c in loops)
            oldloop = next(c for c in oldice if inside(build.registered(WAVE_SEEDS[name]), c))
            oldarea = area(oldloop)
            assert newarea > 1.4*oldarea, (name, 'insufficient thickening')
            gap = min(distance_between_contours(loops, cs) for cs in art['gold'].values())
            assert gap >= .45, (name, 'too close to lettering', gap)
            changes[name] = dict(previous_area_mm2=round(oldarea, 4), area_mm2=round(newarea, 4),
                                 area_increase_percent=round(100*(newarea/oldarea-1), 1),
                                 minimum_gold_clearance_mm=round(gap, 4))
        geometry['gold_xml_and_coordinates_exactly_preserved'] = True
        geometry['upper_wave_crests_exactly_preserved'] = True
        geometry['wave_thickening'] = changes
    return parts, geometry, bore


def deposited_mask(paths, tool, bbox):
    image = Image.new('L', footprint([]).shape[::-1])
    draw = ImageDraw.Draw(image)
    for points, width, slot in paths:
        if slot == tool:
            points = [xy_pixel((x-bbox['x'], y-bbox['y'])) for x, y in points]
            draw_bead(draw, points, width/STEP, 255)
    return image


def connected_shapes(image, seeds):
    """Each seed must fill a different deposited shape; no other beads remain."""
    for index, (name, point) in enumerate(seeds.items()):
        pixel = tuple(round(p) for p in xy_pixel(build.registered(point)))
        assert image.getpixel(pixel) == 255, (name, 'missing or merged printed component')
        ImageDraw.floodfill(image, pixel, index+1)
    leftover = int(np.count_nonzero(np.asarray(image) == 255))
    assert leftover == 0, ('detached deposited pixels', leftover)
    return dict(continuous_components=len(seeds), detached_deposit_pixels=leftover)


def check_slice(parts, result, bore):
    plate = result['sliced_plates'][0]
    assert plate['warning_message'] == ''
    assert [f['id'] for f in plate['filaments']] == [1, 2, 3]
    assert all(f['main_used_g'] > 0 for f in plate['filaments'])
    bbox = plate['objects'][0]['bbox']
    layers = read_toolpaths(LOGS/'plate_1.gcode', bbox, 3)
    report = toolpath_checks(layers, parts, bbox, {}, None, loop_height=2., bore_loop=bore)
    checks = {}
    for z in (2.2, 2.4, 2.6, 2.8):
        gold = deposited_mask(layers[z], 2, bbox)
        probes = {}
        for name, point in COUNTER_PROBES.items():
            pixel = tuple(round(p) for p in xy_pixel(build.registered(point)))
            probes[name] = gold.getpixel(pixel) == 0
        assert all(probes.values()), (z, 'a counter closed in actual toolpaths', probes)
        gold_check = connected_shapes(gold, LETTER_SEEDS)
        checks[str(z)] = dict(gold=gold_check, counters_open=probes)
        if z <= 2.4:
            checks[str(z)]['ice'] = connected_shapes(deposited_mask(layers[z], 1, bbox), WAVE_SEEDS)
    report['relief_layers'] = checks
    report['deposition_check_resolution_mm'] = STEP
    render_slice(layers, parts, bbox, [p['color'] for p in parts],
                 build.DEST/(build.NAME+'_sliced_preview.png'), loop_height=2.)
    return report


def comparison(parts):
    old = read_parts(package(build.SOURCE))
    temporary = build.DEST/(build.NAME+'_previous_preview.png')
    build.preview(old, temporary)
    panels = [Image.open(temporary), Image.open(build.DEST/(build.NAME+'_preview.png'))]
    w, h = 1200, 740
    canvas = Image.new('RGB', (w*2, h), '#F5F5F5')
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype('/usr/share/fonts/TTF/DejaVuSans.ttf', 28)
    labels = (f'{build.SOURCE.parent.name} — previous',
              f'{build.VERSION} — fuller waves' if build.VERSION == 'v08' else 'v07 — refined contours')
    for i, (panel, label) in enumerate(zip(panels, labels)):
        panel.thumbnail((w, h-60), Image.Resampling.LANCZOS)
        canvas.paste(panel, (i*w+(w-panel.width)//2, 55+(h-60-panel.height)//2))
        draw.text((i*w+45, 18), label, font=font, fill='#193D58')
    canvas.save(build.DEST/(build.NAME+'_comparison.png'))
    temporary.unlink()
    isometric(parts, build.DEST/(build.NAME+'_isometric.png'))


def main():
    global LOGS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', choices=['v07', 'v08'], default='v08')
    parser.add_argument('--reuse-slice', action='store_true', help='Inspect existing slicer evidence without re-slicing')
    args = parser.parse_args()
    build.configure(args.version)
    build.PROJECT = saved_project(build.SET, build.VERSION)
    build.DEST = build.PROJECT.parent
    LOGS = build.ROOT / 'validation' / build.SET.name / build.VERSION
    parts, geometry, bore = mesh_checks()
    LOGS.mkdir(parents=True, exist_ok=True)
    if not args.reuse_slice:
        with tempfile.TemporaryDirectory(prefix='lorcana-set06-') as directory:
            run = subprocess.run(bambu_command()+['--datadir', directory, '--debug', '2', '--info',
                                  '--slice', '1', '--outputdir', str(LOGS), str(build.PROJECT)],
                                 cwd=LOGS, capture_output=True, text=True, timeout=180)
        (LOGS/'slice.log').write_text(run.stdout+run.stderr)
        assert run.returncode == 0, (run.returncode, (run.stdout+run.stderr)[-2000:])
        (LOGS/'project.sha256').write_text(digest(build.PROJECT)+'\n')
    else:
        assert (LOGS/'project.sha256').read_text().strip() == digest(build.PROJECT), 'slice is stale'
    log = (LOGS/'slice.log').read_text()
    result = json.loads((LOGS/'result.json').read_text())
    assert result['return_code'] == 0 and 'manifold = yes' in log
    toolpaths = check_slice(parts, result, bore)
    comparison(parts)
    report = dict(project=str(build.PROJECT.relative_to(build.ROOT)), sha256=digest(build.PROJECT),
                  source=str(build.SOURCE.relative_to(build.ROOT)), source_sha256=digest(build.SOURCE),
                  vector=str(build.VECTOR.relative_to(build.ROOT)), vector_sha256=digest(build.VECTOR),
                  wave_vector=(str(build.WAVE_VECTOR.relative_to(build.ROOT)) if build.VERSION == 'v08' else None),
                  wave_vector_sha256=digest(build.WAVE_VECTOR) if build.VERSION == 'v08' else None,
                  artwork_reference=str(build.ARTWORK.relative_to(build.ROOT)),
                  geometry=geometry, nozzle_diameter_mm=.4, layer_height_mm=.2,
                  wall_generator='arachne', toolpath_checks=toolpaths, used_filament_slots=[1, 2, 3],
                  bambu_version=re.search(r'Current BambuStudio Version (\S+)', log).group(1),
                  slice_result=result, physical_print_verified=False,
                  environment_notes='Installed Flatpak CLI uses embedded settings despite missing /app preset-resource messages.')
    (build.DEST/f'Validation_{build.VERSION}.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('slice_result',)}, indent=2))


if __name__ == '__main__':
    main()
