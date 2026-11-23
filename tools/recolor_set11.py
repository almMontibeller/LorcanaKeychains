#!/usr/bin/env python3
"""Build and slice Winterspell v08 with gold text and three blue tones."""

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
from shapely import set_precision
from shapely.geometry import Polygon
from shapely.ops import unary_union

import rebuild_set07 as curves
import rebuild_set11 as previous
import validate_set11 as audit
from full_height_narrow_rims import isometric
from rebuild_set09 import preview
from refine_loops_and_underline import read_toolpaths, render_slice, toolpath_checks
from repair_v02 import NS, PROD, read_parts, thumbnail
from standardize_loop_diameters import bounds, digest, mesh_stats, package, write_mesh
from validate_bambu import bambu_command
from validate_set09 import regions

ROOT = previous.ROOT
VERSION = 'v08'
NAME = previous.SET.name + '_' + VERSION
SOURCE = previous.DEST / (previous.NAME + '.3mf')
DEST = previous.SET / VERSION
VECTOR = Path(__file__).with_name('set11_frost_bands.svg')
YELLOW_PRESET = ROOT / 'sets/Set_09_Fabled/v08/Set_09_Fabled_v08.3mf'
REFERENCE = ('https://i0.wp.com/disneylorcana.com/wp-content/uploads/2026/08/'
             'dlc_s11_logo_en.webp?fit=648%2C300&ssl=1')
MODEL = '3D/3dmodel.model'
CONFIG = 'Metadata/model_settings.config'
SETTINGS = audit.SETTINGS
PALETTE = ['#042F56', '#0078BF', '#A3D8E1', '#FEC600']
NAMES = ['Dark Blue', 'Marine Blue', 'Ice Blue', 'Sunflower Yellow']
SWATCH_CODES = ['11602', '11600', '11601', '10402']
GRID = .001
BAND_LAYERS = (2.2, 2.4)


def frost_masks():
    svg = ET.parse(VECTOR).getroot()
    original_registration = curves.registered
    curves.registered = previous.registered
    try:
        return [unary_union([set_precision(Polygon(curves.sample(path.attrib['d'])[0]), GRID)
                            for path in svg.findall(f"s:g[@id='{name}']/s:path", previous.SVG)])
                for name in ('marine', 'ice')]
    finally:
        curves.registered = original_registration


def section_polygons(shape):
    return tuple(shape.geoms) if shape.geom_type == 'MultiPolygon' else (shape,)


def field_sections(part):
    outline, = audit.polygons(part)
    outline = set_precision(outline, GRID)
    medium_mask, ice_mask = frost_masks()
    medium = outline.intersection(medium_mask)
    ice = medium.intersection(ice_mask)
    return outline.difference(medium), medium.difference(ice), ice


def geometry(original):
    backing, field, lettering = original
    bands = []
    for slot, shape in enumerate(field_sections(field), 1):
        template = dict(field, name=NAMES[slot - 1] + ' · frost field',
                        color=PALETTE[slot - 1], slot=slot)
        bands.append(curves.relief([previous.loops(p) for p in section_polygons(shape)],
                                   2., .4, template))
    return [dict(backing, name='Dark Blue · backing and eyelet', color=PALETTE[0]),
            *bands, dict(lettering, name='Sunflower Yellow · lettering', color=PALETTE[3], slot=4)]


def configure_filaments(original):
    yellow = json.loads(package(YELLOW_PRESET)[SETTINGS])
    settings = copy.deepcopy(original)
    curves.add_filament(settings)
    for key, value in original.items():
        donor = yellow.get(key)
        if isinstance(value, list) and len(value) == 3 and isinstance(donor, list) and len(donor) == 3:
            settings[key][3] = donor[1]
    settings.update(filament_colour=PALETTE, filament_multi_colour=PALETTE,
                    filament_self_index=['1', '2', '3', '4'])
    # Dark-to-light transitions need the larger flush volumes.
    settings['flush_volumes_matrix'] = list(map(str, [
        0, 285, 455, 575, 125, 0, 350, 470,
        155, 150, 0, 275, 140, 230, 330, 0,
    ]))
    assert settings['filament_settings_id'] == ['Bambu PLA Matte @BBL A1'] * 3 + [
        'Bambu PLA Basic @BBL A1']
    return settings


def put_xml(data, key, tree):
    data[key] = ET.tostring(tree, encoding='utf-8', xml_declaration=True)


def write_project(data, parts, project):
    root = ET.fromstring(data[MODEL])
    config = ET.fromstring(data[CONFIG])
    obj = config.find('object')
    assembly = root.find(f"m:resources/m:object[@id='{obj.attrib['id']}']/m:components", NS)
    path = assembly[1].attrib[PROD + 'path'].lstrip('/')
    child_model = ET.fromstring(data[path])
    meshes = child_model.find('m:resources', NS)
    # Keep backing and lettering resources byte-equivalent at the mesh level.
    # Reuse the old field object for Marine Blue and add Dark Blue and Ice Blue.
    field_component = assembly[1]
    field_obj = meshes.find("m:object[@id='2']", NS)
    field_config = obj.find("part[@id='2']")
    first_part_index = list(obj).index(obj.find('part'))
    for position, part, number in ((1, parts[1], '5'), (3, parts[3], '6')):
        new_mesh = copy.deepcopy(field_obj)
        new_mesh.set('id', number)
        new_mesh.set(PROD + 'UUID', str(uuid5(NAMESPACE_URL, f'{NAME}/mesh/{number}')))
        meshes.append(new_mesh)
        component = copy.deepcopy(field_component)
        component.set('objectid', number)
        component.set(PROD + 'UUID', str(uuid5(NAMESPACE_URL, f'{NAME}/component/{number}')))
        assembly.insert(position, component)
        metadata = copy.deepcopy(field_config)
        metadata.set('id', number)
        metadata.set('uuid', str(uuid5(NAMESPACE_URL, f'{NAME}/part/{number}')))
        obj.insert(first_part_index + position, metadata)
        write_mesh(new_mesh, part)
    write_mesh(field_obj, parts[2])
    for component, part in zip(assembly, parts, strict=True):
        meta = obj.find(f"part[@id='{component.attrib['objectid']}']")
        meta.find("metadata[@key='name']").set('value', part['name'])
        meta.find("metadata[@key='extruder']").set('value', str(part['slot']))
        meta.find('mesh_stat').set('face_count', str(len(part['faces'])))
    obj.find("metadata[@key='name']").set('value', project.stem)
    obj.find('metadata[@face_count]').set('face_count', str(sum(len(p['faces']) for p in parts)))
    root.find("m:metadata[@name='Description']", NS).text = (
        'v08 Winterspell. Original v07 backing and lettering geometry. Dark Blue, Marine Blue '
        'and Ice Blue frost bands with Sunflower Yellow lettering. A1 0.4 mm Arachne at 100% scale.')
    data[SETTINGS] = json.dumps(configure_filaments(json.loads(data[SETTINGS])), indent=4).encode()
    put_xml(data, MODEL, root)
    put_xml(data, path, child_model)
    put_xml(data, CONFIG, config)
    data['Metadata/plate_1.png'] = thumbnail(parts, 512)
    data['Metadata/plate_no_light_1.png'] = data['Metadata/plate_1.png']
    data['Metadata/plate_1_small.png'] = thumbnail(parts, 128)
    with ZipFile(project, 'x', ZIP_DEFLATED) as archive:
        for key, value in data.items():
            archive.writestr(key, value)


def compare(original, new, path):
    font_path = next(Path('/usr/share/fonts').rglob('DejaVuSans.ttf'), None)
    font = ImageFont.truetype(str(font_path), 25) if font_path else ImageFont.load_default(size=25)
    with TemporaryDirectory() as tmp:
        panels = []
        for parts in (original, new):
            panel = Path(tmp) / 'panel.png'
            preview(parts, panel, 1500, bounds(original[0]))
            with Image.open(panel) as image:
                panels.append(image.convert('RGB'))
    canvas = Image.new('RGB', (1500, 2 * (panels[0].height + 56)), '#f5f5f5')
    draw = ImageDraw.Draw(canvas)
    for index, (panel, label) in enumerate(zip(panels, ('v07 · Ivory and Ice Blue',
                                                        'v08 · Gold and blue frost bands'))):
        y = index * (panel.height + 56)
        canvas.paste(panel, (0, y + 56))
        draw.text((30, y + 16), label, fill='#193d58', font=font)
    canvas.save(path)


def validate_geometry(source, project, before, after):
    for old, new in ((before[0], after[0]), (before[-1], after[-1])):
        assert old['vertices'] == new['vertices'] and old['faces'] == new['faces']
    assert [p['slot'] for p in after] == [1, 1, 2, 3, 4]
    stats = [dict(name=p['name'], slot=p['slot'], **mesh_stats(p)) for p in after]
    assert all(s['degenerate_triangles'] == 0 for s in stats)
    palette = json.loads(project[SETTINGS])
    assert palette['filament_colour'] == PALETTE
    assert palette['nozzle_diameter'] == ['0.4'] and palette['wall_generator'] == 'arachne'
    old_settings = json.loads(source[SETTINGS])
    scalar_keys = [k for k, value in old_settings.items() if not isinstance(value, list)]
    assert all(palette[k] == old_settings[k] for k in scalar_keys)
    for key, tag in ((MODEL, 'm:build'), (CONFIG, 'assemble')):
        assert ET.tostring(ET.fromstring(source[key]).find(tag, NS)) == ET.tostring(
            ET.fromstring(project[key]).find(tag, NS))
    sections = [audit.polygons(p) for p in after[1:4]]
    assert [len(s) for s in sections] == [1, 2, 2]
    assert all(p.is_valid for section in sections for p in section)
    outlines = [unary_union(s) for s in sections]
    total = unary_union(outlines)
    assert math.isclose(sum(p.area for p in outlines), total.area, abs_tol=1e-4)
    assert len(total.interiors) == 0
    old_field, = audit.polygons(before[1])
    field_delta = old_field.symmetric_difference(total).area
    assert field_delta < .1
    base, = audit.polygons(after[0])
    assert base.covers(total)
    glyphs = audit.polygons(after[-1])
    assert len(glyphs) == 11 and all(total.covers(g) for g in glyphs)
    return dict(backing_and_letter_meshes_identical=True, bore_mm=6.5, manifold_parts=stats,
                palette=[dict(slot=i, filament=n, manufacturer_swatch_code=c, hex_color=h)
                         for i, (n, c, h) in enumerate(zip(NAMES, SWATCH_CODES, PALETTE), 1)],
                band_sections=[len(s) for s in sections],
                band_area_mm2=[round(s.area, 3) for s in outlines],
                field_symmetric_difference_mm2=round(field_delta, 6),
                title_fully_supported=True, original_plate_placement=True)


def validate_slice(project, parts, logs):
    logs.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='winterspell-frost-') as work:
        run = subprocess.run(bambu_command() + ['--datadir', work, '--debug', '2', '--info',
                             '--slice', '1', '--outputdir', str(logs), str(project)],
                             cwd=logs, capture_output=True, text=True, timeout=180)
    log = run.stdout + run.stderr
    (logs / 'slice.log').write_text(log)
    assert run.returncode == 0 and 'manifold = yes' in log, log[-2500:]
    result = json.loads((logs / 'result.json').read_text())
    plate, = result['sliced_plates']
    assert result['return_code'] == 0 and plate['warning_message'] == ''
    assert math.isclose(result['layer_height'], .2, abs_tol=1e-6)
    assert [f['id'] for f in plate['filaments']] == [1, 2, 3, 4]
    assert all(f['main_used_g'] > 0 for f in plate['filaments'])
    bbox = plate['objects'][0]['bbox']
    layers = read_toolpaths(logs / 'plate_1.gcode', bbox, 4)
    bb = bounds(parts[0])
    dx, dy = bbox['x'] - bb[0][0], bbox['y'] - bb[1][0]
    field_checks = {}
    for z in BAND_LAYERS:
        band_report = {}
        for slot, part in enumerate(parts[1:4]):
            raw = np.asarray(audit.deposited(layers[z], slot, dx, dy)) == 255
            comps = [audit.raster(p.buffer(-.24)) for p in audit.polygons(part)]
            coverage = [round(float(np.count_nonzero(raw & p) / p.sum()), 5) for p in comps]
            count = regions(raw)[0]
            assert count == len(comps) and min(coverage) >= .97, (z, slot, count, coverage)
            band_report[NAMES[slot]] = dict(deposit_components=count,
                                           bands_core_coverage=coverage)
        field_checks[str(z)] = band_report
    gold_paths = {z: [(points, width, 2) for points, width, tool in paths if tool == 3]
                  for z, paths in layers.items()}
    _, letters = previous.artwork()
    gold = audit.layer_report(gold_paths, bbox, parts, letters)
    assert list(gold) == ['2.6', '2.8', '3.0']
    assert all(z['deposit_components'] == 11 and
               min(letter['deposited_core_fraction'] for letter in z['letters'].values()) >= .97
               for z in gold.values())
    render_slice(layers, parts, bbox, PALETTE, project.with_name(NAME + '_sliced_preview.png'),
                 loop_height=2.)
    eyelet = toolpath_checks(layers, parts, bbox, {}, None, loop_height=2.,
                             bore_loop=previous.old_bore(parts[0]))
    return dict(bambu_version=re.search(r'Current BambuStudio Version (\S+)', log).group(1),
                estimated_time_minutes=round(plate['total_predication'] / 60, 1),
                used_filament_slots=[1, 2, 3, 4], plate_warnings=plate['warning_message'],
                nozzle_mm=.4, layer_height_mm=.2, xy_scale=1.0, eyelet=eyelet,
                field_layers=field_checks, gold_layers=gold, physical_print_verified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=DEST)
    args = parser.parse_args()
    dest = args.output_dir.resolve()
    project = dest / (NAME + '.3mf')
    if project.exists():
        raise FileExistsError(project)
    dest.mkdir(parents=True, exist_ok=True)
    logs = (ROOT / 'validation' / previous.SET.name / VERSION if dest == DEST
            else dest / 'validation')
    source = package(SOURCE)
    original = read_parts(source)
    write_project(source.copy(), geometry(original), project)
    output = package(project)
    parts = read_parts(output)
    report = validate_geometry(source, output, original, parts)
    preview(parts, dest / (NAME + '_preview.png'))
    isometric(parts, dest / (NAME + '_isometric.png'))
    compare(original, parts, dest / (NAME + '_comparison.png'))
    result = validate_slice(project, parts, logs)
    (dest / ('Geometry_' + VERSION + '.json')).write_text(json.dumps(report, indent=2) + '\n')
    (dest / ('Validation_' + VERSION + '.json')).write_text(json.dumps(
        dict(project=project.name, sha256=digest(project), **result), indent=2) + '\n')
    files = [ROOT / 'tools' / name for name in previous.SOURCE_FILES]
    files += [Path(__file__).resolve(), VECTOR]
    snapshot = dest / 'Source_snapshot.zip'
    with ZipFile(snapshot, 'w', ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT))
    inputs = [*files, SOURCE, YELLOW_PRESET, previous.ARTWORK,
              ROOT / 'sets/Set_09_Fabled/v06/Set_09_Fabled_v06.3mf']
    manifest = dict(project=project.name, sha256=digest(project), artwork_reference=REFERENCE,
                    source_snapshot_sha256=digest(snapshot),
                    inputs_sha256={str(p.relative_to(ROOT)): digest(p) for p in inputs})
    (dest / 'Build_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'gold_layers'}, indent=2))


if __name__ == '__main__':
    main()
