#!/usr/bin/env python3
"""Use thinner radial rims while keeping loops level with the 2 mm backing.

Preserves the current artwork, including Set 05's continuous underline and
reinforced stars. Requires NumPy, Pillow, GLU/Cairo and local Bambu Studio.
"""
import argparse
import json
import math
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

from rebuild_set04 import area, boundary_loops, orient
from PIL import Image

from repair_v02 import NS, read_parts
from set_versions import saved_project
from standardize_loop_diameters import ROOT, bounds, centre, digest, extrude_native, mesh_stats, package
from refine_loops_and_underline import write_project, read_toolpaths, render_slice, toolpath_checks
from validate_bambu import bambu_command

HEIGHT, BORE, OUTER = 2., 6.5, 10.5
COLLECTION = ROOT/'collection/full_height_narrow_rims'


def bore_index(loops, diameter):
    expected = math.pi*(diameter/2)**2
    found = [i for i, loop in enumerate(loops) if abs(abs(area(loop))-expected) < .1
             and min(x for x, y in loop) < 4 and max(x for x, y in loop) < 9]
    assert len(found) == 1, ('expected a single attachment hole', diameter, found)
    return found[0]


def geometry_checks(source, target, old_parts, new_parts, old_loops):
    before, after = package(source), package(target)
    assert new_parts[1:] == old_parts[1:], 'artwork, underline or colour assignments changed'
    assert before['Metadata/project_settings.config'] == after['Metadata/project_settings.config']
    roots = [ET.fromstring(p['3D/3dmodel.model']) for p in (before, after)]
    assert ET.tostring(roots[0].find('m:build', NS)) == ET.tostring(roots[1].find('m:build', NS))
    configs = [ET.fromstring(p['Metadata/model_settings.config']) for p in (before, after)]
    assert ET.tostring(configs[0].find('assemble')) == ET.tostring(configs[1].find('assemble'))
    new_loops = boundary_loops(new_parts[0])
    oi, ni = bore_index(old_loops, 5.5), bore_index(new_loops, BORE)
    def non_bore_points(loops, index):
        return sorted(p for i, loop in enumerate(loops) if i != index for p in loop)
    a, b = non_bore_points(old_loops, oi), non_bore_points(new_loops, ni)
    assert len(a) == len(b)
    deviation = max(math.dist(p, q) for p, q in zip(a, b))
    assert deviation < 1e-8, 'non-bore backing contour changed'
    old_c, new_c = centre(old_loops[oi]), centre(new_loops[ni])
    assert math.dist(old_c, new_c) < 1e-8
    bore = new_loops[ni]
    diameters = [max(p[k] for p in bore)-min(p[k] for p in bore) for k in (0, 1)]
    assert all(abs(d-BORE) < 1e-8 for d in diameters)
    assert {v[2] for v in new_parts[0]['vertices']} == {0., HEIGHT}, 'backing must have one uniform height'
    assert max(abs(x-y) for aa, bb in zip(bounds(old_parts[0])[:2], bounds(new_parts[0])[:2])
               for x, y in zip(aa, bb)) < 1e-8
    outer_loop = max(new_loops, key=lambda c: abs(area(c)))
    left_arc = [math.dist(p, new_c) for p in outer_loop if p[0] <= new_c[0]]
    rim_min, rim_max = min(left_arc)-BORE/2, max(left_arc)-BORE/2
    assert 1.9 < rim_min <= rim_max < 2.1, ('unexpected radial rim width', rim_min, rim_max)
    stats = [mesh_stats(p) for p in new_parts]
    assert stats[0]['degenerate_triangles'] == 0
    flat_before, _ = extrude_native(orient(old_loops), old_parts[0])
    expected = mesh_stats(flat_before)['volume_mm3']-(abs(area(bore))-abs(area(old_loops[oi])))*HEIGHT
    assert abs(expected-stats[0]['volume_mm3']) < 1e-6
    return dict(loop_and_backing_height_mm=HEIGHT, uniform_backing_height=True,
                bore_diameters_xy_mm=diameters, outer_diameter_nominal_mm=OUTER,
                radial_rim_width_nominal_mm=(OUTER-BORE)/2,
                sampled_left_outer_arc_radial_rim_mm=[rim_min, rim_max],
                hole_centre_preserved=True, non_bore_contours_preserved=True,
                non_bore_contour_max_deviation_mm=deviation,
                artwork_meshes_exactly_preserved=True, plate_placement_preserved=True,
                filament_and_process_settings_byte_identical=True,
                parts=[dict(name=p['name'], **s) for p, s in zip(new_parts, stats)])


def isometric(parts, output):
    """Render the actual meshes so the coplanar loop/body are reviewable."""
    yaw, elevation = math.radians(12), math.radians(27)
    right = np.array([math.cos(yaw), -math.sin(yaw), 0.])
    up = np.array([math.sin(yaw)*math.sin(elevation), math.cos(yaw)*math.sin(elevation), math.cos(elevation)])
    camera = np.cross(right, up)
    all_vertices = np.asarray([v for p in parts for v in p['vertices']])
    projected = np.column_stack((all_vertices@right, -(all_vertices@up)))
    low, high = projected.min(axis=0), projected.max(axis=0)
    width, margin = 1800, 70
    scale = (width-2*margin)/(high[0]-low[0])
    height = math.ceil((high[1]-low[1])*scale)+2*margin
    pixels = np.full((height, width, 3), 245, dtype=np.uint8)
    depth_buffer = np.full((height, width), -np.inf)
    for part in parts:
        color = np.array([int(part['color'][i:i+2], 16)/255 for i in (1, 3, 5)])
        vertices = np.asarray(part['vertices'])
        for face in part['faces']:
            v = vertices[list(face)]
            normal = np.cross(v[1]-v[0], v[2]-v[0])
            magnitude = float(np.linalg.norm(normal))
            if magnitude < 1e-12 or normal@camera <= 0:
                continue
            normal /= magnitude
            shade = 1. if normal[2] > .99 else .60+.20*max(0., float(normal@camera))
            xy = np.column_stack((v@right, -(v@up)))
            points = (xy-low)*scale+margin
            x0 = max(0, math.floor(float(points[:, 0].min())))
            x1 = min(width, math.ceil(float(points[:, 0].max()))+1)
            y0 = max(0, math.floor(float(points[:, 1].min())))
            y1 = min(height, math.ceil(float(points[:, 1].max()))+1)
            if x0 >= x1 or y0 >= y1:
                continue
            a, b, c = points
            denominator = (b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
            if abs(denominator) < 1e-12:
                continue
            xx = np.arange(x0, x1)[None, :]+.5
            yy = np.arange(y0, y1)[:, None]+.5
            w0 = ((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/denominator
            w1 = ((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/denominator
            w2 = 1-w0-w1
            depth = v@camera
            interpolated = w0*depth[0]+w1*depth[1]+w2*depth[2]
            region = depth_buffer[y0:y1, x0:x1]
            visible = (w0 >= -1e-8) & (w1 >= -1e-8) & (w2 >= -1e-8) & (interpolated > region)
            region[visible] = interpolated[visible]
            pixels[y0:y1, x0:x1][visible] = np.rint(color*shade*255).astype(np.uint8)
    Image.fromarray(pixels).save(output)


def build_one(folder, command):
    number = int(folder.name[4:6])
    previous, version = ('v06', 'v07') if number == 4 else ('v07', 'v08') if number == 5 else ('v05', 'v06')
    source = saved_project(folder, previous)
    target = folder/version/(folder.name+'_'+version+'.3mf')
    source_hash = digest(source)
    old = read_parts(package(source))
    old_loops = boundary_loops(old[0])
    loops = [list(c) for c in old_loops]
    index = bore_index(loops, 5.5)
    cx, cy = centre(loops[index])
    loops[index] = [(cx+BORE/2*math.cos(i*math.tau/128), cy+BORE/2*math.sin(i*math.tau/128))
                    for i in range(128)]
    base, rotation = extrude_native(orient(loops), old[0])
    parts = [base]+old[1:]
    write_project(source, target, parts, {0},
                  f'{version}; uniform 2 mm backing and attachment loop, 10.5 mm nominal outer diameter, '
                  '6.5 mm bore and 2 mm nominal radial rim; current artwork, profiles and placement retained.')
    parts = read_parts(package(target))
    geometry = geometry_checks(source, target, old, parts, old_loops)
    geometry['tessellation_axis_rotation_degrees'] = rotation
    logs = ROOT/'validation'/folder.name/version
    logs.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='lorcana-radial-rims-') as directory:
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
    colors = json.loads(package(target)['Metadata/project_settings.config'])['filament_colour']
    channels = [f['id'] for f in plate['filaments']]
    assert channels == list(range(1, len(colors)+1))
    assert all(f['main_used_g'] > 0 for f in plate['filaments'])
    layers = read_toolpaths(logs/'plate_1.gcode', plate['objects'][0]['bbox'], len(colors))
    underline = None
    if number == 5:
        underline = json.loads((source.parent/f'Validation_{previous}.json').read_text())['underline']
    actual_bore = loops[index]
    deposited = toolpath_checks(layers, parts, plate['objects'][0]['bbox'], {}, underline,
                                loop_height=HEIGHT, bore_loop=actual_bore)
    render_slice(layers, parts, plate['objects'][0]['bbox'], colors,
                 target.with_name(target.stem+'_sliced_preview.png'), loop_height=HEIGHT)
    if number == 5:
        isometric(parts, target.with_name(target.stem+'_isometric.png'))
    assert digest(source) == source_hash
    report = dict(project=str(target.relative_to(ROOT)), filename=target.name,
                  source=str(source.relative_to(ROOT)), source_sha256=source_hash, output_sha256=digest(target),
                  geometry=geometry, underline=underline, toolpath_checks=deposited,
                  used_filament_slots=channels, bambu_version='02.08.02.61', slice_result=result,
                  physical_print_verified=False)
    (target.parent/f'Geometry_{version}.json').write_text(json.dumps({k: v for k, v in report.items() if k != 'slice_result'}, indent=2)+'\n')
    (target.parent/f'Validation_{version}.json').write_text(json.dumps(report, indent=2)+'\n')
    notes = (f'# {folder.name[7:].replace("_", " ")} {version}\n\n'
             f'Open [{target.name}]({target.name}) as a project in Bambu Studio.\n\n'
             'The loop and backing now share the same flat **2 mm height**. The ring is '
             'thinner in the XY plane: a **6.5 mm hole** inside the existing **10.5 mm '
             'nominal outer diameter** gives a **2 mm nominal radial rim**, reduced from '
             '2.5 mm. The bore centre and every other backing contour are retained.\n\n'
             'The colour meshes, artwork, placement and filament/process settings are '
             'exactly preserved. Bambu imports and slices successfully, uses all intended '
             'colours, and reports no plate warnings. The rebuilt backing is a closed '
             'manifold solid with no degenerate triangles. Actual toolpaths confirm that '
             'the loop reaches the same 2 mm layer as the backing.\n\n')
    if number == 5:
        notes += ('The continuous 0.9 mm underline and reinforced stars are preserved. '
                  'All five ivory layers again pass the continuous-underline check, '
                  'with zero detached deposits.\n\n'
                  f'![Actual mesh, including the level loop]({target.stem}_isometric.png)\n\n')
    notes += (f'![Actual sliced toolpaths]({target.stem}_sliced_preview.png)\n\n'
              f'[Validation_{version}.json](Validation_{version}.json) records the checks. '
              'Physical printing and chain fit have not been tested. Reproduce the current '
              'collection from the project root with '
              '`python3 tools/full_height_narrow_rims.py`, using NumPy, Pillow and local Bambu Studio.\n')
    (target.parent/'README.md').write_text(notes)
    return target, source, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sets', nargs='*', type=int, help='Build only these sets without updating the collection index.')
    args = parser.parse_args()
    command = bambu_command()
    outputs = []
    for folder in sorted((ROOT/'sets').glob('Set_*')):
        number = int(folder.name[4:6])
        if number > 14 or (args.sets and number not in args.sets):
            continue
        print(folder.name+': restoring uniform height and enlarging hole to 6.5 mm', flush=True)
        outputs.append(build_one(folder, command))
        print(folder.name+': geometry, slice and toolpath checks passed', flush=True)
    if args.sets:
        return
    assert len(outputs) == 14
    COLLECTION.mkdir(parents=True, exist_ok=True)
    manifest = dict(loop_and_backing_height_mm=HEIGHT, bore_diameter_mm=BORE,
                    outer_diameter_nominal_mm=OUTER, radial_rim_width_nominal_mm=(OUTER-BORE)/2,
                    projects=[dict(project=r['project'], source=r['source'], source_sha256=r['source_sha256'],
                                   output_sha256=r['output_sha256'], validation=str((p.parent/f'Validation_{p.parent.name}.json').relative_to(ROOT)))
                              for p, _, r in outputs])
    (COLLECTION/'Manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    overview = ('# Full-height loops with narrower radial rims\n\n'
                'All fourteen current projects have loops level with the **2 mm backing**. '
                'The ring is narrower in the XY plane: **10.5 mm nominal outer diameter**, '
                '**6.5 mm hole**, and **2 mm nominal radial rim**. The hole centre and '
                'all non-bore backing contours are retained.\n\n'
                'All fourteen projects pass Bambu slicing with every intended filament '
                'and no plate warnings. Mesh checks confirm uniform 2 mm height across '
                'the complete backing, and actual toolpaths confirm the loop top at Z=2 mm. '
                'Colour meshes and profiles are preserved, including Set 05’s continuous '
                '0.9 mm underline and reinforced stars. All five underline layers remain '
                'continuous with zero detached deposits. The unchanged Set 14 Caramel mesh '
                'retains its four pre-existing degenerate faces; all rebuilt backings have '
                'none. Physical printing and chain fit have not been tested.\n\n'
                '| Set | Current project |\n| --- | --- |\n')
    for target, _, _ in outputs:
        overview += f'| {target.parent.parent.name[4:].replace("_", " ")} | [{target.name}](../../{target.relative_to(ROOT)}) |\n'
    overview += '\n[Manifest.json](Manifest.json) records source/output hashes and per-project validation reports.\n'
    (COLLECTION/'README.md').write_text(overview)
    archive = ROOT/'archives/Lorcana_Keychains_Full_Height_Narrow_Rims.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for target, _, _ in outputs:
            for path in target.parent.iterdir():
                if path.is_file():
                    z.write(path, str(path.relative_to(ROOT)))
        for path in COLLECTION.iterdir():
            if path.is_file():
                z.write(path, str(path.relative_to(ROOT)))
    print('Complete: all 14 full-height, narrow-rim projects validated; '+str(archive.relative_to(ROOT)), flush=True)


if __name__ == '__main__':
    main()
