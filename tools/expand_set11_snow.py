#!/usr/bin/env python3
"""Add selected source-art frost patches to the v1.9 Winterspell keychain."""

import argparse
import json
import math
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image, ImageDraw, ImageFont
from shapely.ops import unary_union

import flatten_set11 as flat
import snow_set11 as snow
from repair_v1_1 import NS, PROD, read_parts, thumbnail
from standardize_loop_diameters import bounds, digest, mesh_stats, package, write_mesh

ROOT = snow.ROOT
SET = snow.trace.SET
VERSION = 'v1.10'
NAME = SET.name + '_' + VERSION
SOURCE = flat.DEST / (flat.NAME + '.3mf')
DEST = SET / VERSION
VECTOR = Path(__file__).with_name('set11_extra_snow_caps.svg')
MODEL, CONFIG, SETTINGS = snow.colors.MODEL, snow.colors.CONFIG, snow.colors.SETTINGS


def extra_caps(letters):
    # Use the established source-coordinate registration, clipping and inset.
    vector = snow.VECTOR
    snow.VECTOR = VECTOR
    try:
        return snow.snow_caps(letters)
    finally:
        snow.VECTOR = vector


def write_project(data, source_parts, caps, target):
    original_snow = source_parts[-1]
    added = snow.curves.relief([snow.trace.loops(p) for _, p in caps.values()],
                               2.6, .4, original_snow)
    parts = [*source_parts[:2], snow.curves.merge([original_snow, added])]
    model = ET.fromstring(data[MODEL])
    config = ET.fromstring(data[CONFIG])
    obj = config.find('object')
    component = model.find(f"m:resources/m:object[@id='{obj.attrib['id']}']/m:components", NS)[-1]
    path = component.attrib[PROD + 'path'].lstrip('/')
    child = ET.fromstring(data[path])
    cap_id = component.attrib['objectid']
    mesh = child.find(f"m:resources/m:object[@id='{cap_id}']", NS)
    write_mesh(mesh, parts[-1])
    obj.find(f"part[@id='{cap_id}']/mesh_stat").set('face_count', str(len(parts[-1]['faces'])))
    obj.find('metadata[@face_count]').set('face_count', str(sum(len(p['faces']) for p in parts)))
    obj.find("metadata[@key='name']").set('value', target.stem)
    model.find("m:metadata[@name='Description']", NS).text = (
        'Winterspell v1.10. Flat 2 mm Dark Blue backing, gold lettering and thirteen raised '
        'Ice Blue snow patches. Earlier lettering, backing, loop and snow patches retained.')
    for key, document in ((MODEL, model), (CONFIG, config), (path, child)):
        snow.colors.put_xml(data, key, document)
    data['Metadata/plate_1.png'] = thumbnail(parts, 512)
    data['Metadata/plate_no_light_1.png'] = data['Metadata/plate_1.png']
    data['Metadata/plate_1_small.png'] = thumbnail(parts, 128)
    with ZipFile(target, 'x', ZIP_DEFLATED) as archive:
        for key, content in data.items():
            archive.writestr(key, content)


def geometry(source, current, old, new, originals, additions, letters):
    assert old[:2] == new[:2] and [p['slot'] for p in new] == [1, 2, 3]
    assert source[SETTINGS] == current[SETTINGS]
    a, b = old[-1], new[-1]
    assert b['vertices'][:len(a['vertices'])] == a['vertices']
    assert b['faces'][:len(a['faces'])] == a['faces']
    assert {v[2] for v in b['vertices']} == {2.6, 3.}
    for path, tag in ((MODEL, 'm:build'), (CONFIG, 'assemble')):
        assert ET.tostring(ET.fromstring(source[path]).find(tag, NS)) == ET.tostring(
            ET.fromstring(current[path]).find(tag, NS))
    expected = {**originals, **additions}
    caps = snow.audit.polygons(b)
    assert len(caps) == len(expected)
    assert unary_union(caps).symmetric_difference(
        unary_union([p for _, p in expected.values()])).area < .0001
    assert all(letters[letter].covers(p) and p.buffer(-.25).area >= 1
               for letter, p in additions.values())
    assert all(p.is_valid for p in caps)
    stats = [dict(name=p['name'], slot=p['slot'], **mesh_stats(p)) for p in new]
    assert all(s['degenerate_triangles'] == 0 for s in stats)
    gold_area = sum(p.area for p in letters.values())
    return dict(parts=stats, dimensions_mm=snow.audit.extents(new), backing_height_mm=2.,
                snow_height_mm=.4, bore_mm=6.5,
                retained_snow_patches=len(originals),
                added_snow_patches={k: dict(letter=g, area_mm2=round(p.area, 3))
                                    for k, (g, p) in additions.items()},
                snow_area_percent_of_letter_faces=round(100*sum(p.area for p in caps)/gold_area, 2),
                prior_geometry_exactly_preserved=True, print_settings_byte_identical=True)


def comparison(old, new, output):
    frame = bounds(old[0])
    font_path = next(Path('/usr/share/fonts').rglob('DejaVuSans.ttf'), None)
    font = ImageFont.truetype(str(font_path), 25) if font_path else ImageFont.load_default(size=25)
    with TemporaryDirectory() as tmp:
        panels = []
        for parts in (old, new):
            path = Path(tmp)/'panel.png'
            snow.preview(parts, path, 1500, frame)
            with Image.open(path) as image:
                panels.append(image.convert('RGB'))
    height = panels[0].height+52
    canvas = Image.new('RGB', (1500, height*2), '#f5f5f5')
    draw = ImageDraw.Draw(canvas)
    for i, (panel, label) in enumerate(zip(panels, ('v1.9 · Seven snow patches',
                                                   'v1.10 · Thirteen snow patches'))):
        draw.text((30, i*height+16), label, fill='#193d58', font=font)
        canvas.paste(panel, (0, i*height+52))
    canvas.save(output)


def validate_slice(project, parts, letters, caps, logs):
    logs.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='winterspell-more-snow-') as tmp:
        run = subprocess.run(snow.bambu_command()+['--datadir', tmp, '--debug', '2', '--info',
                             '--slice', '1', '--outputdir', str(logs), str(project)],
                             cwd=logs, capture_output=True, text=True, timeout=180)
    log = run.stdout+run.stderr
    (logs/'slice.log').write_text(log)
    assert run.returncode == 0 and 'manifold = yes' in log, log[-2200:]
    result = json.loads((logs/'result.json').read_text())
    plate, = result['sliced_plates']
    assert result['return_code'] == 0 and not plate['warning_message']
    assert math.isclose(result['layer_height'], .2, abs_tol=1e-6)
    assert [f['id'] for f in plate['filaments']] == [1, 2, 3]
    assert all(f['main_used_g'] > 0 for f in plate['filaments'])
    bbox = plate['objects'][0]['bbox']
    layers = snow.read_toolpaths(logs/'plate_1.gcode', bbox, 3)
    assert max(z for z, layer in layers.items() if any(t == 0 for _, _, t in layer)) == 2.
    gold = flat.artwork_report(layers, bbox, parts, letters, 1)
    ice = flat.artwork_report(layers, bbox, parts, {k: p for k, (_, p) in caps.items()}, 2)
    for report, targets, count in ((gold, {'2.2': .97, '2.4': .97, '2.6': .97}, len(letters)),
                                   (ice, {'2.8': .95, '3.0': .97}, len(caps))):
        assert report.keys() == targets.keys(), report.keys()
        for z, required in targets.items():
            layer = report[z]
            assert layer['deposit_components'] == count, (z, layer)
            low = {k: v['deposited_core_fraction'] for k, v in layer['letters'].items()
                   if v['deposited_core_fraction'] < required}
            assert not low, (z, low)
    eyelet = snow.toolpath_checks(layers, parts, bbox, {}, None, loop_height=2.,
                                 bore_loop=snow.trace.old_bore(parts[0]))
    snow.render_slice(layers, parts, bbox, snow.PALETTE,
                      project.with_name(NAME+'_sliced_preview.png'), loop_height=2.)
    return dict(bambu_version=re.search(r'Current BambuStudio Version (\S+)', log).group(1),
                estimated_minutes=round(plate['total_predication']/60, 1), nozzle_mm=.4,
                layer_height_mm=.2, xy_scale=1., used_filament_slots=[1, 2, 3],
                plate_warnings=plate['warning_message'], physical_print_verified=False,
                eyelet=eyelet, gold_layers=gold, snow_layers=ice)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=DEST)
    dest = parser.parse_args().output_dir.resolve()
    project = dest/(NAME+'.3mf')
    if project.exists():
        raise FileExistsError(project)
    dest.mkdir(parents=True, exist_ok=True)
    source = package(SOURCE)
    old = read_parts(source)
    _, letters = snow.trace.artwork()
    originals = snow.snow_caps(letters)
    additions = extra_caps(letters)
    write_project(source.copy(), old, additions, project)
    current = package(project)
    parts = read_parts(current)
    report = geometry(source, current, old, parts, originals, additions, letters)
    snow.preview(parts, dest/(NAME+'_preview.png'))
    snow.isometric(parts, dest/(NAME+'_isometric.png'))
    comparison(old, parts, dest/(NAME+'_comparison.png'))
    logs = ROOT/'validation'/SET.name/VERSION if dest == DEST else dest/'validation'
    validation = validate_slice(project, parts, letters, {**originals, **additions}, logs)
    snapshot = dest/'Source_snapshot.zip'
    inputs = [ROOT/'tools'/p for p in snow.trace.SOURCE_FILES] + [
        Path(flat.__file__).resolve(), Path(snow.__file__).resolve(), Path(snow.colors.__file__).resolve(),
        Path(__file__).resolve(), snow.VECTOR, VECTOR]
    with ZipFile(snapshot, 'w', ZIP_DEFLATED) as archive:
        for path in inputs:
            archive.write(path, path.relative_to(ROOT))
    inputs += [SOURCE, snow.trace.ARTWORK, ROOT/'sets/Set_09_Fabled/v1.5/Set_09_Fabled_v1.5.3mf']
    manifest = dict(project=project.name, sha256=digest(project),
                    source_snapshot_sha256=digest(snapshot),
                    inputs_sha256={str(p.relative_to(ROOT)): digest(p) for p in inputs})
    for name, value in (('Build_manifest.json', manifest),
                        (f'Geometry_{VERSION}.json', report),
                        (f'Validation_{VERSION}.json', dict(sha256=digest(project), **validation))):
        (dest/name).write_text(json.dumps(value, indent=2)+'\n')
    print(f'Sliced {len(originals)+len(additions)} snow patches in {validation["estimated_minutes"]} estimated minutes.')


if __name__ == '__main__':
    main()
