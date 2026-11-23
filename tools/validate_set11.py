#!/usr/bin/env python3
"""Audit the Winterspell mesh and compare three Bambu Studio slices."""

import argparse
import itertools
import json
import math
import re
import subprocess
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
from PIL import Image, ImageDraw
from shapely.affinity import scale
from shapely.geometry import Polygon
from shapely.ops import unary_union

import rebuild_set11 as build
from rebuild_set04 import area, boundary_loops, orient
from refine_loops_and_underline import draw_bead, read_toolpaths, render_slice, toolpath_checks
from repair_v1_1 import NS, read_parts
from standardize_loop_diameters import bounds, centre, digest, mesh_stats, package
from validate_bambu import bambu_command
from validate_set09 import regions

SETTINGS = 'Metadata/project_settings.config'
PROFILE_ROOT = Path('/var/lib/flatpak/app/com.bambulab.BambuStudio/current/active/files'
                    '/share/BambuStudio/profiles/BBL')
PROFILE_METADATA = {'type', 'name', 'inherits', 'from', 'setting_id', 'instantiation',
                    'include', 'description', 'filament_id', 'compatible_printers'}
STEP = .025
ORIGIN = (-1., 30.)
SIZE = (4320, 1320)
CORE_INSET = .17


def polygons(part):
    contours = orient(boundary_loops(part))
    shells = [Polygon(c) for c in contours if area(c) > 0]
    holes = [c for c in contours if area(c) < 0]
    return [Polygon(shell.exterior, [h for h in holes if shell.contains(Polygon(h))])
            for shell in shells]


def extents(parts):
    return [round(b - a, 4) for a, b in bounds(parts[0])[:2]] + [
        round(max(p[2] for p in parts[-1]['vertices']), 4)]


def geometry_checks(path):
    before, after = package(build.SOURCE), package(path)
    old, parts = read_parts(before), read_parts(after)
    assert before[SETTINGS] == after[SETTINGS]
    settings = json.loads(after[SETTINGS])
    assert settings['nozzle_diameter'] == ['0.4'] and settings['wall_generator'] == 'arachne'
    for filename, element in (('3D/3dmodel.model', 'm:build'),
                              ('Metadata/model_settings.config', 'assemble')):
        assert ET.tostring(ET.fromstring(before[filename]).find(element, NS)) == ET.tostring(
            ET.fromstring(after[filename]).find(element, NS))
    assert [p['slot'] for p in parts] == [1, 2, 3]
    stats = [dict(name=p['name'], slot=p['slot'], triangles=len(p['faces']), **mesh_stats(p))
             for p in parts]
    assert all(s['degenerate_triangles'] == 0 for s in stats)
    assert [set(round(v[2], 6) for v in p['vertices']) for p in parts] == [
        set(build.Z_LEVELS[i:i + 2]) for i in range(3)]
    (base,), (field,), glyphs = map(polygons, parts)
    assert all(p.is_valid for p in (base, field, *glyphs))
    assert len(base.interiors) == 1 and not field.interiors and len(glyphs) == 11
    bore = build.old_bore(parts[0])
    assert sorted(bore) == sorted(build.old_bore(old[0]))
    _, letters = build.artwork()
    glyph_field = unary_union(glyphs)
    assert glyph_field.symmetric_difference(unary_union(list(letters.values()))).area < 1e-4
    gap, a, b = min((p.distance(q), a, b)
                    for (a, p), (b, q) in itertools.combinations(letters.items(), 2))
    rim = base.exterior.distance(field)
    clearance = field.boundary.distance(glyph_field)
    assert gap >= .50 and rim >= .83 and clearance >= .67
    assert base.covers(field) and all(field.covers(glyph) for glyph in glyphs)
    before_ivory = len(polygons(old[-1]))
    return parts, letters, dict(
        parts=stats, dimensions_previous_mm=extents(old), dimensions_mm=extents(parts),
        backing_openings_previous=sum(len(p.interiors) for p in polygons(old[0])),
        backing_openings=1, ice_blue_components=1, ivory_components_previous=before_ivory,
        ivory_components=len(glyphs), contiguous_glyphs=list(letters),
        narrowest_letter_gap_mm=round(gap, 4), closest_letters=[a, b],
        min_field_clearance_mm=round(clearance, 4), min_marine_border_mm=round(rim, 4),
        relief_fully_supported=True, volumetric_colour_overlap=False,
        eyelet=dict(centre_mm=centre(bore), bore_mm=6.5, outer_diameter_mm=10.5,
                    radial_rim_mm=2., neck_width_mm=7., height_mm=2.,
                    bore_coordinates_exactly_preserved=True),
        plate_placement_preserved=True, filament_and_process_settings_byte_identical=True)


def installed_profile(kind, name):
    path = next((PROFILE_ROOT / kind).rglob(name + '.json'))
    profile = json.loads(path.read_text())
    values = installed_profile(kind, profile['inherits']) if profile.get('inherits') else {}
    for included in profile.get('include', []):
        values.update(installed_profile(kind, included))
    values.update({k: v for k, v in profile.items() if k not in PROFILE_METADATA})
    return values


def fine_project(source, target):
    data = package(source)
    settings = json.loads(data[SETTINGS])
    machine = 'Bambu Lab A1 0.2 nozzle'
    process = '0.10mm Standard @BBL A1 0.2 nozzle'
    filaments = [name + ' 0.2 nozzle' for name in settings['filament_settings_id']]
    settings.update(installed_profile('machine', machine))
    settings.update(installed_profile('process', process))
    profiles = [installed_profile('filament', name) for name in filaments]
    for key in set.intersection(*(set(profile) for profile in profiles)):
        values = [profile[key] for profile in profiles]
        if all(isinstance(v, list) and v for v in values):
            settings[key] = [v[0] for v in values]
        elif all(isinstance(v, str) for v in values):
            settings[key] = values[0]
    settings.update(printer_settings_id=machine, print_settings_id=process,
                    filament_settings_id=filaments, curr_bed_type='Textured PEI Plate',
                    wall_generator='arachne', wall_loops='3', bottom_shell_layers='10',
                    top_shell_layers='10', initial_layer_print_height='0.1',
                    sparse_infill_density='15%', sparse_infill_pattern='grid',
                    enable_support='0', brim_type='no_brim', enable_prime_tower='1')
    assert settings['nozzle_diameter'] == ['0.2']
    assert settings['filament_colour'] == json.loads(data[SETTINGS])['filament_colour']
    data[SETTINGS] = json.dumps(settings, indent=4).encode()
    with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
        for name, content in data.items():
            archive.writestr(name, content)


def enlarged_parts(parts, factor, cy):
    return [dict(part, vertices=[(x * factor, cy + (y - cy) * factor, z)
                                 for x, y, z in part['vertices']]) for part in parts]


def pixel(point):
    x, y = point
    return (x - ORIGIN[0]) / STEP, (ORIGIN[1] - y) / STEP


def raster(shape):
    image = Image.new('L', SIZE)
    draw = ImageDraw.Draw(image)
    for polygon in shape.geoms if shape.geom_type == 'MultiPolygon' else [shape]:
        draw.polygon([pixel(p) for p in polygon.exterior.coords], fill=255)
        for hole in polygon.interiors:
            draw.polygon([pixel(p) for p in hole.coords], fill=0)
    return np.asarray(image) == 255


def deposited(paths, slot, dx, dy):
    image = Image.new('L', SIZE)
    draw = ImageDraw.Draw(image)
    for points, width, tool in paths:
        if tool == slot:
            draw_bead(draw, [pixel((x - dx, y - dy)) for x, y in points], width / STEP, 255)
    return image


def layer_report(layers, bbox, parts, letters):
    bb = bounds(parts[0])
    dx, dy = bbox['x'] - bb[0][0], bbox['y'] - bb[1][0]
    shapes = {name: (raster(p), raster(p.buffer(-CORE_INSET))) for name, p in letters.items()}
    reports = {}
    for z, paths in sorted(layers.items()):
        if z <= build.Z_LEVELS[2] or not any(tool == 2 for _, _, tool in paths):
            continue
        image = deposited(paths, 2, dx, dy)
        raw = np.asarray(image) == 255
        details = {}
        for name, (footprint, core) in shapes.items():
            yy, xx = np.where(raw & core)
            if len(xx):
                component = image.copy()
                ImageDraw.floodfill(component, (int(xx[len(xx) // 2]), int(yy[len(yy) // 2])), 128)
                connected = np.asarray(component) == 128
            else:
                connected = np.zeros_like(raw)
            details[name] = dict(
                deposited_core_fraction=round(np.count_nonzero(connected & core) / core.sum(), 5),
                deposited_nominal_fraction=round(np.count_nonzero(connected & footprint)
                                                 / footprint.sum(), 5))
        reports[str(z)] = dict(deposit_components=regions(raw)[0], letters=details)
    return reports


def field_report(layers, bbox, parts):
    bb = bounds(parts[0])
    dx, dy = bbox['x'] - bb[0][0], bbox['y'] - bb[1][0]
    cores = [raster(polygons(part)[0].buffer(-.25)) for part in parts[:2]]
    report = {}
    for z, slot in ((2., 0), (2.2, 1), (2.4, 1)):
        raw = np.asarray(deposited(layers[z], slot, dx, dy)) == 255
        count, largest = regions(raw)
        core = cores[slot]
        coverage = round(float(np.count_nonzero(core & largest) / core.sum()), 5)
        assert count == 1 and coverage >= .99, (z, count, coverage)
        report[str(z)] = dict(filament_slot=slot + 1, deposit_components=count,
                              deposited_core_fraction=coverage)
    return report


def slice_case(case, project, parts, letters, logs):
    name, factor, nozzle, layer_height = case
    folder = logs / name
    folder.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='winterspell-slice-') as work:
        temporary = Path(work) / project.name
        if nozzle == .2:
            fine_project(project, temporary)
            project = temporary
        if factor != 1.:
            cy = centre(build.old_bore(parts[0]))[1]
            parts = enlarged_parts(parts, factor, cy)
            letters = {n: scale(p, xfact=factor, yfact=factor, origin=(0, cy))
                       for n, p in letters.items()}
            build.write_project(project, temporary, parts, {0, 1, 2},
                                'Temporary 110% XY scale test, original Z heights and process.')
            project = temporary
        run = subprocess.run(bambu_command() + ['--datadir', str(Path(work) / 'settings'),
                             '--debug', '2', '--info', '--slice', '1', '--outputdir',
                             str(folder), str(project)],
                             cwd=work, capture_output=True, text=True, timeout=180)
    log = run.stdout + run.stderr
    (folder / 'slice.log').write_text(log)
    assert run.returncode == 0 and 'manifold = yes' in log, log[-3500:]
    result = json.loads((folder / 'result.json').read_text())
    assert result['return_code'] == 0 and math.isclose(result['layer_height'], layer_height, abs_tol=1e-6)
    plate = result['sliced_plates'][0]
    assert plate['warning_message'] == ''
    assert [f['id'] for f in plate['filaments']] == [1, 2, 3]
    assert all(f['main_used_g'] > 0 for f in plate['filaments'])
    bbox = plate['objects'][0]['bbox']
    layers = read_toolpaths(folder / 'plate_1.gcode', bbox, 3)
    glyphs = layer_report(layers, bbox, parts, letters)
    assert len(glyphs) == round((build.Z_LEVELS[3] - build.Z_LEVELS[2]) / layer_height)
    top = glyphs['3.0']['letters']
    minimum = min(d['deposited_core_fraction'] for z in glyphs.values() for d in z['letters'].values())
    return dict(nozzle_mm=nozzle, layer_height_mm=layer_height, xy_scale=factor,
                overall_dimensions_mm=extents(parts), bore_mm=round(6.5 * factor, 2),
                estimated_time_minutes=round(plate['total_predication'] / 60, 1),
                filament_slots=[f['id'] for f in plate['filaments']],
                plate_warnings=plate['warning_message'],
                min_core_coverage_all_layers=minimum,
                mean_top_nominal_coverage=round(sum(v['deposited_nominal_fraction']
                                                    for v in top.values()) / len(top), 5),
                layer_results=glyphs,
                bambu_version=re.search(r'Current BambuStudio Version (\S+)', log).group(1)), layers, bbox


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=build.DEST / (build.NAME + '.3mf'))
    parser.add_argument('--logs-dir', type=Path)
    args = parser.parse_args()
    project = args.project.resolve()
    logs = args.logs_dir
    if logs is None:
        logs = (build.ROOT / 'validation' / build.SET.name / build.VERSION
                if project.parent == build.DEST else project.parent / 'validation')
    logs = logs.resolve()

    parts, letters, geometry = geometry_checks(project)
    cases = [('stock_04', 1., .4, .2), ('scaled_04', 1.1, .4, .2), ('stock_02', 1., .2, .1)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [pool.submit(slice_case, case, project, parts, letters, logs) for case in cases]
        (stock, layers, bbox), (scaled, _, _), (fine, _, _) = [job.result() for job in jobs]
    for test in (stock, scaled, fine):
        assert all(layer['deposit_components'] == len(letters)
                   for layer in test['layer_results'].values())
        assert test['min_core_coverage_all_layers'] >= .97, test
    bore = build.old_bore(parts[0])
    eyelet = toolpath_checks(layers, parts, bbox, {}, None, loop_height=2., bore_loop=bore)
    render_slice(layers, parts, bbox, [p['color'] for p in parts],
                 project.with_name(project.stem + '_sliced_preview.png'), loop_height=2.)
    geometry_path = project.parent / ('Geometry_' + build.VERSION + '.json')
    geometry_path.write_text(json.dumps(geometry, indent=2) + '\n')
    report = dict(project=project.name, output_sha256=digest(project),
                  baseline=str(build.SOURCE.relative_to(build.ROOT)), baseline_sha256=digest(build.SOURCE),
                  geometry_report=geometry_path.name, physical_print_verified=False,
                  raster_step_mm=STEP, core_inset_mm=CORE_INSET, stock_eyelet_toolpaths=eyelet,
                  stock_backing_and_field_toolpaths=field_report(layers, bbox, parts),
                  slice_comparison=dict(stock_04=stock, scaled_04=scaled, stock_02=fine))
    (project.parent / ('Validation_' + build.VERSION + '.json')).write_text(
        json.dumps(report, indent=2) + '\n')
    for name, item in report['slice_comparison'].items():
        print(name, {k: v for k, v in item.items() if k != 'layer_results'})


if __name__ == '__main__':
    main()
