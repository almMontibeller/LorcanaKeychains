#!/usr/bin/env python3
"""Match Set 04's loop diameters across the other thirteen current projects.

Only enlarge the bore. Retain the outer contours, backing thickness, artwork,
filaments, placement and process settings. Requires NumPy, Pillow, Cairo, GLU
and the installed Bambu Studio runtime. Historical projects are never replaced.
"""
from pathlib import Path
import collections
import hashlib
import io
import json
import math
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from rebuild_set04 import area, boundary_loops, extrude, orient
from repair_v1_1 import IDENTITY, NS, read_parts, thumbnail
from validate_bambu import bambu_command

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = ROOT / 'collection/loop_diameters'
REFERENCE = ROOT / 'sets/Set_04_Ursulas_Return/v1.4/Set_04_Ursulas_Return_v1.4.1_printed.3mf'
CORE = NS['m']
PROD = 'http://schemas.microsoft.com/3dmanufacturing/production/2015/06'
TAG = lambda name: '{'+CORE+'}'+name
ET.register_namespace('', CORE)
ET.register_namespace('p', PROD)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package(path):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        return {name: archive.read(name) for name in archive.namelist()}


def bore_index(loops):
    candidates = [i for i, c in enumerate(loops)
                  if min(x for x, y in c) < 4 and max(x for x, y in c) < 9
                  and 15 < abs(area(c)) < 25]
    assert len(candidates) == 1, ('expected one attachment bore', candidates)
    return candidates[0]


def centre(loop):
    return tuple((min(p[k] for p in loop)+max(p[k] for p in loop))/2 for k in (0, 1))


def bounds(part):
    return [(min(v[k] for v in part['vertices']), max(v[k] for v in part['vertices']))
            for k in range(3)]


def mesh_stats(part):
    vertices, faces = np.asarray(part['vertices']), np.asarray(part['faces'])
    a, b, c = (vertices[faces[:, i]] for i in range(3))
    cross = np.cross(b-a, c-a)
    degenerate = int(np.count_nonzero(np.sum(cross*cross, axis=1) < 1e-22))
    volume = float(np.einsum('ij,ij->', a, np.cross(b, c))/6)
    edges = collections.Counter((f[i], f[(i+1) % 3]) for f in part['faces'] for i in range(3))
    assert all(value == edges[(b, a)] == 1 for (a, b), value in edges.items())
    assert volume > 0
    return dict(volume_mm3=volume, degenerate_triangles=degenerate, closed_manifold=True)


def extrude_native(loops, template):
    """Change tessellation axes if aligned legacy corners confuse GLU.

    Only the coordinates fed to the tessellator are rotated. Every vertex in
    the resulting mesh uses the original, unrotated contour coordinates.
    """
    native = [p for c in loops for p in c]
    failures = []
    for degrees in (0, 17, 31, 47):
        angle = math.radians(degrees)
        co, si = math.cos(angle), math.sin(angle)
        rotated = [[(x*co-y*si, x*si+y*co) for x, y in c] for c in loops]
        try:
            mesh = extrude(rotated, 0., 2., template)
        except AssertionError as exc:
            failures.append(str(exc))
            continue
        assert len(mesh['vertices']) == 2*len(native)
        mesh['vertices'] = [(native[i % len(native)][0], native[i % len(native)][1], z)
                            for i, (_, _, z) in enumerate(mesh['vertices'])]
        if mesh_stats(mesh)['degenerate_triangles']:
            failures.append('degenerate triangle after restoring native coordinates')
            continue
        return mesh, degrees
    raise AssertionError(('unable to tessellate native backing', failures))


def write_mesh(obj, part):
    obj.remove(obj.find(TAG('mesh')))
    mesh = ET.SubElement(obj, TAG('mesh'))
    vs, fs = ET.SubElement(mesh, TAG('vertices')), ET.SubElement(mesh, TAG('triangles'))
    for vertex in part['vertices']:
        ET.SubElement(vs, TAG('vertex'), dict(zip(('x', 'y', 'z'), (f'{v:.9f}' for v in vertex))))
    for face in part['faces']:
        ET.SubElement(fs, TAG('triangle'), dict(zip(('v1', 'v2', 'v3'), map(str, face))))


def check_contours(previous, current):
    old, new = [boundary_loops(p) for p in (previous, current)]
    old_bore, new_bore = bore_index(old), bore_index(new)
    def points_except_bore(loops, index):
        return sorted(p for i, c in enumerate(loops) if i != index for p in c)
    a, b = points_except_bore(old, old_bore), points_except_bore(new, new_bore)
    assert len(a) == len(b)
    deviation = max(math.dist(p, q) for p, q in zip(a, b))
    assert deviation < 1e-8, ('outer or other interior contours changed', deviation)
    old_c, new_c = centre(old[old_bore]), centre(new[new_bore])
    assert math.dist(old_c, new_c) < 1e-8
    diameter = [max(p[k] for p in new[new_bore])-min(p[k] for p in new[new_bore]) for k in (0, 1)]
    assert all(abs(d-5.5) < 1e-8 for d in diameter)
    assert {round(v[2], 8) for v in current['vertices']} == {0., 2.}
    assert max(abs(x-y) for aa, bb in zip(bounds(previous), bounds(current)) for x, y in zip(aa, bb)) < 1e-8
    return dict(bore_diameters_xy_mm=diameter, bore_centre_mm=new_c,
                bore_centre_preserved=True, outer_diameter_nominal_mm=10.5,
                rim_width_nominal_mm=2.5, backing_and_loop_thickness_mm=2.,
                non_bore_contours_preserved=True, non_bore_contour_max_deviation_mm=deviation,
                overall_dimensions_preserved=True)


def update(source, target, reference_bore):
    data = package(source)
    original = read_parts(data)
    loops = boundary_loops(original[0])
    index = bore_index(loops)
    cx, cy = centre(loops[index])
    old_area = abs(area(loops[index]))
    rx, ry = centre(reference_bore)
    loops[index] = [(cx+x-rx, cy+y-ry) for x, y in reference_bore]
    base, rotation = extrude_native(orient(loops), original[0])
    parts = [base]+original[1:]
    root = ET.fromstring(data['3D/3dmodel.model'])
    config = ET.fromstring(data['Metadata/model_settings.config'])
    obj = config.find('object')
    assembly = root.find(f"m:resources/m:object[@id='{obj.get('id')}']", NS)
    component = assembly.find('m:components', NS)[0]
    oid = component.get('objectid')
    resource_path = component.get('{'+PROD+'}path', '3D/3dmodel.model').lstrip('/')
    resource = root if resource_path == '3D/3dmodel.model' else ET.fromstring(data[resource_path])
    write_mesh(resource.find(f"m:resources/m:object[@id='{oid}']", NS), base)
    component.set('transform', ' '.join(map(str, IDENTITY)))
    cfg = obj.find(f"part[@id='{oid}']")
    for md in list(cfg.findall('metadata')):
        if md.get('key', '').startswith('source_'):
            cfg.remove(md)
    cfg.find("metadata[@key='matrix']").set('value', '1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1')
    cfg.find('mesh_stat').set('face_count', str(len(base['faces'])))
    obj.find("metadata[@key='name']").set('value',
        obj.find("metadata[@key='name']").get('value').replace(source.parent.name, target.parent.name))
    obj.find('metadata[@face_count]').set('face_count', str(sum(len(p['faces']) for p in parts)))
    description = root.find("m:metadata[@name='Description']", NS)
    if description is None:
        description = ET.SubElement(root, TAG('metadata'), {'name': 'Description'})
    description.text = (f'{target.parent.name}; Set 04 attachment diameters: 5.5 mm bore, '
                        '10.5 mm nominal outer diameter, 2.5 mm nominal rim; '
                        'original 2 mm backing and loop thickness; original artwork and print settings.')
    if resource is not root:
        if not any(k.startswith('{'+PROD+'}') for e in resource.iter() for k in e.attrib):
            resource.set('xmlns:p', PROD)
        data[resource_path] = ET.tostring(resource, encoding='utf-8', xml_declaration=True)
    data['3D/3dmodel.model'] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    data['Metadata/model_settings.config'] = ET.tostring(config, encoding='utf-8', xml_declaration=True)
    data['Metadata/plate_1.png'] = thumbnail(parts, 512)
    data['Metadata/plate_no_light_1.png'] = data['Metadata/plate_1.png']
    data['Metadata/plate_1_small.png'] = thumbnail(parts, 128)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, raw in data.items():
            archive.writestr(name, raw)
    loaded_data = package(target)
    loaded = read_parts(loaded_data)
    assert loaded[1:] == original[1:], 'artwork or colour assignments changed'
    assert loaded_data['Metadata/project_settings.config'] == package(source)['Metadata/project_settings.config']
    attachment = check_contours(original[0], loaded[0])
    old_volume, new_volume = mesh_stats(original[0])['volume_mm3'], mesh_stats(loaded[0])['volume_mm3']
    removed = (abs(area(reference_bore))-old_area)*2
    assert abs((old_volume-new_volume)-removed) < 1e-6, 'changes exceed the intended bore enlargement'
    stats = [mesh_stats(p) for p in loaded]
    assert stats[0]['degenerate_triangles'] == 0
    # Retain any legacy degenerate colour faces rather than editing artwork.
    assert [s['degenerate_triangles'] for s in stats[1:]] == [mesh_stats(p)['degenerate_triangles'] for p in original[1:]]
    for name in loaded_data:
        if name.endswith('.rels'):
            for rel in ET.fromstring(loaded_data[name]):
                if rel.get('Target', '').startswith('/'):
                    assert rel.get('Target').lstrip('/') in loaded_data
    image = Image.open(io.BytesIO(thumbnail(loaded, 1600)))
    bb = bounds(loaded[0])
    height = min(1600, math.ceil(1600*(.88*(bb[1][1]-bb[1][0])/(bb[0][1]-bb[0][0])+.12)))
    preview = target.with_name(target.stem+'_preview.png')
    image.crop((0, (1600-height)//2, 1600, (1600+height)//2)).save(preview)
    report = dict(filename=target.name, project=str(target.relative_to(ROOT)),
                  source=str(source.relative_to(ROOT)), source_sha256=digest(source),
                  output_sha256=digest(target), reference=str(REFERENCE.relative_to(ROOT)),
                  attachment=attachment, artwork_meshes_exactly_preserved=True,
                  filament_and_process_settings_byte_identical=True,
                  volume_removed_mm3=old_volume-new_volume, tessellation_axis_rotation_degrees=rotation,
                  parts=[dict(name=p['name'], slot=p['slot'], **s) for p, s in zip(loaded, stats)])
    return report, loaded


def validate(source, target, report, command):
    # Check the original XML resources and placement independently of the mesh reader.
    packages = [package(p) for p in (source, target)]
    roots = [ET.fromstring(d['3D/3dmodel.model']) for d in packages]
    assert ET.tostring(roots[0].find('m:build', NS)) == ET.tostring(roots[1].find('m:build', NS))
    configs = [ET.fromstring(d['Metadata/model_settings.config']) for d in packages]
    for old, new in zip(configs[0].find('object').findall('part')[1:], configs[1].find('object').findall('part')[1:]):
        assert ET.tostring(old) == ET.tostring(new)
    assert ET.tostring(configs[0].find('assemble')) == ET.tostring(configs[1].find('assemble'))
    for old, new in zip(roots[0].findall('.//m:component', NS)[1:], roots[1].findall('.//m:component', NS)[1:]):
        assert ET.tostring(old) == ET.tostring(new)
        for package_, component in zip(packages, (old, new)):
            path = component.get('{'+PROD+'}path', '3D/3dmodel.model').lstrip('/')
            resource = ET.fromstring(package_[path])
            mesh = resource.find(f"m:resources/m:object[@id='{component.get('objectid')}']/m:mesh", NS)
            if package_ is packages[0]:
                old_xml = ET.tostring(mesh)
            else:
                assert old_xml == ET.tostring(mesh)
    logs = ROOT / 'validation' / target.parent.parent.name / target.parent.name
    logs.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='lorcana-diameters-') as directory:
        run = subprocess.run(command+['--datadir', directory, '--debug', '2', '--info', '--slice', '1',
                                     '--outputdir', str(logs), str(target)],
                             cwd=logs, capture_output=True, text=True, timeout=180)
    log = run.stdout+run.stderr
    (logs/'slice.log').write_text(log)
    result = json.loads((logs/'result.json').read_text())
    assert run.returncode == result['return_code'] == 0, (target.name, result)
    assert 'manifold = yes' in log
    plate = result['sliced_plates'][0]
    assert plate['warning_message'] == '', (target.name, plate['warning_message'])
    settings = json.loads(packages[1]['Metadata/project_settings.config'])
    channels = [f['id'] for f in plate['filaments']]
    assert channels == list(range(1, len(settings['filament_colour'])+1))
    assert all(f['main_used_g'] > 0 for f in plate['filaments'])
    # The loop remains in the backing colour through its original 2 mm top.
    assert '; Z_HEIGHT: 2' in (logs/'plate_1.gcode').read_text()
    validation = dict(filename=target.name, sha256=digest(target),
                      attachment=report['attachment'], geometry=report['parts'],
                      artwork_xml_and_meshes_preserved=True, plate_placement_preserved=True,
                      filament_and_process_settings_byte_identical=True,
                      used_filament_slots=channels, bambu_version='02.08.02.61', slice_result=result,
                      physical_print_verified=False,
                      environment_notes='Installed Flatpak CLI uses embedded settings despite missing /app preset-resource messages.')
    (target.parent/f'Validation_{target.parent.name}.json').write_text(json.dumps(validation, indent=2)+'\n')
    (target.parent/f'Geometry_{target.parent.name}.json').write_text(json.dumps(report, indent=2)+'\n')
    return validation


def revision_readme(target):
    text = (f'# {target.parent.parent.name[7:].replace("_", " ")} {target.parent.name}\n\n'
            f'Open [{target.name}]({target.name}) as a project in Bambu Studio.\n\n'
            'The attachment hole matches Set 04: **5.5 mm bore**, **10.5 mm nominal outer '
            'diameter**, and **2.5 mm nominal rim**. The original 2 mm loop and backing '
            'thickness is retained. Only the hole is enlarged; all other backing contours, '
            'artwork, colours, placement and process settings are preserved.\n\n'
            'Bambu Studio 02.08.02.61 imports and slices the project successfully, uses all '
            'intended filaments and reports no plate warnings. The rebuilt backing is a '
            'closed manifold solid without degenerate triangles. Source colour meshes '
            'are preserved exactly, including any pre-existing mesh details. Physical '
            'printing and ring fit have not been tested.\n\n'
            f'![Updated project]({target.stem}_preview.png)\n\n'
            f'Geometry: [Geometry_{target.parent.name}.json](Geometry_{target.parent.name}.json). '
            f'Validation: [Validation_{target.parent.name}.json](Validation_{target.parent.name}.json).\n\n'
            'Rebuild and validate all thirteen diameter revisions from the repository root '
            'with Python, NumPy and Pillow:\n\n'
            '```sh\npython3 tools/standardize_loop_diameters.py\n```\n')
    (target.parent/'README.md').write_text(text)


def main():
    COLLECTION.mkdir(parents=True, exist_ok=True)
    reference_parts = read_parts(package(REFERENCE))
    reference_loops = boundary_loops(reference_parts[0])
    reference_bore = reference_loops[bore_index(reference_loops)]
    assert all(abs(max(p[k] for p in reference_bore)-min(p[k] for p in reference_bore)-5.5) < 1e-8 for k in (0, 1))
    reference_hash = digest(REFERENCE)
    command = bambu_command()
    reports, projects = [], []
    previews = {4: (REFERENCE, reference_parts)}
    readme = (ROOT/'README.md').read_text()
    for folder in sorted((ROOT/'sets').glob('Set_*')):
        n = int(folder.name[4:6])
        if n == 4:
            continue
        old_version, version = ('v1.4', 'v1.5') if n == 5 else ('v1.2', 'v1.3')
        sources = list((folder/old_version).glob('*.3mf'))
        assert len(sources) == 1
        source = sources[0]
        target = folder/version/(folder.name+'_'+version+'.3mf')
        print(f'{folder.name}: enlarging bore to 5.5 mm; thickness retained', flush=True)
        report, parts = update(source, target, reference_bore)
        validation = validate(source, target, report, command)
        assert digest(source) == report['source_sha256']
        revision_readme(target)
        report['slice_passed'] = True
        report['filament_slots_used'] = validation['used_filament_slots']
        reports.append(report)
        projects.append(target)
        previews[n] = (target, parts)
        readme = readme.replace(str(source.relative_to(ROOT)), str(target.relative_to(ROOT)))
        readme = readme.replace(source.name, target.name)
        print(f'{folder.name}: geometry and Bambu slice passed', flush=True)
    assert len(reports) == 13
    assert digest(REFERENCE) == reference_hash
    manifest = dict(reference=str(REFERENCE.relative_to(ROOT)), reference_sha256=reference_hash,
                    updated_projects=13, bore_diameter_mm=5.5, outer_diameter_nominal_mm=10.5,
                    rim_width_nominal_mm=2.5, thickness_changed=False, projects=reports)
    (COLLECTION/'Manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    overview = ('# Shared attachment diameters\n\n'
                'All thirteen other current sets now use Set 04’s 5.5 mm attachment bore '
                'and nominal 10.5 mm outer diameter (2.5 mm rim). Their original 2 mm '
                'backing and loop thickness is retained. Set 04’s printed reference '
                'project is unchanged.\n\n'
                'All thirteen revisions pass Bambu Studio slicing with every intended '
                'filament and no plate warnings. Artwork, colour meshes, non-bore backing '
                'contours, placement and project settings are preserved. Set 05 retains '
                'its continuous red panel and reinforced stars. The rebuilt backings have '
                'no degenerate triangles; Set 14’s four pre-existing degenerate Caramel '
                'faces remain in its unchanged colour mesh. Physical printing and ring '
                'fit have not been tested.\n\n'
                '| Set | Current project |\n| --- | --- |\n')
    for n, (path, _) in sorted(previews.items()):
        overview += f'| {path.parent.parent.name[4:].replace("_", " ")} | [{path.name}](../../{path.relative_to(ROOT)}) |\n'
    overview += ('\n![All current sets](Preview.png)\n\n'
                 '[Manifest.json](Manifest.json) records source and output hashes, geometry '
                 'checks and slice results. Per-set validation reports and slicer evidence '
                 'are stored alongside each revision and under `validation/`.\n\n'
                 'Reproduce with `python3 tools/standardize_loop_diameters.py` from the '
                 'repository root, using Python with NumPy and Pillow and local Bambu Studio.\n')
    (COLLECTION/'README.md').write_text(overview)
    sheet = Image.new('RGB', (2000, 1200), '#F5F5F5')
    draw = ImageDraw.Draw(sheet)
    for i, (n, (path, parts)) in enumerate(sorted(previews.items())):
        im = Image.open(io.BytesIO(thumbnail(parts, 900)))
        # All models are wider than tall; trim the square thumbnail background.
        vertices = [v for p in parts for v in p['vertices']]
        dx = max(v[0] for v in vertices)-min(v[0] for v in vertices)
        dy = max(v[1] for v in vertices)-min(v[1] for v in vertices)
        height = min(900, math.ceil(900*(.88*dy/dx+.12)))
        im = ImageOps.contain(im.crop((0, (900-height)//2, 900, (900+height)//2)), (480, 255))
        x, y = i % 4*500, i//4*300
        sheet.paste(im, (x+(500-im.width)//2, y+35+(255-im.height)//2))
        label = path.parent.parent.name[4:].replace('_', ' ')
        draw.text((x+15, y+12), label+(' (reference)' if n == 4 else ''), fill='#302B35')
    sheet.save(COLLECTION/'Preview.png')
    note = ('\nThe latest projects share Set 04’s **5.5 mm attachment bore** and '
            '**10.5 mm nominal outer diameter**, with each set’s existing thickness retained. '
            'See [all updated projects and validation](collection/loop_diameters/README.md).\n')
    if 'collection/loop_diameters/README.md' not in readme:
        readme = readme.replace('\nFor example,', note+'\nFor example,', 1)
    if 'python3 tools/standardize_loop_diameters.py' not in readme:
        readme = readme.replace('python3 tools/validate_set05.py\n',
                                'python3 tools/validate_set05.py\npython3 tools/standardize_loop_diameters.py\n', 1)
    (ROOT/'README.md').write_text(readme)
    archive = ROOT/'archives/Lorcana_Keychains_Shared_Loop_Diameters.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in projects+[REFERENCE, COLLECTION/'README.md', COLLECTION/'Manifest.json', COLLECTION/'Preview.png']:
            z.write(path, str(path.relative_to(ROOT)))
    print(f'Complete: {len(reports)} updated projects; reference unchanged; {archive.relative_to(ROOT)}', flush=True)


if __name__ == '__main__':
    main()
