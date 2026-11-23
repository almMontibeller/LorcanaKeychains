#!/usr/bin/env python3
"""Build and slice Winterspell v09 with a Dark Blue field and raised snow caps."""

import argparse
import copy
import json
import math
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import NAMESPACE_URL, uuid5
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import Polygon

import rebuild_set07 as curves
import rebuild_set11 as trace
import recolor_set11 as colors
import validate_set11 as audit
from full_height_narrow_rims import isometric
from rebuild_set09 import preview
from refine_loops_and_underline import read_toolpaths, render_slice, toolpath_checks
from repair_v02 import NS, PROD, read_parts, thumbnail
from standardize_loop_diameters import bounds, digest, mesh_stats, package, write_mesh
from validate_bambu import bambu_command
from validate_set09 import regions

ROOT = trace.ROOT
VERSION = 'v09'
NAME = trace.SET.name + '_' + VERSION
DEST = trace.SET / VERSION
BASELINE = colors.DEST / (colors.NAME + '.3mf')
GEOMETRY_SOURCE = colors.SOURCE
VECTOR = Path(__file__).with_name('set11_snow_caps.svg')
PALETTE_SLOTS = (0, 3, 2)
PALETTE = [colors.PALETTE[i] for i in PALETTE_SLOTS]
SNOW_BOTTOM = 3.
SNOW_HEIGHT = .4
SNOW_INSET = .05
SNOW_LINE_WIDTHS = dict(outer_wall_line_width=.38, inner_wall_line_width=.38,
                       top_surface_line_width=.33, internal_solid_infill_line_width=.33)


def snow_caps(letters):
    svg = ET.parse(VECTOR).getroot()
    registered = curves.registered
    curves.registered = trace.registered
    caps = {}
    try:
        for path in svg.findall("s:g[@id='snow']/s:path", trace.SVG):
            title, letter = (path.attrib[key] for key in ('id', 'data-letter'))
            mask = Polygon(curves.sample(path.attrib['d'])[0])
            supported = letters[letter].buffer(-SNOW_INSET)
            cap = supported.intersection(mask).simplify(.009)
            assert cap.geom_type == 'Polygon' and cap.is_valid and letters[letter].covers(cap)
            caps[title] = (letter, cap)
    finally:
        curves.registered = registered
    return caps


def output_parts(source, caps):
    backing, field, letters = source
    snow = curves.relief([trace.loops(p) for _, p in caps.values()], SNOW_BOTTOM,
                         SNOW_HEIGHT, dict(letters, slot=3, color=PALETTE[2],
                                           name='Ice Blue · snow on lettering'))
    return [dict(backing, slot=1, color=PALETTE[0], name='Dark Blue · backing and eyelet'),
            dict(field, slot=1, color=PALETTE[0], name='Dark Blue · title field'),
            dict(letters, slot=2, color=PALETTE[1], name='Sunflower Yellow · lettering'),
            snow]


def print_settings(source, baseline):
    settings = copy.deepcopy(source)
    for key, value in settings.items():
        donor = baseline.get(key)
        if isinstance(value, list) and len(value) == 3 and isinstance(donor, list) and len(donor) == 4:
            settings[key] = [donor[i] for i in PALETTE_SLOTS]
    settings['filament_self_index'] = ['1', '2', '3']
    settings['flush_volumes_matrix'] = [baseline['flush_volumes_matrix'][4*i+j]
                                        for i in PALETTE_SLOTS for j in PALETTE_SLOTS]
    settings['flush_volumes_vector'] = [baseline['flush_volumes_vector'][2*i+j]
                                        for i in PALETTE_SLOTS for j in range(2)]
    assert settings['filament_colour'] == PALETTE
    assert settings['filament_settings_id'] == ['Bambu PLA Matte @BBL A1',
                                               'Bambu PLA Basic @BBL A1',
                                               'Bambu PLA Matte @BBL A1']
    return settings


def write_project(data, baseline, parts, project):
    root = ET.fromstring(data[colors.MODEL])
    config = ET.fromstring(data[colors.CONFIG])
    obj = config.find('object')
    assembly = root.find(f"m:resources/m:object[@id='{obj.attrib['id']}']/m:components", NS)
    path = assembly[-1].attrib[PROD + 'path'].lstrip('/')
    child = ET.fromstring(data[path])
    meshes = child.find('m:resources', NS)
    object_id = str(max(int(o.attrib['id']) for o in (*meshes, root.find('m:resources/m:object', NS))) + 1)
    mesh = copy.deepcopy(meshes[-1])
    component = copy.deepcopy(assembly[-1])
    meta = copy.deepcopy(obj.findall('part')[-1])
    for item, id_key, uuid_key, label in (
            (mesh, 'id', PROD + 'UUID', 'mesh'),
            (component, 'objectid', PROD + 'UUID', 'component'),
            (meta, 'id', 'uuid', 'part')):
        item.set(id_key, object_id)
        item.set(uuid_key, str(uuid5(NAMESPACE_URL, f'{NAME}/snow/{label}')))
    write_mesh(mesh, parts[-1])
    meshes.append(mesh)
    assembly.append(component)
    obj.append(meta)
    for element, part in zip(obj.findall('part'), parts, strict=True):
        element.find("metadata[@key='name']").set('value', part['name'])
        element.find("metadata[@key='extruder']").set('value', str(part['slot']))
        element.find('mesh_stat').set('face_count', str(len(part['faces'])))
    for key, width in SNOW_LINE_WIDTHS.items():
        ET.SubElement(meta, 'metadata', {'key': key, 'value': str(width)})
    obj.find("metadata[@key='name']").set('value', project.stem)
    obj.find('metadata[@face_count]').set('face_count', str(sum(len(p['faces']) for p in parts)))
    root.find("m:metadata[@name='Description']", NS).text = (
        'Winterspell v09. Single Dark Blue background, Sunflower Yellow lettering, and raised '
        'Ice Blue snow accents. Original footprint and 6.5 mm eyelet bore. A1 0.4 mm Arachne.')
    data[colors.SETTINGS] = json.dumps(print_settings(json.loads(data[colors.SETTINGS]),
                                      json.loads(baseline[colors.SETTINGS])), indent=4).encode()
    colors.put_xml(data, colors.MODEL, root)
    colors.put_xml(data, colors.CONFIG, config)
    colors.put_xml(data, path, child)
    data['Metadata/plate_1.png'] = thumbnail(parts, 512)
    data['Metadata/plate_no_light_1.png'] = data['Metadata/plate_1.png']
    data['Metadata/plate_1_small.png'] = thumbnail(parts, 128)
    with ZipFile(project, 'x', ZIP_DEFLATED) as archive:
        for key, value in data.items():
            archive.writestr(key, value)


def compare(old, new, path):
    font_path = next(Path('/usr/share/fonts').rglob('DejaVuSans.ttf'), None)
    font = ImageFont.truetype(str(font_path), 25) if font_path else ImageFont.load_default(size=25)
    with TemporaryDirectory() as tmp:
        panels = []
        for parts in (old, new):
            panel = Path(tmp) / 'panel.png'
            preview(parts, panel, 1500, bounds(old[0]))
            with Image.open(panel) as image:
                panels.append(image.convert('RGB'))
    canvas = Image.new('RGB', (1500, 2 * (panels[0].height + 56)), '#f5f5f5')
    draw = ImageDraw.Draw(canvas)
    for index, (panel, label) in enumerate(zip(panels, ('v08 · Three blue tones',
                                                        'v09 · Dark Blue with lettering snow caps'))):
        y = index * (panel.height + 56)
        canvas.paste(panel, (0, y + 56))
        draw.text((30, y + 16), label, fill='#193d58', font=font)
    canvas.save(path)


def validate_geometry(baseline, source_parts, new, parts, letters, caps):
    for old, current in zip(source_parts, parts):
        assert old['vertices'] == current['vertices'] and old['faces'] == current['faces']
    old = read_parts(baseline)
    for a, b in ((old[0], parts[0]), (old[-1], parts[2])):
        assert a['vertices'] == b['vertices'] and a['faces'] == b['faces']
    for key, tag in ((colors.MODEL, 'm:build'), (colors.CONFIG, 'assemble')):
        old_tree, new_tree = (ET.fromstring(d[key]) for d in (baseline, new))
        assert ET.tostring(old_tree.find(tag, NS)) == ET.tostring(new_tree.find(tag, NS))
    assert [p['slot'] for p in parts] == [1, 1, 2, 3]
    assert [p['color'] for p in parts] == [PALETTE[0], *PALETTE]
    assert {round(p[2], 6) for p in parts[-1]['vertices']} == {3., 3.4}
    stats = [dict(name=p['name'], slot=p['slot'], **mesh_stats(p)) for p in parts]
    assert all(p['degenerate_triangles'] == 0 for p in stats)
    saved_caps = audit.polygons(parts[-1])
    assert len(saved_caps) == len(caps)
    cap_details = {}
    for name, (letter, expected) in caps.items():
        actual = next(p for p in saved_caps if p.covers(expected.representative_point()))
        assert actual.symmetric_difference(expected).area < .0001
        assert letters[letter].covers(actual) and actual.buffer(-.25).area > 1
        cap_details[name] = dict(letter=letter, area_mm2=round(actual.area, 3))
    return dict(parts=stats, total_dimensions_mm=audit.extents(parts),
                backing_and_letters_match_v08=True, field_matches_v07=True, bore_mm=6.5,
                cap_height_mm=SNOW_HEIGHT, cap_z_mm=[3., 3.4], caps=cap_details)


def slice_model(project, parts, letters, caps, logs):
    logs.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='winterspell-snow-') as work:
        run = subprocess.run(bambu_command() + ['--datadir', work, '--debug', '2', '--info',
                             '--slice', '1', '--outputdir', str(logs), str(project)],
                             cwd=logs, capture_output=True, text=True, timeout=180)
    log = run.stdout + run.stderr
    (logs / 'slice.log').write_text(log)
    assert run.returncode == 0 and 'manifold = yes' in log, log[-2400:]
    result = json.loads((logs / 'result.json').read_text())
    plate, = result['sliced_plates']
    assert result['return_code'] == 0 and not plate['warning_message']
    assert math.isclose(result['layer_height'], .2, abs_tol=1e-6)
    assert [f['id'] for f in plate['filaments']] == [1, 2, 3] and all(f['main_used_g'] > 0 for f in plate['filaments'])
    bbox = plate['objects'][0]['bbox']
    layers = read_toolpaths(logs / 'plate_1.gcode', bbox, 3)
    gold_paths = {z: [(points, width, 2) for points, width, tool in paths if tool == 1]
                  for z, paths in layers.items()}
    gold = audit.layer_report(gold_paths, bbox, parts, letters)
    snow = audit.layer_report(layers, bbox, parts, {name: p for name, (_, p) in caps.items()})
    for details, targets, count in (
            (gold, {'2.6': .97, '2.8': .97, '3.0': .97}, len(letters)),
            (snow, {'3.2': .95, '3.4': .97}, len(caps))):
        assert details.keys() == targets.keys(), tuple(details)
        for z, threshold in targets.items():
            layer = details[z]
            assert layer['deposit_components'] == count, (z, layer)
            assert all(r['deposited_core_fraction'] >= threshold for r in layer['letters'].values()), (z, layer)
    bb = bounds(parts[0])
    blue = {}
    for z, part in ((2., parts[0]), (2.2, parts[1]), (2.4, parts[1])):
        footprint, = audit.polygons(part)
        core = audit.raster(footprint.buffer(-.25))
        raw = np.asarray(audit.deposited(layers[z], 0, bbox['x'] - bb[0][0], bbox['y'] - bb[1][0])) == 255
        count, largest = regions(raw)
        coverage = round(float(np.count_nonzero(core & largest) / core.sum()), 5)
        assert count == 1 and coverage >= .99, (z, count, coverage)
        blue[str(z)] = dict(deposit_components=count, deposited_core_fraction=coverage)
    render_slice(layers, parts, bbox, PALETTE, project.with_name(NAME + '_sliced_preview.png'), loop_height=2.)
    eyelet = toolpath_checks(layers, parts, bbox, {}, None, loop_height=2.,
                             bore_loop=trace.old_bore(parts[0]))
    return dict(bambu_version=re.search(r'Current BambuStudio Version (\S+)', log).group(1),
                estimated_time_minutes=round(plate['total_predication'] / 60, 1),
                nozzle_mm=.4, layer_height_mm=.2, xy_scale=1.,
                plate_warnings=plate['warning_message'], filament_slots=[1, 2, 3],
                snow_line_widths_mm=SNOW_LINE_WIDTHS,
                physical_print_verified=False, eyelet=eyelet, background_layers=blue,
                gold_layers=gold, snow_layers=snow)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=DEST)
    args = parser.parse_args()
    dest = args.output_dir.resolve()
    project = dest / (NAME + '.3mf')
    if project.exists():
        raise FileExistsError(project)
    dest.mkdir(parents=True, exist_ok=True)
    logs = ROOT / 'validation' / trace.SET.name / VERSION if dest == DEST else dest / 'validation'
    source, baseline = map(package, (GEOMETRY_SOURCE, BASELINE))
    source_parts = read_parts(source)
    _, letters = trace.artwork()
    caps = snow_caps(letters)
    write_project(source, baseline, output_parts(source_parts, caps), project)
    new = package(project)
    parts = read_parts(new)
    geometry = validate_geometry(baseline, source_parts, new, parts, letters, caps)
    preview(parts, dest / (NAME + '_preview.png'))
    isometric(parts, dest / (NAME + '_isometric.png'))
    compare(read_parts(baseline), parts, dest / (NAME + '_comparison.png'))
    validation = slice_model(project, parts, letters, caps, logs)
    for name, data in (('Geometry', geometry), ('Validation', dict(project=project.name,
                         sha256=digest(project), **validation))):
        (dest / f'{name}_{VERSION}.json').write_text(json.dumps(data, indent=2) + '\n')
    files = [ROOT / 'tools' / name for name in trace.SOURCE_FILES]
    files.extend((Path(colors.__file__).resolve(), Path(__file__).resolve(), VECTOR))
    snapshot = dest / 'Source_snapshot.zip'
    with ZipFile(snapshot, 'w', ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT))
    inputs = files + [BASELINE, GEOMETRY_SOURCE, trace.ARTWORK,
                      ROOT / 'sets/Set_09_Fabled/v06/Set_09_Fabled_v06.3mf']
    manifest = dict(project=project.name, sha256=digest(project),
                    source_snapshot_sha256=digest(snapshot),
                    inputs_sha256={str(p.relative_to(ROOT)): digest(p) for p in inputs})
    (dest / 'Build_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Validated {len(caps)} snow caps at 100% with the 0.4 mm nozzle. '
          f'Estimated print time {validation["estimated_time_minutes"]} minutes.')


if __name__ == '__main__':
    main()
