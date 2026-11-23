#!/usr/bin/env python3
"""Extend the eyelet of the edited Into the Inkdark v01 project."""

import argparse
import io
import json
import shutil
import tempfile
import xml.etree.ElementTree as ET
from hashlib import sha256
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shapely.affinity import translate
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union

import rebuild_set15 as first
from rebuild_set09 import preview
from repair_v02 import IDENTITY
from standardize_loop_diameters import centre

VERSION = 'v02'
NAME = first.SET.name + '_' + VERSION
SOURCE = first.DEST / (first.NAME + '.3mf')
DEST = first.SET / VERSION
NECK_LENGTH = 4.
NECK_WIDTH = 4.5
SHOULDER_RADIUS = .65
BODY_EDGE = 9.7925
DATE = '2026-11-22'


def extended_backing(saved_base):
    old_bore = Polygon(saved_base.interiors[0])
    cx, cy = centre(old_bore.exterior.coords)
    old_outer = Polygon(saved_base.exterior)
    silhouette, _ = first.artwork()
    # Restore the source edge just where the original stock eyelet joined it.
    junction = box(-1., cy - 6., BODY_EDGE + 1., cy + 6.)
    body = old_outer.difference(junction).union(silhouette.intersection(junction))
    new_x = BODY_EDGE - NECK_LENGTH - first.EYELET_RADIUS
    new_bore = translate(old_bore, xoff=new_x - cx)
    eyelet = Point(new_x, cy).buffer(first.EYELET_RADIUS, quad_segs=48)
    neck = box(new_x, cy - NECK_WIDTH / 2, BODY_EDGE + 1.3, cy + NECK_WIDTH / 2)
    joined = body.union(eyelet).union(neck)
    local = joined.intersection(box(new_x - 1.5, cy - 6., BODY_EDGE + 1., cy + 6.))
    fillets = local.buffer(SHOULDER_RADIUS, quad_segs=12).buffer(-SHOULDER_RADIUS, quad_segs=12)
    outer = joined.union(fillets).simplify(.0005)
    assert outer.geom_type == 'Polygon' and not outer.interiors
    base = Polygon(outer.exterior, [new_bore.exterior])
    assert base.is_valid
    return base, junction


def project_template(data, target):
    model = ET.fromstring(data[first.MODEL])
    model.find("m:metadata[@name='ModificationDate']", first.NS).text = DATE
    config = ET.fromstring(data[first.CONFIG])
    backing = config.find("assemble/assemble_item[@volume_id='0']")
    if backing is not None:
        backing.set('transform', ' '.join(map(str, IDENTITY)))
    # Bambu Studio regenerates these cached plate views after loading the geometry.
    plate = config.find('plate')
    for key in ('top_file', 'pick_file'):
        entry = plate.find(f"metadata[@key='{key}']")
        if entry is not None:
            data.pop(entry.get('value').lstrip('/'), None)
            plate.remove(entry)
    data.pop('Metadata/plate_1.json', None)
    data[first.MODEL] = ET.tostring(model, encoding='utf-8', xml_declaration=True)
    data[first.CONFIG] = ET.tostring(config, encoding='utf-8', xml_declaration=True)
    with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
        for path, raw in data.items():
            archive.writestr(path, raw)


def validate_geometry(before, after, baseline_data, project_data, expected, junction):
    assert baseline_data[first.SETTINGS] == project_data[first.SETTINGS]
    buildings = [ET.fromstring(data[first.MODEL]).find('m:build', first.NS)
                 for data in (baseline_data, project_data)]
    assert ET.tostring(buildings[0]) == ET.tostring(buildings[1])
    assert before[1:] == after[1:]
    assert (before[0]['slot'], before[0]['color']) == (after[0]['slot'], after[0]['color'])
    assert {v[2] for v in after[0]['vertices']} == {0., first.HEIGHT}
    stats = first.mesh_stats(after[0])
    assert stats['degenerate_triangles'] == 0

    old_base, = first.outlines(before[0])
    base, = first.outlines(after[0])
    assert base.is_valid and len(base.interiors) == 1
    assert base.symmetric_difference(expected).area < 1e-5
    changed = junction.union(box(base.bounds[0] - 1, 0, BODY_EDGE, base.bounds[3]))
    assert base.symmetric_difference(old_base).difference(changed).area < 1e-5
    old_bore, bore = Polygon(old_base.interiors[0]), Polygon(base.interiors[0])
    cx, cy = centre(bore.exterior.coords)
    old_x, old_y = centre(old_bore.exterior.coords)
    assert abs(old_y - cy) < 1e-6
    assert abs(bore.bounds[2] - bore.bounds[0] - 2 * first.BORE_RADIUS) < 1e-6
    assert abs(bore.bounds[3] - bore.bounds[1] - 2 * first.BORE_RADIUS) < 1e-6
    assert old_bore.symmetric_difference(translate(bore, xoff=old_x-cx)).area < 1e-5
    assert abs(BODY_EDGE - (cx + first.EYELET_RADIUS) - NECK_LENGTH) < 1e-6
    assert abs(base.bounds[0] - (cx - first.EYELET_RADIUS)) < 1e-6
    bridge = box(cx + first.EYELET_RADIUS, cy - NECK_WIDTH / 2 + .001,
                 BODY_EDGE, cy + NECK_WIDTH / 2 - .001)
    assert base.covers(bridge)

    art = unary_union([shape for part in after[1:] for shape in first.outlines(part)])
    assert base.covers(art)
    return base, bore, dict(
        dimensions_before_mm=first.dimensions(before), dimensions_mm=first.dimensions(after),
        neck_length_mm=NECK_LENGTH, neck_width_mm=NECK_WIDTH, eyelet_shift_left_mm=round(old_x-cx, 4),
        backing_and_neck_height_mm=first.HEIGHT, bore_diameter_mm=2 * first.BORE_RADIUS,
        eyelet_outer_diameter_nominal_mm=2 * first.EYELET_RADIUS,
        bore_to_nearest_raised_letter_before_mm=round(old_bore.distance(art), 3),
        bore_to_nearest_raised_letter_mm=round(bore.distance(art), 3),
        lettering_meshes_and_plate_placement_preserved=True, profile_byte_identical=True,
        colors=[p['color'] for p in after], backing_mesh=stats)


def slice_project(project, logs, parts, base, bore):
    # Move the audit coordinates into the shared raster's positive X window.
    xoff = -base.bounds[0]
    shifted = [dict(part, vertices=[(x+xoff, y, z) for x, y, z in part['vertices']]) for part in parts]
    _, words = first.artwork()
    glyphs = {name: translate(shape, xoff=xoff) for word in words for name, shape in word.items()}
    toolpaths, result, version = first.slice_checks(
        project, logs, shifted, translate(base, xoff=xoff), translate(bore, xoff=xoff), glyphs)
    bbox = result['sliced_plates'][0]['objects'][0]['bbox']
    layers = first.read_toolpaths(logs / 'plate_1.gcode', bbox, 3)
    cy = bore.centroid.y
    x = BODY_EDGE - NECK_LENGTH / 2 + xoff
    # Both side walls must cross the middle of the neck on every backing layer.
    wall_masks = [first.raster(box(x - .12, y - .2, x + .12, y + .2))
                  for y in (cy - NECK_WIDTH / 2 + .22, cy + NECK_WIDTH / 2 - .22)]
    neck_layers = []
    for z in sorted(float(layer) for layer in toolpaths['backing_layers']):
        drawn = first.deposit(layers[z], 0, bbox['x'], bbox['y'] - base.bounds[1])
        assert all(np.any(drawn & mask) for mask in wall_masks), (z, 'missing neck wall')
        neck_layers.append(z)
    toolpaths['neck_layers_with_both_side_walls_mm'] = neck_layers
    return toolpaths, result, version


def comparison(before, after, output):
    frame = [(min(a[0], b[0]), max(a[1], b[1]))
             for a, b in zip(first.bounds(before[0]), first.bounds(after[0]), strict=True)]
    font_file = next(Path('/usr/share/fonts').rglob('DejaVuSans.ttf'), None)
    font = ImageFont.truetype(str(font_file), 26) if font_file else ImageFont.load_default(size=26)
    with tempfile.TemporaryDirectory() as temp:
        panel = Path(temp) / 'panel.png'
        preview(before, panel, width=1500, frame=frame)
        with Image.open(panel) as image:
            height = image.height + 56
            canvas = Image.new('RGB', (image.width, height * 2), '#f5f5f5')
            canvas.paste(image, (0, 56))
        preview(after, panel, width=1500, frame=frame)
        with Image.open(panel) as image:
            canvas.paste(image, (0, height + 56))
    draw = ImageDraw.Draw(canvas)
    draw.text((28, 15), 'v01 · Updated colors and short eyelet', font=font, fill='#042F56')
    draw.text((28, height + 15), f'{VERSION} · {NECK_LENGTH:g} mm neck', font=font, fill='#042F56')
    canvas.save(output)


def build_manifest(work, project, baseline):
    # Carry the exact edited project so later edits to v01 cannot change this build.
    script = Path(__file__).resolve()
    fabled = first.ROOT / 'sets/Set_09_Fabled/v06/Set_09_Fabled_v06.3mf'
    scripts = [first.ROOT / 'tools' / (name + '.py') for name in first.SOURCE_SCRIPTS]
    inputs = [first.VECTOR, first.ARTWORK, fabled, *scripts, script]
    files = {str(path.relative_to(first.ROOT)): path.read_bytes() for path in inputs}
    files[str(SOURCE.relative_to(first.ROOT))] = baseline
    snapshot = work / 'Source_snapshot.zip'
    with ZipFile(snapshot, 'w', ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    manifest = dict(project_sha256=first.digest(project), source_snapshot_sha256=first.digest(snapshot),
                    baseline=str(SOURCE.relative_to(first.ROOT)), baseline_sha256=sha256(baseline).hexdigest(),
                    inputs_sha256={path: sha256(content).hexdigest() for path, content in files.items()})
    (work / 'Build_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=DEST)
    dest = parser.parse_args().output_dir.resolve()
    target = dest / (NAME + '.3mf')
    if target.exists():
        raise FileExistsError(target)
    baseline = SOURCE.read_bytes()
    with ZipFile(io.BytesIO(baseline)) as archive:
        assert archive.testzip() is None
        before_data = {name: archive.read(name) for name in archive.namelist()}
    before = first.read_parts(before_data)
    old_base, = first.outlines(before[0])
    base, junction = extended_backing(old_base)
    loops = first.orient([list(ring.coords)[:-1] for ring in (base.exterior, *base.interiors)])
    parts = [first.relief([loops], 0., first.HEIGHT, before[0]), *before[1:]]
    with tempfile.TemporaryDirectory(prefix='inkdark-neck-') as tmp:
        work = Path(tmp)
        project = work / target.name
        template = work / 'template.3mf'
        project_template(dict(before_data), template)
        first.write_project(template, project, parts, {0},
                            'v02; 4 mm eyelet neck with retained v01 filament and print settings.')
        saved_data = first.package(project)
        saved = first.read_parts(saved_data)
        saved_base, bore, geometry = validate_geometry(before, saved, before_data, saved_data, base, junction)
        first.isometric(saved, work / (NAME + '_isometric.png'))
        comparison(before, saved, work / (NAME + '_comparison.png'))
        toolpaths, result, version = slice_project(project, work / 'slice', saved, saved_base, bore)
        settings = json.loads(saved_data[first.SETTINGS])
        report = dict(project_sha256=first.digest(project), baseline_sha256=sha256(baseline).hexdigest(),
                      geometry=geometry, toolpaths=toolpaths, bambu_studio=version,
                      nozzle_mm=float(settings['nozzle_diameter'][0]),
                      layer_height_mm=float(settings['layer_height']),
                      wall_generator=settings['wall_generator'],
                      plate_warning=result['sliced_plates'][0]['warning_message'],
                      physical_print_verified=False)
        (work / 'Validation_v02.json').write_text(json.dumps(report, indent=2) + '\n')
        build_manifest(work, project, baseline)
        logs = dest / 'Slice'
        logs.mkdir(parents=True, exist_ok=True)
        for name in ('slice.log', 'result.json', 'plate_1.gcode'):
            shutil.copyfile(work / 'slice' / name, logs / name)
        for path in (*work.glob('*.png'), *work.glob('*.json'), work / 'Source_snapshot.zip'):
            shutil.copyfile(path, dest / path.name)
        with project.open('rb') as built, target.open('xb') as released:
            shutil.copyfileobj(built, released)
    print(f'{target.name} · {geometry["dimensions_mm"]} mm · Bambu Studio {version}')


if __name__ == '__main__':
    main()
