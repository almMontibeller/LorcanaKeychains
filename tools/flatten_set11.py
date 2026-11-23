#!/usr/bin/env python3
"""Build Winterspell v10 on the original flat 2 mm backing."""

import argparse
import json
import math
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import snow_set11 as snow

ROOT = snow.ROOT
VERSION = 'v10'
NAME = snow.trace.SET.name + '_' + VERSION
SOURCE = snow.DEST / (snow.NAME + '.3mf')
DEST = snow.trace.SET / VERSION
DROP = .4
REGISTRY = snow.colors
NS, PROD = snow.NS, snow.PROD


def lower(part):
    return dict(part, vertices=[(x, y, round(z-DROP, 9)) for x, y, z in part['vertices']])


def write_project(data, parts, target):
    root = ET.fromstring(data[REGISTRY.MODEL])
    config = ET.fromstring(data[REGISTRY.CONFIG])
    obj = config.find('object')
    model = root.find(f"m:resources/m:object[@id='{obj.attrib['id']}']/m:components", NS)
    field = model[1]
    field_id = field.attrib['objectid']
    path = field.attrib[PROD + 'path'].lstrip('/')
    child = ET.fromstring(data[path])
    resources = child.find('m:resources', NS)
    model.remove(field)
    resources.remove(resources.find(f"m:object[@id='{field_id}']", NS))
    obj.remove(obj.find(f"part[@id='{field_id}']"))
    for component, part in zip(list(model)[1:], parts[1:], strict=True):
        mesh = resources.find(f"m:object[@id='{component.attrib['objectid']}']", NS)
        snow.write_mesh(mesh, part)
    obj.find("metadata[@key='name']").set('value', target.stem)
    obj.find('metadata[@face_count]').set('face_count', str(sum(len(p['faces']) for p in parts)))
    root.find("m:metadata[@name='Description']", NS).text = (
        'Winterspell v10. Flat 2 mm Dark Blue backing and eyelet. Original Sunflower Yellow '
        'lettering and Ice Blue snow caps lowered by 0.4 mm. Maximum height 3 mm.')
    for key, tree in ((REGISTRY.MODEL, root), (REGISTRY.CONFIG, config), (path, child)):
        REGISTRY.put_xml(data, key, tree)
    data['Metadata/plate_1.png'] = snow.thumbnail(parts, 512)
    data['Metadata/plate_no_light_1.png'] = data['Metadata/plate_1.png']
    data['Metadata/plate_1_small.png'] = snow.thumbnail(parts, 128)
    with ZipFile(target, 'x', ZIP_DEFLATED) as archive:
        for name, content in data.items():
            archive.writestr(name, content)


def compare(before, after, output):
    font_path = next(Path('/usr/share/fonts').rglob('DejaVuSans.ttf'), None)
    font = ImageFont.truetype(str(font_path), 26) if font_path else ImageFont.load_default(size=26)
    panels = []
    with TemporaryDirectory() as tmp:
        for parts in (before, after):
            p = Path(tmp) / 'panel.png'
            snow.isometric(parts, p)
            with Image.open(p) as image:
                panels.append(image.convert('RGB'))
    height = max(p.height for p in panels) + 50
    layout = Image.new('RGB', (panels[0].width, height*2), '#f5f5f5')
    draw = ImageDraw.Draw(layout)
    for index, (image, label) in enumerate(zip(panels, ('v09 · Raised Dark Blue field',
                                                        'v10 · Flat Dark Blue backing'))):
        draw.text((35, index*height+16), label, fill='#193d58', font=font)
        layout.paste(image, (0, index*height+50))
    layout.save(output)


def validate_geometry(baseline, new, before, after):
    assert after[0] == before[0]
    assert [p['slot'] for p in after] == [1, 2, 3]
    assert after[1:] == [lower(p) for p in before[2:]]
    assert baseline[REGISTRY.SETTINGS] == new[REGISTRY.SETTINGS]
    for file, tag in ((REGISTRY.MODEL, 'm:build'), (REGISTRY.CONFIG, 'assemble')):
        assert ET.tostring(ET.fromstring(baseline[file]).find(tag, NS)) == ET.tostring(
            ET.fromstring(new[file]).find(tag, NS))
    records = [dict(name=p['name'], slot=p['slot'], **snow.mesh_stats(p)) for p in after]
    assert all(p['degenerate_triangles'] == 0 for p in records)
    assert [{p[2] for p in part['vertices']} for part in after] == [
        {0., 2.}, {2., 2.6}, {2.6, 3.}]
    backing, = snow.audit.polygons(after[0])
    assert all(backing.covers(g) for g in snow.audit.polygons(after[1]))
    return dict(parts=records, dimensions_mm=snow.audit.extents(after),
                backing_height_mm=2., bore_mm=6.5, removed_blue_relief_mm=DROP,
                translated_artwork_mm=-DROP, original_footprint_and_print_settings=True)


def artwork_report(layers, bbox, parts, shapes, tool):
    # Reuse the artwork audit at its reference elevations and report actual Z.
    paths = {round(z+DROP, 3): [(p, w, 2) for p, w, t in segment if t == tool]
             for z, segment in layers.items() if any(t == tool for _, _, t in segment)}
    return {str(round(float(z)-DROP, 3)): layer
            for z, layer in snow.audit.layer_report(paths, bbox, parts, shapes).items()}


def slice_project(project, parts, logdir):
    logdir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='winterspell-flat-') as tmp:
        run = subprocess.run(snow.bambu_command()+['--datadir', tmp, '--debug', '2', '--info',
                             '--slice', '1', '--outputdir', str(logdir), str(project)],
                             cwd=logdir, capture_output=True, text=True, timeout=180)
    log = run.stdout+run.stderr
    (logdir/'slice.log').write_text(log)
    assert run.returncode == 0 and 'manifold = yes' in log, log[-2000:]
    result = json.loads((logdir/'result.json').read_text())
    plate, = result['sliced_plates']
    assert result['return_code'] == 0 and plate['warning_message'] == ''
    assert math.isclose(result['layer_height'], .2, abs_tol=1e-6)
    assert [f['id'] for f in plate['filaments']] == [1, 2, 3]
    assert all(f['main_used_g'] > 0 for f in plate['filaments'])
    bbox = plate['objects'][0]['bbox']
    layers = snow.read_toolpaths(logdir/'plate_1.gcode', bbox, 3)
    assert max(z for z, paths in layers.items() if any(t == 0 for _, _, t in paths)) == 2.
    _, letters = snow.trace.artwork()
    caps = {key: polygon for key, (_, polygon) in snow.snow_caps(letters).items()}
    gold = artwork_report(layers, bbox, parts, letters, 1)
    ice = artwork_report(layers, bbox, parts, caps, 2)
    for report, targets, count in ((gold, {'2.2': .97, '2.4': .97, '2.6': .97}, len(letters)),
                                   (ice, {'2.8': .95, '3.0': .97}, len(caps))):
        assert report.keys() == targets.keys(), report.keys()
        for z, threshold in targets.items():
            layer = report[z]
            assert layer['deposit_components'] == count, (z, layer)
            assert all(r['deposited_core_fraction'] >= threshold for r in layer['letters'].values()), (z, layer)
    bb = snow.bounds(parts[0])
    blue = np.asarray(snow.audit.deposited(layers[2.], 0, bbox['x']-bb[0][0], bbox['y']-bb[1][0])) == 255
    backing, = snow.audit.polygons(parts[0])
    core = snow.audit.raster(backing.buffer(-.25))
    count, largest = snow.regions(blue)
    coverage = round(float(np.count_nonzero(core & largest) / core.sum()), 5)
    assert count == 1 and coverage >= .99
    eyelet = snow.toolpath_checks(layers, parts, bbox, {}, None, loop_height=2.,
                                  bore_loop=snow.trace.old_bore(parts[0]))
    snow.render_slice(layers, parts, bbox, snow.PALETTE,
                      project.with_name(NAME+'_sliced_preview.png'), loop_height=2.)
    return dict(bambu_version=re.search(r'Current BambuStudio Version (\S+)', log).group(1),
                estimated_minutes=round(plate['total_predication']/60, 1), nozzle_mm=.4,
                layer_height_mm=.2, scale=1., plate_warnings='', physical_print_verified=False,
                blue_top_mm=2., blue_top_core_coverage=coverage,
                gold_layers=gold, snow_layers=ice, eyelet=eyelet)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=DEST)
    dest = parser.parse_args().output_dir.resolve()
    project = dest/(NAME+'.3mf')
    if project.exists():
        raise FileExistsError(project)
    dest.mkdir(parents=True, exist_ok=True)
    original = snow.package(SOURCE)
    before = snow.read_parts(original)
    parts = [before[0], *(lower(p) for p in before[2:])]
    write_project(original.copy(), parts, project)
    saved = snow.package(project)
    after = snow.read_parts(saved)
    geometry = validate_geometry(original, saved, before, after)
    snow.preview(after, dest/(NAME+'_preview.png'))
    snow.isometric(after, dest/(NAME+'_isometric.png'))
    compare(before, after, dest/(NAME+'_comparison.png'))
    logs = ROOT/'validation'/snow.trace.SET.name/VERSION if dest == DEST else dest/'validation'
    validation = slice_project(project, after, logs)
    inputs = [ROOT/'tools'/p for p in snow.trace.SOURCE_FILES]
    inputs.extend((Path(__file__).resolve(), Path(snow.__file__).resolve(),
                   Path(REGISTRY.__file__).resolve(), snow.VECTOR))
    snapshot = dest/'Source_snapshot.zip'
    with ZipFile(snapshot, 'w', ZIP_DEFLATED) as archive:
        for path in inputs:
            archive.write(path, path.relative_to(ROOT))
    inputs += [SOURCE, ROOT/'sets/Set_09_Fabled/v06/Set_09_Fabled_v06.3mf']
    manifest = dict(project=project.name, sha256=snow.digest(project),
                    source_snapshot_sha256=snow.digest(snapshot),
                    inputs_sha256={str(p.relative_to(ROOT)): snow.digest(p) for p in inputs})
    for path, data in (('Build_manifest.json', manifest), (f'Geometry_{VERSION}.json', geometry),
                       (f'Validation_{VERSION}.json', dict(sha256=snow.digest(project), **validation))):
        (dest/path).write_text(json.dumps(data, indent=2)+'\n')
    print(f'Sliced {project.name} in {validation["estimated_minutes"]} estimated minutes.')


if __name__ == '__main__':
    main()
